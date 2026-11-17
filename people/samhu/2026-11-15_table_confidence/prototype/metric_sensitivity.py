"""Post-inspection scoring repair, with original frozen results preserved.

Reuses all emitted text/native probabilities. Applies the same corrected metric
on both sides. Fresh labels never fit a calibration map or choose a feature.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime,timezone
import statistics
from common import ROOT,RUN,RESULTS,read,write,sha,digest
import table_structure_v2 as metric
from numeric_accuracy import numbers,numeric_score
from calibration import fit_isotonic
from analyze import analyze,fresh_evaluation

OUT=RESULTS/'metric_v2'
DETAILS=RUN/'metric_v2'

def flatten(grids):
 result=[];counts=Counter()
 for index,grid in enumerate(grids):
  row_ids={}
  for fact in metric.facts(grid)['facts']:
   key=(tuple(fact['section']),fact['row_label']);row_key=(fact['row'],key)
   if row_key not in row_ids:counts[key]+=1;row_ids[row_key]=counts[key]
   result.append(dict(**fact,grid_index=index));result[-1]['row_occurrence']=row_ids[row_key]
 return result

def rescore(d):
 d=deepcopy(d);expected=flatten(d['reference_grids']);predicted=flatten(d['predicted_grids'])
 evidence={(f['grid_index'],f['row'],f['column']):f.get('confidence') for f in d['predicted_facts_detail']}
 for f in predicted:
  confidence=evidence.get((f['grid_index'],f['row'],f['column']))
  if confidence is not None:f['confidence']=confidence
 ref_values=[n for f in expected for n in numbers(f['raw'])]
 eligible=bool(expected);structured=d['structure_status']=='structured'
 required=d['engine'] in ('paddle_vl','glm','monkey','mineru_table')
 score=metric.fact_score(expected,predicted)
 d.update(reference_facts=len(expected),predicted_facts=len(predicted),financial_reference_eligible=eligible,
  fact_f1=score['f1'] if structured and eligible else 0. if required and eligible else None,
  fact_exact=score['exact'] if structured and eligible else False if required and eligible else None,
  numeric_data_f1=numeric_score(ref_values,[n for f in predicted for n in numbers(f['raw'])])['f1'] if structured and ref_values else 0. if required and eligible else None,
  financial_value_recall=numeric_score(ref_values,numbers(d['output_text']))['recall'] if ref_values else None)
 counts=Counter(metric.fact_key(f) for f in expected);cells=[]
 for f in predicted:
  key=metric.fact_key(f);correct=counts[key]>0
  if correct:counts[key]-=1
  cells.append(dict(**{k:v for k,v in f.items() if k!='key'},correct=correct))
 missing=[]
 for f in expected:
  key=metric.fact_key(f)
  if counts[key]>0:missing.append(f);counts[key]-=1
 d.update(expected_facts=expected,predicted_facts_detail=cells,missing_facts=missing,metric_version='v2_post_inspection_header_repair')
 return d

def main():
 original=read(RESULTS/'pairs.json');old_details=read(RUN/'evaluation_details.json')
 details=[rescore(d) for d in old_details]
 keys=set(original['pairs'][0]);pairs=[{k:d[k] for k in keys} for d in details]
 assert len(details)==len(original['pairs'])==686
 changes=[dict(cohort=b['cohort'],engine=b['engine'],table_id=b['table_id'],old=a['fact_f1'],new=b['fact_f1'],old_reference_facts=a['reference_facts'],new_reference_facts=b['reference_facts']) for a,b in zip(old_details,details) if a['fact_f1']!=b['fact_f1'] or a['reference_facts']!=b['reference_facts']]
 write(OUT/'pairs.json',dict(**{k:v for k,v in original.items() if k!='pairs'},pairs=pairs,metric_version='v2_post_inspection_header_repair'))
 write(DETAILS/'evaluation_details.json',details)
 frozen=read(RESULTS/'calibrators_frozen.json')
 # First assess the ORIGINAL pre-inspection forecasts against corrected truth.
 result,predictions=fresh_evaluation(pairs,frozen)
 write(OUT/'fresh_original_maps.json',dict(results=result,predictions=predictions,policy='Original forecasts unchanged; corrected metric labels after inspection. Sensitivity analysis, not an untouched end-to-end test.'))
 # Operational repair refits only development labels, keeping every original
 # selected feature and review threshold. No fresh-label selection is possible.
 revised=deepcopy(frozen);development=[r for r in pairs if r['cohort']!='fresh_public']
 for m in revised['models']:
  valid=[r for r in development if r['engine']==m['engine'] and r['table_id'] in m['training_examples'] and r[m['target']] is not None]
  assert len(valid)==m['training_rows']
  fitting=[r for r in valid if r[m['feature']] is not None]
  m['model']=fit_isotonic([r[m['feature']] for r in fitting],[r[m['target']] for r in fitting]);m['baseline']=statistics.mean(r[m['target']] for r in valid)
 revised.update(revised_utc=datetime.now(timezone.utc).isoformat(),fresh_outputs_inspected=True,metric_version='v2_post_inspection_header_repair',
  original_calibrators_sha256=sha(RESULTS/'calibrators_frozen.json'),metric_code_sha256=sha(ROOT/'prototype/table_structure_v2.py'),
  development_pairs_sha256=digest(development),source_pairs_file_sha256=sha(OUT/'pairs.json'),
  policy='Development labels rescored after fresh inspection. Features and cutoffs kept from original freeze. No fitting on fresh labels. Fresh results are post-inspection sensitivity, not untouched validation.')
 write(OUT/'calibrators_revised.json',revised)
 result,predictions=fresh_evaluation(pairs,revised)
 write(OUT/'fresh_validation.json',dict(results=result,predictions=predictions,policy=revised['policy']))
 summaries,predictions=analyze(development)
 write(OUT/'development_validation.json',dict(summaries=summaries,predictions=predictions,pairs_sha256=sha(OUT/'pairs.json'),caveats=[revised['policy']]))
 write(OUT/'audit.json',dict(status='pass',created_utc=revised['revised_utc'],changes=changes,original_pairs_sha256=sha(RESULTS/'pairs.json'),
  original_calibrators_sha256=sha(RESULTS/'calibrators_frozen.json'),original_metric_sha256=sha(ROOT/'prototype/table_structure.py'),corrected_metric_sha256=sha(ROOT/'prototype/table_structure_v2.py'),
  native_values_unchanged=all(all(a[k]==b[k] for k in keys if k.startswith('native_')) for a,b in zip(original['pairs'],pairs)),
  policy=revised['policy']))
 print('Scored',len(pairs),'outputs;',len(changes),'metric changes; original files preserved.',flush=True)

if __name__=='__main__':main()
