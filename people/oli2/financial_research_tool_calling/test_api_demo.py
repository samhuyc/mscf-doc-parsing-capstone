from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
import socket
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pydantic import ValidationError

import api_demo as agent
from mock_responses import MockClient, final_response, tool_response


class AgentTests(unittest.TestCase):
    def setUp(self):
        # Any accidental network connection fails the offline test suite.
        self.network = patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.output = io.StringIO()
        self.quiet = redirect_stdout(self.output)
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)

    def test_four_scenarios_real_tools_mock_api(self):
        for scenario, calls, expected in [
            ("search", ["search_report"], "98.9"),
            ("compare", ["search_report", "calculate"], "+7.7"),
            ("calculate", ["calculate"], "0.1"),
            ("insufficient", ["search_report"], "证据不足"),
        ]:
            with self.subTest(scenario=scenario):
                client = MockClient(scenario)
                with patch.object(agent, "execute_tool", wraps=agent.execute_tool) as execute:
                    answer = agent.run_agent(client, scenario)
                self.assertEqual([call.args[0] for call in execute.call_args_list], calls)
                self.assertIn(expected, answer)
                if scenario in {"search", "compare"}:
                    self.assertIn("[S1]", answer)
                    self.assertIn(agent.PUBLIC_REPORT, answer)
                for request in client.requests:
                    self.assertEqual(request["model"], "gpt-6.1-sol")
                    self.assertFalse(request["store"])
                    self.assertFalse(request["parallel_tool_calls"])

    def test_tool_results_call_id_and_export_allowlist(self):
        client = MockClient()
        agent.run_agent(client)
        returned = client.requests[1]["input"][-1]
        self.assertEqual(returned["call_id"], "call_1")
        evidence = json.loads(returned["output"])
        self.assertEqual(set(evidence), set(agent.EXPORT_FIELDS))
        self.assertNotIn("chunk_id", evidence)
        self.assertNotIn("content", evidence)
        self.assertEqual(client.requests[2]["input"][-1]["call_id"], "call_2")
        self.assertEqual(json.loads(client.requests[2]["input"][-1]["output"]), "7.7")

    def test_invalid_tools_and_arguments(self):
        for name, arguments in [
            ("exec", {"code": "print(1)"}),
            ("calculate", {"a": 1, "b": "2", "operation": "subtract"}),
            ("calculate", {"a": "NaN", "b": "2", "operation": "subtract"}),
            ("calculate", {"a": "0.3", "b": "0.2", "operation": "multiply"}),
            ("calculate", {"a": "4", "b": "2", "operation": "subtract"}),
            ("search_report", {"question": "CVS", "extra": "unexpected"}),
        ]:
            with self.subTest(name=name, arguments=arguments), self.assertRaises(agent.StopAgent):
                agent.execute_tool(name, arguments, "calculate", None)

    def test_evidence_required_before_calculation(self):
        with self.assertRaises(agent.StopAgent):
            agent.execute_tool("calculate", {"a": "98.9", "b": "91.2", "operation": "subtract"}, "compare", None)

    def test_fabricated_final_answer_rejected(self):
        client = SimpleNamespace(responses=SimpleNamespace(
            create=lambda **kwargs: final_response("compare", "123", "S1")))
        with self.assertRaises(agent.StopAgent):
            agent.run_agent(client)

    def test_wrong_citation_and_value_rejected(self):
        evidence = agent.execute_tool("search_report", {"question": "CVS total revenues 2Q 2025 2Q 2024"}, "search", None)
        for value, citation in [("999", "S1"), ("98.9", "S9")]:
            with self.subTest(value=value), self.assertRaises(agent.StopAgent):
                agent.render_answer(dict(kind="search", value=value, unit="十亿美元", citation=citation), "search", evidence, None)

    def run_fake_final(self, final):
        """Use real search evidence, then substitute only the fake model's final text."""
        client = MockClient("search")
        original_create = client.responses.create
        def create(**payload):
            result = original_create(**payload)
            if result.output_text:
                result.output[0].content[0].text = json.dumps(final)
            return result
        with patch.object(client.responses, "create", side_effect=create):
            return agent.run_agent(client, "search")

    def test_pydantic_normal_result_and_generated_schema(self):
        final = dict(kind="search", value="98.9", unit="十亿美元", citation="S1")
        result = agent.FinancialResearchResult.model_validate(final)
        self.assertEqual(result.value, "98.9")
        self.assertEqual(result.model_dump(), final)
        self.assertIn("98.9 十亿美元", self.run_fake_final(final))
        self.assertEqual(agent.FINAL_FORMAT["schema"], agent.FinancialResearchResult.model_json_schema())
        self.assertEqual(set(agent.FINAL_FORMAT["schema"]["required"]), set(final))
        self.assertFalse(agent.FINAL_FORMAT["schema"]["additionalProperties"])

    def test_pydantic_missing_fields_through_loop(self):
        final = dict(kind="search", value="98.9", unit="十亿美元", citation="S1")
        for field in final:
            incomplete = {key: value for key, value in final.items() if key != field}
            with self.subTest(field=field), self.assertRaisesRegex(agent.StopAgent, "Schema Validation"):
                self.run_fake_final(incomplete)

    def test_pydantic_wrong_types_and_extra_fields_through_loop(self):
        for field, value in [
            ("value", 98.9), ("value", True), ("value", ["98.9"]),
            ("unit", 1000000000), ("citation", {"id": "S1"}),
            ("extra", "unexpected"),
        ]:
            final = dict(kind="search", value="98.9", unit="十亿美元", citation="S1")
            final[field] = value
            with self.subTest(field=field, value=value), self.assertRaisesRegex(agent.StopAgent, "Schema Validation"):
                self.run_fake_final(final)

    def test_schema_valid_wrong_citation_fails_evidence_validation(self):
        final = dict(kind="search", value="98.9", unit="十亿美元", citation="S9")
        agent.FinancialResearchResult.model_validate(final)
        with self.assertRaisesRegex(agent.StopAgent, "Citation"):
            self.run_fake_final(final)

    def test_schema_valid_wrong_amount_fails_evidence_validation(self):
        final = dict(kind="search", value="999", unit="十亿美元", citation="S1")
        agent.FinancialResearchResult.model_validate(final)
        with self.assertRaisesRegex(agent.StopAgent, "最终数值"):
            self.run_fake_final(final)

    def test_schema_valid_wrong_unit_fails_evidence_validation(self):
        final = dict(kind="search", value="98.9", unit="无单位", citation="S1")
        agent.FinancialResearchResult.model_validate(final)
        with self.assertRaisesRegex(agent.StopAgent, "最终单位"):
            self.run_fake_final(final)

    def test_insufficient_state_and_invalid_amount_format(self):
        final = dict(kind="insufficient", value=None, unit=None, citation=None)
        # A search with returned evidence must not silently change its answer kind.
        with self.assertRaises(agent.FinalValidationError) as stopped:
            self.run_fake_final(final)
        self.assertEqual(stopped.exception.rule, "kind_matches_task")
        self.assertEqual(agent.render_answer(final, "insufficient", None, None), "证据不足，无法回答。")
        self.assertEqual(agent.run_agent(MockClient("insufficient"), "insufficient"), "证据不足，无法回答。")
        for field, value in [("value", "98.9"), ("unit", "十亿美元"), ("citation", "S1")]:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                agent.FinancialResearchResult.model_validate({**final, field: value})
        for amount in ("NaN", "Infinity", "not a number", "", None):
            with self.subTest(amount=amount), self.assertRaisesRegex(agent.StopAgent, "Schema Validation"):
                self.run_fake_final(dict(kind="search", value=amount, unit="十亿美元", citation="S1"))

    def test_request_and_token_limits(self):
        client = MockClient()
        with self.assertRaises(agent.StopAgent):
            agent.run_agent(client, limits=replace(agent.Limits(), requests=1))
        self.assertEqual(len(client.requests), 1)
        client = MockClient()
        with self.assertRaises(agent.StopAgent):
            agent.run_agent(client, limits=replace(agent.Limits(), total_tokens=100))
        self.assertEqual(client.requests, [])

    def test_five_round_cap(self):
        counter = []
        def repeat(**kwargs):
            counter.append(1)
            return tool_response("calculate", {"a": "0.3", "b": "0.2", "operation": "subtract"}, len(counter))
        client = SimpleNamespace(responses=SimpleNamespace(create=repeat))
        with patch.object(agent, "execute_tool", wraps=agent.execute_tool) as execute:
            with self.assertRaises(agent.StopAgent):
                agent.run_agent(client, "calculate")
        self.assertEqual(execute.call_count, 5)
        self.assertEqual(len(counter), 6)

    def test_actual_usage_and_incomplete_response_stop(self):
        for change in ("usage", "status"):
            item = tool_response("calculate", {"a": "0.3", "b": "0.2", "operation": "subtract"})
            if change == "usage":
                item.usage.total_tokens = 12001
            else:
                item.status = "incomplete"
            client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: item))
            with self.subTest(change=change), patch.object(agent, "execute_tool") as execute:
                with self.assertRaises(agent.StopAgent):
                    agent.run_agent(client, "calculate")
                execute.assert_not_called()

    def test_api_access_error_stops_without_model_fallback(self):
        import httpx2
        from openai import NotFoundError
        # Synthetic HTTP objects only; construction never sends a request.
        request = httpx2.Request("POST", "https://api.openai.com/v1/responses")
        error = NotFoundError("model unavailable", response=httpx2.Response(404, request=request), body=None)
        with patch.object(MockClient, "create", side_effect=error) as create:
            with patch("sys.argv", ["api_demo.py"]):
                self.assertEqual(agent.main(), 1)
        self.assertEqual(create.call_count, 1)
        self.assertIn("HTTP 404", self.output.getvalue())

    def test_default_dry_run_never_constructs_live_client(self):
        with patch("openai.OpenAI", side_effect=AssertionError("Live client forbidden")):
            with patch("sys.argv", ["api_demo.py"]):
                self.assertEqual(agent.main(), 0)
            with patch("sys.argv", ["api_demo.py", "--live"]):
                self.assertEqual(agent.main(), 1)

    def test_smoke_cli_dry_run_without_key_access(self):
        class ForbiddenEnvironment(dict):
            def __getitem__(self, key):
                if key == "OPENAI_API_KEY":
                    raise AssertionError("Key read forbidden")
                return super().__getitem__(key)
            def get(self, key, default=None):
                if key == "OPENAI_API_KEY":
                    raise AssertionError("Key read forbidden")
                return super().get(key, default)
        with patch.object(agent.os, "environ", ForbiddenEnvironment()), \
                patch("openai.OpenAI", side_effect=AssertionError("Live client forbidden")), \
                patch("sys.argv", ["api_demo.py", "--scenario", "calculate", "--max-requests", "3"]):
            self.assertEqual(agent.main(), 0)
        output = self.output.getvalue()
        self.assertIn("FAKE", output)
        self.assertIn("Input=200, Output=40, Total=240", output)
        self.assertIn('"value": "0.1"', output)

    def test_smoke_cli_live_wiring_uses_only_fake_client_and_dummy_key(self):
        client = MockClient("calculate")
        with patch.object(agent.os, "environ", {"OPENAI_API_KEY": "offline-placeholder"}), \
                patch("openai.OpenAI") as constructor, \
                patch("sys.argv", ["api_demo.py", "--scenario", "calculate", "--live", "--confirm-paid-api"]):
            constructor.return_value.__enter__.return_value = client
            self.assertEqual(agent.main(), 0)
        constructor.assert_called_once_with(api_key="offline-placeholder",
            base_url="https://api.openai.com/v1", max_retries=0, timeout=30.0)
        self.assertEqual(len(client.requests), 2)
        for payload in client.requests:
            self.assertEqual(payload["max_output_tokens"], 1024)
            self.assertEqual(payload["service_tier"], "default")
            self.assertEqual(payload["model"], "gpt-6.1-sol")
        self.assertNotIn("offline-placeholder", self.output.getvalue())

    def test_smoke_cli_stops_repeated_tool_calls_at_three_requests(self):
        counter = []
        def repeat(**payload):
            counter.append(payload)
            return tool_response("calculate", {"a": "0.3", "b": "0.2", "operation": "subtract"}, len(counter))
        with patch.object(MockClient, "create", side_effect=repeat), \
                patch("sys.argv", ["api_demo.py", "--scenario", "calculate"]):
            self.assertEqual(agent.main(), 1)
        self.assertEqual(len(counter), 3)
        self.assertIn("总请求次数上限", self.output.getvalue())
        with patch("openai.OpenAI") as constructor, \
                patch("sys.argv", ["api_demo.py", "--max-requests", "4"]), \
                patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit):
            agent.main()
        constructor.assert_not_called()

    def test_sdk_credit_error_no_retry_with_offline_http_transport(self):
        import httpx2
        from openai import OpenAI
        requests = []
        def respond(request):
            requests.append(request)
            return httpx2.Response(429, json={"error": {
                "message": "private error body must stay hidden",
                "type": "insufficient_quota", "code": "credit_balance_exhausted"}})
        # The actual SDK serializes requests into a local fake transport. No sockets.
        with patch.object(agent.os, "environ", {"OPENAI_API_KEY": "offline-placeholder"}):
            client = OpenAI(api_key="offline-placeholder", max_retries=0,
                            base_url="https://api.openai.com/v1",
                            http_client=httpx2.Client(transport=httpx2.MockTransport(respond)))
            with patch("openai.OpenAI", return_value=client), \
                    patch("sys.argv", ["api_demo.py", "--scenario", "calculate", "--live", "--confirm-paid-api"]):
                self.assertEqual(agent.main(), 1)
        self.assertEqual(len(requests), 1)
        self.assertEqual(json.loads(requests[0].content)["model"], "gpt-6.1-sol")
        output = self.output.getvalue()
        self.assertIn("credit_balance_exhausted", output)
        self.assertIn("费用未知", output)
        self.assertNotIn("private error body", output)
        self.assertNotIn("offline-placeholder", output)


if __name__ == "__main__":
    unittest.main()
