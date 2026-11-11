"""Checks for label leakage, sign/context sensitivity and failure handling."""
import copy
import unittest

from build_demo import ROOT, fit, predictions, read, single_number, table_grid


class ConfidenceTests(unittest.TestCase):
    def setUp(self):
        self.cfg = read(ROOT/'protocol.json')['documents'][0]
        self.primary = read(ROOT/'assets/cvs_2025q2_mineru_ocr.json')['markdown']
        self.other = read(ROOT/'assets/cvs_2025q2_pymupdf4llm.json')['markdown']

    def test_sign_error_breaks_agreement(self):
        changed = self.primary.replace('$98.9', '-98.9')
        result = predictions(changed, self.other, self.cfg)[0]
        self.assertEqual(result['evidence_group'], 'weaker')
        self.assertFalse(result['features']['value_agreement'])

    def test_wrong_period_breaks_agreement(self):
        result = predictions(self.primary.replace('2Q 2025', '2Q 2023'), self.other, self.cfg)[0]
        self.assertEqual(result['evidence_group'], 'weaker')
        self.assertFalse(result['features']['column_header_agreement'])

    def test_shared_wrong_value_is_documented_blind_spot(self):
        # Synthetic perturbation only. This is not part of observed source results.
        result = predictions(self.primary.replace('$98.9', '$89.9'), self.other.replace('$98.9', '$89.9'), self.cfg)[0]
        self.assertEqual(result['evidence_group'], 'stronger')

    def test_replay_labels_do_not_fit_confidence(self):
        records = read(ROOT/'reviewed_cells.json')
        before = fit(records)
        mutated = copy.deepcopy(records)
        for row in mutated:
            if row['split']=='replay':
                row['correct'] = not row['correct']
        self.assertEqual(before,fit(mutated))

    def test_no_unvalidated_probabilities_emitted(self):
        records = read(ROOT/'reviewed_cells.json')
        self.assertTrue(records)
        self.assertTrue(all(r['confidence'] is None for r in records))
        self.assertTrue(all(r['confidence_status']=='not_estimated_insufficient_validation' for r in records))

    def test_empty_group_abstains(self):
        result = fit([dict(split='development',evidence_group='stronger',correct=True,document='a')])
        self.assertIsNone(result['weaker']['observed_rate'])

    def test_collapsed_table_yields_no_separate_values(self):
        result = predictions('<table><tr><td>2025</td></tr><tr><td>Revenue 100 200</td></tr></table>', self.other, self.cfg)
        self.assertEqual(result,[])

    def test_merged_numeric_string_is_invalid(self):
        self.assertFalse(single_number('3,037.10.0'))
        self.assertTrue(single_number('(49,553,722)'))
        self.assertTrue(single_number('26%'))

    def test_span_grid_preserves_shared_label(self):
        grid,_ = table_grid('<table><tr><td rowspan="2">A B</td><td>1</td></tr><tr><td>2</td></tr></table>')
        self.assertEqual(grid[1][0]['text'],'A B')
        self.assertEqual(grid[1][1]['text'],'2')
        self.assertEqual(grid[1][0]['rowspan'],2)


if __name__=='__main__':
    unittest.main()
