from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from evaluation import final_runner as final
from evaluation.live_runner import load_suite


class FinalEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(redirect_stdout(io.StringIO()))
        self.enterContext(patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden')))
        self.enterContext(patch('openai.OpenAI',side_effect=AssertionError('Live forbidden')))
        self.folder=Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_full_fixed_suite_preserves_labels_and_exposes_scope_mismatch(self):
        original,_,digest=load_suite()
        report=final.run_evaluation(self.folder)
        self.assertEqual(report['executed_turns'],11)
        self.assertEqual(report['requests'],28)
        self.assertFalse(report['stopped_early'])
        self.assertEqual(report['usage_kind'],'simulated')
        self.assertIsNone(report['cost']['usd'])
        self.assertEqual(report['suite_sha256'],digest)
        expected=[t['expected'] for c in original['cases'] for t in c['turns']]
        self.assertEqual([t['expected'] for t in report['turns']],expected)
        mismatch=[t for t in report['turns'] if not t['evaluation']['passed']]
        self.assertEqual([t['case_id'] for t in mismatch],['L05'])
        self.assertEqual(mismatch[0]['observed']['behavior'],'unsupported')
        self.assertEqual(mismatch[0]['observed']['pending_companies'],['CVS','UNH'])
        self.assertEqual(len(list((self.folder/'state').rglob('snapshots/*.json'))),11)
        self.assertEqual(report['metrics']['numerical_accuracy']['correct'],7)
        self.assertEqual(report['metrics']['citation_accuracy']['correct'],7)

    def test_frozen_manifest_rejects_worktree_drift_before_live(self):
        saved={'commit':'fixed','schema_version':'1'}
        path=self.folder/'version.json'; path.write_text(json.dumps(saved))
        with patch.object(final,'git',return_value=''),patch.object(final,'version_record',return_value=saved):
            self.assertEqual(final.verify_frozen(path),saved)
        with patch.object(final,'git',return_value=' M code.py'):
            with self.assertRaises(ValueError): final.verify_frozen(path)
        with patch.object(final,'git',return_value=''),patch.object(final,'version_record',return_value={'commit':'changed'}):
            with self.assertRaises(ValueError): final.verify_frozen(path)

    def test_version_covers_transitive_retrieval_and_runtime(self):
        record = final.version_record()
        self.assertTrue(all(any(path.endswith('/'+name) for path in record['retrieval_code'])
                            for name in ('retrieval.py','structure.py','chunker.py')))
        self.assertIn('tiktoken',record['runtime'])
        self.assertIn('markdown-it-py',record['runtime'])
        self.assertEqual([tool['name'] for tool in record['tools']['definitions']],['search_report','calculate'])

    def test_freeze_is_append_only_and_live_needs_confirmation(self):
        path=self.folder/'version.json'
        with patch.object(final,'git',side_effect=lambda *a:'feature' if a[0]=='branch' else ''), patch.object(final,'version_record',return_value={'commit':'fixed'}):
            final.freeze(path)
            with self.assertRaises(FileExistsError): final.freeze(path)
        self.assertEqual(final.main(['--live']),1)
        with patch.object(final,'verify_frozen',side_effect=ValueError('changed')):
            with self.assertRaises(ValueError): final.main(['--live','--confirm-paid-api'])


if __name__=='__main__': unittest.main()
