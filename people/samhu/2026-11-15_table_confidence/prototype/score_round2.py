"""Reference-free native confidence with the sealed round-two quality map."""
import argparse
from pathlib import Path
from common import ROOT,RESULTS,read,write,sha
from native_evidence import features
from header_evidence import header_features
from calibration_round2 import predict
from score import score_record as legacy_score,FEATURE_PATHS


def score_record(record,engine,frozen):
 result=legacy_score(record,engine,{})
 base,alignment=features(record,engine)
 values={key:base[group][stat] for key,(group,stat) in FEATURE_PATHS.items()}
 values.update(header_features(record.get('text',''),engine,alignment))
 result['native'].update(values)
 m=next((m for m in frozen.get('models',[]) if m['engine']==engine and m['method']=='header_selected'),None)
 if not m:
  result.update(quality_estimates=[],calibration_status='No round-two association model for this text-only configuration')
  return result
 value=values.get(m['feature']);missing=value is None
 estimate=predict(m['model'],value) if not missing else m['baseline']
 low=missing or value<=m['review_cutoff']
 result.update(quality_estimates=[dict(target='fact_f1',expected_score=estimate,feature=m['feature'],native_feature_value=value,
  training_mean_baseline=m['baseline'],training_tables=m['training_rows'],training_issuers=len(m['training_issuers']),missing_feature_baseline_fallback=missing,
  outside_training_confidence_range=not missing and not m['model'][0]['low']<=value<=m['model'][-1]['high'],low_native_review_flag=low,
  note='Expected row-column-value F1, not the probability that the whole table is correct.')],
  review_priority='high' if low or result['operational_flags'] else 'not_flagged',
  review_basis=result['operational_flags']+(['training_native_cutoff'] if low else []),
  calibration_frozen_utc=frozen['frozen_utc'],metric_version='v2',calibration_version='round2',
  calibration_status='Experimental; inspect validation evidence before using estimates for decisions')
 return result

def load_frozen():
 frozen=read(RESULTS/'round2/calibrators_frozen.json')
 for name,h in frozen['code_sha256'].items():
  if sha(ROOT/'prototype'/name)!=h:raise RuntimeError('Implementation differs from sealed calibration: '+name)
 return frozen

def main():
 p=argparse.ArgumentParser();p.add_argument('--engine',required=True,choices=['paddle_vl','glm','monkey','mineru_table']);p.add_argument('--record',required=True,type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
 result=score_record(read(a.record),a.engine,load_frozen())
 if a.output:write(a.output,result)
 else:print(__import__('json').dumps(result,indent=2,allow_nan=False))
if __name__=='__main__':main()
