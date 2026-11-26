"""Freeze the assembled English evaluation into portable, score-level evidence."""
import argparse
import csv
import gzip
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
METRICS = ('full_teds','structure_teds','grits_content','fact_f1','numeric_cell_f1',
           'critical_span_recall','critical_context_recall','text_similarity','fin_ed','numeric_f1',
           'rows_exact','rows','value_matches','values','nonempty','grids','seconds')

def load(path):
    return json.loads(path.read_text(encoding='utf-8'))

def table(path, cols, items):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore',lineterminator='\n')
        writer.writeheader()
        writer.writerows(items)

def compact(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',',':'))

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--run-dir', type=Path, required=True)
    cli.add_argument('--source-repo', type=Path, required=True, help='Working copy with saved crop predictions')
    cli.add_argument('--output',type=Path,default=HERE/'evidence')
    args=cli.parse_args()
    d=args.run_dir
    out=args.output
    out.mkdir(parents=True,exist_ok=True)
    data=load(d/'english_workbook.json')
    numeric=load(d/'numeric_cells.json')
    edit=load(d/'fin_text_metrics.json')
    inputs=data['inputs']
    registry=data['models']
    input_rows=[dict(v, id=k, language='English') for k,v in inputs.items()]
    reference_root=args.source_repo/'people/samhu/2026-11-15_table_confidence/runs/native_prototype'
    uk_references={}
    for cohort,source_folder in [('ft','benchmark'),('hold','confirmatory'),('ukcrop','fresh_public')]:
        references=load(reference_root/source_folder/'references.json')
        for row in (r for r in input_rows if r['ds']==cohort):
            ref=references[row['id']]
            assert ref['image_sha256']==row['source_sha']
            if cohort=='ukcrop':
                uk_references[row['id']]={k:ref[k] for k in ('grids','image_sha256','reference_kind','basis')}
                row['source']='evidence/uk_table_references.json'
            else:
                row['source']=ref['source']
                row['annotation_sha']=ref['source_sha256']
    (out/'uk_table_references.json').write_text(json.dumps(uk_references,indent=2,ensure_ascii=False)+'\n')
    table(out/'inputs.csv',['id','ds','order','issuer','language','display','page','unit','label_kind','fields','source','source_sha','pdf_sha','annotation_sha'],sorted(input_rows,key=lambda r:(r['ds'],int(r['order']),r['id'])))
    observations=[]
    predictions=[]
    for v in data['obs']:
        key='|'.join((v['id'],v['m'],v['out_hash']))
        row=dict(v,issuer=inputs[v['id']]['issuer'])
        if v['ds'] in ('ft','hold'): row['numeric_cell_f1']=numeric[key]
        if v['ds']=='fc': row['fin_ed']=edit[key]
        # FinCriticalED has a gated distribution. Its predictions are identified by hash.
        if v['ds']=='fc':
            proof='FinCriticalED run evidence (hash only)'
        else:
            raw=v.get('raw')
            if raw is None and v['ds'] in ('ft','hold','ukcrop'):
                raw=load(args.source_repo/v['source'])['text']
            if raw is not None:
                assert hashlib.sha256(raw.encode()).hexdigest()==v['out_hash']
                predictions.append(dict(id=v['id'],parser=v['m'],sha256=v['out_hash'],native_text=raw))
                proof='predictions.jsonl.gz'
            else:
                proof='Archived whole-document filing check; see filing_checks.csv'
        row['evidence']=proof
        observations.append(row)
    assert len({(r['id'],r['m']) for r in observations})==len(observations)
    table(out/'observations.csv',['id','ds','m','issuer','state',*METRICS,'runtime','input_hash','out_hash','evidence'],observations)
    archive=b'\n'.join(compact(r).encode() for r in predictions)+b'\n'
    (out/'predictions.jsonl.gz').write_bytes(gzip.compress(archive,mtime=0))
    checks=[]
    for v in data['fieldrows']:
        r=dict(v,issuer=inputs[v['id']]['issuer'],pdf_page=inputs[v['id']]['page'])
        for key in ('values','pymupdf_observed','mineru_vlm_observed'):
            r[key]=compact(v[key]) if v.get(key) is not None else ''
        checks.append(r)
    table(out/'filing_checks.csv',['id','issuer','pdf_page','row','values','pymupdf_observed','pymupdf_matched','mineru_vlm_observed','mineru_vlm_matched','provenance'],checks)
    (out/'metric_outcomes.csv').write_text((d/'final/English_Parsing_Metric_Outcomes.csv').read_text(encoding='utf-8'), encoding='utf-8')
    (out/'michael_overlap.json').write_text(json.dumps(load(d/'michael_overlap.json'),indent=2)+'\n')
    created=datetime.fromtimestamp((d/'english_workbook.json').stat().st_mtime,ZoneInfo('America/New_York')).isoformat(timespec='seconds')
    release={'snapshot_et':created,'models':registry,'observations':len(observations),'input_count':len(inputs),'published_predictions':len(predictions),'upstream_revision':'11f2a5a8b4cabb1f88a54c788d92941dd329e375'}
    (out/'release.json').write_text(json.dumps(release,indent=2,ensure_ascii=False)+'\n')
    print(f"{len(inputs)} inputs, {len(observations)} observations, {len(predictions)} prediction texts")

if __name__=='__main__':
    main()
