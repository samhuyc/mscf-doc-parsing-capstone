import math
import unittest
from collections import defaultdict, deque

import numpy as np
from score_probes import stable_logsoftmax, ctc_character_evidence, attach_characters


class ProbeTests(unittest.TestCase):
    def test_small_tail_survives_before_normalization(self):
        values = np.array([100, 80, 79], dtype=np.float32)
        actual = stable_logsoftmax(values, np)
        expected = -math.log1p(math.exp(-20)+math.exp(-21))
        self.assertLess(actual[0], 0)
        self.assertAlmostEqual(float(actual[0])/expected, 1, places=6)
        self.assertLess(math.exp(float(actual[0])), 1)

    def test_ties_are_not_deleted(self):
        actual = stable_logsoftmax(np.array([1000,1000,1000]), np)
        np.testing.assert_allclose(np.exp(actual), [1/3]*3, atol=1e-7)

    def test_shift_invariance_and_float64_reference(self):
        values = np.array([12,10,-3,1], dtype=np.float32)
        actual = stable_logsoftmax(values, np)
        expected = values.astype(np.float64)-np.log(np.exp(values.astype(np.float64)).sum())
        np.testing.assert_allclose(actual, expected, atol=2e-6)
        np.testing.assert_allclose(stable_logsoftmax(values+1000, np), actual, atol=2e-6)

    def test_ctc_repeated_letter_separated_by_blank_is_preserved(self):
        # CTC path A,A,blank,A,B collapses to AAB, not AB.
        scores = np.array([[[.1,.8,.1],[.05,.9,.05],[.8,.1,.1],
                            [.15,.7,.15],[.2,.2,.6]]])
        row = ctc_character_evidence(scores, ['blank','A','B'])[0]
        self.assertEqual(row['text'], 'AAB')
        self.assertEqual([u['timestep'] for u in row['characters']], [0,3,4])
        self.assertEqual([u['score'] for u in row['characters']], [.8,.7,.6])

    def test_alignment_restores_crop_order(self):
        evidence=defaultdict(deque)
        evidence[('B',.6)].append({'characters':[{'text':'B'}], 'distribution_sum_max_error':0})
        evidence[('A',.8)].append({'characters':[{'text':'A'}], 'distribution_sum_max_error':0})
        units=attach_characters([{'text':'A','score':.8},{'text':'B','score':.6}], evidence)
        self.assertEqual([(u['text'],u['line_index']) for u in units], [('A',0),('B',1)])

    def test_unmatched_score_is_rejected(self):
        with self.assertRaises(ValueError):
            attach_characters([{'text':'a','score':.8}], defaultdict(deque))

    def test_logits_are_not_mislabeled_probabilities(self):
        with self.assertRaises(ValueError):
            ctc_character_evidence(np.array([[[3.,-1.,0.]]]), ['blank','A','B'])

    def test_full_page_metric_penalizes_repetition_and_omission(self):
        from evaluate_pages import page_metrics
        self.assertEqual(page_metrics('hello world','hello world')['cer'],0)
        self.assertGreater(page_metrics('hello world','hello world '*20)['cer'],1)
        self.assertEqual(page_metrics('hello world','')['character_accuracy_proxy'],0)
        with self.assertRaises(ValueError):page_metrics('','anything')

    def test_space_character_score_is_not_silently_dropped(self):
        from core import summarize
        units=[{'text':'a','score':1.,'unit_kind':'character'},
               {'text':' ','score':.5,'unit_kind':'character'}]
        self.assertEqual(summarize(units)['mean'],.75)


if __name__ == '__main__':
    unittest.main()
