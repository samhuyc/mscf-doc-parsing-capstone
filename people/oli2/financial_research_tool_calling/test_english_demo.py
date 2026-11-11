from contextlib import redirect_stdout
import io
from pathlib import Path
import re
import socket
import tempfile
import unittest
from unittest.mock import patch

import api_demo as agent
import financial_agent as app


class EnglishDemoTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden')))
        self.enterContext(patch('openai.OpenAI', side_effect=AssertionError('Live client forbidden')))
        self.enterContext(patch('session_demo.resolve_question', side_effect=AssertionError('Rules forbidden')))
        original = app.FinancialAgent
        self.enterContext(patch.object(app, 'FinancialAgent', side_effect=lambda **kwargs:
            original(directory=self.folder, **kwargs)))

    def run_cli(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = app.main(list(args))
        return code, output.getvalue()

    def assert_english(self, output):
        self.assertIsNone(re.search(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]', output))
        self.assertNotIn('\\u5341', output)  # Do not hide Chinese units with JSON escaping.

    def test_full_demo_uses_real_tools_and_prints_only_english(self):
        with patch.object(agent, 'search_report', wraps=agent.search_report) as search, \
             patch.object(agent, 'calculate', wraps=agent.calculate) as calculate:
            code, output = self.run_cli('--demo-en')
        self.assertEqual(code, 0)
        self.assert_english(output)
        self.assertEqual(search.call_count, 3)
        calculate.assert_called_once_with(a='98.9', b='91.2', operation='subtract')
        for question in app.ENGLISH_DEMO_QUESTIONS: self.assertIn(question, output)
        for text in ('OFFLINE DEMO', 'Fake Responses', 'No live GPT requests',
                     'CVS Q2 2025 consolidated revenue: $98.9 billion',
                     'CVS Q2 2024 consolidated revenue: $91.2 billion',
                     'Year-over-year increase: approximately $7.7 billion',
                     app.ENGLISH_CLARIFICATION, 'PDF page 6', agent.PUBLIC_REPORT,
                     '"requests": 11', '"total_tokens": 1320', '"usage_kind": "simulated"'):
            self.assertIn(text, output)

    def test_display_numbers_follow_tool_results_not_fixed_demo_values(self):
        evidence = agent.search_report('CVS total revenues 2Q 2025 2Q 2024')
        with patch.object(agent, 'search_report', return_value={**evidence,
                'revenue_2025_q2': '100.0', 'revenue_2024_q2': '90.0'}):
            code, output = self.run_cli('--demo-en')
        self.assertEqual(code, 0)
        self.assertIn('$100.0 billion', output)
        self.assertIn('$90.0 billion', output)
        self.assertIn('$10.0 billion', output)
        self.assertNotIn('$98.9', output)
        self.assertNotIn('$7.7', output)
        self.assert_english(output)

    def test_chinese_demo_still_works(self):
        code, output = self.run_cli('--demo')
        self.assertEqual(code, 0)
        self.assertIn('十亿美元', output)
        self.assertIn('+7.7', output)
        self.assertIn('你指 2025 Q2', output)

    def test_tool_failure_has_safe_english_error_and_stops(self):
        with patch.object(agent, 'search_report', side_effect=RuntimeError('中文敏感错误')) as search:
            code, output = self.run_cli('--demo-en')
        self.assertEqual(code, 1)
        self.assert_english(output)
        self.assertIn('Tool execution or evidence validation failed', output)
        self.assertIn('no retry', output)
        self.assertEqual(search.call_count, 1)
        self.assertNotIn('User: '+app.ENGLISH_DEMO_QUESTIONS[1], output)

    def test_budget_and_storage_failure_are_english(self):
        for failure in ('budget', 'storage'):
            with self.subTest(failure=failure):
                if failure == 'budget':
                    original_ask = app.FinancialAgent.side_effect
                    with patch.object(app, 'FinancialAgent', side_effect=lambda **kw:
                            original_ask(caps={**app.CAPS, 'requests_per_task': 2}, **kw)):
                        code, output = self.run_cli('--demo-en')
                    self.assertIn('budget', output)
                else:
                    with patch.object(app, 'save_state_snapshot', side_effect=OSError('中文路径')):
                        code, output = self.run_cli('--demo-en')
                    self.assertIn('storage failed', output)
                self.assertEqual(code, 1)
                self.assert_english(output)

    def test_wrong_amount_and_citation_are_rejected_before_english_answer(self):
        from mock_responses import final_response
        for response in (final_response('search', '999', 'S1'), final_response('search', '98.9', 'S9')):
            with self.subTest(response=response.output_text), patch('mock_responses.final_response', return_value=response):
                code, output = self.run_cli('--demo-en')
            self.assertEqual(code, 1)
            self.assert_english(output)
            self.assertIn('financial answer validation failed', output)
            self.assertNotIn('consolidated revenue: $', output)

    def test_insufficient_evidence_is_english_without_fabricated_amounts(self):
        with patch.object(agent, 'search_report', return_value=None):
            code, output = self.run_cli('--demo-en')
        self.assertEqual(code, 0)
        self.assert_english(output)
        self.assertIn('Insufficient evidence', output)
        self.assertNotIn('$98.9', output)
        self.assertNotIn('$7.7', output)

    def test_live_flags_rejected_and_offline_never_reads_key(self):
        class NoKeys(dict):
            def __getitem__(self, key):
                if key == 'OPENAI_API_KEY': raise AssertionError('Key access forbidden')
                return super().__getitem__(key)
        with patch('financial_agent.os.environ', NoKeys()):
            for flags in (('--live',), ('--confirm-paid-api',), ('--live', '--confirm-paid-api')):
                code, output = self.run_cli('--demo-en', *flags)
                self.assertEqual(code, 1)
                self.assert_english(output)
                self.assertIn('offline only', output)
            code, output = self.run_cli('--demo-en')
        self.assertEqual(code, 0)
        self.assert_english(output)


if __name__ == '__main__': unittest.main()
