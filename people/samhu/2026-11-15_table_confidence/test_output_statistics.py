import unittest
from output_statistics import summarize_outputs
from regions import table_summary


class TestStatistics(unittest.TestCase):
    def record(self, values, text='x'):
        units=[dict(text='x', score=v) for v in values]
        return dict(status='success', confidence=table_summary(units), text=text, seconds=2)

    def test_pending_is_not_empty_or_zero(self):
        s=summarize_outputs([self.record([.9]),dict(status='pending'),dict(status='failed')],4)
        self.assertEqual((s['completed'],s['failed'],s['pending'],s['empty_text']),(1,1,2,0))
        self.assertAlmostEqual(s['median_table_confidence'],.9)

    def test_zero_score_is_not_missing(self):
        s=summarize_outputs([self.record([0,.9]),self.record([],'')],2)
        self.assertEqual(s['zero_geometric_mean_tables'],1)
        self.assertEqual(s['scored_tables'],1)
        self.assertEqual(s['empty_text'],1)
        self.assertEqual(s['median_table_confidence'],0)

    def test_median_weights_tables_equally(self):
        s=summarize_outputs([self.record([.5]),self.record([1]*100)],2)
        self.assertEqual(s['median_table_confidence'],.75)


if __name__=='__main__':
    unittest.main()
