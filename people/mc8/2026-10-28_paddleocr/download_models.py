"""Cache exact official Paddle models before timed sequential inference runs."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import time
import urllib.request

from common import ROOT, dump
from prepare import sha

MODELS=['PP-DocBlockLayout','PP-DocLayout_plus-L','PP-OCRv5_mobile_det','PP-OCRv5_mobile_rec',
        'PP-LCNet_x1_0_table_cls','SLANeXt_wired','SLANet_plus',
        'RT-DETR-L_wired_table_cell_det','RT-DETR-L_wireless_table_cell_det','PP-LCNet_x1_0_doc_ori']
SAVED=ROOT/'model_sources.json'
PRIOR={r['model']:r for r in json.loads(SAVED.read_text())} if SAVED.exists() else {}


def download(model):
    base=ROOT/'cache/paddlex/official_models'/model
    base.mkdir(parents=True,exist_ok=True)
    if model in PRIOR:
        record=PRIOR[model]
        for name,info in record['files'].items():
            if not (base/name).is_file() or sha(base/name)!=info['sha256']:
                raise ValueError(f'Pinned cached model changed or missing: {model}/{name}')
        print('Verified cached',model,record['revision'],flush=True)
        return record
    with urllib.request.urlopen('https://huggingface.co/api/models/PaddlePaddle/'+model,timeout=60) as response:
        info=json.load(response)
    revision=info['sha']
    names=[s['rfilename'] for s in info['siblings'] if s['rfilename'].endswith(('.json','.yml','.yaml','.pdiparams'))]
    started=time.monotonic()
    print('Downloading',model,'revision',revision,flush=True)
    files={}
    for name in names:
        target=base/name
        if not target.exists():
            temporary=target.with_suffix(target.suffix+'.part')
            for attempt in range(3):
                try:
                    url=f'https://huggingface.co/PaddlePaddle/{model}/resolve/{revision}/{name}'
                    with urllib.request.urlopen(url,timeout=120) as response,temporary.open('wb') as out:
                        expected=response.headers.get('Content-Length')
                        count=0
                        while block:=response.read(1024*1024):
                            count+=len(block)
                            out.write(block)
                    if expected and count!=int(expected):
                        raise ValueError('Truncated model download')
                    temporary.replace(target)
                    break
                except Exception:
                    if attempt==2:
                        raise
                    time.sleep(2**attempt)
        files[name]=dict(bytes=target.stat().st_size,sha256=sha(target))
    print('Cached',model,sum(f['bytes'] for f in files.values()),'bytes',round(time.monotonic()-started,1),'seconds',flush=True)
    return dict(model=model,repository='PaddlePaddle/'+model,revision=revision,files=files)


def main():
    records=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(download,m):m for m in MODELS}
        for future in as_completed(futures):
            records.append(future.result())
            dump(ROOT/'model_sources.json',sorted(records,key=lambda r:r['model']))
    print('All',len(records),'models cached; downloads excluded from parser timings.',flush=True)


if __name__=='__main__':
    main()
