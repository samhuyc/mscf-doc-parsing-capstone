// CPU multimodal recognition with passive, pre-sampling native logit capture.
// The executable loads weights only when invoked with a runtime settings file.
#include "llama.h"
#include "ggml-backend.h"
#include "mtmd.h"
#include "mtmd-helper.h"
#include "nlohmann/json.hpp"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
using json = nlohmann::json;

static std::string hex(const std::string & s) {
    const char * digits = "0123456789abcdef";
    std::string out; out.reserve(s.size()*2);
    for (unsigned char b : s) { out += digits[b>>4]; out += digits[b&15]; }
    return out;
}
static std::string piece(const llama_vocab * vocab, llama_token token) {
    std::vector<char> buf(256);
    int n = llama_token_to_piece(vocab, token, buf.data(), buf.size(), 0, true);
    if (n < 0) { buf.resize(-n); n = llama_token_to_piece(vocab,token,buf.data(),buf.size(),0,true); }
    if (n < 0) throw std::runtime_error("Token piece exceeds allocated buffer");
    return std::string(buf.data(), n);
}

int main(int argc, char ** argv) {
    if (argc != 2 || std::string(argv[1]) == "--help") {
        std::cout << "confidence-vlm SETTINGS.json < jobs.jsonl\n"
                     "One resident CPU model, one image per JSON line; no network.\n";
        return argc == 2 ? 0 : 2;
    }
    try {
        json cfg; std::ifstream file(argv[1]); file >> cfg;
        ggml_backend_load_all(); llama_backend_init();
        auto mp = llama_model_default_params(); mp.n_gpu_layers = 0; mp.load_mode = LLAMA_LOAD_MODE_MMAP;
        std::unique_ptr<llama_model, decltype(&llama_model_free)> model(
            llama_model_load_from_file(cfg.at("model").get<std::string>().c_str(), mp), llama_model_free);
        if (!model) throw std::runtime_error("Failed to load local language weights");
        auto cp = llama_context_default_params();
        cp.n_ctx = cfg.at("context"); cp.n_batch = cfg.at("batch"); cp.n_ubatch = cfg.at("batch");
        cp.n_threads = cfg.at("threads"); cp.n_threads_batch = cfg.at("threads");
        cp.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_DISABLED;
        std::unique_ptr<llama_context, decltype(&llama_free)> ctx(llama_init_from_model(model.get(),cp),llama_free);
        if (!ctx) throw std::runtime_error("Failed to allocate CPU context");
        auto vp = mtmd_context_params_default(); vp.use_gpu = false; vp.warmup = false;
        vp.n_threads = cfg.at("threads"); vp.print_timings = false;
        vp.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_DISABLED;
        std::unique_ptr<mtmd_context, decltype(&mtmd_free)> vision(
            mtmd_init_from_file(cfg.at("mmproj").get<std::string>().c_str(),model.get(),vp),mtmd_free);
        if (!vision) throw std::runtime_error("Failed to load matching image encoder/projector");
        const llama_vocab * vocab = llama_model_get_vocab(model.get());
        const int n_vocab = llama_vocab_n_tokens(vocab);
        const int max_tokens = cfg.at("max_tokens");
        const auto eos_ids = cfg.value("eos_token_ids", std::vector<int>{});
        std::string line;
        while (std::getline(std::cin,line)) {
            if (line.empty()) continue;
            json result;
            try {
                const auto job = json::parse(line);
                llama_memory_clear(llama_get_memory(ctx.get()),true);
                auto bitmap_wrapper = mtmd_helper_bitmap_init_from_file(vision.get(),
                    job.at("image").get<std::string>().c_str(), false, mtmd_helper_init_opt_default());
                std::unique_ptr<mtmd_bitmap, decltype(&mtmd_bitmap_free)> bitmap(bitmap_wrapper.bitmap,mtmd_bitmap_free);
                if (!bitmap) throw std::runtime_error("Unable to decode input image");
                std::unique_ptr<mtmd_input_chunks, decltype(&mtmd_input_chunks_free)> chunks(mtmd_input_chunks_init(),mtmd_input_chunks_free);
                std::string prompt = job.at("prompt");
                mtmd_input_text input{prompt.data(),prompt.size(),false,true};
                const mtmd_bitmap * bitmaps[] = {bitmap.get()};
                if (mtmd_tokenize(vision.get(),chunks.get(),&input,bitmaps,1))
                    throw std::runtime_error("Multimodal prompt tokenization failed");
                const size_t prompt_tokens = mtmd_helper_get_n_tokens(chunks.get());
                if (prompt_tokens+1 >= llama_n_ctx(ctx.get())) throw std::runtime_error("Image/prompt exceeds configured context");
                llama_pos past = 0;
                if (mtmd_helper_eval_chunks(vision.get(),ctx.get(),chunks.get(),0,0,cp.n_batch,true,&past))
                    throw std::runtime_error("Image/prompt evaluation failed");
                json units = json::array();
                std::string stop = "token_limit";
                size_t used = prompt_tokens;
                for (int step=0; step<max_tokens; ++step) {
                    const float * logits = llama_get_logits_ith(ctx.get(),-1);
                    if (!logits) throw std::runtime_error("Missing decoder logits");
                    // Greedy choice uses the untouched logits, without penalties,
                    // truncation, temperature scaling or grammar masking.
                    int best = std::max_element(logits,logits+n_vocab)-logits;
                    if (!std::isfinite(logits[best])) throw std::runtime_error("Non-finite decoder logits");
                    if (llama_vocab_is_eog(vocab,best) || std::find(eos_ids.begin(),eos_ids.end(),best)!=eos_ids.end()) {stop="eos";break;}
                    // FP32 log1p normalization preserves very small competing
                    // probability mass. Kahan summation stays in FP32.
                    float mass=0.0f, correction=0.0f;
                    for (int i=0;i<n_vocab;++i) if (i!=best) {
                        if (std::isnan(logits[i]) || logits[i]==INFINITY) throw std::runtime_error("Invalid vocabulary logit");
                        float y=std::exp(logits[i]-logits[best])-correction;
                        float t=mass+y; correction=(t-mass)-y; mass=t;
                    }
                    float logp=-std::log1p(mass);
                    units.push_back({{"token_id",best},{"piece_hex",hex(piece(vocab,best))},
                        {"selected_logit",logits[best]},{"log_probability",logp},
                        {"score",std::exp(logp)},{"other_exp_mass_fp32",mass}});
                    if (step+1 == max_tokens) break;
                    if (++used >= llama_n_ctx(ctx.get())) {stop="context_limit";break;}
                    // mtmd handles M-RoPE image positions; single generated text
                    // tokens continue from its reported position.
                    llama_token next=best;
                    auto batch=llama_batch_get_one(&next,1);
                    // Explicit positions are required after multimodal prompts.
                    llama_pos position[4]={past,past,past,0};
                    llama_seq_id seq=0; llama_seq_id * seqs[]={&seq};
                    int32_t nseq[]={1}; int8_t output[]={1};
                    batch.pos=position; batch.n_seq_id=nseq; batch.seq_id=seqs; batch.logits=output;
                    if (llama_decode(ctx.get(),batch)) throw std::runtime_error("Autoregressive decoding failed");
                    ++past;
                }
                result={{"status","success"},{"confidence_units",units},{"stop_reason",stop},
                        {"truncated",stop!="eos"},{"prompt_tokens",prompt_tokens},
                        {"probability_normalization","original FP32 logits -> FP32 log1p softmax; EOS excluded"},
                        {"backend","llama.cpp-cpu"}};
            } catch (const std::exception & e) { result={{"status","failed"},{"error",e.what()},{"confidence_units",json::array()}}; }
            std::cout << result.dump() << std::endl;
        }
    } catch (const std::exception & e) { std::cerr << e.what() << '\n'; return 1; }
    return 0;
}
