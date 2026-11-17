"""Within-model, issuer-separated assessment; no fresh-label selection."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import math
import statistics
from common import ROOT,RUN,RESULTS,read,write,sha,digest
from calibration import FEATURES,outer_predictions,metrics,cluster_interval,fit_isotonic,predict,choose_feature
from evaluate_table_accuracy import spearman,error_auc

TARGETS=('fact_f1','grits_content_f1','financial_value_recall')
STRUCTURED=('paddle_vl','glm','monkey','mineru_table')

def ranking(rows,feature,target):
    rows=[r for r in rows if r.get(feature) is not None and r.get(target) is not None]
    if not rows:return dict(n=0)
    xs=[r[feature] for r in rows];ys=[r[target] for r in rows]
    rho=spearman(xs,ys)
    def correlation(rs):return spearman([r[feature] for r in rs],[r[target] for r in rs])
    bad=[y<.95 for y in ys]
    return dict(n=len(rows),issuers=len({r['issuer'] for r in rows}),mean_accuracy=statistics.mean(ys),
                mean_native=statistics.mean(xs),native_range=[min(xs),max(xs)],spearman=rho,
                spearman_issuer_bootstrap_95=cluster_interval(rows,correlation),
                error_auc_below_95=error_auc(xs,[not b for b in bad]),errors_below_95=sum(bad),
                exact_tables=sum(y>=1-1e-9 for y in ys))

def cohorts(rows):
    for name,allowed in [('benchmark',{'benchmark'}),('sponsor',{'sponsor_development','repairs','sponsor_table_mode'}),('development',{'benchmark','sponsor_development','repairs','sponsor_table_mode'})]:
        yield name,[r for r in rows if r['cohort'] in allowed]

def analyze(rows):
    summaries=[];predictions=[]
    for cohort,rs in cohorts(rows):
        for engine in sorted({r['engine'] for r in rs}):
            for target in TARGETS:
                if target!='financial_value_recall' and engine not in STRUCTURED:continue
                valid=[r for r in rs if r['engine']==engine and r.get(target) is not None and r.get('financial_reference_eligible',True)]
                if not valid:continue
                result=dict(cohort=cohort,engine=engine,target=target,total_rows=len(valid),mean_accuracy_all=statistics.mean(r[target] for r in valid),ranking=ranking(valid,'native_numeric',target))
                for name,select in [('numeric',False),('selected_native',True)]:
                    pred=outer_predictions(valid,target=target,select=select)
                    result[name]=metrics(pred)
                    predictions.extend(dict(**p,cohort=cohort,engine=engine,target=target,method=name) for p in pred)
                summaries.append(result)
    return summaries,predictions

def freeze(rows,path):
    if path.exists():raise RuntimeError('Calibration freeze already exists; do not overwrite after holdout inspection')
    development=[r for r in rows if r['cohort']!='fresh_public']
    models=[]
    for cohort,rs in cohorts(development):
        if cohort=='sponsor':continue
        for engine in sorted({r['engine'] for r in rs}):
            for target in TARGETS:
                if target!='financial_value_recall' and engine not in STRUCTURED:continue
                valid=[r for r in rs if r['engine']==engine and r.get(target) is not None and r.get('financial_reference_eligible',True)]
                if not valid:continue
                selected,losses=choose_feature(valid,target)
                for name,feature in [('numeric','native_numeric'),('selected_native',selected)]:
                    fitting=[r for r in valid if r.get(feature) is not None]
                    if not fitting:continue
                    xs=[r[feature] for r in fitting];ys=[r[target] for r in fitting]
                    models.append(dict(training_cohort=cohort,engine=engine,target=target,method=name,feature=feature,
                      model=fit_isotonic(xs,ys),baseline=statistics.mean(r[target] for r in valid),training_rows=len(valid),feature_fit_rows=len(fitting),
                      training_issuers=sorted({r['issuer'] for r in valid}),training_examples=[r['table_id'] for r in valid],
                      feature_cv_losses=losses if name=='selected_native' else {},review_cutoff=sorted(xs)[max(0,math.ceil(.2*len(xs))-1)]))
    write(path,dict(frozen_utc=datetime.now(timezone.utc).isoformat(),fresh_outputs_inspected=False,
                   development_pairs_sha256=digest(development),protocol_sha256=sha(ROOT/'prototype/protocol.json'),source_pairs_file_sha256=sha(RESULTS/'pairs.json'),
                   code_sha256={n:sha(ROOT/'prototype'/n) for n in ('analyze.py','calibration.py','evaluate.py','table_structure.py','native_evidence.py','reference_annotations.py')},
                   policy='No refitting, score selection or threshold selection on fresh-public labels. Both benchmark-only and combined-development models are frozen.',models=models))

def fresh_evaluation(rows,frozen):
    fresh=[r for r in rows if r['cohort']=='fresh_public'];results=[];all_predictions=[]
    for m in frozen['models']:
        selected=[r for r in fresh if r['engine']==m['engine'] and r.get(m['target']) is not None]
        assert not {r['issuer'] for r in selected}.intersection(m['training_issuers'])
        pred=[dict(table_id=r['table_id'],issuer=r['issuer'],truth=r[m['target']],prediction=predict(m['model'],r[m['feature']]) if r.get(m['feature']) is not None else m['baseline'],missing_selected_confidence=r.get(m['feature']) is None,
                   baseline=m['baseline'],native=r[m['feature']],review=r.get(m['feature']) is None or r[m['feature']]<=m['review_cutoff'],selected_feature=m['feature']) for r in selected]
        identity={k:m[k] for k in ('training_cohort','engine','target','method','feature')}
        results.append(dict(**identity,**metrics(pred),issuer_breakdown=[dict(issuer=issuer,**metrics([r for r in pred if r['issuer']==issuer])) for issuer in sorted({r['issuer'] for r in pred})],format_breakdown=[dict(format=name,**metrics([r for r in pred if (r['issuer'] in {'harrods','dyson'})==scanned])) for name,scanned in [('real_scan',True),('digital',False)]]))
        all_predictions.extend(dict(**identity,**r) for r in pred)
    return results,all_predictions

def main():
    p=argparse.ArgumentParser();p.add_argument('--freeze',action='store_true');p.add_argument('--fresh',action='store_true');a=p.parse_args()
    data=read(RESULTS/'pairs.json');rows=data['pairs'];path=RESULTS/'calibrators_frozen.json'
    if a.freeze:
        audit=read(RESULTS/'development_audit.json')
        if audit['status']!='pass':raise RuntimeError('Complete the development audit before freezing')
        if data.get('pending') or any(r['status']!='success' for r in data.get('availability',[])):raise RuntimeError('Development outputs or native evidence incomplete')
        if data['code_sha256']!={n:sha(ROOT/'prototype'/n) for n in data['code_sha256']}:raise RuntimeError('Scoring code changed; recompute development accuracy')
        fresh_reference_freeze=read(RUN/'fresh_holdout_reference_freeze.json')
        if fresh_reference_freeze['references_sha256']!=sha(RUN/'fresh_public/references.json'):raise RuntimeError('Fresh reference snapshot changed')
        freeze(rows,path)
    if a.fresh:
        result,predictions=fresh_evaluation(rows,read(path));write(RESULTS/'fresh_validation.json',dict(results=result,predictions=predictions,frozen_calibrators_sha256=sha(path)))
    else:
        summaries,predictions=analyze([r for r in rows if r['cohort']!='fresh_public'])
        write(RESULTS/'development_validation.json',dict(summaries=summaries,predictions=predictions,pairs_sha256=sha(RESULTS/'pairs.json'),
          caveats=['Retrospective development diagnostics; metric repairs used source and development outputs.','Issuer grouping prevents calibration leakage but does not prove no foundation-model pretraining overlap.','GriTS gives partial text credit; financial facts penalize association errors but deterministic parsing is imperfect.','Tesseract scores are native heuristic confidence, not token probabilities.','Financial value recall ignores extra values and row/column assignment; not a substitute for table accuracy.']))
        for r in summaries:
            if r['cohort']=='development' and r['target']=='fact_f1':
                print(r['engine'],r['ranking'],{k:r['selected_native'][k] for k in ('mse_gain','mse_gain_issuer_bootstrap_95','selection_counts')})
if __name__=='__main__':main()
