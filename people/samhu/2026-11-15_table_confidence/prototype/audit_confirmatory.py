"""Independent integrity checks and disclosed post-test measurement audit."""
from datetime import datetime,timezone
from common import ROOT,OLD,RUN,RESULTS,read,write,sha
from extract_evidence import outputs
from calibration_round2 import metrics

OUT=RESULTS/'round2'
ISSUES={
 'fintabnet_test_02146':dict(kind='reference_and_scorer_defect',reason='Source image contains “in millions of dollars, except ratios”; benchmark reference omits this caption. Frozen scorer also misclassifies the model caption/year row as body data. Financial F1 is not interpretable for this case.',source_checked=True),
 'fintabnet_test_09879':dict(kind='header_interpretation_defect',reason='Frozen scorer treats the 2014/2013 row beside “Foreign exchange” as body values. Year associations are not fully assessed; visible GLM section-label errors are nevertheless real.',source_checked=True)
}

def main():
 root=RUN/'confirmatory';errors=[];total=0
 for table in read(root/'tables.json')['tables']:
  assert sha(root/table['image'])==table['image_sha256']
  for engine,record,identity in outputs(root,table):
   total+=1
   if record.get('image_sha256')!=table['image_sha256']:errors.append((engine,table['table_id'],'input mismatch'))
   evidence=read(RUN/'evidence/confirmatory'/engine/(table['table_id']+'.json'))
   if len(evidence['aligned_units'])!=len(record.get('confidence_units',[])):errors.append((engine,table['table_id'],'unit count'))
   if [u['score'] for u in evidence['aligned_units']]!=[u['score'] for u in record.get('confidence_units',[])]:errors.append((engine,table['table_id'],'probabilities changed'))
 assert total==77 and not errors,errors
 human=sha(OLD/'review/financial_ground_truth.json');assert human=='6414f57c45d29453f60120669aa14905ef9a2dede67b4f60299a67141f3ccada'
 validation=read(OUT/'test_validation.json');sensitivity=[]
 for s in validation['summaries']:
  rs=[r for r in validation['predictions'] if r['engine']==s['engine'] and r['method']==s['method'] and r['table_id'] not in ISSUES]
  sensitivity.append(dict(engine=s['engine'],method=s['method'],**metrics(rs)))
 write(OUT/'measurement_audit.json',dict(utc=datetime.now(timezone.utc).isoformat(),status='integrity_pass_with_measurement_limitations',outputs=total,
  identical_model_inputs=True,native_probabilities_unchanged=True,human_reviews_unchanged=True,issues=ISSUES,
  policy='Original sealed 11-table results remain untouched. This is a post-inspection exclusion sensitivity across all models, with the same frozen forecasts and cutoffs; not a new untouched test.',
  sensitivity=sensitivity))
 for s in sensitivity:
  if s['method']=='header_selected':print(s['engine'],'n',s['n'],'gain',round(s['mse_gain'],4),'CI',s['mse_gain_issuer_bootstrap_95'])

if __name__=='__main__':main()
