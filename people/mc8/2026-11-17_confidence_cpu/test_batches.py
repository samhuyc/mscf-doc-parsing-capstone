"""Synthetic batch/resume/scoring checks; no recognizers or real dataset scoring."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import batches
import evaluate
import pipeline
from common import read, write, sha, digest, HERE, sam_paths
from score_summary import summarize_engines
from markdown_report import render_summary, regenerate_reports


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root/'run'
        self.data = self.root/'data'
        self.tables = [dict(table_id=f'd{i}', split='development') for i in range(4)]
        self.tables += [dict(table_id=f't{i}', split='test') for i in range(2)]
        write(self.data/'tables.json', dict(tables=self.tables))
        self.config = dict(engines=['glm'])

    def fake_stage(self, command, **kwargs):
        self.calls.append(command)
        script = Path(command[1]).name
        if script == 'calibrate.py':
            write(self.run/'calibrators-frozen.json', {'synthetic': True})
        if script == 'evaluate.py':
            split = command[command.index('--split')+1]
            limit = int(command[command.index('--limit')+1])
            selected = [t for t in self.tables if t['split'] == split][:limit]
            pairs = [dict(table_id=t['table_id'], engine='glm', inference_status='success',
                          fact_f1=.2 if t['table_id'] in ('d0', 'd1') else .8,
                          financial_value_recall=1., measurement_flags=[]) for t in selected]
            write(self.run/split/'pairs.json', dict(pairs=pairs))
            write(self.run/split/'summary.json', dict(split=split,scored_tables=len(selected),
                  total_split_tables=sum(t['split']==split for t in self.tables),
                  engines=summarize_engines(pairs,engines=self.config['engines'])))
        return subprocess.CompletedProcess(command, 0)

    def launch(self, execute=True, runner=None, retry=False, size=2, one_batch=True):
        self.calls = []
        with patch('batches.DATA', self.data), patch('batches.LOCAL', self.root), \
             patch('batches.config', return_value=self.config), \
             patch('evaluate.config', return_value=self.config), \
             patch('preflight.check', return_value={'ready': True}), \
             patch('calibrate.check_freeze', return_value={}), \
             patch('batches.subprocess.run', side_effect=runner or self.fake_stage), \
             contextlib.redirect_stdout(io.StringIO()):
            batches.launch(self.run, size, execute, retry, one_batch=one_batch)

    def test_2000_tables_are_20_disjoint_batches(self):
        tables = [dict(table_id=str(i), split='development' if i < 1600 else 'test')
                  for i in range(2000)]
        plan = batches.batch_plan(tables, 100)
        self.assertEqual(len(plan), 20)
        self.assertTrue(all(len(b['table_ids']) == 100 for b in plan))
        self.assertEqual(len({tid for b in plan for tid in b['table_ids']}), 2000)
        self.assertEqual([b['limit'] for b in plan[15:]], [1600, 100, 200, 300, 400])

    def test_plan_does_not_write_or_execute(self):
        self.launch(execute=False)
        self.assertFalse(self.run.exists())
        self.assertEqual(self.calls, [])

    def test_each_launch_advances_once_and_updates_cumulative_mean(self):
        self.launch()
        self.assertEqual([Path(c[1]).name for c in self.calls], ['run.py', 'evaluate.py'])
        first = read(self.run/'summary.json')
        self.assertEqual(first['completed_tables'], 2)
        self.assertEqual(first['engines']['glm']['planned'], 2)
        self.assertAlmostEqual(first['engines']['glm']['fact_f1'], .2)
        self.assertFalse((self.run/'test').exists())
        self.assertFalse((self.run/'calibrators-frozen.json').exists())
        self.launch()
        self.assertEqual(self.calls[0][-1], '4')
        self.assertEqual([Path(c[1]).name for c in self.calls], ['run.py', 'evaluate.py', 'calibrate.py'])
        second = read(self.run/'summary.json')
        self.assertEqual(second['completed_tables'], 4)
        self.assertAlmostEqual(second['engines']['glm']['fact_f1'], .5)
        self.assertEqual(read(self.run/'batch-results/batch-01.json'), first)
        self.assertEqual(read(self.run/'batch-progress.json')['completed_batches'], 2)

    def test_test_batch_preserves_development_freeze_and_aggregates_both_splits(self):
        self.launch(); self.launch()
        frozen = (self.run/'calibrators-frozen.json').read_bytes()
        self.launch()
        self.assertEqual([Path(c[1]).name for c in self.calls], ['run.py', 'evaluate.py'])
        self.assertIn('test', self.calls[0])
        self.assertEqual((self.run/'calibrators-frozen.json').read_bytes(), frozen)
        summary = read(self.run/'summary.json')
        self.assertEqual(summary['completed_tables'], 6)
        self.assertAlmostEqual(summary['engines']['glm']['fact_f1'], .6)
        self.assertEqual(set(summary['splits']), {'development', 'test'})
        self.launch()
        self.assertEqual(self.calls, [])
        self.assertEqual(read(self.run/'batch-progress.json')['completed_batches'], 3)

    def test_interruption_resumes_same_batch_and_preserves_last_summary(self):
        self.launch()
        first = read(self.run/'summary.json')
        def interrupt(command, **kwargs):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.launch(runner=interrupt)
        self.assertEqual(read(self.run/'batch-progress.json')['completed_batches'], 1)
        self.assertEqual(read(self.run/'summary.json'), first)
        self.assertEqual(read(self.run/'pipeline-status.json')['state'], 'interrupted')
        self.launch()
        self.assertEqual(read(self.run/'batch-progress.json')['completed_batches'], 2)

    def test_failure_does_not_advance_and_retry_flag_is_forwarded(self):
        def fail(command, **kwargs):
            raise subprocess.CalledProcessError(1, command)
        with self.assertRaises(subprocess.CalledProcessError):
            self.launch(runner=fail)
        self.assertEqual(read(self.run/'batch-progress.json')['completed_batches'], 0)
        self.launch(retry=True)
        self.assertIn('--retry-failed', self.calls[0])
        self.assertNotIn('--retry-failed', self.calls[1])

    def test_interrupted_after_freeze_does_not_rerun_development(self):
        self.launch(); self.launch()
        ledger = read(self.run/'batch-progress.json')
        ledger['completed_batches'] = 1
        write(self.run/'batch-progress.json', ledger)
        self.launch()
        self.assertEqual(self.calls, [])
        self.assertEqual(read(self.run/'batch-progress.json')['completed_batches'], 2)

    def test_partial_final_batches_and_changed_size_rejected(self):
        plan = batches.batch_plan(self.tables, 3)
        self.assertEqual([len(b['table_ids']) for b in plan], [3, 1, 2])
        self.launch()
        with self.assertRaisesRegex(RuntimeError, 'Batch settings/data changed'):
            self.launch(size=3)

    def test_default_pipeline_continues_after_each_batch(self):
        with patch.object(sys, 'argv', ['pipeline.py', '--run-dir', str(self.run)]), \
             patch('batches.launch') as launch:
            pipeline.main()
        launch.assert_called_once_with(self.run, 100, False, False, one_batch=False)

    def test_pipeline_one_batch_flag_is_forwarded(self):
        with patch.object(sys, 'argv', ['pipeline.py', '--one-batch', '--run-dir', str(self.run)]), \
             patch('batches.launch') as launch:
            pipeline.main()
        launch.assert_called_once_with(self.run, 100, False, False, one_batch=True)

    def test_continuous_run_saves_both_formats_at_every_batch_and_finishes(self):
        self.launch(one_batch=False)
        self.assertEqual([Path(c[1]).name for c in self.calls],
                         ['run.py','evaluate.py','run.py','evaluate.py','calibrate.py','run.py','evaluate.py'])
        self.assertEqual(read(self.run/'batch-progress.json')['completed_batches'],3)
        self.assertEqual(read(self.run/'pipeline-status.json')['state'],'complete')
        for batch, count in ((1,2),(2,4),(3,6)):
            prefix=self.run/'batch-results'/f'batch-{batch:02d}'
            self.assertEqual(read(prefix.with_suffix('.json'))['completed_tables'],count)
            self.assertIn(f'**Tables completed:** {count} / 6',prefix.with_suffix('.md').read_text())
        self.assertIn('**Tables completed:** 6 / 6',(self.run/'summary.md').read_text())
        self.assertTrue((self.run/'development/summary.md').exists())
        self.assertTrue((self.run/'test/summary.md').exists())

    def test_continuous_failure_retains_last_result_and_resumes_at_failed_batch(self):
        def fail_second_batch(command,**kwargs):
            if Path(command[1]).name=='run.py' and command[command.index('--limit')+1]=='4':
                raise subprocess.CalledProcessError(1,command)
            return self.fake_stage(command,**kwargs)
        with self.assertRaises(subprocess.CalledProcessError):
            self.launch(runner=fail_second_batch,one_batch=False)
        self.assertEqual(read(self.run/'batch-progress.json')['completed_batches'],1)
        self.assertEqual(read(self.run/'pipeline-status.json')['batch_number'],2)
        first_json=(self.run/'batch-results/batch-01.json').read_bytes()
        first_md=(self.run/'batch-results/batch-01.md').read_bytes()
        self.assertEqual((self.run/'summary.json').read_bytes(),first_json)
        self.assertEqual((self.run/'summary.md').read_bytes(),first_md)
        self.launch(one_batch=False)
        self.assertEqual(self.calls[0][self.calls[0].index('--limit')+1],'4')
        self.assertEqual(read(self.run/'batch-progress.json')['completed_batches'],3)
        self.assertEqual((self.run/'batch-results/batch-01.json').read_bytes(),first_json)
        self.assertEqual((self.run/'batch-results/batch-01.md').read_bytes(),first_md)

    def test_continuous_interrupt_retains_checkpoint_and_elapsed_time(self):
        def interrupt_second_batch(command,**kwargs):
            if Path(command[1]).name=='run.py' and command[command.index('--limit')+1]=='4':
                raise KeyboardInterrupt()
            return self.fake_stage(command,**kwargs)
        with self.assertRaises(KeyboardInterrupt):
            self.launch(runner=interrupt_second_batch,one_batch=False)
        state=read(self.run/'pipeline-status.json')
        self.assertEqual(state['state'],'interrupted')
        self.assertEqual(state['completed_batches'],1)
        self.launch(one_batch=False)
        self.assertGreaterEqual(read(self.run/'pipeline-status.json')['elapsed_seconds'],state['elapsed_seconds'])

    def test_backfill_markdown_preserves_json_and_precise_scores(self):
        self.launch()
        paths=[self.run/'summary.json',self.run/'batch-results/batch-01.json',
               self.run/'development/summary.json']
        saved={p:p.read_bytes() for p in paths}
        for path in paths:path.with_suffix('.md').unlink()
        self.assertEqual(len(regenerate_reports(self.run)),3)
        for path in paths:
            self.assertEqual(path.read_bytes(),saved[path])
            self.assertTrue(path.with_suffix('.md').exists())

    def test_markdown_distinguishes_missing_metric_from_zero_and_test_forecasts(self):
        summary=dict(split='test',scored_tables=2,total_split_tables=2,engines={
            'tesseract':dict(planned=2,statuses=dict(success=1,failed=1),eligible_financial_tables=0,
                            fact_f1=None,financial_value_recall=0.,flagged_measurements=1),
            'glm':dict(planned=2,statuses=dict(success=2),eligible_financial_tables=2,
                       fact_f1=.1234567,financial_value_recall=.75,flagged_measurements=0,
                       forecast=dict(n=2,issuers=1,mae=.1,baseline_mae=.2,mse=.01,baseline_mse=.04,mse_gain=.03))})
        report=render_summary(summary)
        self.assertIn('| Tesseract | 2 | 1 | 1 | 0 | 0 | N/A | 0.00% | 1 |',report)
        self.assertIn('0.1235 | 75.00%',report)
        self.assertIn('## Held-out forecast quality',report)
        self.assertIn('held-out test rows only',report)

    def test_forecast_metrics_use_only_held_out_rows(self):
        sam_paths()
        rows = [dict(engine='glm',table_id='dev',issuer='dev',fact_f1=.2,
                     financial_value_recall=1.,measurement_flags=[],inference_status='success'),
                dict(engine='glm',table_id='test',issuer='test',fact_f1=.8,
                     financial_value_recall=1.,measurement_flags=[],inference_status='success',
                     expected_f1=.7,baseline=.5,selected_feature='native_numeric',review=False)]
        with patch('calibration_round2.metrics',return_value=dict(n=1)) as metrics:
            result=summarize_engines(rows,include_forecasts=True,engines=['glm'])
        self.assertAlmostEqual(result['glm']['fact_f1'],.5)
        self.assertEqual([r['table_id'] for r in metrics.call_args[0][0]],['test'])


class ScoringCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root/'run'
        self.data = self.root/'data'
        self.tables = [dict(table_id=f'd{i}', split='development', issuer='fake',
                            image_sha256='image', source_sha256='source', sam_original=False)
                       for i in range(3)]
        write(self.data/'tables.json', dict(tables=self.tables))
        write(self.data/'references.json', {t['table_id']: dict(grids=[], reference_kind='synthetic') for t in self.tables})
        self.settings = dict(config_sha256=sha(HERE/'config.json'), tables_sha256=sha(self.data/'tables.json'),
                             adapters_sha256={n: sha(HERE/n) for n in ('worker.py', 'native_vlm.cpp', 'sam_bridge.py')},
                             runtime_build_sha256=sha(HERE/'runtime-build.json'), model_conversion=None)
        write(self.run/'development/tesseract/settings.json', self.settings)
        for t in self.tables:
            self.record(t['table_id'])

    def record(self, tid, text='123', status='success'):
        write(self.run/'development/tesseract'/f'{tid}.json',
              dict(image_sha256='image', source_sha256='source', settings_sha256=digest(self.settings),
                   status=status, text=text))

    def score(self, limit):
        argv = ['evaluate.py', '--execute', '--split', 'development', '--limit', str(limit),
                '--cache-scores', '--run-dir', str(self.run)]
        with patch.object(sys, 'argv', argv), patch('evaluate.DATA', self.data), \
             patch('evaluate.config', return_value=dict(engines=['tesseract'])), \
             patch('sam_bridge.parse_output', return_value=dict(status='text', grids=[])) as parse, \
             patch('sam_bridge.flatten_facts', return_value=[dict(raw='123')]), \
             contextlib.redirect_stdout(io.StringIO()):
            evaluate.main()
        return parse.call_count

    def test_prefix_excludes_unrun_tables_and_reuses_scores(self):
        self.assertEqual(self.score(1), 1)
        self.assertEqual(len(read(self.run/'development/pairs.json')['pairs']), 1)
        self.assertEqual(self.score(2), 1)
        self.assertEqual(self.score(2), 0)
        self.assertEqual(read(self.run/'development/summary.json')['scored_tables'], 2)
        self.assertEqual(read(self.run/'development/summary.json')['engines']['tesseract']['planned'], 2)

    def test_changed_record_invalidates_only_its_score(self):
        self.score(2)
        self.record('d0', text='456')
        self.assertEqual(self.score(2), 1)
        rows = read(self.run/'development/pairs.json')['pairs']
        self.assertEqual(rows[0]['financial_value_recall'], 0)
        self.assertEqual(rows[1]['financial_value_recall'], 1)

    def test_missing_record_retry_invalidates_cache(self):
        (self.run/'development/tesseract/d0.json').unlink()
        self.score(1)
        self.assertEqual(read(self.run/'development/pairs.json')['pairs'][0]['inference_status'], 'missing')
        self.record('d0')
        self.assertEqual(self.score(1), 1)
        self.assertEqual(read(self.run/'development/pairs.json')['pairs'][0]['inference_status'], 'success')

    def test_failed_selected_record_remains_in_denominator(self):
        self.record('d0', status='failed')
        self.score(2)
        summary = read(self.run/'development/summary.json')['engines']['tesseract']
        self.assertEqual(summary['planned'], 2)
        self.assertEqual(summary['statuses'], dict(failed=1, success=1))
        self.assertEqual(summary['financial_value_recall'], .5)


if __name__ == '__main__':
    unittest.main()
