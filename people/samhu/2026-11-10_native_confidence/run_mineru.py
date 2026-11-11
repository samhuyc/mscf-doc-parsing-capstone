"""Instrument the local MinerU2.5-Pro recognition model, retaining token log-probabilities.

This is full-page text recognition, NOT the full MinerU layout/table pipeline.
Scores come from the decoder, never from a prompt asking for confidence.
"""
import argparse
import importlib.metadata
import math
import os
from pathlib import Path
import tempfile
import time
from core import ROOT, SPONSOR, digest, document_result, read, sha, sources, summarize, write


def normalized_logprob(values, token, array_module):
    """Re-normalize the full decoder distribution in FP32, preserving its ranking.

    The backend subtracts logsumexp in BF16; rounding can make its exp values
    sum above/below 1. Re-normalization removes the constant error without
    temperature scaling, truncating candidates or fitting against labels.
    """
    flat=values.reshape(-1).astype(array_module.float32)
    maximum=flat.max()
    normalizer=maximum+array_module.log(array_module.exp(flat-maximum).sum())
    return float((flat[token]-normalizer).item()), float(normalizer.item())


def collect_stream(stream, tokenizer, array_module=None):
    """MLX's final yield repeats the last token or carries EOS: count neither twice."""
    if array_module is None:
        import numpy as array_module
    chunks, tokens = [], []
    last_step = 0
    stopped = False
    for item in stream:
        chunks.append(item.text)
        token = int(item.token)
        if tokenizer.stopping_criteria(token):
            stopped = True
            continue
        if item.generation_tokens <= last_step:
            continue
        last_step = item.generation_tokens
        raw_logprob = float(item.logprobs.reshape(-1)[token].item())
        logprob, correction = normalized_logprob(item.logprobs,token,array_module)
        if not math.isfinite(logprob) or logprob > 1e-5:
            raise ValueError('Invalid selected-token log-probability')
        tokens.append({'token_id':token,'text':tokenizer.decode([token]),
                       'score':math.exp(min(0,logprob)),'log_probability':logprob,
                       'backend_log_probability':raw_logprob,'log_normalization_correction':correction,
                       'unit_kind':'subword_token','score_kind':'selected_token_softmax_probability'})
    return ''.join(chunks), tokens, stopped


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--model',type=Path,required=True)
    cli.add_argument('--output',type=Path,default=ROOT/'runs/mineru')
    cli.add_argument('--documents',nargs='+')
    cli.add_argument('--pages',type=int,nargs='+')
    cli.add_argument('--max-tokens',type=int,default=4096)
    args=cli.parse_args()
    os.environ.setdefault('HF_HUB_OFFLINE','1')
    import pymupdf
    from PIL import Image
    from mlx_vlm import load, stream_generate
    import mlx.core as mx
    from safetensors import safe_open
    config=read(args.model/'config.json')
    metadata=args.model/'.cache/huggingface/download/model.safetensors.metadata'
    revision=metadata.read_text().splitlines()[0] if metadata.exists() else args.model.name
    settings={'engine':'mineru','model_snapshot':revision,'processor_use_fast':True,
              'config_sha256':sha(args.model/'config.json'),
              'weight_sha256':sha(args.model/'model.safetensors'),
              'versions':{k:importlib.metadata.version(k) for k in ('mlx','mlx-vlm','mlx-lm','transformers','torch','torchvision','pymupdf','pillow')},
              'task':'full_page_text_recognition','prompt':'\nText Recognition:',
              'max_tokens':args.max_tokens,'temperature':0.0,'render_dpi':150,'max_image_side':1536,
              'repetition_penalty':None,'logit_bias':None,
              'probability_normalization':'Full backend log-probability vector re-normalized in FP32',
              'score_semantics':'Unmodified decoder log-softmax of each emitted subword token; EOS excluded'}
    previous=args.output/'settings.json'
    if previous.exists() and read(previous)!=settings:raise ValueError('Configuration changed; choose new output directory')
    write(previous,settings)
    # Reproduce MinerU's MLX compatibility fix without changing model files.
    with tempfile.TemporaryDirectory(prefix='mineru-native-') as temp:
        prepared=Path(temp)
        with safe_open(args.model/'model.safetensors',framework='numpy') as weights:
            has_head=any(k in weights.keys() for k in ('lm_head.weight','language_model.lm_head.weight'))
        if config.get('model_type')=='qwen2_vl' and not has_head:
            config.update(config.get('text_config',{}))
        for child in args.model.iterdir():
            if child.name!='config.json':(prepared/child.name).symlink_to(child.resolve())
        write(prepared/'config.json',config)
        print('Loading local MinerU model',flush=True)
        model,processor=load(str(prepared),use_fast=True)
        tokenizer=processor.tokenizer
        prompt=processor.apply_chat_template([{'role':'user','content':[
            {'type':'image'},{'type':'text','text':settings['prompt']}]}],tokenize=False,add_generation_prompt=True)
        results=[]
        for source in sources():
            if args.documents and source['id'] not in args.documents:continue
            path=SPONSOR/'inputs'/(source['id']+'.pdf')
            if sha(path)!=source['sha256']:raise ValueError('Source hash mismatch')
            pages=[]
            with pymupdf.open(path) as pdf:
                for i,page in enumerate(pdf):
                    if args.pages and i+1 not in args.pages:continue
                    dest=args.output/source['id']/f'page_{i+1:03}.json'
                    if dest.exists():
                        record=read(dest)
                        if record['settings_sha256']!=digest(settings) or record['source_sha256']!=source['sha256']:
                            raise ValueError('Existing output mismatch')
                    else:
                        started=time.monotonic()
                        record={'engine':'mineru','document':source['id'],'page':i+1,
                                'source_sha256':source['sha256'],'settings_sha256':digest(settings)}
                        try:
                            pix=page.get_pixmap(dpi=150,colorspace=pymupdf.csRGB,alpha=False)
                            image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
                            image.thumbnail((1536,1536),Image.Resampling.LANCZOS)
                            stream=stream_generate(model,processor,prompt,image=[image],
                                                   max_tokens=args.max_tokens,temperature=0.0)
                            text,tokens,stopped=collect_stream(stream,tokenizer,mx)
                            record.update(status='success',text=text,confidence_units=tokens,
                                          units=[{'text':text,'score':None,'unit_kind':'page'}] if text.strip() else [],
                                          confidence=summarize(tokens),truncated=not stopped,
                                          stop_reason='eos' if stopped else 'token_limit',width=image.width,height=image.height)
                        except Exception as exc:
                            record.update(status='failed',units=[],error=f'{type(exc).__name__}: {exc}')
                        record['seconds']=round(time.monotonic()-started,3)
                        write(dest,record)
                        print(source['id'],i+1,record['status'],len(record.get('confidence_units',[])),
                              record['seconds'],record.get('error',''),flush=True)
                    pages.append(record)
            result=document_result(source['id'],'mineru',pages,source['pages'])
            results.append(result)
            write(args.output/source['id']/'document.json',result)
            write(args.output/'documents.json',results)


if __name__=='__main__':main()
