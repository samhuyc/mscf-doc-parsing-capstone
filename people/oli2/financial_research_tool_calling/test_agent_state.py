from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import asdict, replace
import io
import json
import socket
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import api_demo as agent
from mock_responses import MockClient, final_response, tool_response


class AgentStateTests(unittest.TestCase):
    def setUp(self):
        self.state = agent.AgentState()
        self.output = io.StringIO()
        self.quiet = redirect_stdout(self.output)
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)
        self.network = patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def test_compare_state_before_tools_and_after_success(self):
        before_tools = []
        before_requests = []
        original_execute = agent.execute_tool
        client = MockClient()
        original_create = client.responses.create

        def execute(*args):
            before_tools.append(deepcopy(self.state))
            return original_execute(*args)

        def create(**payload):
            before_requests.append(deepcopy(self.state))
            return original_create(**payload)

        with patch.object(agent, "execute_tool", side_effect=execute):
            with patch.object(client.responses, "create", side_effect=create):
                answer = agent.run_agent(client, state=self.state)

        search, calculate = before_tools
        self.assertEqual(search.user_question, agent.SCENARIOS["compare"])
        self.assertEqual(search.status, "running")
        self.assertEqual(search.pending_tool_call["name"], "search_report")
        self.assertEqual((search.api_request_count, search.tool_call_count, search.total_tokens), (1, 1, 120))
        self.assertIsNone(search.evidence)
        self.assertEqual(calculate.pending_tool_call["arguments"], {"a": "98.9", "b": "91.2", "operation": "subtract"})
        self.assertEqual(calculate.pending_tool_call["call_id"], "call_2")
        self.assertEqual(calculate.evidence["citation"], "S1")
        self.assertEqual((calculate.api_request_count, calculate.tool_call_count, calculate.total_tokens), (2, 2, 240))
        self.assertIsNone(calculate.calculation)

        self.assertIsNone(before_requests[1].pending_tool_call)
        self.assertEqual(len(before_requests[1].history), 3)
        self.assertEqual(before_requests[2].calculation, "7.7")
        self.assertEqual(len(before_requests[2].history), 5)
        self.assertEqual(self.state.final_answer, answer)
        self.assertEqual(self.state.status, "completed")
        self.assertEqual(self.state.stage, "finished")
        self.assertEqual(self.state.api_request_count, 3)
        self.assertEqual(self.state.tool_call_count, 2)
        self.assertEqual((self.state.input_tokens, self.state.output_tokens, self.state.total_tokens), (300, 60, 360))
        self.assertEqual(len(self.state.history), 6)  # Includes the final model message.
        self.assertIsNone(self.state.pending_tool_call)
        self.assertIsNone(self.state.error)

    def test_second_tool_failure_retains_evidence_and_hides_exception_body(self):
        marker = "FAKE_PRIVATE_CREDENTIAL_DO_NOT_LOG"
        with patch.object(agent, "calculate", side_effect=RuntimeError(marker)):
            with self.assertRaises(agent.StopAgent):
                agent.run_agent(MockClient(), state=self.state)
        self.assertEqual(self.state.status, "failed")
        self.assertEqual(self.state.failure_stage, "tool_execution")
        self.assertEqual(self.state.pending_tool_call["name"], "calculate")
        self.assertEqual(self.state.evidence["citation"], "S1")
        self.assertEqual(len(self.state.history), 3)
        self.assertEqual((self.state.api_request_count, self.state.tool_call_count), (2, 2))
        self.assertEqual(self.state.total_tokens, 240)
        self.assertIsNone(self.state.calculation)
        self.assertIsNone(self.state.final_answer)
        self.assertNotIn(marker, json.dumps(asdict(self.state)) + self.output.getvalue())

    def test_budget_stops_preserve_progress(self):
        for limits, request_count, tool_count in [
            (replace(agent.Limits(), total_tokens=100), 0, 0),
            (replace(agent.Limits(), requests=1), 1, 1),
        ]:
            with self.subTest(limits=limits):
                state = agent.AgentState()
                client = MockClient()
                with self.assertRaises(agent.StopAgent):
                    agent.run_agent(client, limits=limits, state=state)
                self.assertEqual(state.status, "failed")
                self.assertEqual(state.failure_stage, "budget_check")
                self.assertEqual(state.api_request_count, request_count)
                self.assertEqual(state.tool_call_count, tool_count)
                self.assertEqual(len(client.requests), request_count)
                self.assertEqual(state.evidence is not None, bool(tool_count))
                self.assertIsNone(state.pending_tool_call)

    def test_actual_usage_over_budget_is_retained(self):
        response = tool_response("calculate", {"a": "0.3", "b": "0.2", "operation": "subtract"})
        response.usage.input_tokens = 12000
        response.usage.output_tokens = 1
        response.usage.total_tokens = 12001
        client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: response))
        with self.assertRaises(agent.StopAgent):
            agent.run_agent(client, "calculate", state=self.state)
        self.assertEqual(self.state.status, "failed")
        self.assertEqual(self.state.failure_stage, "response_validation")
        self.assertEqual(self.state.total_tokens, 12001)
        self.assertEqual((self.state.api_request_count, self.state.tool_call_count), (1, 0))

    def test_api_failure_counts_attempt_and_sanitizes_state(self):
        import httpx2
        from openai import RateLimitError
        marker = "FAKE_PRIVATE_HEADER"
        response = httpx2.Response(429, request=httpx2.Request("POST", "https://api.openai.com/v1/responses"))
        error = RateLimitError(marker, response=response, body=None)
        with patch.object(MockClient, "create", side_effect=error):
            with self.assertRaises(RateLimitError):
                agent.run_agent(MockClient(), state=self.state)
        self.assertEqual(self.state.failure_stage, "api_request")
        self.assertEqual(self.state.status, "failed")
        self.assertEqual(self.state.api_request_count, 1)
        self.assertEqual(self.state.total_tokens, 0)  # No reported Usage received.
        self.assertNotIn(marker, json.dumps(asdict(self.state)))

    def test_final_validation_failure_records_stage(self):
        client = SimpleNamespace(responses=SimpleNamespace(
            create=lambda **kwargs: final_response("compare", "999", "S1")))
        with self.assertRaises(agent.StopAgent):
            agent.run_agent(client, state=self.state)
        self.assertEqual(self.state.failure_stage, "final_validation")
        self.assertEqual(self.state.status, "failed")
        self.assertIsNone(self.state.final_answer)

    def test_insufficient_evidence_is_completed_abstention(self):
        answer = agent.run_agent(MockClient("insufficient"), "insufficient", state=self.state)
        self.assertEqual(self.state.status, "completed")
        self.assertEqual(self.state.final_answer, answer)
        self.assertIn("证据不足", answer)
        self.assertIsNone(self.state.error)
        self.assertIsNone(self.state.pending_tool_call)
        self.assertIsNone(self.state.calculation)
        self.assertEqual(self.state.api_request_count, 1)

    def test_invalid_tool_json_retains_pending_call(self):
        response = tool_response("calculate", {})
        response.output[0].arguments = "{"
        client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: response))
        with self.assertRaises(agent.StopAgent):
            agent.run_agent(client, "calculate", state=self.state)
        self.assertEqual(self.state.failure_stage, "tool_validation")
        self.assertEqual(self.state.pending_tool_call["arguments"], "{")

    def test_state_isolation_and_reuse_guard(self):
        untouched = agent.AgentState()
        agent.run_agent(MockClient("calculate"), "calculate", state=self.state)
        saved = deepcopy(self.state)
        with self.assertRaises(agent.StopAgent):
            agent.run_agent(MockClient(), state=self.state)
        self.assertEqual(self.state, saved)
        self.assertEqual(untouched.history, [])
        self.assertEqual(untouched.status, "pending")


if __name__ == "__main__":
    unittest.main()
