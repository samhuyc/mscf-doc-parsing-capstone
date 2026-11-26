"""Recompute the presentation tables from saved scores. Python standard library only."""
import argparse
import csv
import gzip
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
MODELS=('paddle_vl','glm','mineru_vlm','monkey','pymupdf')
TABLE=('full_teds','structure_teds','grits_content','fact_f1','numeric_cell_f1')
TEXT=('critical_span_recall','critical_context_recall','text_similarity','fin_ed','numeric_f1')

def rows(base,filename):
    with (base/filename).open(encoding='utf-8',newline='') as f:
        return list(csv.DictReader(f))

def summarize(items,metrics):
    result={}
    for metric in metrics:
        nums=[float(v[metric]) for v in items if v[metric]!='']
        if nums:result[metric]=statistics.mean(nums)
    return result

def reconstruct(base):
    meta=json.loads((base/'release.json').read_text())
    inputs={r['id']:r for r in rows(base,'inputs.csv')}
    obs=rows(base,'observations.csv')
    assert len(obs)==len({(r['id'],r['m']) for r in obs})==meta['observations']
    assert len(inputs)==meta['input_count']==105
    assert all(r['language']=='English' for r in inputs.values())
    out={'release':meta,'matched':{},'other_tables':{},'pages':{},'checks':{},'michael':{}}
    for ds in ('ft','hold','ukcrop'):
        models={m:{r['id']:r for r in obs if r['ds']==ds and r['m']==m} for m in MODELS}
        common=set.intersection(*(set(a) for a in models.values()))
        paired=sorted(common,key=lambda k:int(inputs[k]['order']))
        out['matched'][ds]={'ids':paired,'n':len(paired),'issuers':len({inputs[i]['issuer'] for i in paired}),
            'scores':{m:summarize([rr[i] for i in paired],TABLE) for m,rr in models.items()},
            'timeouts':{m:sum(rr[i]['state']=='timeout' for i in paired) for m,rr in models.items()}}
        out['other_tables'][ds]={m:{'n':len(rr),'metrics':summarize(list(rr.values()),TABLE)} for m,rr in models.items()}
    for m in ('mineru_vlm','pymupdf'):
        out['pages'][m]=summarize([r for r in obs if r['ds']=='fc' and r['m']==m],TEXT)
        for ds in ('ak','aq','uk'):
            select=[r for r in obs if r['m']==m and r['ds']==ds]
            assert len(select)==sum(i['ds']==ds for i in inputs.values())
            counts={k:sum(int(v[k]) for v in select) for k in ('rows_exact','rows','value_matches','values')}
            out['checks'].setdefault(ds,{})[m]={**counts,'pages':len(select)}
            if ds=='uk':
                for issuer in {v['issuer'] for v in select}:
                    rs=[r for r in select if r['issuer']==issuer]
                    out['checks'].setdefault(issuer,{})[m]={k:sum(int(v[k]) for v in rs) for k in ('rows_exact','rows','value_matches','values')}
    for row in rows(base,'metric_outcomes.csv'):
        if row['Dataset and cohort']=='FinTabNet · Michael 300':
            out['michael'].setdefault(row['Parser'],{})[row['Metric ID']]=dict(value=float(row['Value']),n=int(row['Score denominator']))
        if row['Selection'] not in {'Main cohort','Matched MinerU inputs'} or not row['Value']:continue
        if row['Dataset and cohort']!='FinTabNet · development' or row['Metric ID'] not in TABLE:continue
        model=next(m for m in MODELS if meta['models'][m]['name']==row['Parser'])
        measured=out['matched']['ft']['scores'][model] if row['Selection']=='Matched MinerU inputs' else out['other_tables']['ft'][model]['metrics']
        assert math.isclose(measured[row['Metric ID']],float(row['Value']),abs_tol=1e-10)
    checks=rows(base,'filing_checks.csv')
    for m in ('mineru_vlm','pymupdf'):
        for ds in ('ak','aq','uk'):
            sub=[r for r in checks if inputs[r['id']]['ds']==ds];dst=out['checks'][ds][m]
            assert len(sub)==dst['rows'] and sum(len(json.loads(r['values'])) for r in sub)==dst['values']
            assert sum(int(r[m+'_matched']) for r in sub)==dst['value_matches']
            assert sum(int(r[m+'_matched'])==len(json.loads(r['values'])) for r in sub)==dst['rows_exact']
    return out

def verify_predictions(base):
    ref={(r['id'],r['m']):r for r in rows(base,'observations.csv') if r['evidence']=='predictions.jsonl.gz'}
    with gzip.open(base/'predictions.jsonl.gz','rt',encoding='utf-8') as f:
        for line in f:
            r=json.loads(line)
            assert hashlib.sha256(r['native_text'].encode()).hexdigest()==r['sha256']==ref.pop((r['id'],r['parser']))['out_hash']
    assert not ref

def verify_michael(base, summary):
    original = HERE.parents[2] / 'people/mc8/2026-11-17_confidence_cpu/results/300_tables/scores.csv'
    if not original.is_file():
        return  # The flat evidence bundle may be copied without the rest of the repository.
    with original.open(encoding='utf-8', newline='') as handle:
        archive = list(csv.DictReader(handle))
    assert len(archive) == len({(r['table_id'], r['engine']) for r in archive}) == 2100
    names = summary['release']['models']
    columns = {'fact_f1':'fact_f1','grits_content':'grits_content_f1','number_recall':'financial_value_recall'}
    for model in ('paddle_vl','glm','monkey'):
        entries = [r for r in archive if r['engine'] == model]
        official = summary['michael'][names[model]['name']]
        for metric, column in columns.items():
            eligible = [float(r[column]) for r in entries if r[column] != '']
            assert len(eligible) == official[metric]['n']
            assert math.isclose(statistics.mean(eligible), official[metric]['value'], abs_tol=1e-10)
    archive_ids = {r['table_id'] for r in archive}
    participants = rows(base,'inputs.csv')
    overlap = json.loads((base/'michael_overlap.json').read_text())
    for key in ('ft','hold'):
        cohort_ids = {r['id'] for r in participants if r['ds'] == key}
        assert archive_ids & cohort_ids == set(overlap['tables'][key])

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,default=HERE/'evidence');p.add_argument('--json',action='store_true')
    args=p.parse_args()
    d=reconstruct(args.evidence);verify_predictions(args.evidence);verify_michael(args.evidence,d)
    if args.json:print(json.dumps(d,indent=2,ensure_ascii=False));return
    ft=d['matched']['ft'];print(f"Same {ft['n']} development tables from {ft['issuers']} issuers")
    print('Parser | Structure TEDS | Full TEDS | Financial fact F1')
    for m,ss in ft['scores'].items():
        print(f"{d['release']['models'][m]['name']} | {ss['structure_teds']:.3f} | {ss['full_teds']:.3f} | {ss['fact_f1']:.3f}")
    for m,ss in d['pages'].items():
        uk=d['checks']['uk'][m]
        print(f"{m}: critical spans {ss['critical_span_recall']:.3f}, strict contexts {ss['critical_context_recall']:.3f}, UK row-linked values {uk['value_matches']}/{uk['values']}")
    print('Verified against structured outcomes, filing checks and saved prediction hashes.')

if __name__=='__main__':
    main()
