"""Freeze round-two native-only maps before new-issuer test inference."""
from collections import Counter
from datetime import datetime,timezone
import math,statistics
from common import ROOT,RUN,RESULTS,read,write,sha,digest
from header_evidence import header_features
import calibration_round2 as cal
from analyze import ranking

OUT=RESULTS/'round2'
CODE=('table_structure_v2.py','header_evidence.py','calibration_round2.py','train_round2.py','native_evidence.py')

def augment(row,detail):
 evidence=read(RUN/'evidence'/('sponsor_all' if row['cohort']=='sponsor_development' else row['cohort'])/row['engine']/(row['table_id']+'.json'))
 f=header_features(detail['output_text'],row['engine'],dict(units=evidence['aligned_units']))
 return dict(**row,**f)

def main():
 if (OUT/'calibrators_frozen.json').exists():raise RuntimeError('Round-two freeze already exists')
 data=read(RESULTS/'metric_v2/pairs.json');details=read(RUN/'metric_v2/evaluation_details.json')
 rows=[augment(r,d) for r,d in zip(data['pairs'],details) if r['financial_reference_eligible'] and r['engine'] in ('paddle_vl','glm','monkey','mineru_table')]
 assert len(rows)==376
 summaries=[];predictions=[];models=[]
 original=cal.FEATURES[:8];expanded=cal.FEATURES
 for engine in ('paddle_vl','glm','monkey','mineru_table'):
  rs=[r for r in rows if r['engine']==engine]
  for method,features,select in [('numeric',original,False),('original_selected',original,True),('header_selected',expanded,True)]:
   cal.FEATURES=features
   pred=cal.outer_predictions(rs,select=select)
   summaries.append(dict(engine=engine,method=method,**cal.metrics(pred),raw_numeric_ranking=ranking(rs,'native_numeric','fact_f1')))
   predictions.extend(dict(engine=engine,method=method,**p) for p in pred)
   feature,losses=cal.choose_feature(rs,'fact_f1') if select else ('native_numeric',{})
   fitting=[r for r in rs if r.get(feature) is not None];xs=[r[feature] for r in fitting]
   models.append(dict(engine=engine,method=method,feature=feature,target='fact_f1',model=cal.fit_isotonic(xs,[r['fact_f1'] for r in fitting]),baseline=statistics.mean(r['fact_f1'] for r in rs),
    training_rows=len(rs),training_issuers=sorted({r['issuer'] for r in rs}),training_examples=[r['table_id'] for r in rs],
    review_cutoff=sorted(xs)[max(0,math.ceil(.2*len(xs))-1)],feature_cv_losses=losses))
   print(engine,method,feature,'gain',round(summaries[-1]['mse_gain'],5),flush=True)
 cal.FEATURES=expanded
 write(OUT/'development_pairs.json',dict(pairs=rows))
 write(OUT/'development_validation.json',dict(summaries=summaries,predictions=predictions))
 write(OUT/'calibrators_frozen.json',dict(frozen_utc=datetime.now(timezone.utc).isoformat(),test_outputs_inspected=False,
  code_sha256={n:sha(ROOT/'prototype'/n) for n in CODE},models=models,training_pairs_sha256=digest(rows),
  test_policy='Confirmatory40: one new issuer each, excluded every development issuer, no fitting or selection on test labels.',
  metric_version='v2',source_sensitivity_audit_sha256=sha(RESULTS/'metric_v2/audit.json'),protocol_sha256=sha(ROOT/'prototype/protocol_round2.json')))
 print('Frozen round two.',flush=True)

if __name__=='__main__':main()
