"""Compact result exports; predictions and native probabilities stay separate."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import statistics
from common import ROOT,RUN,RESULTS,read,write,sha
from analyze import ranking

NAMES=dict(paddle='PP-OCR',tesseract='Tesseract',paddle_vl='PaddleOCR-VL',glm='GLM-OCR',monkey='MonkeyOCR',mineru='MinerU text',mineru_table='MinerU table')
def triage(pred):
 if not pred:return {}
 reviewed=[r for r in pred if r['review']];kept=[r for r in pred if not r['review']]
 bad=[r for r in pred if r['truth']<.95];caught=[r for r in reviewed if r['truth']<.95]
 return dict(tables=len(pred),reviewed=len(reviewed),review_fraction=len(reviewed)/len(pred),
  errors_below_95=len(bad),caught=len(caught),error_capture=len(caught)/len(bad) if bad else None,
  review_precision=len(caught)/len(reviewed) if reviewed else None,
  kept_mean_accuracy=statistics.mean(r['truth'] for r in kept) if kept else None,
  all_mean_accuracy=statistics.mean(r['truth'] for r in pred),
  note='Threshold is the bottom-20% native cutoff from training issuers; missing selected scores go to review. Test coverage varies; ties stay together.')

def main():
 data=read(RESULTS/'pairs.json');rows=data['pairs'];development=read(RESULTS/'development_validation.json');fresh=read(RESULTS/'fresh_validation.json') if (RESULTS/'fresh_validation.json').exists() else dict(results=[],predictions=[])
 report=dict(created_utc=datetime.now(timezone.utc).isoformat(),pairs_sha256=sha(RESULTS/'pairs.json'),
  unique_crops=len({r['image_sha256'] for r in rows}),outputs=len(rows),
  native_numeric_missing=sum(r['native_numeric'] is None for r in rows),
  cohort_outputs=dict(Counter(r['cohort'] for r in rows)),reference_kinds=dict(Counter((r['reference_kind']) for r in rows)),models=[])
 for engine,name in NAMES.items():
  rs=[r for r in rows if r['engine']==engine];times=[r['runtime_seconds'] for r in rs if r['runtime_seconds'] is not None]
  item=dict(engine=engine,name=name,outputs=len(rs),median_recognition_seconds=statistics.median(times) if times else None,
   native_numeric_coverage=sum(r['native_numeric'] is not None for r in rs),truncated=sum(r['truncated'] for r in rs),development=[],fresh=[])
  for s in development['summaries']:
   if s['engine']!=engine:continue
   entry=dict(s)
   for method in ('numeric','selected_native'):
    pred=[p for p in development['predictions'] if p['engine']==engine and p['cohort']==s['cohort'] and p['target']==s['target'] and p['method']==method]
    entry[method]=dict(s[method],triage=triage(pred))
   item['development'].append(entry)
  for s in fresh['results']:
   if s['engine']!=engine:continue
   pred=[p for p in fresh['predictions'] if all(p[k]==s[k] for k in ('engine','target','method','training_cohort'))]
   eligible=[r for r in rs if r['cohort']=='fresh_public' and r.get(s['target']) is not None]
   item['fresh'].append(dict(s,triage=triage(pred),raw_numeric_ranking=ranking(eligible,'native_numeric',s['target'])))
  report['models'].append(item)
 failures=sorted([r for r in rows if r['engine'] in ('paddle_vl','glm','monkey','mineru_table') and r['native_numeric'] is not None and r['native_numeric']>=.99 and r['fact_f1'] is not None and r['fact_f1']<.9],key=lambda r:r['fact_f1'])
 report['high_confidence_association_failures']=[{k:r[k] for k in ('cohort','engine','table_id','native_numeric','fact_f1','grits_content_f1')} for r in failures]
 report['interpretation']=['Native probabilities can rank some errors; useful calibration must beat the training-mean baseline on other issuers.',
  'Only four fresh issuers; transfer results are provisional, with assistant-source-checked references.',
  'Strict financial facts and GriTS answer different questions. Inspect disagreements before treating scores as ground truth.',
  'Missing numeric output has no numeric confidence and remains in prediction evaluation via an explicit training-mean fallback.',
  'Tesseract confidence is a native heuristic score, not a probability. Text-only tasks lack comparable table-association output.']
 write(RESULTS/'report.json',report)
 print('Exported',report['outputs'],'outputs across',report['unique_crops'],'unique crops.')
if __name__=='__main__':main()
