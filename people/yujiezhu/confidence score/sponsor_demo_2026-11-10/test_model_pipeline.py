"""Synthetic tests verify plumbing; none of these rows enter the reported pilot."""
import copy
import tempfile
import unittest
from pathlib import Path

import numpy as np

from model_pipeline import (ROOT, FEATURES, audit, diagnostics, family, feature_values,
                            fit_calibrated, import_reviews, infer, labels, matrix, number,
                            predict_saved, read, serialize, split_rows, train, write_review_queue)


class CorrectnessModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=read(ROOT/'reviewed_cells.json')

    def test_features_cannot_read_truth_or_identity(self):
        original=self.rows[0]; changed=copy.deepcopy(original)
        for key in ['numeric_correct','row_correct','column_correct','unit_correct','correct']:
            changed[key]=not changed[key]
        changed.update(reference_value='fabricated',reference_row='wrong',reference_column='wrong',
                       reference_unit='wrong',document='other',human_verified=True,reviewer='test',sample_id='other')
        self.assertEqual(feature_values(original),feature_values(changed))

    def test_numeric_features_ignore_header_changes(self):
        changed=copy.deepcopy(self.rows[0]); changed['column_header']='wrong period'
        changed['features']['column_header_bound']=False
        self.assertTrue(np.array_equal(matrix([self.rows[0]],'numeric'),matrix([changed],'numeric')))
        self.assertFalse(np.array_equal(matrix([self.rows[0]],'association'),matrix([changed],'association')))

    def test_correct_numbers_with_bad_headers_are_separate_targets(self):
        rows=[r for r in self.rows if r['document']=='rolls_royce_2026h1_release']
        self.assertEqual(labels(rows,'numeric').tolist(),[1]*10)
        self.assertEqual(labels(rows,'association').tolist(),[0]*10)

    def test_sign_decimal_and_parentheses(self):
        self.assertNotEqual(number('4.921'),number('4,921'))
        self.assertNotEqual(number('-100'),number('100'))
        self.assertEqual(number('(100)'),number('-100'))
        for malformed in ['(100','100)','(-100)','1,23','3,037.10.0']:
            self.assertIsNone(number(malformed),malformed)

    def test_rolls_royce_family_never_splits(self):
        rows=[r for r in self.rows if r['document'].startswith('rolls_royce')]
        self.assertEqual(len({family(r) for r in rows}),1)
        with self.assertRaisesRegex(ValueError,'document_family_leakage'):
            split_rows(self.rows,{'train':['edf_2024','rolls_royce_2026h1'],
                                 'calibration':['cvs_2025q2'],'test':['rolls_royce_2026h1','hippodrome_2025']})

    def test_numeric_failure_fold_is_not_filled_in_sample(self):
        d=diagnostics(self.rows,'numeric')
        edf=next(f for f in d['folds'] if f['held_family']=='edf_2024')
        self.assertEqual(edf['status'],'not_scored')
        self.assertEqual(d['scored_errors'],0)
        self.assertEqual(d['total_errors'],5)
        self.assertTrue(all(p['diagnostic_probability'] is None for p in d['predictions'] if p['family']=='edf_2024'))

    def test_saved_coefficients_reproduce_model(self):
        fitted=train(self.rows,'numeric')
        np.testing.assert_allclose(predict_saved(serialize(fitted,'numeric'),self.rows,'numeric'),
                                   fitted.predict_proba(matrix(self.rows,'numeric'))[:,1],atol=1e-12)

    def test_drafts_cannot_be_calibrated(self):
        split={'train':['cvs_2025q2','edf_2024'],'calibration':['hippodrome_2025'],'test':['rolls_royce_2026h1']}
        with self.assertRaisesRegex(ValueError,'independently_reviewed_labels_required'):
            fit_calibrated(self.rows,'numeric',split)

    def test_test_labels_do_not_change_fitted_or_calibrated_parameters(self):
        rows=[]
        for group in ['synthetic_train','synthetic_calibration','synthetic_test']:
            for i in range(12):
                r=copy.deepcopy(self.rows[i%len(self.rows)])
                r.update(sample_id=f'{group}:{i}',document=group,document_family=group,
                         numeric_correct=bool(i%3),human_verified=True,reviewer='synthetic test fixture')
                if i%3==0:
                    r['comparison_value']='999'
                rows.append(r)
        assignments={part:['synthetic_'+part] for part in ['train','calibration','test']}
        first=fit_calibrated(rows,'numeric',assignments)
        altered=copy.deepcopy(rows)
        for r in altered:
            if family(r)=='synthetic_test':
                r['numeric_correct']=not r['numeric_correct']
        second=fit_calibrated(altered,'numeric',assignments)
        self.assertEqual(first['base'],second['base'])
        self.assertEqual(first['sigmoid'],second['sigmoid'])
        self.assertEqual([p['calibrated'] for p in first['predictions']],
                         [p['calibrated'] for p in second['predictions']])
        testing=[r for r in rows if family(r)=='synthetic_test']
        predictions=infer({'numeric':first},testing)
        np.testing.assert_allclose([r['numeric']['estimated_probability'] for r in predictions],
                                   [r['calibrated'] for r in first['predictions']],atol=1e-12)
        self.assertTrue(all(r['association']['estimated_probability'] is None for r in predictions))
        for r in testing:
            for key in ['numeric_correct','row_correct','column_correct','unit_correct','correct','reference_value']:
                r.pop(key,None)
        self.assertEqual(predictions,infer({'numeric':first},testing))

    def test_exported_proposals_do_not_become_human_reviews(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'review.csv'; write_review_queue(self.rows,path)
            imported=import_reviews(self.rows,path)
            self.assertFalse(any(r['human_verified'] for r in imported))

    def test_one_class_training_refuses(self):
        with self.assertRaisesRegex(ValueError,'only_one_class'):
            train([r for r in self.rows if r['numeric_correct']],'numeric')


if __name__=='__main__':
    unittest.main()
