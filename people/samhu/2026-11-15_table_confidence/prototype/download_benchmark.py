"""Freeze a reproducible public table cohort before inspecting predictions."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from html import escape
import json
from pathlib import Path
import random
import re
import time
import urllib.request
from common import ROOT, RUN, read, write, sha, digest
from review_panel import parse_grids

DATASET='docling-project/FinTabNet_OTSL'
API='https://datasets-server.huggingface.co/rows?dataset=docling-project%2FFinTabNet_OTSL&config=default&split=test'

def fetch(offset):
    url=f'{API}&offset={offset}&length=3'
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url,timeout=45) as r:return offset,json.load(r)
        except Exception:
            if attempt==2:raise
            time.sleep(1+attempt)

def restore_html(row):
    cells=iter(row['cells'][0]);count=0
    def fill(match):
        nonlocal count
        count+=1
        return match.group(0)+escape(''.join(next(cells)['tokens']))
    html=re.sub(r'<td\b[^>]*>',fill,''.join(row['html_restored']))
    assert next(cells,None) is None
    return '<table>'+html+'</table>'

def main():
    out=RUN/'benchmark';out.mkdir(parents=True,exist_ok=True)
    if (out/'tables.json').exists():print('Frozen benchmark already exists.');return
    total=10397;rng=random.Random(20261116)
    offsets=list(range(0,total-3,37));rng.shuffle(offsets)
    candidates=[];errors=[];seen=Counter();audits=[]
    # Fixed random-order candidates; filtering never uses model outputs.
    for start in range(0,len(offsets),12):
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures=[pool.submit(fetch,o) for o in offsets[start:start+12]]
            for f in futures:
                try:offset,data=f.result()
                except Exception as exc:errors.append(str(exc));continue
                assert data['num_rows_total']==total
                for item in data['rows']:
                    row=item['row'];family=row['filename'].split('.')[0]
                    if seen[family]>=2 or family in {'CVS','EDF','RR'}:continue
                    if item['truncated_cells']:continue
                    if not (3<=row['rows']<=45 and 2<=row['cols']<=14 and row['rows']*row['cols']<=250):continue
                    if row['image']['width']<200 or row['image']['height']<80:continue
                    html=restore_html(row)
                    if len(re.findall(r'\d+',re.sub(r'<[^>]*>',' ',html)))<6:continue
                    candidates.append((item['row_idx'],row,html));seen[family]+=1
                    if len(candidates)==60:break
                if len(candidates)==60:break
        print('Selected',len(candidates),'tables from',len(seen),'issuers',flush=True)
        if len(candidates)==60:break
    tables=[];refs={}
    for index,row,html in candidates:
        tid=f'fintabnet_test_{index:05d}';image=out/(tid+'.jpg')
        with urllib.request.urlopen(row['image']['src'],timeout=45) as response:image.write_bytes(response.read())
        stable={k:v for k,v in row.items() if k!='image'}
        write(out/(tid+'_annotation.json'),stable)
        family=row['filename'].split('.')[0]
        table=dict(table_id=tid,document='fintabnet_'+row['filename'].split('.page')[0],page=1,
                   issuer=family,image=image.name,image_sha256=sha(image),source_sha256=digest(stable),
                   models={},layout_score=None,source_dataset=DATASET,source_row=index,source_filename=row['filename'])
        tables.append(table)
        refs[tid]=dict(table_id=tid,issuer=family,grids=parse_grids(html),html=html,
                      reference_kind='public_benchmark_annotation',human_verified=False,
                      source_sha256=table['source_sha256'],image_sha256=table['image_sha256'],
                      source=f'{API}&offset={index}&length=1')
    settings=dict(dataset=DATASET,split='test',seed=20261116,selection='fixed random offset order; at most two tables per issuer; geometry/numeric filters only',
                  reference_policy='Original dataset cell text and restored HTML; not independently verified; training overlap unknown',render_dpi=200)
    write(out/'references.json',refs);write(out/'tables.json',dict(settings=settings,pages=[],tables=tables))
    write(out/'selection_audit.json',dict(requested=60,selected=len(tables),issuer_counts=dict(seen),retrieval_errors=errors))
    print('Frozen',len(tables),'tables,',len(seen),'issuers.',flush=True)

if __name__=='__main__':main()
