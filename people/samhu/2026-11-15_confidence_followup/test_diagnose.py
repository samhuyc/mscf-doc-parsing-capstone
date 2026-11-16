import unittest
from diagnose import correlation, family, risk, selection


def row(confidence, accuracy=1, errors=0, reference=10):
    return {'confidence': {'mean': confidence, 'fraction_below_0_90': confidence},
            'character_accuracy_proxy': accuracy, 'edit_errors': errors,
            'reference_characters': reference, 'truncated': False}


class DiagnosticsTests(unittest.TestCase):
    def test_ties_are_not_broken_using_answers(self):
        rows = [row(.9, .1), row(.9, 1), row(.1, .5)]
        self.assertEqual(selection(rows, 'mean', .5)['pages'], 2)
        self.assertEqual(selection(rows, 'mean', .2)['pages'], 2)
        self.assertEqual(selection(rows, 'mean', .5), selection(list(reversed(rows)), 'mean', .5))

    def test_missing_scores_remain_missing(self):
        result = selection([row(None), row(.9)], 'mean', 1)
        self.assertEqual(result['missing_scores'], 1)
        self.assertEqual(result['actual_coverage'], .5)
        self.assertEqual(selection([row(None)], 'mean', .5)['pages'], 0)

    def test_lower_bad_fraction_ranks_higher(self):
        rows = [row(.1, 1), row(.2, .7), row(.3, .2)]
        self.assertAlmostEqual(correlation(rows, 'fraction_below_0_90')['spearman'], 1)

    def test_constant_correctness_is_undefined(self):
        self.assertIsNone(correlation([row(.1), row(.2), row(.3)], 'mean')['spearman'])

    def test_repetition_cer_is_not_capped(self):
        result = risk([row(.99, 0, 70, 10)])
        self.assertEqual(result['micro_cer'], 7)
        self.assertEqual(result['mean_page_error_proxy'], 1)

    def test_related_documents_share_family(self):
        self.assertEqual(family('rolls_royce_2026h1_release'), family('rolls_royce_2026h1_presentation'))
        self.assertNotEqual(family('edf_2024'), family('cvs_2025q2'))


if __name__ == '__main__':
    unittest.main()
