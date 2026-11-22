"""Reporting checks using saved synthetic rows, without OCR or calibration fits."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from common import read, write
from markdown_report import render_summary, regenerate_reports
from report_details import collect_details, prediction_details
from score_summary import summarize_engines


class ReportDetailsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name)
        self.rows = []
        for i, truth in enumerate((1., .5, .2)):
            for engine in ('tesseract', 'glm'):
                self.rows.append(dict(table_id=f'd{i}', engine=engine, issuer=f'issuer{i}',
                    split='development', inference_status='success',
                    fact_f1=truth if engine == 'glm' else None,
                    grits_content_f1=.9 if engine == 'glm' else None,
                    financial_value_recall=.8, native_numeric=(0. if i == 0 else None),
                    financial_reference_eligible=True, measurement_flags=['audit needed'] if i == 0 else [],
                    truncated=False))
                write(self.run/'development'/engine/f'd{i}.json', dict(seconds=i+1))
        write(self.run/'development/pairs.json', dict(pairs=self.rows))
        write(self.run/'batch-progress.json', dict(batches=[
            dict(split='development', table_ids=['d0', 'd1']),
            dict(split='development', table_ids=['d2'])]))
        engines = summarize_engines(self.rows[:4], engines=['tesseract', 'glm'])
        self.summary = dict(completed_batches=1, total_batches=2, completed_tables=2,
            total_tables=3, scored_outputs=4, engines=engines, splits=dict(development=dict(
                split='development', scored_tables=2, total_split_tables=3, engines=engines)))

    def details(self):
        with patch('report_details.DATA', self.run/'no-manifest'):
            return collect_details(self.run, self.summary)

    def test_historical_prefix_excludes_later_scores_and_times_and_preserves_inputs(self):
        originals = {p: p.read_bytes() for p in self.run.rglob('*.json')}
        details = self.details()
        self.assertEqual(details['counts']['unique_crops'], 2)
        self.assertEqual(details['counts']['financial_crops'], 2)
        self.assertEqual(details['counts']['outputs'], 4)
        glm = details['engines']['glm']
        self.assertAlmostEqual(glm['mean_fact_f1'], .75)
        self.assertAlmostEqual(glm['mean_grits'], .9)
        self.assertEqual(glm['median_recognition_seconds'], 1.5)
        self.assertEqual(glm['timed_outputs'], 2)
        self.assertEqual(glm['numeric_coverage'], 1)
        self.assertEqual(glm['mean_native_numeric'], 0.)
        self.assertEqual(glm['errors_below_95'], 1)
        self.assertEqual(glm['exact_tables'], 1)
        self.assertEqual(glm['ranking_by_split']['development']['n'], 1)
        self.assertIsNone(glm['ranking_by_split']['development']['spearman'])
        self.assertIsNone(details['engines']['tesseract']['mean_grits'])
        self.assertIsNone(glm['prediction'])
        for p, contents in originals.items():
            self.assertEqual(p.read_bytes(), contents)

    def test_changed_scores_refuse_to_relabel_old_snapshot(self):
        self.rows[1]['fact_f1'] = .1
        write(self.run/'development/pairs.json', dict(pairs=self.rows))
        with self.assertRaisesRegex(ValueError, 'Saved scores changed'):
            self.details()

    def test_render_covers_sam_metrics_with_explicit_pending_and_valid_tables(self):
        report = render_summary(self.summary, self.details())
        for term in ('GriTS content F1', 'Mean native numeric', 'Median recognition (s)',
                     'Spearman 95% issuer CI', 'Error AUC', 'Exact F1 tables', 'Baseline MAE',
                     'Baseline MSE', 'MSE gain 95% issuer CI', 'Selected feature',
                     'Error capture', 'Kept mean F1', 'audit needed', 'Pending',
                     'descriptive development results'):
            self.assertIn(term, report)
        width = None
        for line in report.splitlines():
            if line.startswith('|'):
                width = width or line.count('|')
                self.assertEqual(line.count('|'), width, line)
            else:
                width = None

    def test_regeneration_ignores_metrics_sidecars_and_preserves_summary_json(self):
        path = self.run/'batch-results/batch-01.json'
        write(path, self.summary)
        original = path.read_bytes()
        with patch('report_details.DATA', self.run/'no-manifest'):
            for _ in range(2):
                self.assertEqual(regenerate_reports(self.run), [path.with_suffix('.md')])
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(read(path.with_name('batch-01-metrics.json'))['counts']['outputs'], 4)
        self.assertFalse(path.with_name('batch-01-metrics.md').exists())

    def test_forecast_and_review_use_test_rows_only(self):
        rows = [dict(table_id='d0', issuer='dev', split='development', fact_f1=0.,
                     expected_f1=1., baseline=0., selected_feature='native_all', review=True),
                dict(table_id='t0', issuer='test', split='test', fact_f1=.8,
                     expected_f1=.7, baseline=.5, selected_feature='native_numeric', review=False)]
        result = prediction_details(rows)
        self.assertEqual(result['n'], 1)
        self.assertAlmostEqual(result['mae'], .1)
        self.assertAlmostEqual(result['mse'], .01)
        self.assertAlmostEqual(result['baseline_mae'], .3)
        self.assertEqual(result['triage'], dict(reviewed=0, total=1, errors=1, caught=0, error_capture=0.))
        details = self.details()
        details['engines']['glm']['prediction'] = result
        report = render_summary(self.summary, details)
        self.assertIn('native_numeric (1)', report)
        self.assertIn('| GLM-OCR | 0 / 1 | 1 | 0 | 0.00% | 1 | 100.00% | 0.8000 | 0.8000 |', report)
        width = None
        for line in report.splitlines():
            if line.startswith('|'):
                width = width or line.count('|')
                self.assertEqual(line.count('|'), width, line)
            else:
                width = None


if __name__ == '__main__':
    unittest.main()
