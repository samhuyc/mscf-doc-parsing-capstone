import unittest
from score import score_record,estimate_quality

class TestScoring(unittest.TestCase):
 def record(self):return dict(status='success',text='100',confidence_units=[dict(text='100',score=.99)],truncated=True)
 def test_high_native_does_not_override_truncation_or_approve(self):
  r=score_record(self.record(),'tesseract',{})
  self.assertEqual(r['native']['native_numeric'],.99);self.assertEqual(r['review_priority'],'high')
  self.assertFalse(r['automatic_approval']);self.assertIsNone(r['native']['probability_table_correct'])
  self.assertIn('token_limit_reached',r['operational_flags'])
 def test_missing_selected_score_is_explicit_baseline(self):
  model=dict(engine='glm',training_cohort='development',method='selected_native',target='fact_f1',feature='native_structure',
    model=[dict(low=.7,high=.9,prediction=.8)],baseline=.6,training_rows=10,training_issuers=['a','b'],review_cutoff=.7)
  r=estimate_quality({'native_structure':None},'glm',{'models':[model]})[0]
  self.assertEqual(r['expected_score'],.6);self.assertTrue(r['missing_feature_baseline_fallback']);self.assertTrue(r['low_native_review_flag'])
if __name__=='__main__':unittest.main()
