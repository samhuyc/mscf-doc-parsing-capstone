"""Run PP-OCRv5 on every page, preserving native recognition-line scores."""
import argparse
import importlib.metadata
import os
from pathlib import Path
import time
from core import ROOT, SPONSOR, digest, document_result, read, sha, sources, summarize, write


def parse_result(result):
    data = result.get('res', result)
    texts, scores, polygons = data['rec_texts'], data['rec_scores'], data['rec_polys']
    if not len(texts) == len(scores) == len(polygons):
        raise ValueError('Unaligned recognition outputs')
    units = []
    for text, score, polygon in zip(texts, scores, polygons):
        poly = polygon.tolist() if hasattr(polygon, 'tolist') else polygon
        units.append({'text':text, 'score':float(score), 'native_score':float(score),
                      'score_kind':'paddle_native_recognition_score', 'unit_kind':'line', 'polygon':poly})
    summarize(units)  # Reject invalid native values rather than silently clipping.
    return units


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output',type=Path,default=ROOT/'runs/paddle')
    cli.add_argument('--documents',nargs='+')
    cli.add_argument('--pages',nargs='+',type=int)
    args=cli.parse_args()
    os.environ.setdefault('PADDLE_PDX_CACHE_HOME', str(ROOT/'work/paddlex'))
    os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK','True')
    os.environ.setdefault('PADDLE_PDX_MODEL_SOURCE','bos')
    import numpy as np
    import pymupdf
    from paddleocr import PaddleOCR
    config=dict(text_detection_model_name='PP-OCRv5_mobile_det',
                text_recognition_model_name='PP-OCRv5_mobile_rec',
                use_doc_orientation_classify=False,use_doc_unwarping=False,
                use_textline_orientation=False,device='cpu',cpu_threads=4,
                enable_mkldnn=False,text_det_limit_side_len=1280,text_det_limit_type='max',
                text_rec_score_thresh=0.0)
    settings={'engine':'paddle','config':config,'render_dpi':200,
              'versions':{k:importlib.metadata.version(k) for k in ('paddleocr','paddlepaddle','paddlex','pymupdf')},
              'score_semantics':'Native recognition score of each detected line; not detection confidence or calibrated correctness'}
    previous=args.output/'settings.json'
    if previous.exists() and read(previous)!=settings:raise ValueError('Configuration changed; choose a new output directory')
    write(previous,settings)
    model=PaddleOCR(**config)
    results=[]
    selected=[s for s in sources() if not args.documents or s['id'] in args.documents]
    if not selected:raise ValueError('No documents selected')
    for source in selected:
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
                    record={'engine':'paddle','document':source['id'],'page':i+1,
                            'source_sha256':source['sha256'],'settings_sha256':digest(settings)}
                    try:
                        pix=page.get_pixmap(dpi=200,colorspace=pymupdf.csRGB,alpha=False)
                        rgb=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3)
                        predictions=list(model.predict(rgb[:,:,::-1].copy()))
                        if len(predictions)!=1:raise ValueError('Expected one page result')
                        units=parse_result(predictions[0])
                        record.update(status='success',units=units,text='\n'.join(u['text'] for u in units),
                                      width=pix.width,height=pix.height,confidence=summarize(units))
                    except Exception as exc:
                        record.update(status='failed',units=[],error=f'{type(exc).__name__}: {exc}')
                    record['seconds']=round(time.monotonic()-started,3)
                    write(dest,record)
                    print(source['id'],i+1,record['status'],len(record['units']),record.get('error',''),flush=True)
                pages.append(record)
        result=document_result(source['id'],'paddle',pages,source['pages'])
        results.append(result)
        write(args.output/source['id']/'document.json',result)
        write(args.output/'documents.json',results)


if __name__=='__main__':main()
