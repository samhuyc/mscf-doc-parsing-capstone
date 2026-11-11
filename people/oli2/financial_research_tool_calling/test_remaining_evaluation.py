from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation import live_runner as runner
from evaluation.live_fixtures import client_for


class RemainingEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(redirect_stdout(io.StringIO()))
        self.suite, self.dataset, self.digest = runner.load_suite()
        self.remaining = runner.select_remaining(self.suite, self.digest)

    def test_selection_preserves_gold_order_and_keeps_two_turn_session(self):
        original = deepcopy(self.suite)
        self.assertEqual([case['id'] for case in self.remaining['cases']], ['L05','L06','L07','L08'])
        self.assertEqual(sum(len(case['turns']) for case in self.remaining['cases']), 5)
        self.assertEqual(self.remaining['caps'], runner.REMAINING_CAPS)
        for case in self.remaining['cases']:
            self.assertEqual(case, next(c for c in self.suite['cases'] if c['id'] == case['id']))
        self.assertEqual(self.suite, original)

    def test_reject_changed_history_labels_or_already_executed_turn(self):
        prior = json.loads(runner.PRIOR_REPORT.read_text(encoding='utf-8'))
        for mutation in ('executed', 'label', 'hash'):
            invalid = deepcopy(prior)
            row = next(t for t in invalid['turns'] if t['case_id'] == 'L05')
            if mutation == 'executed':
                row['observed']['executed'] = True
            elif mutation == 'label':
                row['expected']['behavior'] = 'answer'
            else:
                invalid['suite_sha256'] = 'invalid'
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                path = Path(folder)/'prior.json'
                path.write_text(json.dumps(invalid),encoding='utf-8')
                with self.assertRaises(runner.EvaluationError):
                    runner.select_remaining(self.suite,self.digest,path)

    def test_offline_remaining_only_and_context_without_old_amounts(self):
        clients = {}
        def factory(case_id, index):
            client = client_for(case_id,index)
            clients[(case_id,index)] = client
            return client
        report = runner.evaluate(self.remaining,self.dataset,self.digest,fake_factory=factory)
        self.assertEqual(set(clients),{('L05',0),('L06',0),('L06',1),('L07',0),('L08',0)})
        self.assertEqual((report['planned_turns'],report['executed_turns'],report['requests']),(5,5,11))
        self.assertEqual(report['selection']['mode'],'remaining_five')
        self.assertEqual(report['metrics']['numerical_accuracy']['eligible'],2)
        self.assertEqual(report['metrics']['citation_accuracy']['eligible'],2)
        self.assertEqual(report['metrics']['intent_understanding_accuracy']['eligible'],5)
        self.assertIsNone(report['cost']['usd'])
        data = json.loads(clients[('L06',1)].requests[0]['input'][0]['content'])
        self.assertEqual(data['session']['current_topic']['company'],'CVS')
        self.assertNotIn('98.9',json.dumps(data))
        isolated = json.loads(clients[('L07',0)].requests[0]['input'][0]['content'])
        self.assertIsNone(isolated['session']['current_topic']['company'])

    def test_suite_budget_remains_shared_and_failure_stops_selection(self):
        report = runner.evaluate(self.remaining,self.dataset,self.digest,
                                 caps={**runner.REMAINING_CAPS,'requests':1})
        self.assertEqual(report['requests'],1)
        self.assertTrue(report['stopped_early'])
        self.assertEqual(report['metrics']['intent_understanding_accuracy']['eligible'],5)
        self.assertLess(report['executed_turns'],5)

    def test_cli_remaining_is_offline_by_default_and_uses_separate_report(self):
        with patch.object(runner.os,'environ',{}), \
                patch('openai.OpenAI',side_effect=AssertionError('Live forbidden')), \
                patch('sys.argv',['live_runner.py','--remaining']), patch.object(runner,'write_report') as write:
            self.assertEqual(runner.main(),0)
        report, path = write.call_args.args
        self.assertEqual(path.name,'remaining_offline_contract_check')
        self.assertEqual(report['selection']['mode'],'remaining_five')
        self.assertEqual(report['planned_turns'],5)
        with patch('sys.argv',['live_runner.py','--remaining','--live']), \
                patch('openai.OpenAI',side_effect=AssertionError('Confirmation required')):
            self.assertEqual(runner.main(),1)


if __name__ == '__main__':
    unittest.main()
