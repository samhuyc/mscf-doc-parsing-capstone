from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
import socket
import unittest
from unittest.mock import patch

import api_demo as agent
import llm_session_demo as llm
from mock_responses import tool_response
from session_demo import Session, resolve_question


class LLMUnderstandingTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.enterContext(redirect_stdout(self.output))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")))
        self.enterContext(patch("openai.OpenAI", side_effect=AssertionError("Live constructor forbidden")))
        # GPT understanding must not secretly fall back to the old keyword parser.
        self.enterContext(patch("session_demo.resolve_question", side_effect=AssertionError("Rule parser forbidden")))

    def run_question(self, parsed=None, question=llm.QUESTIONS[0], session=None, **kwargs):
        client = llm.FakeUnderstandingClient(parsed if parsed is not None else llm.demo_fixtures()[0])
        result = llm.run_llm_turn(session if session is not None else Session(), question, client, **kwargs)
        return result, client

    def test_three_natural_turns_retrieve_fresh_then_clarify_period_pair(self):
        session = Session()
        results, clients = [], []
        with patch.object(agent, "search_report", wraps=agent.search_report) as search:
            for question, parsed in zip(llm.QUESTIONS, llm.demo_fixtures()):
                result, client = self.run_question(parsed, question, session)
                results.append(result)
                clients.append(client)
        self.assertEqual(search.call_count, 2)
        self.assertIn("98.9", results[0].answer)
        self.assertIn("91.2", results[1].answer)
        self.assertEqual(results[2].outcome, "clarification")
        self.assertEqual([r.state.api_request_count for r in results], [3, 3, 1])
        self.assertEqual([r.state.total_tokens for r in results], [360, 360, 120])
        self.assertEqual(len({r.state.task_id for r in results}), 3)
        self.assertIsNone(results[2].state.evidence)
        self.assertEqual(session.year, 2024)
        self.assertEqual(len(session.recent_turns), 2)
        for client in clients:
            context = json.loads(client.requests[0]["input"][0]["content"])
            self.assertNotIn("98.9", json.dumps(context))
            self.assertNotIn("91.2", json.dumps(context))
            self.assertNotIn("tools", client.requests[0])
        self.assertEqual(json.loads(clients[1].requests[0]["input"][0]["content"])["session"]["current_topic"]["year"], 2025)

    def test_clear_comparison_counts_understanding_and_all_tools(self):
        parsed = {**llm.demo_fixtures()[0], "intent": "compare",
                  "comparison_period": {"year": 2024, "quarter": 2}}
        result, client = self.run_question(parsed, "请比较 CVS 2025 Q2 和 2024 Q2 合并总营收增加的金额")
        self.assertEqual(result.outcome, "completed")
        self.assertIn("+7.7", result.answer)
        self.assertIn(agent.PUBLIC_REPORT, result.answer)
        self.assertEqual((result.state.api_request_count, result.state.tool_call_count), (4, 2))
        self.assertEqual((result.state.input_tokens, result.state.output_tokens, result.state.total_tokens), (400, 80, 480))
        self.assertEqual(json.loads(client.requests[-1]["input"][-1]["output"]), "7.7")
        self.assertEqual(client.requests[-1]["input"][-1]["call_id"], "call_2")

    def test_company_and_period_switch_and_sessions_are_isolated(self):
        first_session, other = Session(), Session()
        self.run_question(session=first_session)
        parsed = {**llm.demo_fixtures()[0], "company": "UNH", "period": {"year": 2024, "quarter": 3}}
        result, _ = self.run_question(parsed, "换成 UNH，查二零二四年第三季度", first_session)
        self.assertEqual((first_session.company, first_session.year, first_session.quarter), ("UNH", 2024, 3))
        self.assertEqual(result.answer, "证据不足，无法回答。")
        self.assertIsNone(result.state.evidence)
        self.assertIsNone(other.company)
        self.assertEqual(len(other.recent_turns), 0)

    def test_missing_slots_and_multiple_company_period_metric_ambiguity(self):
        for question in ("那去年同期呢？", "CVS 和 UNH 那家公司营收多少？",
                         "二季度还是三季度的营收呢？", "营收或利润增长多少？"):
            parsed = dict(company=None, metric=None, period=None, comparison_period=None, intent=None,
                          needs_clarification=True, clarification_question="请明确公司、季度和指标。")
            session = Session()
            with self.subTest(question=question), patch.object(agent, "execute_tool") as execute:
                result, _ = self.run_question(parsed, question, session)
            self.assertEqual(result.outcome, "clarification")
            self.assertEqual(result.state.status, "completed")
            self.assertEqual(result.state.api_request_count, 1)
            execute.assert_not_called()
            self.assertIsNone(session.company)

    def test_wrong_schema_types_missing_fields_and_invented_amount_rejected(self):
        base = llm.demo_fixtures()[0]
        invalid = [{k: v for k, v in base.items() if k != "company"},
                   {**base, "needs_clarification": "false"},
                   {**base, "period": {"year": "2025", "quarter": 2}},
                   {**base, "period": {"year": 2025, "quarter": 5}},
                   {**base, "value": "98.9"},
                   {**base, "needs_clarification": True},
                   {**base, "company": None}]
        for parsed in invalid:
            with self.subTest(parsed=parsed), patch.object(agent, "execute_tool") as execute:
                result, client = self.run_question(parsed)
                self.assertEqual(result.outcome, "failed")
                self.assertIn("Schema", result.answer)
                self.assertEqual(len(client.requests), 1)
                execute.assert_not_called()

    def test_unsupported_metric_and_comparison_not_silently_rewritten(self):
        base = llm.demo_fixtures()[0]
        for parsed in ({**base, "metric": "net_income"}, {**base, "intent": "unsupported"},
                       {**base, "intent": "compare", "comparison_period": {"year": 2023, "quarter": 2}}):
            session = Session()
            with patch.object(agent, "execute_tool") as execute:
                result, _ = self.run_question(parsed, session=session)
            self.assertEqual(result.outcome, "failed")
            self.assertIsNone(session.company)
            execute.assert_not_called()

    def test_shared_request_cap_not_reset_after_understanding(self):
        result, client = self.run_question(limits=replace(llm.SESSION_LIMITS, requests=1))
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(result.state.api_request_count, 1)
        self.assertEqual(result.state.tool_call_count, 0)
        self.assertEqual(result.state.total_tokens, 120)
        self.assertEqual(result.outcome, "failed")
        self.assertEqual(result.state.failure_stage, "budget_check")

    def test_total_token_budget_and_context_budget_stop_before_request(self):
        for kwargs in ({"limits": replace(llm.SESSION_LIMITS, total_tokens=100)}, {"context_budget": 100}):
            with self.subTest(kwargs=kwargs):
                result, client = self.run_question(**kwargs)
                self.assertEqual(result.outcome, "failed")
                self.assertEqual(client.requests, [])

    def test_usage_consumed_in_understanding_prevents_financial_request(self):
        client = llm.FakeUnderstandingClient(llm.demo_fixtures()[0])
        original = client.create
        def high_usage(**payload):
            response = original(**payload)
            response.usage.input_tokens = 9980
            response.usage.total_tokens = 10000
            return response
        with patch.object(client, "create", side_effect=high_usage):
            result = llm.run_llm_turn(Session(), llm.QUESTIONS[0], client)
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(result.state.total_tokens, 10000)
        self.assertEqual(result.state.failure_stage, "budget_check")

    def test_understanding_must_not_execute_a_tool(self):
        client = llm.FakeUnderstandingClient(llm.demo_fixtures()[0])
        with patch.object(client, "create", return_value=tool_response("calculate", {"a": "0.3", "b": "0.2", "operation": "subtract"})), \
                patch.object(agent, "execute_tool") as execute:
            result = llm.run_llm_turn(Session(), llm.QUESTIONS[0], client)
        self.assertEqual(result.outcome, "failed")
        self.assertEqual(result.state.api_request_count, 1)
        execute.assert_not_called()

    def test_invalid_json_is_rejected_without_a_tool(self):
        client = llm.FakeUnderstandingClient(llm.demo_fixtures()[0])
        original = client.create
        def broken(**payload):
            response = original(**payload)
            response.output[0].content[0].text = "not JSON"
            return response
        with patch.object(client, "create", side_effect=broken), patch.object(agent, "execute_tool") as execute:
            result = llm.run_llm_turn(Session(), llm.QUESTIONS[0], client)
        self.assertEqual(result.outcome, "failed")
        self.assertIn("Schema", result.answer)
        execute.assert_not_called()

    def test_external_failure_is_safe(self):
        client = llm.FakeUnderstandingClient(llm.demo_fixtures()[0])
        with patch.object(client, "create", side_effect=RuntimeError("private credential data")):
            result = llm.run_llm_turn(Session(), llm.QUESTIONS[0], client)
        self.assertEqual(result.outcome, "failed")
        self.assertNotIn("private credential", self.output.getvalue())
        self.assertEqual(result.state.api_request_count, 1)

    def test_explicit_clarification_can_continue_with_new_state_and_evidence(self):
        session = Session()
        prior, _ = self.run_question(llm.demo_fixtures()[2], llm.QUESTIONS[2], session)
        parsed = {**llm.demo_fixtures()[0], "intent": "compare",
                  "comparison_period": {"year": 2024, "quarter": 2}}
        result, _ = self.run_question(parsed, "我是说 CVS 2025 Q2 相比 2024 Q2 的合并总营收增加金额", session)
        self.assertNotEqual(prior.state.task_id, result.state.task_id)
        self.assertIn("+7.7", result.answer)
        self.assertEqual(result.state.api_request_count, 4)
        self.assertIsNone(prior.state.evidence)

    def test_incomplete_response_or_missing_usage_stops_understanding(self):
        for change in ("status", "usage"):
            client = llm.FakeUnderstandingClient(llm.demo_fixtures()[0])
            original = client.create
            def incomplete(**payload):
                response = original(**payload)
                setattr(response, change, "incomplete" if change == "status" else None)
                return response
            with self.subTest(change=change), patch.object(client, "create", side_effect=incomplete):
                result = llm.run_llm_turn(Session(), llm.QUESTIONS[0], client)
            self.assertEqual(result.outcome, "failed")
            self.assertEqual(result.state.api_request_count, 1)
            self.assertEqual(result.state.tool_call_count, 0)

    def test_rule_baseline_remains_available_and_cli_is_offline_by_default(self):
        baseline = resolve_question("CVS 2025 Q2 的合并总营收是多少？", Session())
        self.assertEqual(baseline.year, 2025)
        with patch.object(llm.os, "environ", {}), patch("sys.argv", ["llm_session_demo.py"]):
            self.assertEqual(llm.main(), 0)
        with patch.object(llm.os, "environ", {}), patch("sys.argv", ["llm_session_demo.py", "--live"]):
            self.assertEqual(llm.main(), 1)


if __name__ == "__main__":
    unittest.main()
