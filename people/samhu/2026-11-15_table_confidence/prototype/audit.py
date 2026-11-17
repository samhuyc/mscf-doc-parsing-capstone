"""Final coverage, provenance and native-evidence checks (no silent exclusions)."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import math
from common import ROOT,OLD,RUN,RESULTS,read,write,sha
from evaluate import reference_sets
from extract_evidence import outputs

def main():
 p=argparse.ArgumentParser();p.add_argument('--development-only',action='store_true');a=p.parse_args()
 if not a.development_only and not (RESULTS/'calibrators_frozen.json').exists():raise RuntimeError('Freeze calibration before reading fresh output evidence')
 snapshot=read(RUN/'human_review_snapshot.json');human=OLD/'review/financial_ground_truth.json'
 # Snapshot schema is recorded rather than inferred.
 saved=snapshot.get('sha256',snapshot.get('human_review_sha256'))
 errors=[];coverage=[];identities={};equivalence=[];truncated=[];no_numbers=[]
 for cohort,root,refs in reference_sets():
  if cohort=='fresh_public' and a.development_only:continue
  engines=('mineru_table',) if cohort=='sponsor_table_mode' else ('paddle','tesseract','paddle_vl','glm','monkey','mineru')+(('mineru_table',) if cohort in ('benchmark','fresh_public') else ())
  for table in read(root/'tables.json')['tables']:
   tid=table['table_id']
   if tid not in refs:continue
   if sha(root/table['image'])!=table['image_sha256']:errors.append(f'{cohort}/{tid}: image hash mismatch')
   if table['image_sha256']!=refs[tid]['image_sha256']:errors.append(f'{cohort}/{tid}: reference image mismatch')
   identities[cohort,tid]=table['image_sha256']
   existing={e:(record,identity) for e,record,identity in outputs(root,table)}
   for engine in engines:
    if engine not in existing:
     coverage.append(dict(cohort=cohort,engine=engine,table_id=tid,status='missing'));continue
    record,identity=existing[engine];coverage.append(dict(cohort=cohort,engine=engine,table_id=tid,status=record['status']))
    if record.get('image_sha256',table['image_sha256'])!=table['image_sha256']:errors.append(f'{cohort}/{tid}/{engine}: output image mismatch')
    units=record.get('confidence_units',[])
    if record['status']=='success' and record.get('text','').strip() and not units:errors.append(f'{cohort}/{tid}/{engine}: text without native evidence')
    if any(not isinstance(u.get('score'),(int,float)) or not math.isfinite(u['score']) or not 0<=u['score']<=1 for u in units):errors.append(f'{cohort}/{tid}/{engine}: invalid native score')
    evidence_path=RUN/'evidence'/root.name/engine/(tid+'.json')
    expected=dict(**identity,code_sha256=sha(ROOT/'prototype/native_evidence.py'),image_sha256=table['image_sha256'])
    if record['status']=='success':
     if not evidence_path.exists():errors.append(f'{cohort}/{tid}/{engine}: no aligned evidence')
     else:
      evidence=read(evidence_path)
      if evidence.get('status')!='success' or evidence.get('provenance')!=expected:errors.append(f'{cohort}/{tid}/{engine}: failed or stale aligned evidence')
      else:
       if evidence['features']['numeric_tokens']['n']==0:no_numbers.append(dict(cohort=cohort,engine=engine,table_id=tid,reason='No emitted numeric tokens; native score is undefined, accuracy remains included.'))
       if len(evidence['aligned_units'])!=len(units):errors.append(f'{cohort}/{tid}/{engine}: lost native units')
    if record.get('hook_equivalence_passed'):equivalence.append(dict(cohort=cohort,engine=engine,table_id=tid))
    if record.get('truncated'):truncated.append(dict(cohort=cohort,engine=engine,table_id=tid))
 for (cohort,tid),image in identities.items():
  if cohort=='sponsor_table_mode':
   source=identities.get(('sponsor_development',tid),identities.get(('repairs',tid)))
   if source!=image:errors.append(f'{tid}: MinerU table-mode pixels differ')
 if not a.development_only:
  frozen=read(RESULTS/'calibrators_frozen.json')
  for name,expected in frozen['code_sha256'].items():
   if sha(ROOT/'prototype'/name)!=expected:errors.append(f'Frozen code changed: {name}')
  fresh_reference_freeze=read(RUN/'fresh_holdout_reference_freeze.json')
  if sha(RUN/'fresh_public/references.json')!=fresh_reference_freeze['references_sha256']:errors.append('Fresh reference labels changed after source freeze')
 unchanged=saved==sha(human)
 if not unchanged:errors.append('Human review snapshot mismatch; inspect schema and changes')
 result=dict(created_utc=datetime.now(timezone.utc).isoformat(),status='pass' if not errors and all(r['status']=='success' for r in coverage) else 'incomplete_or_failed',
  mode='development_only' if a.development_only else 'all',expected_outputs=len(coverage),successful_outputs=sum(r['status']=='success' for r in coverage),
  coverage_counts={str(k):v for k,v in Counter((r['cohort'],r['engine'],r['status']) for r in coverage).items()},
  unique_input_images=len(set(identities.values())),human_reviews_unchanged=unchanged,human_review_sha256=sha(human),
  native_feature_code_sha256=sha(ROOT/'prototype/native_evidence.py'),control_equivalence_records=equivalence,truncated_outputs=truncated,outputs_without_emitted_numbers=no_numbers,errors=errors,
  missing_or_failed=[r for r in coverage if r['status']!='success'])
 write(RESULTS/('development_audit.json' if a.development_only else 'final_audit.json'),result)
 print({k:result[k] for k in ('status','expected_outputs','successful_outputs','unique_input_images','human_reviews_unchanged','errors')})
if __name__=='__main__':main()
