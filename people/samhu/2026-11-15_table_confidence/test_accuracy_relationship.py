import unittest
from evaluate_table_accuracy import ranks,spearman,error_auc,summarize,matched_cohort,LABELS


class TestAssociation(unittest.TestCase):
    def test_matched_cohort_checks_identity_not_just_count(self):
        rows=[dict(engine=e,table_id=t,primary_eligible=True,confidence=.9)
              for e in LABELS for t in ('a','b')]
        self.assertTrue(matched_cohort(rows,['a','b'])['complete'])
        rows[-1]['table_id']='c'
        self.assertFalse(matched_cohort(rows,['a','b'])['complete'])

    def test_missing_score_cannot_pass_complete_cohort(self):
        rows=[dict(engine=e,table_id='a',primary_eligible=True,confidence=.9) for e in LABELS]
        rows[-1]['confidence']=None
        self.assertFalse(matched_cohort(rows,['a'])['complete'])

    def test_ties_receive_average_rank(self):
        self.assertEqual(ranks([2,1,2]),[1.5,0,1.5])

    def test_direction_and_constant_outcome(self):
        self.assertAlmostEqual(spearman([1,2,3],[1,2,3]),1)
        self.assertAlmostEqual(spearman([1,2,3],[3,2,1]),-1)
        self.assertIsNone(spearman([1,2,3],[1,1,1]))

    def test_auc_uses_low_confidence_to_rank_errors(self):
        self.assertEqual(error_auc([.1,.9],[False,True]),1)
        self.assertEqual(error_auc([.9,.1],[False,True]),0)
        self.assertEqual(error_auc([.5,.5],[False,True]),.5)
        self.assertIsNone(error_auc([.5,.6],[True,True]))

    def test_tied_rejection_is_not_arbitrary(self):
        rows=[dict(primary_eligible=True,confidence=c,issuer='a',numeric=dict(f1=y,exact=y==1),financial_values=dict(recall=y)) for c,y in [(0,.5),(0,.6),(.9,1),(.95,1),(.99,1)]]
        s=summarize(rows,bootstrap=0)
        self.assertEqual(s['rejection_20_percent']['retained'],3)
        self.assertEqual(s['rejection_20_percent']['retained_mean_numeric_error'],0)


if __name__=='__main__':unittest.main()
