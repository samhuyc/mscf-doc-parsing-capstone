"""Render sponsor PDFs and capture Tesseract text and native word confidence together."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from functools import partial
import csv
import importlib.metadata
import io
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from core import ROOT, SPONSOR, digest, document_result, read, sha, sources, summarize, write


def parse_tsv(tsv):
    units = []
    reader=csv.DictReader(io.StringIO(tsv), delimiter='\t', quoting=csv.QUOTE_NONE)
    if not {'level','conf','text','left','top','width','height'}.issubset(reader.fieldnames or []):
        raise ValueError('Tesseract did not return TSV confidence output')
    for r in reader:
        if r.get('level') != '5' or not (r.get('text') or '').strip():
            continue
        confidence = float(r['conf'])
        if confidence < 0:
            continue  # Tesseract's non-word/unavailable sentinel, not a probability.
        if not math.isfinite(confidence) or confidence > 100:
            raise ValueError('Invalid Tesseract confidence')
        x, y, w, h = [int(r[k]) for k in ('left','top','width','height')]
        units.append({'text':r['text'], 'score':confidence/100,
                      'native_score':confidence, 'score_kind':'tesseract_word_confidence_0_100',
                      'unit_kind':'word', 'bbox':[x,y,x+w,y+h],
                      'line_id':[int(r[k]) for k in ('block_num','par_num','line_num')]})
    return units


def run_document(source, args, settings):
    import pymupdf
    pdf_path = SPONSOR / 'inputs' / (source['id']+'.pdf')
    if sha(pdf_path) != source['sha256']:
        raise ValueError('Source hash changed: '+source['id'])
    folder = args.output/source['id']
    pages = []
    with pymupdf.open(pdf_path) as pdf:
        if len(pdf) != source['pages']:
            raise ValueError('Page inventory mismatch')
        for index in range(len(pdf)):
            page_number = index+1
            if args.pages and page_number not in args.pages:
                continue
            out = folder/f'page_{page_number:03}.json'
            if out.exists():
                p = read(out)
                if p['source_sha256'] != source['sha256'] or p['settings_sha256'] != digest(settings):
                    raise ValueError('Existing output does not match configuration')
                pages.append(p)
                continue
            started=time.monotonic()
            record={'document':source['id'],'page':page_number,'engine':'tesseract',
                    'source_sha256':source['sha256'],'settings_sha256':digest(settings)}
            try:
                pix=pdf[index].get_pixmap(dpi=args.dpi, colorspace=pymupdf.csRGB,alpha=False)
                with tempfile.TemporaryDirectory(prefix='native-ocr-') as temp:
                    image=Path(temp)/'page.png'
                    pix.save(image)
                    command=[args.binary,str(image),'stdout','--tessdata-dir',str(args.tessdata),
                             '-l','eng','--psm','3','--dpi',str(args.dpi),'-c','tessedit_create_tsv=1']
                    proc=subprocess.run(command,capture_output=True,text=True,timeout=args.timeout,
                                        env={**os.environ,'OMP_THREAD_LIMIT':'2'},check=True)
                    tsv=proc.stdout
                    units=parse_tsv(tsv)
                    record.update(status='success',units=units,text=' '.join(u['text'] for u in units),
                                  width=pix.width,height=pix.height,confidence=summarize(units),
                                  image_sha256=sha(image))
            except Exception as exc:
                record.update(status='failed',units=[],error=f'{type(exc).__name__}: {exc}')
            record['seconds']=round(time.monotonic()-started,3)
            write(out,record)
            pages.append(record)
            print(source['id'],page_number,record['status'],len(record['units']),flush=True)
    result=document_result(source['id'],'tesseract',pages,source['pages'])
    write(folder/'document.json',result)
    return result


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output',type=Path,default=ROOT/'runs/tesseract')
    cli.add_argument('--binary',default=shutil.which('tesseract') or '/opt/homebrew/bin/tesseract')
    cli.add_argument('--tessdata',type=Path,default=SPONSOR/'cache/tessdata')
    cli.add_argument('--dpi',type=int,default=300)
    cli.add_argument('--timeout',type=int,default=180)
    cli.add_argument('--workers',type=int,default=2)
    cli.add_argument('--documents',nargs='+')
    cli.add_argument('--pages',type=int,nargs='+')
    args=cli.parse_args()
    if min(args.dpi,args.timeout,args.workers)<=0:
        cli.error('dpi, timeout and workers must be positive')
    version=subprocess.check_output([args.binary,'--version'],text=True).splitlines()[0]
    settings={'engine':'tesseract','backend':'standalone_cli','version':version,
              'pymupdf_version':importlib.metadata.version('pymupdf'),'render_dpi':args.dpi,
              'psm':3,'language':'eng','tessdata_sha256':sha(args.tessdata/'eng.traineddata'),
              'forced_ocr_all_pages':True,'native_pdf_text_used':False,
              'score_semantics':'Native word confidence divided by 100; not calibrated correctness probability'}
    previous=args.output/'settings.json'
    if previous.exists() and read(previous)!=settings:
        raise ValueError('Configuration changed; choose a new output directory')
    write(previous,settings)
    selected=[s for s in sources() if not args.documents or s['id'] in args.documents]
    if not selected:cli.error('No documents selected')
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results=list(pool.map(partial(run_document,args=args,settings=settings),selected))
    write(args.output/'documents.json',results)


if __name__=='__main__':
    main()
