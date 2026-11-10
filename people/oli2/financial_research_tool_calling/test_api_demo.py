from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
import socket
from types import SimpleNamespace
import unittest
from unittest.mock import patch

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
                agent.render_answer(dict(kind="search", value=value, citation=citation), "search", evidence, None)

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


if __name__ == "__main__":
    unittest.main()
