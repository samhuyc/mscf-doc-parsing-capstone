import unittest
from copy import deepcopy
from unittest.mock import patch
import calibration_round2 as cal
from score_round2 import score_record

class TestRound2(unittest.TestCase):
 def rows(self):
  return [dict(table_id=str(i),issuer=str(i//2),fact_f1=(i%4)/3,native_numeric=.6+i/100,native_header=.5+i/30) for i in range(12)]
 def test_heldout_labels_cannot_change_selection(self):
  rows=self.rows();a=cal.outer_predictions(rows,select=True);changed=deepcopy(rows)
  for r in changed:
   if r['issuer']=='0':r['fact_f1']=1-r['fact_f1']
  b=cal.outer_predictions(changed,select=True)
  self.assertEqual([(r['prediction'],r['selected_feature']) for r in a if r['issuer']=='0'],[(r['prediction'],r['selected_feature']) for r in b if r['issuer']=='0'])
 def test_missing_header_remains_in_evaluation(self):
  rows=self.rows();rows[0]['native_header']=None
  a=cal.outer_predictions(rows,feature='native_header');self.assertEqual(len(a),len(rows))
  self.assertEqual(a[0]['prediction'],a[0]['baseline']);self.assertTrue(a[0]['review'])
 def test_scorer_never_approves_or_uses_reference(self):
  record=dict(status='success',text='100',confidence_units=[dict(text='100',score=.99)])
  # Tesseract alignment avoids loading a tokenizer; the calibration is synthetic.
  m=dict(engine='tesseract',method='header_selected',feature='native_numeric',baseline=.5,training_rows=10,training_issuers=['a','b'],review_cutoff=.8,model=[dict(low=.8,high=1,prediction=.75)])
  r=score_record(record,'tesseract',dict(models=[m],frozen_utc='test'))
  self.assertEqual(r['quality_estimates'][0]['expected_score'],.75)
  self.assertEqual(r['native']['native_numeric'],.99);self.assertFalse(r['automatic_approval']);self.assertIsNone(r['native']['probability_table_correct'])
if __name__=='__main__':unittest.main()
