"""Evaluate the sealed round-two test without changing frozen maps."""
from datetime import datetime,timezone
from collections import Counter
import statistics,sys
from common import ROOT,RUN,RESULTS,read,write,sha,digest
import evaluate
import table_structure_v2 as metric
from header_evidence import header_features
from calibration_round2 import predict,metrics
from analyze import ranking

OUT=RESULTS/'round2'

def main():
 seal=read(OUT/'test_seal.json');frozen=read(OUT/'calibrators_frozen.json');root=RUN/'confirmatory'
 for name,h in frozen['code_sha256'].items():assert sha(ROOT/'prototype'/name)==h,name
 assert seal['evaluator_sha256']==sha(ROOT/'prototype/evaluate_confirmatory.py')
 assert seal['references_sha256']==sha(root/'references.json')
 assert seal['tables_sha256']==sha(root/'tables.json')
 assert read(root/'prototype_batch.json')['status']=='completed'
 assert not set(seal['test_issuers']).intersection(seal['development_issuers'])
 if not (OUT/'first_inspection.json').exists():write(OUT/'first_inspection.json',dict(utc=datetime.now(timezone.utc).isoformat(),frozen_sha256=sha(OUT/'calibrators_frozen.json'),test_seal_sha256=sha(OUT/'test_seal.json')))
 # Reuse the evaluator, routing every output away from preserved round one.
 evaluate.reference_sets=lambda:iter([('confirmatory',root,read(root/'references.json'))])
 evaluate.facts=metric.facts;evaluate.fact_key=metric.fact_key;evaluate.fact_score=metric.fact_score
 evaluate.RESULTS=OUT
 def route(path,data):
  if path==OUT/'pairs.json':path=OUT/'test_pairs.json'
  if path==RUN/'evaluation_details.json':path=RUN/'confirmatory_evaluation_details.json'
  write(path,data)
 evaluate.write=route;sys.argv=[sys.argv[0]];evaluate.main()
 data=read(OUT/'test_pairs.json');details=read(RUN/'confirmatory_evaluation_details.json');rows=[]
 for row,d in zip(data['pairs'],details):
  evidence=read(RUN/'evidence/confirmatory'/row['engine']/(row['table_id']+'.json'))
  rows.append(dict(**row,**header_features(d['output_text'],row['engine'],dict(units=evidence['aligned_units']))))
 data.update(pairs=rows,metric_version='v2',round=2)
 write(OUT/'test_pairs.json',data)
 results=[];all_predictions=[]
 for m in frozen['models']:
  rs=[r for r in rows if r['engine']==m['engine'] and r['fact_f1'] is not None]
  pred=[dict(table_id=r['table_id'],issuer=r['issuer'],truth=r['fact_f1'],prediction=predict(m['model'],r[m['feature']]) if r.get(m['feature']) is not None else m['baseline'],baseline=m['baseline'],native=r.get(m['feature']),selected_feature=m['feature'],missing_selected_confidence=r.get(m['feature']) is None,review=r.get(m['feature']) is None or r[m['feature']]<=m['review_cutoff']) for r in rs]
  bad=[r for r in pred if r['truth']<.95];reviewed=[r for r in pred if r['review']];caught=[r for r in bad if r['review']]
  results.append(dict(engine=m['engine'],method=m['method'],feature=m['feature'],**metrics(pred),ranking=ranking(rs,'native_numeric','fact_f1'),
   triage=dict(reviewed=len(reviewed),total=len(pred),errors=len(bad),caught=len(caught),error_capture=len(caught)/len(bad) if bad else None)))
  all_predictions.extend(dict(engine=m['engine'],method=m['method'],**p) for p in pred)
 write(OUT/'test_validation.json',dict(summaries=results,predictions=all_predictions,calibrators_sha256=sha(OUT/'calibrators_frozen.json'),seal_sha256=sha(OUT/'test_seal.json')))
 expected=len(read(root/'tables.json')['tables'])*7
 assert len(rows)==expected and not data['pending']
 assert all(r['inference_status']=='success' for r in rows)
 assert all(r['native_status']=='available' for r in rows)
 for tid in {r['table_id'] for r in rows}:
  assert {r['engine'] for r in rows if r['table_id']==tid}=={'paddle','tesseract','glm','paddle_vl','monkey','mineru','mineru_table'}
  assert len({r['image_sha256'] for r in rows if r['table_id']==tid})==1
 write(OUT/'test_audit.json',dict(status='pass',outputs=len(rows),unique_crops=len(rows)//7,issuers=len(seal['test_issuers']),issuer_overlap=[],
  metric_frozen_before_inference=True,all_native_units_aligned=True,source_refs_unchanged=True,
  missing_numeric_scores=sum(r['native_numeric'] is None for r in rows),truncated=[dict(engine=r['engine'],table_id=r['table_id']) for r in rows if r['truncated']],
  caveats=['Public benchmark pretraining overlap unknown.','Source annotations are public dataset labels, not human-approved references.','One crop per issuer; small sample.']))
 for r in results:
  if r['method']=='header_selected':print(r['engine'],'mean',round(r['ranking']['mean_accuracy'],3),'MAE',round(r['mae'],3),'baseline',round(r['baseline_mae'],3),'MSE gain',round(r['mse_gain'],4),'CI',r['mse_gain_issuer_bootstrap_95'],flush=True)

if __name__=='__main__':main()
