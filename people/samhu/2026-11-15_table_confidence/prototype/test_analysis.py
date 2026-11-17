import unittest
from analyze import ranking,fresh_evaluation

class TestAnalysis(unittest.TestCase):
 def test_error_auc_direction(self):
  rows=[dict(issuer=str(i),native_numeric=x,fact_f1=y) for i,(x,y) in enumerate([(.1,0),(.2,.5),(.8,1),(.9,1)])]
  self.assertEqual(ranking(rows,'native_numeric','fact_f1')['error_auc_below_95'],1)
 def test_fresh_issuer_overlap_rejected(self):
  row=dict(cohort='fresh_public',engine='glm',issuer='a',table_id='a1',fact_f1=1,native_numeric=.9)
  m=dict(engine='glm',target='fact_f1',feature='native_numeric',training_issuers=['a'])
  with self.assertRaises(AssertionError):fresh_evaluation([row],dict(models=[m]))
if __name__=='__main__':unittest.main()
