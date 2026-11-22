"""Convert pinned checkpoints to CPU GGUF and render prompts; no inference."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from common import HERE, LOCAL, MODELS, config, read, write, sha


def normalized_config(name, raw):
    if name=='monkey':
        from transformers.models.qwen2_5_vl.configuration_qwen2_5_vl import Qwen2_5_VLConfig
        # Publisher omits standard vision defaults; recover them from the
        # pinned Transformers configuration class, without creating a model.
        return Qwen2_5_VLConfig.from_dict(raw).to_dict()
    if name=='mineru':
        from transformers.models.qwen2_vl.configuration_qwen2_vl import Qwen2VLConfig
        return Qwen2VLConfig.from_dict(raw).to_dict()
    return raw


def render_prompt(name, task):
    from jinja2.sandbox import ImmutableSandboxedEnvironment
    root=MODELS/'hf'/name
    if (root/'chat_template.jinja').exists():template=(root/'chat_template.jinja').read_text()
    elif (root/'chat_template.json').exists():template=read(root/'chat_template.json')['chat_template']
    else:template=read(root/'tokenizer_config.json')['chat_template']
    env=ImmutableSandboxedEnvironment(trim_blocks=True,lstrip_blocks=True)
    def raise_exception(message):raise ValueError(message)
    env.globals['raise_exception']=raise_exception
    tc=read(root/'tokenizer_config.json')
    tokens={k:v['content'] if isinstance(v,dict) else v for k,v in tc.items() if k.endswith('_token')}
    value=env.from_string(template).render(messages=[dict(role='user',content=[dict(type='image'),dict(type='text',text=task)])],
                 add_generation_prompt=True,add_vision_id=False,tools=None,**tokens)
    # mtmd inserts architecture-specific image boundary tokens. Replace the
    # whole HF image block to avoid inserting those tokens twice.
    markers=['<|vision_start|><|image_pad|><|vision_end|>',
             '<|IMAGE_START|><|IMAGE_PLACEHOLDER|><|IMAGE_END|>',
             '<|begin_of_image|><|image|><|end_of_image|>']
    matches=sum(value.count(marker) for marker in markers)
    if matches!=1:raise ValueError(f'Expected one image block in {name} prompt, found {matches}')
    for marker in markers:value=value.replace(marker,'<__media__>')
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--engines',nargs='+',choices=list(config()['models']));args=p.parse_args()
    source=LOCAL/'llama-src';converter=source/'convert_hf_to_gguf.py'
    if not converter.exists():raise RuntimeError('Fetch pinned llama.cpp source first')
    result={}
    for name in args.engines or config()['models']:
        original=MODELS/'hf'/name
        if not list(original.glob('*.safetensors')):raise RuntimeError('Checkpoint download incomplete: '+name)
        prepared=LOCAL/'conversion-input'/name;prepared.mkdir(parents=True,exist_ok=True)
        for path in original.iterdir():
            if path.name in ('config.json',) or (name=='glm' and path.name=='tokenizer_config.json') or path.suffix=='.part':continue
            dest=prepared/path.name
            if not dest.exists():dest.symlink_to(path.resolve())
        raw=read(original/'config.json');normalized=normalized_config(name,raw)
        write(prepared/'config.json',normalized)
        if name=='glm':
            tokenizer_config=read(original/'tokenizer_config.json')
            if tokenizer_config.get('tokenizer_class')=='TokenizersBackend':
                # New publisher metadata name for the generic fast-tokenizer
                # backend; the same tokenizer.json works on Transformers 4.
                tokenizer_config['tokenizer_class']='PreTrainedTokenizerFast'
            if isinstance(tokenizer_config.get('extra_special_tokens'),list):
                tokenizer_config['additional_special_tokens']=tokenizer_config.pop('extra_special_tokens')
            dest=prepared/'tokenizer_config.json'
            if dest.is_symlink():dest.unlink()
            write(dest,tokenizer_config)
            from tokenizers import Tokenizer
            from transformers import AutoTokenizer
            raw_tokenizer=Tokenizer.from_file(str(original/'tokenizer.json'))
            adapted_tokenizer=AutoTokenizer.from_pretrained(prepared,trust_remote_code=False)
            if raw_tokenizer.get_vocab()!=adapted_tokenizer.get_vocab():raise ValueError('GLM metadata adapter changed token IDs')
            for text in ['Revenue 2025 £1,234.50 (98.7%)','<table><tr><td>Cash</td></tr></table>','财务 € —']:
                if raw_tokenizer.encode(text,add_special_tokens=False).ids!=adapted_tokenizer.encode(text,add_special_tokens=False):raise ValueError('GLM metadata adapter changed encoding')
        target=MODELS/'gguf'/name;target.mkdir(parents=True,exist_ok=True)
        model=target/'model-f16.gguf';projector=target/'mmproj-f16.gguf'
        provenance=target/'conversion.json'
        identity=dict(source_config_sha256=sha(original/'config.json'),normalized_config_sha256=sha(prepared/'config.json'),
                      source_weights={f.name:sha(f) for f in original.glob('*.safetensors')},
                      llama_revision=(LOCAL/'llama-revision.txt').read_text().strip(),
                      model=config()['models'][name],format='f16',low_bit_quantization=False,
                      conversion_only=True,inference_run=False)
        if name=='glm':identity['tokenizer_config_adapter']=dict(source_sha256=sha(original/'tokenizer_config.json'),adapted_sha256=sha(prepared/'tokenizer_config.json'),change='TokenizersBackend -> PreTrainedTokenizerFast; extra_special_tokens list -> additional_special_tokens; tokenizer.json unchanged',vocabulary_ids_verified_unchanged=True,encoding_checks=3)
        if provenance.exists():
            prior=read(provenance)
            if prior['input']!=identity:raise RuntimeError('Conversion settings changed; use another output version')
            if sha(model)!=prior['model_sha256'] or sha(projector)!=prior['mmproj_sha256']:raise ValueError('Converted asset changed')
        else:
            for output,extra in [(model,[]),(projector,['--mmproj'])]:
                temporary=output.with_suffix('.gguf.part')
                command=[sys.executable,str(converter),str(prepared),'--outtype','f16','--outfile',str(temporary),*extra]
                print('Converting',name,'projector' if extra else 'language weights',flush=True)
                with (target/('projector-conversion.log' if extra else 'model-conversion.log')).open('w') as log:
                    subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,
                                   env={**os.environ,'OMP_NUM_THREADS':'1','TOKENIZERS_PARALLELISM':'false','HF_HUB_OFFLINE':'1'})
                temporary.replace(output)
            write(provenance,dict(input=identity,model_sha256=sha(model),mmproj_sha256=sha(projector),
                                  model_bytes=model.stat().st_size,mmproj_bytes=projector.stat().st_size))
        result[name]=read(provenance)
    prompts={name:render_prompt(name,entry['prompt']) for name,entry in config()['models'].items()}
    prompts['mineru_table']=render_prompt('mineru','\nTable Recognition:')
    write(HERE/'rendered-prompts.json',prompts)
    # Store hashes in Git; large converted weights remain ignored/local.
    existing=read(HERE/'model-conversions.json') if (HERE/'model-conversions.json').exists() else {}
    existing.update(result);write(HERE/'model-conversions.json',existing)
    print('GGUF assets and prompts ready. No model was loaded for inference.',flush=True)


if __name__=='__main__':main()
