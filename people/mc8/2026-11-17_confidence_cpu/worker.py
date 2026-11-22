"""One resident recognizer; explicit --execute required. No reference access."""
import argparse
import bisect
import importlib.metadata
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time
from common import HERE, LOCAL, MODELS, DATA, config, read, write, sha, digest, environment
from progress import InferenceProgress


def decoded_record(record):
    units=record.get('confidence_units',[])
    pieces=[bytes.fromhex(u.pop('piece_hex')) for u in units]
    raw=b''.join(pieces)
    try:text=raw.decode('utf-8')
    except UnicodeDecodeError:
        record.update(text=raw.decode('utf-8',errors='replace'),alignment_error='Invalid or incomplete emitted UTF-8; native features unavailable',raw_output_hex=raw.hex())
        return record
    boundaries=[0]
    for char in text:boundaries.append(boundaries[-1]+len(char.encode('utf-8')))
    pos=0
    for u,piece in zip(units,pieces):
        start=pos;pos+=len(piece)
        a=max(0,bisect.bisect_right(boundaries,start)-1)
        b=bisect.bisect_left(boundaries,pos)
        if not piece:b=a
        u.update(decoded_span=[a,b],text=text[a:b],unit_kind='emitted_token',score_kind='native_full_vocabulary_probability')
    record.update(text=text,token_ids=[u['token_id'] for u in units])
    return record


