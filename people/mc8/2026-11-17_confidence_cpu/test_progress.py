"""Synthetic progress/resume/launcher checks. No model execution or fitting."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from common import read, write
import pipeline
import worker
import run as inference_run
from progress import InferenceProgress, ElapsedTimer, elapsed_seconds, snapshot, render


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name)
        self.tables = [dict(table_id='dev1', split='development'),
                       dict(table_id='dev2', split='development'),
                       dict(table_id='test1', split='test')]

    def test_snapshot_before_run_is_read_only(self):
        missing = self.run/'absent'
        data = snapshot(missing, self.tables, ['glm'])
        self.assertEqual(data['planned_outputs'], 3)
        self.assertEqual(data['processed'], 0)
        self.assertFalse(missing.exists())
        self.assertIn('0.00%', render(data))

    def test_resume_and_retry_counts_unique_outputs(self):
        root = self.run/'development/glm'
        write(root/'dev1.json', dict(status='success', seconds=2))
        write(root/'dev2.json', dict(status='failed', seconds=3))
        progress = InferenceProgress(root, 'glm', 'development', self.tables[:2])
        data = snapshot(self.run, self.tables, ['glm'])
        self.assertEqual((data['processed'], data['succeeded'], data['failed']), (2, 1, 1))
        self.assertAlmostEqual(data['inference_percent'], 200/3)
        progress.start('dev2')
        progress.record('dev2', dict(status='success', seconds=4))
        progress.finish('complete')
        data = snapshot(self.run, self.tables, ['glm'])
        self.assertEqual((data['processed'], data['succeeded'], data['failed']), (2, 2, 0))
        self.assertEqual(data['engines'][0]['seconds'], 6)
        # Reused pilot output is one result, rather than an extra work unit.
        resumed = InferenceProgress(root, 'glm', 'development', self.tables[:2])
        self.assertEqual(resumed.state['processed'], 2)

    def test_dead_worker_is_reported_as_interrupted(self):
        write(self.run/'development/glm/progress.json', dict(
            state='running', pid=99999999, current_table='dev1',
            current_started_epoch=1, succeeded=0, failed=0, processed=0, seconds=0))
        data = snapshot(self.run, self.tables, ['glm'])
        self.assertEqual(data['active'][0]['state'], 'interrupted')

    def test_live_total_and_model_timers_include_active_table(self):
        write(self.run/'pipeline-status.json',dict(state='running',pid=123,
              elapsed_seconds=20,updated_utc='1970-01-01T00:01:40+00:00'))
        write(self.run/'development/glm/progress.json',dict(state='running',pid=123,
              elapsed_seconds=10,updated_utc='1970-01-01T00:01:40+00:00',
              current_started_epoch=102,current_table='dev2',seconds=2,
              succeeded=1,failed=0,processed=1))
        with patch('progress.time.time',return_value=105),patch('progress.alive',return_value=True):
            data=snapshot(self.run,self.tables,['glm'])
        self.assertEqual(data['total_elapsed_seconds'],25)
        self.assertEqual(data['engines'][0]['elapsed_seconds'],15)
        self.assertEqual(data['active'][0]['seconds_in_table'],3)
        self.assertEqual(data['engines'][0]['remaining_inference_seconds_estimate'],1)
        text=render(data)
        self.assertIn('Total running time (pipeline): 00:00:25',text)
        self.assertIn('Runtime',text)
        self.assertIn('Left (est.)',text)

    def test_timer_survives_resume_and_excludes_paused_time(self):
        previous=dict(state='interrupted',elapsed_seconds=12,
                      first_started_utc='1970-01-01T00:00:00+00:00')
        with patch('progress.time.monotonic',return_value=200):
            timer=ElapsedTimer(previous)
        state=dict(state='interrupted')
        with patch('progress.time.monotonic',return_value=205):timer.update(state)
        self.assertEqual(state['elapsed_seconds'],17)
        with patch('progress.time.time',return_value=999999):
            self.assertEqual(elapsed_seconds(state),17)
        with patch('progress.time.monotonic',return_value=300):resumed=ElapsedTimer(state)
        with patch('progress.time.monotonic',return_value=310):resumed.update(state)
        self.assertEqual(state['elapsed_seconds'],27)
        self.assertEqual(state['first_started_utc'],previous['first_started_utc'])

    def test_legacy_timing_is_recovered_and_dead_timers_stop(self):
        old=dict(state='interrupted',started_utc='1970-01-01T00:01:40+00:00',
                 updated_utc='1970-01-01T00:02:40+00:00',seconds=55)
        with patch('progress.time.time',return_value=10000):
            self.assertEqual(elapsed_seconds(old),60)
        stopped=dict(state='running',pid=123,elapsed_seconds=65,
                     updated_utc='1970-01-01T00:02:40+00:00')
        with patch('progress.alive',return_value=False),patch('progress.time.time',return_value=10000):
            self.assertEqual(elapsed_seconds(stopped),65)

    def launch(self, runner, retry=False):
        argv = ['pipeline.py', '--execute', '--full', '--run-dir', str(self.run)]
        if retry:
            argv.append('--retry-failed')
        with patch.object(sys, 'argv', argv), \
             patch('pipeline.LOCAL', self.run), \
             patch('preflight.check', return_value={'ready': True}), \
             patch('pipeline.subprocess.run', side_effect=runner), \
             contextlib.redirect_stdout(io.StringIO()):
            pipeline.main()

    def test_launcher_stops_before_full_batch_after_pilot_failure(self):
        calls = []
        def fail(command, **kwargs):
            calls.append(command)
            raise subprocess.CalledProcessError(1, command)
        with self.assertRaises(subprocess.CalledProcessError):
            self.launch(fail)
        self.assertEqual(len(calls), 1)
        self.assertIn('--limit', calls[0])
        state = read(self.run/'pipeline-status.json')
        self.assertEqual(state['state'], 'failed')
        self.assertEqual(state['completed_stages'], [])

    def test_launcher_stage_order_and_completion(self):
        calls = []
        self.launch(lambda command, **kwargs: calls.append(command))
        self.assertEqual([Path(c[1]).name for c in calls],
                         ['run.py', 'run.py', 'evaluate.py', 'calibrate.py', 'run.py', 'evaluate.py'])
        state = read(self.run/'pipeline-status.json')
        self.assertEqual(state['state'], 'complete')
        self.assertEqual(len(state['completed_stages']), 6)

    def test_launcher_preserves_elapsed_time_on_resume(self):
        write(self.run/'pipeline-status.json',dict(state='interrupted',elapsed_seconds=123.5,
              first_started_utc='1970-01-01T00:00:00+00:00'))
        with patch('progress.time.monotonic',return_value=100):
            self.launch(lambda command,**kwargs: None)
        state=read(self.run/'pipeline-status.json')
        self.assertEqual(state['elapsed_seconds'],123.5)
        self.assertEqual(state['first_started_utc'],'1970-01-01T00:00:00+00:00')

    def test_frozen_resume_retries_only_test_and_preserves_calibration(self):
        write(self.run/'calibrators-frozen.json', {'synthetic': True})
        calls = []
        with patch('calibrate.check_freeze', return_value={}):
            self.launch(lambda command, **kwargs: calls.append(command), retry=True)
        self.assertEqual([Path(c[1]).name for c in calls], ['run.py', 'evaluate.py'])
        self.assertIn('--retry-failed', calls[0])
        self.assertIn('test', calls[0])
        self.assertEqual(read(self.run/'calibrators-frozen.json'), {'synthetic': True})
        self.assertEqual(len(read(self.run/'pipeline-status.json')['completed_stages']), 6)

    def test_keyboard_interrupt_persists_status(self):
        with self.assertRaises(KeyboardInterrupt):
            self.launch(lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()))
        self.assertEqual(read(self.run/'pipeline-status.json')['state'], 'interrupted')

    def test_development_cannot_be_changed_after_freeze(self):
        write(self.run/'calibrators-frozen.json', {'synthetic': True})
        write(self.run/'data/tables.json', {'tables': self.tables})
        argv=['run.py','--execute','--split','development','--run-dir',str(self.run)]
        with patch.object(sys,'argv',argv), patch('run.DATA',self.run/'data'), \
             patch('preflight.check',return_value={'ready': True}), \
             contextlib.redirect_stdout(io.StringIO()), \
             self.assertRaisesRegex(RuntimeError,'Development inference is frozen'):
            inference_run.main()
        self.assertFalse((self.run/'development').exists())


class WorkerWiringTests(unittest.TestCase):
    """Use a fake OCR subprocess and fabricated text, never recognizer weights."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root/'data'
        self.data.mkdir()
        self.tables = []
        for index in range(2):
            image = self.data/f'fake{index}.jpg'
            image.write_bytes(b'synthetic image placeholder; never decoded')
            self.tables.append(dict(table_id=f'fake{index}',split='development',image=image.name,
                                    image_sha256=worker.sha(image),source_sha256='fake-source'))
        write(self.data/'tables.json', {'tables': self.tables})

    def launch(self, fake, limit=None):
        argv=['worker.py','--execute','--engine','tesseract','--split','development',
              '--run-dir',str(self.root/'run/development')]
        if limit is not None:argv+=['--limit',str(limit)]
        units=[dict(text='Revenue 123',score=.9)]
        # Parsing is replaced as well as the subprocess: no OCR is performed.
        from common import sam_paths
        sam_paths()
        with patch.object(sys,'argv',argv), patch('worker.DATA',self.data), \
             patch('worker.subprocess.run',side_effect=fake) as call, \
             patch('run_tesseract.parse_tsv',return_value=units), \
             contextlib.redirect_stdout(io.StringIO()):
            worker.main()
        return call.call_count

    def test_worker_persists_progress_and_reuses_cached_outputs(self):
        fake=lambda *a,**kw: subprocess.CompletedProcess(a[0],0,stdout='fabricated TSV',stderr='')
        self.assertEqual(self.launch(fake),2)
        self.assertEqual(self.launch(fake),0)
        # The launcher's repeated one-table check must not reset full-run counts.
        self.assertEqual(self.launch(fake,limit=1),0)
        progress=read(self.root/'run/development/tesseract/progress.json')
        self.assertEqual((progress['state'],progress['processed'],progress['succeeded']),('complete',2,2))
        record=read(self.root/'run/development/tesseract/fake0.json')
        self.assertEqual(record['native_status'],'available')

    def test_growing_prefix_executes_only_new_tables(self):
        fake=lambda *a,**kw: subprocess.CompletedProcess(a[0],0,stdout='fabricated TSV',stderr='')
        self.assertEqual(self.launch(fake,limit=1),1)
        first=(self.root/'run/development/tesseract/fake0.json').read_bytes()
        self.assertEqual(self.launch(fake,limit=2),1)
        self.assertEqual((self.root/'run/development/tesseract/fake0.json').read_bytes(),first)
        self.assertEqual(self.launch(fake,limit=2),0)

    def test_worker_timeout_retains_failure_and_stops_initial_batch(self):
        calls=[]
        def timeout(command,**kwargs):
            calls.append(command)
            raise subprocess.TimeoutExpired(command,1)
        with self.assertRaises(SystemExit):
            self.launch(timeout)
        self.assertEqual(len(calls),1)
        folder=self.root/'run/development/tesseract'
        self.assertEqual(read(folder/'fake0.json')['status'],'failed')
        self.assertFalse((folder/'fake1.json').exists())
        progress=read(folder/'progress.json')
        self.assertEqual((progress['state'],progress['failed'],progress['processed']),('failed',1,1))


if __name__ == '__main__':
    unittest.main()
