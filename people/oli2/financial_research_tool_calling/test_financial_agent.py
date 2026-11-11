from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

import httpx2 as httpx
from openai import APIConnectionError
import api_demo as agent
import financial_agent as app
from state_snapshot import load_state_snapshot
from long_term_memory import search_memory


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.enterContext(redirect_stdout(self.output))
        self.enterContext(patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden')))
        self.enterContext(patch('openai.OpenAI', side_effect=AssertionError('Live forbidden')))
        self.enterContext(patch('session_demo.resolve_question', side_effect=AssertionError('Rules forbidden')))
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.app = app.FinancialAgent(directory=self.directory)

    def ask(self, parsed=None, question='自然语言问题', target=None, **kwargs):
        return (target or self.app).ask(question, fake_client=app.IntegratedFakeClient(parsed or app.fixture()), **kwargs)

    def test_direct_lookup_snapshot_memory_and_fresh_revalidation(self):
        with patch.object(agent, 'search_report', wraps=agent.search_report) as search:
            first = self.ask(question='public question with pretend-secret-marker')
            plans = []
            second = self.ask(context_observer=plans.append)
        self.assertEqual(search.call_count, 2)
        self.assertEqual(first.category, 'answer')
        self.assertIn('98.9', first.answer)
        self.assertNotEqual(first.state.task_id, second.state.task_id)
        self.assertTrue(any(first.state.task_id in p.memory_task_ids for p in plans))
        snap = load_state_snapshot(self.directory/'snapshots'/f'{first.state.task_id}.json')
        self.assertEqual(snap.api_request_count, 3)
        records = search_memory('CVS', app.METRIC, 2025, 2, directory=self.directory/'memory')
        self.assertEqual(len(records), 2)
        text = ''.join(p.read_text(encoding='utf-8') for p in self.directory.rglob('*.json'))
        self.assertNotIn('pretend-secret-marker', text)
        self.assertNotIn('history', text)
        self.assertNotIn('98.9', ''.join(p.read_text() for p in (self.directory/'memory').rglob('*.json')))

    def test_followup_then_period_clarification_then_compare(self):
        results = [self.app.ask(q) for q in app.DEMO_QUESTIONS]
        self.assertEqual([r.category for r in results], ['answer','answer','ambiguity','answer'])
        self.assertIn('91.2', results[1].answer)
        self.assertIn('+7.7', results[3].answer)
        self.assertEqual(results[3].state.calculation, '7.7')
        self.assertEqual([r.state.api_request_count for r in results], [3,3,1,4])
        self.assertEqual(len({r.state.task_id for r in results}), 4)
        self.assertEqual(len(self.app.session.recent_turns), 2)
        self.assertIsNone(self.app.session.pending_question)
        self.assertEqual(len(self.app.budget.events), 11)

    def test_multiple_companies_is_scope_not_ambiguity_and_selection_continues(self):
        result = self.app.ask('CVS 和 UNH 2025 Q2 的合并总营收是多少？')
        self.assertEqual(result.category, 'unsupported_capability')
        self.assertEqual(result.state.tool_call_count, 0)
        self.assertEqual(self.app.session.pending_companies, ('CVS','UNH'))
        self.assertIsNotNone(self.app.session.pending_question)
        client = app.IntegratedFakeClient(app.fixture())
        resumed = self.app.ask('先查 CVS', fake_client=client)
        context = json.loads(client.requests[0]['input'][0]['content'])['session']
        self.assertEqual(context['pending_companies'], ['CVS','UNH'])
        self.assertEqual(context['current_topic']['year'], 2025)
        self.assertEqual(resumed.category, 'answer')
        self.assertEqual(self.app.session.pending_companies, ())

    def test_true_ambiguity_keeps_candidates_without_tools(self):
        parsed = {**app.fixture(), 'company':None, 'request_scope':'ambiguous',
            'candidate_companies':['CVS','UNH'], 'needs_clarification':True,
            'clarification_question':'那家公司指 CVS 还是 UNH？'}
        result = self.ask(parsed)
        self.assertEqual(result.category, 'ambiguity')
        self.assertEqual(self.app.session.pending_companies, ('CVS','UNH'))
        self.assertIsNone(self.app.session.company)
        self.assertEqual(result.state.api_request_count, 1)
        self.assertIsNone(result.state.evidence)

    def test_unsupported_metric_percentage_and_comparison(self):
        for parsed in (
            {**app.fixture(), 'metric':'net_income'},
            {**app.fixture(), 'request_scope':'unsupported', 'intent':'unsupported'},
            {**app.fixture(intent='compare'), 'comparison_period':{'year':2023,'quarter':2}},
        ):
            with self.subTest(parsed=parsed):
                result = self.ask(parsed)
                self.assertEqual(result.category, 'unsupported_capability')
                self.assertEqual(result.state.tool_call_count, 0)

    def test_other_company_period_are_insufficient_not_unsupported(self):
        for parsed in (app.fixture(company='UNH'),app.fixture(company='AMZN'),app.fixture(year=2023)):
            result = self.ask(parsed)
            self.assertEqual(result.category, 'insufficient_evidence')
            self.assertEqual(result.state.tool_call_count, 1)
            self.assertIsNone(result.state.evidence)
        self.assertFalse((self.directory/'memory').exists())

    def test_schema_failure_stops_without_retry(self):
        parsed = {**app.fixture(),'request_scope':'multiple_companies','candidate_companies':['CVS','UNH']}
        result = self.ask(parsed)
        self.assertEqual(result.category, 'failed')
        self.assertEqual(result.state.failure_stage, 'final_validation')
        self.assertTrue(self.app.stopped)
        with self.assertRaises(agent.StopAgent): self.ask()
        self.assertEqual(len(self.app.budget.events), 1)

    def test_tool_failure_keeps_safe_state_and_stops(self):
        with patch.object(agent, 'search_report', side_effect=RuntimeError('credential-marker')):
            result = self.ask()
        self.assertEqual(result.state.failure_stage, 'tool_execution')
        self.assertEqual(result.state.pending_tool_call['name'], 'search_report')
        self.assertNotIn('credential-marker', result.answer)
        self.assertTrue(self.app.stopped)
        self.assertEqual(load_state_snapshot(self.directory/'snapshots'/f'{result.state.task_id}.json').status, 'failed')

    def test_api_error_stops_and_hides_body(self):
        fake = app.IntegratedFakeClient(app.fixture())
        with patch.object(fake, 'create', side_effect=APIConnectionError(
                message='credential-marker',request=httpx.Request('POST','https://api.openai.com/v1/responses'))):
            result = self.app.ask('test', fake_client=fake)
        self.assertEqual(result.state.api_request_count, 1)
        self.assertTrue(self.app.stopped)
        self.assertNotIn('credential-marker', result.answer)
        self.assertEqual(result.state.failure_stage, 'api_request')

    def test_global_request_budget_is_not_reset_between_tasks(self):
        target = app.FinancialAgent(directory=self.directory, caps={**app.CAPS,'requests':3})
        self.assertEqual(self.ask(target=target).category, 'answer')
        self.assertEqual(self.ask(target=target).category, 'failed')
        self.assertEqual(len(target.budget.events), 3)
        self.assertTrue(target.stopped)

    def test_global_token_budget_prevents_first_network_call(self):
        target = app.FinancialAgent(directory=self.directory, caps={**app.CAPS,'total_tokens':1})
        result = self.ask(target=target)
        self.assertEqual(result.category, 'failed')
        self.assertEqual(len(target.budget.events), 0)

    def test_task_limit_still_counts_understanding(self):
        target = app.FinancialAgent(directory=self.directory, caps={**app.CAPS,'requests_per_task':2})
        result = self.ask(target=target)
        self.assertEqual(result.state.api_request_count, 2)
        self.assertEqual(result.state.tool_call_count, 1)
        self.assertEqual(result.state.failure_stage, 'budget_check')

    def test_unexpected_usage_stops_before_any_tool(self):
        from mock_responses import tool_response
        for mode in ('missing','inconsistent','output_over_limit','global_over_limit'):
            with self.subTest(mode=mode):
                target=app.FinancialAgent(directory=self.directory/mode)
                fake=app.IntegratedFakeClient(app.fixture())
                reply=tool_response('search_report', {'question':'CVS 2025 Q2'})
                if mode=='missing': reply.usage=None
                elif mode=='inconsistent': reply.usage.total_tokens=1
                elif mode=='output_over_limit':
                    reply.usage.output_tokens=1025; reply.usage.total_tokens=1125
                else:
                    reply.usage.input_tokens=31000; reply.usage.total_tokens=31020
                with patch.object(fake,'create',return_value=reply),patch.object(agent,'execute_tool') as execute:
                    result=target.ask('test',fake_client=fake)
                self.assertTrue(target.stopped)
                self.assertEqual(result.category,'failed')
                execute.assert_not_called()
                self.assertEqual(len(target.budget.events),1)

    def test_final_wrong_amount_and_citation_cannot_be_persisted_as_memory(self):
        from mock_responses import MockClient, final_response
        for final in (final_response('search','99.9','S1'),final_response('search','98.9','S999')):
            target=app.FinancialAgent(directory=self.directory/final.output_text[-12:].encode().hex())
            fake=app.IntegratedFakeClient(app.fixture())
            fake.delegate=MockClient('search',query=agent.ResearchQuery('CVS',app.METRIC,2025,2,'search'))
            original_create=fake.delegate.create
            def create(**payload):
                if any(i.get('type')=='function_call_output' for i in payload['input']): return final
                return original_create(**payload)
            with patch.object(fake.delegate,'create',side_effect=create):
                result=target.ask('test',fake_client=fake)
            self.assertEqual(result.category,'failed')
            self.assertIsNotNone(result.state.final_validation_diagnostic)
            self.assertFalse((target.directory/'memory').exists())

    def test_memory_never_substitutes_for_fresh_evidence(self):
        self.ask()
        with patch.object(agent, 'search_report', return_value=None):
            result = self.ask()
        self.assertEqual(result.category, 'insufficient_evidence')
        self.assertIsNone(result.state.evidence)
        self.assertNotIn('98.9', result.answer)

    def test_corrupt_retrieval_fields_stop_before_evidence_or_memory(self):
        evidence = agent.search_report('CVS total revenues 2Q 2025 2Q 2024')
        for field, value in [('revenue_2025_q2','NaN'), ('revenue_2024_q2',91.2),
                             ('unit','百万美元'), ('citation','S9'), ('page',7),
                             ('page',True), ('source_title','untrusted title'), ('source_url','https://example.com')]:
            with self.subTest(field=field, value=value):
                target = app.FinancialAgent(directory=self.directory/str(value).encode().hex())
                with patch.object(agent, 'search_report', return_value={**evidence, field:value}):
                    result = self.ask(target=target)
                self.assertEqual(result.category,'failed')
                self.assertEqual(result.state.failure_stage,'tool_execution')
                self.assertEqual(result.state.api_request_count,2)
                self.assertIsNone(result.state.evidence)
                self.assertFalse((target.directory/'memory').exists())
                self.assertTrue(target.stopped)

    def test_sessions_isolated_and_storage_corruption_stops(self):
        self.ask()
        other = app.FinancialAgent(directory=self.directory)
        self.assertIsNone(other.session.company)
        memory = next((self.directory/'memory').rglob('*.json'))
        memory.write_text('{bad json',encoding='utf-8')
        result = self.ask(target=other)
        self.assertEqual(result.category, 'failed')
        self.assertEqual(result.state.tool_call_count, 0)

    def test_persistence_failure_stops_without_repeating_tools(self):
        with patch('financial_agent.save_state_snapshot', side_effect=OSError('private path')):
            result = self.ask()
        self.assertEqual(result.category,'persistence_error')
        self.assertTrue(self.app.stopped)
        self.assertNotIn('private path',result.answer)

    def test_cli_offline_and_unconfirmed_live_never_read_key(self):
        class NoKeys(dict):
            def __getitem__(self, key):
                if key == 'OPENAI_API_KEY': raise AssertionError('No key reads')
                return super().__getitem__(key)
        with patch('financial_agent.os.environ', NoKeys()), patch('financial_agent.STORAGE', self.directory):
            self.assertEqual(app.main(['--live']), 1)
            # Patch constructor default explicitly: Python default arguments bind at definition time.
            with patch('financial_agent.FinancialAgent', side_effect=lambda **kw: original(directory=self.directory,**kw)):
                self.assertEqual(app.main(['--demo']),0)
        self.assertIn('simulated',self.output.getvalue())


original = app.FinancialAgent
if __name__ == '__main__': unittest.main()