class VLM:
    def __init__(self,engine,settings,folder):
        self.engine=engine
        name='mineru' if engine=='mineru_table' else engine
        runtime=dict(model=str(MODELS/'gguf'/name/'model-f16.gguf'),mmproj=str(MODELS/'gguf'/name/'mmproj-f16.gguf'),
                     **{k:settings[k] for k in ('threads','context','batch','max_tokens')})
        generation=read(MODELS/'hf'/name/'generation_config.json')
        stop=generation.get('eos_token_id')
        runtime['eos_token_ids']=stop if isinstance(stop,list) else [stop] if stop is not None else []
        path=folder/'runtime.json';write(path,runtime)
        self.log=(folder/'native.log').open('a')
        self.process=subprocess.Popen([str(LOCAL/'cpu-build/bin/confidence-vlm'),str(path)],
                                      stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,text=True,bufsize=1)
        self.selector=selectors.DefaultSelector();self.selector.register(self.process.stdout,selectors.EVENT_READ)
        self.prompt=read(HERE/'rendered-prompts.json')[engine]
    def recognize(self,image,timeout):
        self.process.stdin.write(json.dumps(dict(image=str(image),prompt=self.prompt))+'\n');self.process.stdin.flush()
        if not self.selector.select(timeout):raise TimeoutError('CPU crop timeout; process terminated, failure retained')
        line=self.process.stdout.readline()
        if not line:raise RuntimeError('Native process exited; see native.log')
        return decoded_record(json.loads(line))
    def close(self):
        self.selector.close()
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        self.log.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true')
    p.add_argument('--engine',choices=config()['engines'],required=True);p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--limit',type=int);p.add_argument('--retry-failed',action='store_true')
    p.add_argument('--split',choices=['development','test'],required=True);args=p.parse_args()
    if not args.execute:p.error('Inference requires explicit --execute')
    environment();cfg=config()
    from sam_bridge import evidence,check_frozen_code
    check_frozen_code()
    from regions import table_summary
    root=args.run_dir.resolve()/args.engine;root.mkdir(parents=True,exist_ok=True)
    identity=dict(engine=args.engine,config_sha256=sha(HERE/'config.json'),tables_sha256=sha(DATA/'tables.json'),
                  model_conversion=read(HERE/'model-conversions.json').get('mineru' if args.engine=='mineru_table' else args.engine),
                  **{k:cfg[k] for k in ('threads','context','batch','max_tokens','max_image_side')},
                  source_contract='Sam native evidence + financial-association F1; new CPU backend, no reused calibration',
                  versions={name:importlib.metadata.version(name) for name in ('numpy','Pillow','paddlepaddle','paddleocr','paddlex')},
                  runtime_build_sha256=sha(HERE/'runtime-build.json'),
                  adapters_sha256={n:sha(HERE/n) for n in ('worker.py','native_vlm.cpp','sam_bridge.py')})
    settings=root/'settings.json'
    if settings.exists() and read(settings)!=identity:raise RuntimeError('Settings changed; choose a new run directory')
    write(settings,identity);settings_sha=digest(identity)
    split_tables=[t for t in read(DATA/'tables.json')['tables'] if t['split']==args.split]
    tables=split_tables[:args.limit]
    # A repeated one-table pilot must preserve counts from an earlier full run.
    progress=InferenceProgress(root,args.engine,args.split,split_tables)
    vlm=None;paddle=None;verified=False;failures=0;ever_succeeded=False
    final_state='interrupted'
    try:
        for table in tables:
            out=root/(table['table_id']+'.json')
            provenance=dict(table_id=table['table_id'],image_sha256=table['image_sha256'],source_sha256=table['source_sha256'],settings_sha256=settings_sha)
            if out.exists():
                old=read(out)
                if any(old[k]!=v for k,v in provenance.items()):raise RuntimeError('Cached record provenance mismatch')
                if old['status']=='success' or not args.retry_failed:
                    if old['status']!='success':failures+=1
                    else:ever_succeeded=True
                    continue
            progress.start(table['table_id'])
            started=time.monotonic();record={};abort=False
            try:
                image=DATA/table['image']
                if sha(image)!=table['image_sha256']:raise ValueError('Source image hash changed')
                if args.engine=='tesseract':
                    from run_tesseract import parse_tsv
                    command=[str(HERE/'.venv/bin/tesseract'),str(image),'stdout','--tessdata-dir',str(MODELS/'tessdata'),
                             '-l','eng','--psm','3','--dpi','200','-c','tessedit_create_tsv=1']
                    proc=subprocess.run(command,capture_output=True,text=True,check=True,timeout=cfg['timeout_seconds_per_table'])
                    units=parse_tsv(proc.stdout)
                    record=dict(status='success',text='\n'.join(u['text'] for u in units),units=units,confidence_units=units,backend='tesseract-cpu')
                elif args.engine=='paddle':
                    import numpy as np
                    from PIL import Image
                    from paddleocr import PaddleOCR
                    from run_tables import PADDLE_CONFIG,paddle_crop
                    if paddle is None:paddle=PaddleOCR(**{**PADDLE_CONFIG,'cpu_threads':cfg['threads']},text_detection_model_dir=str(MODELS/'PP-OCRv5_mobile_det'),text_recognition_model_dir=str(MODELS/'PP-OCRv5_mobile_rec'))
                    with Image.open(image) as im:pixels=np.asarray(im.convert('RGB'))[:,:,::-1].copy()
                    record=paddle_crop(paddle,pixels,verify=not verified);verified=True
                    record['backend']='paddlepaddle-3.0.0-cpu'
                else:
                    from PIL import Image
                    if vlm is None:vlm=VLM(args.engine,cfg,root)
                    with tempfile.TemporaryDirectory(prefix='crop-',dir=LOCAL) as temp:
                        prepared=Path(temp)/'input.png'
                        with Image.open(image) as im:
                            im=im.convert('RGB');im.thumbnail((cfg['max_image_side'],)*2,Image.Resampling.LANCZOS);im.save(prepared)
                            prepared_size=list(im.size)
                        prepared_sha=sha(prepared)
                        record=vlm.recognize(prepared,cfg['timeout_seconds_per_table'])
                        record.update(prepared_image_sha256=prepared_sha,prepared_image_dimensions=prepared_size)
                    record['instrumentation_equivalence']='Passive argmax/logit capture by construction; no cross-backend equivalence claim'
                if record['status']!='success':raise RuntimeError(record.get('error','Inference failed'))
                record['confidence']=table_summary(record['confidence_units'])
                # Scientific summaries use model output only, never reference labels.
                try:
                    features,alignment=evidence(record,args.engine)
                    record.update(native_features=features,aligned_units=alignment['units'],native_status='available')
                except Exception as exc:record.update(native_status='unavailable',native_error=str(exc))
                ever_succeeded=True
            except Exception as exc:
                record.update(status='failed',error=f'{type(exc).__name__}: {exc}',text=record.get('text',''),confidence_units=record.get('confidence_units',[]))
                failures+=1
                # Do not reload broken weights 2,000 times. The first failure
                # remains recorded and unfinished cases stay visibly missing.
                abort=not ever_succeeded
                if vlm is not None:vlm.close();vlm=None
            record.update(**provenance,engine=args.engine,seconds=round(time.monotonic()-started,3),
                          probability_table_correct=None,calibrated=False)
            write(out,record)
            progress.record(table['table_id'],record)
            state=progress.state
            print(args.engine,table['table_id'],record['status'],
                  f"[{state['processed']}/{state['total']}; {100*state['processed']/state['total']:.2f}%; failed={state['failed']}]",flush=True)
            if record['status']=='failed':print('  '+record['error'],flush=True)
            if abort:
                print('Stopped after initial recognizer failure; fix it before resuming.',flush=True)
                break
        final_state='failed' if failures else 'complete'
    finally:
        if vlm is not None:vlm.close()
        progress.finish(final_state)
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
