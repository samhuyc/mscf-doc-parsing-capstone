from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import socket
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError
import api_demo as agent
import llm_session_demo as llm
from mock_responses import MockClient
from evaluation import live_runner


class OutputGuardrailTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.enterContext(redirect_stdout(self.output))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")))
        self.enterContext(patch("openai.OpenAI", side_effect=AssertionError("Live client forbidden")))

    def run_final(self, final):
        client, state = MockClient("compare"), agent.AgentState()
        original = client.create
        def substitute(**payload):
            response = original(**payload)
            if response.output_text:
                response.output[0].content[0].text = final if isinstance(final, str) else json.dumps(final)
            return response
        with patch.object(client.responses, "create", side_effect=substitute):
            try:
                answer = agent.run_agent(client, "compare", state=state)
            except agent.StopAgent:
                answer = None
        return state, client, answer

    def good(self):
        return dict(kind="compare", value="7.7", unit="十亿美元", citation="S1")

    def test_task_schemas_and_local_pydantic_have_identical_kind_constraints(self):
        base = deepcopy(agent.FINAL_FORMAT)
        for kind in agent.SCENARIOS:
            schema = agent.final_format_for(kind)
            self.assertEqual(schema["schema"]["properties"]["kind"]["enum"], [kind])
            self.assertFalse(schema["schema"]["additionalProperties"])
            self.assertEqual(set(schema["schema"]["required"]), {"kind", "value", "unit", "citation"})
            local = agent.final_result_model(kind).model_json_schema()
            self.assertEqual(local["properties"]["kind"]["const"], kind)
            self.assertEqual({k:v for k,v in local["properties"].items() if k != "kind"},
                             {k:v for k,v in schema["schema"]["properties"].items() if k != "kind"})
            with self.assertRaises(ValidationError):
                agent.final_result_model(kind).model_validate({**self.good(), "kind": "calculate" if kind != "calculate" else "search"})
        self.assertEqual(agent.FINAL_FORMAT, base)

    def test_calculate_tool_does_not_change_compare_answer_type(self):
        state, client, answer = self.run_final(self.good())
        self.assertEqual(state.status, "completed")
        self.assertIn("+7.7", answer)
        self.assertIsNone(state.final_validation_diagnostic)
        self.assertEqual(state.api_request_count, 3)
        self.assertEqual([item["name"] for item in state.history if item.get("type") == "function_call"],
                         ["search_report", "calculate"])
        for payload in client.requests:
            self.assertEqual(payload["text"]["format"]["schema"]["properties"]["kind"]["enum"], ["compare"])
            self.assertIn("USER TASK", payload["instructions"])
        self.assertEqual(json.loads(client.requests[-1]["input"][-1]["output"]), "7.7")

    def test_wrong_kind_stops_without_rewriting_or_retry_and_records_actual_kind(self):
        for wrong in ("calculate", "search", "insufficient"):
            final = {**self.good(), "kind": wrong}
            if wrong == "insufficient":
                final.update(value=None, unit=None, citation=None)
            with self.subTest(wrong=wrong):
                state, client, answer = self.run_final(final)
                self.assertIsNone(answer)
                self.assertIsNone(state.final_answer)
                self.assertEqual(state.calculation, "7.7")
                self.assertEqual(len(client.requests), 3)
                diagnostic = state.final_validation_diagnostic
                self.assertEqual(diagnostic["expected_kind"], "compare")
                self.assertEqual(diagnostic["actual_kind"], wrong)
                self.assertEqual(diagnostic["validation_rule"], "kind_matches_task")
                self.assertEqual(diagnostic["stage"], state.failure_stage)
                self.assertEqual(state.failure_stage, "final_validation")
                self.assertEqual(final["kind"], wrong)

    def test_correct_kind_wrong_amount_fails_evidence_validation(self):
        final = {**self.good(), "value": "999"}
        agent.final_result_model("compare").model_validate(final)
        state, _, _ = self.run_final(final)
        self.assertEqual(state.final_validation_diagnostic["validation_rule"], "amount_matches_tool")
        self.assertEqual(state.final_validation_diagnostic["structured_summary"]["value"], "<redacted>")

    def test_correct_amount_wrong_citation_fails_evidence_validation(self):
        state, _, _ = self.run_final({**self.good(), "citation": "S9"})
        diagnostic = state.final_validation_diagnostic
        self.assertEqual(diagnostic["validation_rule"], "citation_matches_evidence")
        self.assertEqual(diagnostic["structured_summary"]["citation"], "S9")
        self.assertEqual(diagnostic["structured_summary"]["value"], "7.7")

    def test_missing_and_wrong_types_rejected_with_safe_schema_rules(self):
        invalid = [{k:v for k,v in self.good().items() if k != "unit"},
                   {**self.good(), "value": 7.7}, {**self.good(), "citation": {}}, []]
        for final in invalid:
            with self.subTest(final=final):
                state, _, _ = self.run_final(final)
                self.assertEqual(state.final_validation_diagnostic["validation_rule"], "schema_contract")
                self.assertTrue(state.final_validation_diagnostic["schema_issues"])

    def test_invalid_json_logs_no_raw_body(self):
        state, _, _ = self.run_final("secret-canary-not-json")
        self.assertEqual(state.final_validation_diagnostic["validation_rule"], "valid_json")
        self.assertNotIn("secret-canary", self.output.getvalue())

    def test_diagnostics_redact_unknown_keys_credentials_numbers_and_reasoning(self):
        canary = "secret-canary-do-not-log"
        final = dict(kind=canary, value="12345678901234567890", unit=canary, citation=canary,
                     **{canary: {"api_key": canary}, "reasoning": canary})
        state, _, _ = self.run_final(final)
        diagnostic = state.final_validation_diagnostic
        serialized = json.dumps(diagnostic) + self.output.getvalue() + state.error
        self.assertNotIn(canary, serialized)
        self.assertNotIn("12345678901234567890", serialized)
        self.assertEqual(diagnostic["actual_kind"], "<redacted>")
        self.assertEqual(diagnostic["structured_summary"]["extra_field_count"], 2)
        self.assertTrue(all(set(issue) == {"field", "type"} for issue in diagnostic["schema_issues"]))

    def test_retest_context_does_not_restore_prior_state_or_evidence(self):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path = folder/'synthetic_prior.json'
        path.write_text(json.dumps({'turns':[
            {'case_id':'L04', 'turn':1, 'question':'CVS 的合并总营收增长了多少？',
             'observed':{'behavior':'clarify','task_id':'historical-test-task','evidence':{'amount':'999'}}},
            {'case_id':'L04', 'turn':2, 'question':'我指 2025 Q2 比 2024 Q2'}]}), encoding='utf-8')
        original = llm.compare_retest_context
        self.enterContext(patch.object(llm, 'compare_retest_context', side_effect=lambda: original(path)))
        session, question = llm.compare_retest_context()
        self.assertEqual(question, "我指 2025 Q2 比 2024 Q2")
        self.assertEqual(session.recent_turns[0].question, "CVS 的合并总营收增长了多少？")
        self.assertEqual(session.recent_turns[0].answer, "")
        self.assertIsNone(session.company)
        with patch("sys.argv", ["llm_session_demo.py", "--compare-retest"]):
            self.assertEqual(llm.main(), 0)
        output = self.output.getvalue()
        self.assertIn('"requests": 4', output)
        self.assertIn('"total_tokens": 480', output)

    def test_evaluation_persists_safe_failure_diagnostic(self):
        suite, dataset, digest = live_runner.load_suite()
        def wrong_final(case_id, index):
            client = llm.FakeUnderstandingClient(llm.demo_fixtures()[0])
            original = client.create
            def create(**payload):
                response = original(**payload)
                if payload["text"]["format"]["name"] == "financial_answer" and response.output_text:
                    response.output[0].content[0].text = json.dumps(dict(kind="calculate", value="98.9", unit="十亿美元", citation="S1"))
                return response
            client.create = create
            return client
        report = live_runner.evaluate(suite, dataset, digest, fake_factory=wrong_final)
        diagnostic = report["turns"][0]["observed"]["final_validation_diagnostic"]
        self.assertEqual(diagnostic["actual_kind"], "calculate")
        self.assertEqual(diagnostic["expected_kind"], "search")
        self.assertEqual(report["requests"], 3)
        self.assertTrue(report["stopped_early"])


if __name__ == "__main__":
    unittest.main()
