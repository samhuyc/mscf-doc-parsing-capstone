"""Fetch pinned weights / FinTabNet Parquet. Never load recognizers or infer."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import time
import urllib.request
from common import HERE, REPO, LOCAL, MODELS, config, read, write, sha


def get_json(url):
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return json.load(r)
        except Exception:
            if attempt == 5: raise
            time.sleep(min(2**attempt, 20))


def ranged_tail(item, part):
    """Resume a large file with four bounded HTTP ranges, then hash it whole."""
    total=item['bytes'];offset=part.stat().st_size if part.exists() else 0
    if offset>=total:return
    width=max(32*1024*1024,(total-offset+3)//4)
    pieces=[]
    for start in range(offset,total,width):
        end=min(total-1,start+width-1)
        pieces.append((start,end,part.with_name(part.name+f'.range-{start}-{end}')))
    def fetch_piece(piece):
        start,end,path=piece;wanted=end-start+1
        for attempt in range(8):
            done=path.stat().st_size if path.exists() else 0
            if done==wanted:return path
            if done>wanted:path.unlink();done=0
            try:
                req=urllib.request.Request(item['url'],headers={'Range':f'bytes={start+done}-{end}','User-Agent':'mc8-confidence-setup'})
                with urllib.request.urlopen(req,timeout=120) as response:
                    if response.status!=206:raise ValueError('Server did not honor bounded byte range')
                    expected=f'bytes {start+done}-{end}/'
                    if not response.headers.get('Content-Range','').startswith(expected):raise ValueError('Unexpected Content-Range')
                    with path.open('ab') as out:
                        remaining=wanted-done
                        while remaining:
                            block=response.read(min(4*1024*1024,remaining))
                            if not block:raise IOError('Truncated range response')
                            out.write(block);remaining-=len(block)
                print('Range ready',Path(item['path']).parent.name,start,end,flush=True)
                return path
            except Exception:
                if attempt==7:raise
                time.sleep(min(2**attempt,20))
    with ThreadPoolExecutor(max_workers=4) as pool:paths=list(pool.map(fetch_piece,pieces))
    with part.open('ab') as out:
        for path in paths:
            with path.open('rb') as stream:shutil.copyfileobj(stream,out,4*1024*1024)
    for path in paths:path.unlink()


def download(item):
    path = Path(item['path']); path.parent.mkdir(parents=True, exist_ok=True)
    expected = item.get('sha256')
    if path.exists() and (not expected or sha(path) == expected):
        return {**item, 'bytes':path.stat().st_size, 'sha256':sha(path)}
    part = path.with_name(path.name+'.part')
    for attempt in range(8):
        try:
            if item.get('bytes',0)>128*1024*1024:
                ranged_tail(item,part)
                if part.stat().st_size!=item['bytes']:raise ValueError('Large-file size mismatch')
                actual=sha(part)
                if expected and actual!=expected:
                    part.unlink();raise ValueError('Large-file SHA256 mismatch')
                part.replace(path)
                print('Verified',path.name,path.stat().st_size,flush=True)
                return {**item,'bytes':path.stat().st_size,'sha256':actual}
            offset = part.stat().st_size if part.exists() else 0
            req = urllib.request.Request(item['url'], headers={'User-Agent':'mc8-confidence-setup', **({'Range':f'bytes={offset}-'} if offset else {})})
            with urllib.request.urlopen(req, timeout=120) as r:
                append = offset and r.status == 206
                with part.open('ab' if append else 'wb') as out:
                    while block := r.read(4*1024*1024): out.write(block)
            actual = sha(part)
            if expected and actual != expected:
                part.unlink()
                raise ValueError('SHA256 mismatch: '+str(path))
            if item.get('bytes') and part.stat().st_size != item['bytes']:
                raise ValueError('Size mismatch: '+str(path))
            part.replace(path)
            print('Verified', path.name, path.stat().st_size, flush=True)
            return {**item, 'bytes':path.stat().st_size, 'sha256':actual}
        except Exception:
            if attempt == 7: raise
            time.sleep(min(2**attempt, 20))


def hf_items(repository, revision, prefix, target, dataset=False):
    kind = 'datasets' if dataset else 'models'
    meta = get_json(f'https://huggingface.co/api/{kind}/{repository}/revision/{revision}?blobs=true')
    write(LOCAL/'sources'/(repository.replace('/','--')+'.json'), meta)
    items=[]
    for f in meta['siblings']:
        name=f['rfilename']
        if dataset:
            if 'test' not in name or not name.endswith('.parquet'): continue
            short=Path(name).name
        else:
            if not name.startswith(prefix): continue
            short=name[len(prefix):]
            if '/' in short or not short.endswith(('.safetensors','.json','.txt','.model','.jinja','.py')): continue
        lfs=f.get('lfs',{})
        items.append(dict(path=str(target/short), url=f'https://huggingface.co/{"datasets/" if dataset else ""}{repository}/resolve/{meta["sha"]}/{name}',
                          bytes=f.get('size',lfs.get('size')), sha256=lfs.get('sha256'), repository=repository, revision=meta['sha'], source_file=name))
    if not items: raise ValueError('No source assets for '+repository)
    return items


def baseline_items():
    records=read(REPO/'people/mc8/2026-10-28_paddleocr/model_sources.json')
    items=[]
    for r in records:
        if r['model'] not in ('PP-OCRv5_mobile_det','PP-OCRv5_mobile_rec','PP-DocLayout_plus-L'): continue
        for name, f in r['files'].items():
            items.append(dict(path=str(MODELS/r['model']/name), url=f'https://huggingface.co/{r["repository"]}/resolve/{r["revision"]}/{name}', **f))
    items.append(dict(path=str(MODELS/'tessdata/eng.traineddata'), url='https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/eng.traineddata', sha256='7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2'))
    return items


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--models',action='store_true');cli.add_argument('--data',action='store_true')
    cli.add_argument('--workers',type=int,default=4)
    args=cli.parse_args()
    if not args.models and not args.data: cli.error('Choose --models and/or --data')
    items=[]
    if args.models:
        items+=baseline_items()
        for name,r in config()['models'].items():
            items+=hf_items(r['repository'],r['revision'],r['prefix'],MODELS/'hf'/name)
    if args.data:
        dataset=config()['dataset']['repository']
        meta=get_json(f'https://huggingface.co/api/datasets/{dataset}')
        items+=hf_items(dataset,meta['sha'],'',LOCAL/'parquet',dataset=True)
    needed=sum(i.get('bytes') or 0 for i in items if not Path(i['path']).exists())
    if shutil.disk_usage(HERE).free < needed+16*1024**3: raise RuntimeError('Insufficient disk headroom for weights plus conversion')
    write(LOCAL/'download-plan.json',items)
    print('Planned files:',len(items),'remaining bytes:',needed,flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool: results=list(pool.map(download,items))
    suffix='all' if args.models and args.data else 'models' if args.models else 'data'
    write(LOCAL/f'downloaded-{suffix}.json',results)
    print('Assets ready; no model loading or inference performed.',flush=True)


if __name__=='__main__': main()
