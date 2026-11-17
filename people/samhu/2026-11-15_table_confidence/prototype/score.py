"""Reference-free native confidence and frozen expected-quality estimates.

Input is one saved recognizer output, including its original confidence units.
No ground-truth table or other recognizer is read by this scoring interface.
"""
import argparse
from pathlib import Path
from common import ROOT,RESULTS,read,write,sha
from native_evidence import features
from calibration import predict
from table_structure import parse_output

FEATURE_PATHS={'native_numeric':('numeric_tokens','geometric_mean'),'native_all':('all_tokens','geometric_mean'),
 'native_numeric_p10':('numeric_tokens','p10'),'native_number_p10':('numeric_cells','p10'),
 'native_structure':('structure_tokens','geometric_mean'),'native_structure_p10':('structure_tokens','p10'),'native_visible':('visible_tokens','geometric_mean'),'native_visible_p10':('visible_tokens','p10')}

def estimate_quality(feature_values,engine,frozen):
 estimates=[]
 for model in frozen.get('models',[]):
  if model['engine']!=engine or model['training_cohort']!='development' or model['method']!='selected_native':continue
  if model['target']=='financial_value_recall' and engine in ('paddle_vl','glm','monkey','mineru_table'):continue
  value=feature_values[model['feature']]
  out_of_range=value is not None and not model['model'][0]['low']<=value<=model['model'][-1]['high']
  estimates.append(dict(target=model['target'],expected_score=predict(model['model'],value) if value is not None else model['baseline'],
    feature=model['feature'],native_feature_value=value,training_mean_baseline=model['baseline'],
    training_tables=model['training_rows'],training_issuers=len(model['training_issuers']),
    missing_feature_baseline_fallback=value is None,outside_training_confidence_range=out_of_range,
    low_native_review_flag=value is None or value<=model['review_cutoff'],
    note='Expected metric score from frozen development calibration; not probability that the entire table is correct.'))
 return estimates

def score_record(record,engine,frozen):
 feature,alignment=features(record,engine)
 values={key:feature[group][stat] for key,(group,stat) in FEATURE_PATHS.items()}
 flags=[]
 if values['native_numeric'] is None:flags.append('no_emitted_numeric_confidence')
 if record.get('status')!='success':flags.append('recognizer_failed')
 if record.get('truncated'):flags.append('token_limit_reached')
 if record.get('repetition_flag'):flags.append('repeated_output')
 if not record.get('text','').strip():flags.append('empty_output')
 try:structure=parse_output(record.get('text',''),engine)['status']
 except Exception:structure='invalid_structure'
 if engine in ('paddle_vl','glm','monkey','mineru_table') and structure!='structured':flags.append('missing_or_invalid_table_structure')
 estimates=estimate_quality(values,engine,frozen)
 primary=next((m for m in estimates if m['target']=='fact_f1'),next((m for m in estimates if m['target']=='financial_value_recall'),None))
 low_native=bool(primary and primary['low_native_review_flag'])
 return dict(engine=engine,table_id=record.get('table_id'),image_sha256=record.get('image_sha256'),
  native=dict(**values,numeric_tokens=feature['numeric_tokens']['n'],
    kind='native_word_score_divided_by_100' if engine=='tesseract' else 'native_ctc_selected_path_character_probability' if engine=='paddle' else 'native_emitted_token_probability',
    probability_table_correct=None),quality_estimates=estimates,
  structural_status=structure,operational_flags=flags,
  review_priority='high' if flags or low_native else 'routine',review_basis=flags+(['training_native_cutoff'] if low_native else []),
  automatic_approval=False,calibration_frozen_utc=frozen.get('frozen_utc'),
  limitations=['Omitted content has no emitted-token confidence.','Calibration may not transfer to new layouts, scans or model revisions.','Operational flags are separate from native probability.'])

def main():
 p=argparse.ArgumentParser();p.add_argument('--engine',required=True,choices=['paddle','tesseract','paddle_vl','glm','monkey','mineru','mineru_table']);p.add_argument('--record',required=True,type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
 frozen_path=RESULTS/'calibrators_frozen.json'
 frozen=read(frozen_path) if frozen_path.exists() else {}
 if frozen and frozen['code_sha256']['native_evidence.py']!=sha(ROOT/'prototype/native_evidence.py'):raise RuntimeError('Native feature implementation differs from frozen calibration')
 result=score_record(read(a.record),a.engine,frozen)
 if a.output:write(a.output,result)
 else:print(__import__('json').dumps(result,indent=2,allow_nan=False))
if __name__=='__main__':main()
