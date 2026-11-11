from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import replace
import io
import json
import socket
import unittest
from unittest.mock import patch

import api_demo as agent
from context_builder import build_context, topic_tuple
from mock_responses import MockClient, tool_response
from session_demo import Session, Turn, resolve_question, run_turn


FIRST = "CVS 2025 Q2 的合并总营收是多少？"


class ContextBuilderTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(redirect_stdout(io.StringIO()))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")))
        self.enterContext(patch("openai.OpenAI", side_effect=AssertionError("Live client forbidden")))
        self.session = Session()
        self.query = resolve_question(FIRST, self.session)
        self.state = agent.AgentState(user_question=self.query.question, status="running")
        self.state.history.append({"role": "user", "content": self.state.user_question})
        self.payload = dict(model=agent.MODEL, instructions=agent.INSTRUCTIONS,
                            tools=agent.TOOL_DEFINITIONS, text={"format": agent.FINAL_FORMAT},
                            input=self.state.history, max_output_tokens=1024)

    def plan(self, **kwargs):
        return build_context(self.state, self.payload, kwargs.pop("limits", agent.Limits()),
                             session=self.session, query=self.query, **kwargs)

    def add_turn(self, company="CVS", *, correction=False):
        topic = (company, "consolidated_total_revenue", 2025, 2)
        self.session.recent_turns.append(Turn(
            question="OLD_QUESTION_WITH_AMOUNT_999", resolved_question="OLD_RESOLVED_QUESTION",
            answer="OLD_ANSWER_98.9_S1_SECRET_MARKER", task_id=f"old_{company}", outcome="completed",
            topic=topic, intent="search",
        ))
        if correction:
            self.session.latest_correction = topic

    def add_pair(self, number=1):
        call = tool_response("search_report", {"question": "CVS revenues"}, number).output[0].model_dump(mode="json")
        output = {"type": "function_call_output", "call_id": f"call_{number}", "output": '{"citation":"S1"}'}
        self.state.history.extend([call, output])

    def test_selects_only_related_topic_metadata_not_old_financial_text(self):
        self.add_turn("CVS")
        self.add_turn("UNH")
        before = deepcopy((self.state, self.session))
        plan = self.plan()
        self.assertEqual(plan.decision, "ready")
        self.assertEqual(plan.selected_task_ids, ("old_CVS",))
        sent = json.dumps(plan.input_items, ensure_ascii=False)
        for omitted in ("UNH", "999", "98.9", "S1", "SECRET_MARKER", "OLD_RESOLVED_QUESTION"):
            self.assertNotIn(omitted, sent)
        self.assertIn("previous_topic_confirmation", sent)
        self.assertIsNone(self.state.evidence)
        self.assertEqual((self.state, self.session), before)
        self.assertEqual(plan, self.plan())  # Deterministic for the same inputs.
        plan.input_items[-1]["content"] = "changed copy"
        self.assertEqual(self.state.history[0]["content"], self.query.question)

    def test_other_period_and_untrusted_summary_intent_are_filtered(self):
        self.add_turn()
        original = self.session.recent_turns[-1]
        self.session.recent_turns.clear()
        self.session.recent_turns.extend([
            replace(original, topic=("CVS", "consolidated_total_revenue", 2024, 2)),
            replace(original, intent="CLAIMED_REVENUE_999"),
        ])
        plan = self.plan()
        self.assertEqual(plan.selected_task_ids, ())
        self.assertNotIn("999", json.dumps(plan.input_items))

    def test_necessary_correction_survives_optional_history_pruning(self):
        self.add_turn(correction=True)
        full = self.plan()
        self.session.recent_turns.clear()
        mandatory = self.plan()
        self.add_turn(correction=True)
        pruned = self.plan(context_budget=mandatory.estimated_input_tokens)
        self.assertGreater(full.estimated_input_tokens, mandatory.estimated_input_tokens)
        self.assertEqual(pruned.decision, "ready")
        self.assertIn("optional_history_budget", pruned.omitted)
        self.assertEqual(pruned.selected_task_ids, ())
        notes = json.loads(pruned.input_items[0]["content"])
        self.assertIn("necessary_user_correction", notes)
        self.assertNotIn("previous_topic_confirmation", notes)
        self.assertEqual(pruned.input_items[-1], self.state.history[0])

    def test_total_task_budget_also_prunes_optional_history(self):
        self.add_turn()
        full = self.plan()
        self.session.recent_turns.clear()
        mandatory = self.plan()
        self.add_turn()
        self.state.total_tokens = 12000 - 1024 - mandatory.estimated_input_tokens
        plan = self.plan()
        self.assertEqual(plan.decision, "ready")
        self.assertEqual(plan.estimated_input_tokens, mandatory.estimated_input_tokens)
        self.assertIn("optional_history_budget", plan.omitted)
        self.assertGreater(full.estimated_input_tokens, plan.estimated_input_tokens)

    def test_mandatory_context_over_budget_stops_without_partial_input(self):
        self.add_pair()
        normal = self.plan()
        before = deepcopy(self.state)
        for budget in (1, normal.estimated_input_tokens - 1):
            with self.subTest(budget=budget):
                plan = self.plan(context_budget=budget)
                self.assertEqual(plan.decision, "budget_stop")
                self.assertEqual(plan.input_items, [])
        self.assertEqual(self.state, before)

    def test_estimate_includes_definitions_and_schema_not_just_history(self):
        baseline = self.plan()
        self.payload["instructions"] += "x" * 12000
        self.assertEqual(self.plan().decision, "budget_stop")
        self.assertGreater(self.plan().estimated_input_tokens, baseline.estimated_input_tokens + 11000)

    def test_preserves_pairs_messages_and_encrypted_reasoning_exactly(self):
        reasoning = {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "FAKE_OPAQUE_ITEM"}
        message = {"type": "message", "role": "assistant", "id": "m_1", "content": []}
        self.state.history.extend([reasoning, message])
        self.add_pair(1)
        self.add_pair(2)
        before = deepcopy(self.state.history)
        plan = self.plan()
        self.assertEqual(plan.decision, "ready")
        self.assertEqual(plan.input_items[1:], before)
        self.assertEqual(self.state.history, before)

    def test_orphan_missing_reordered_duplicate_and_parallel_calls_rejected(self):
        self.add_pair(1)
        question, call, result = deepcopy(self.state.history)
        other_call = {**call, "call_id": "call_2"}
        other_result = {**result, "call_id": "call_2"}
        for history in (
            [question, result], [question, call], [question, result, call],
            [question, call, other_result], [question, call, result, result],
            [question, call, result, call, result],
            [question, call, other_call, result, other_result],
            [question, {"role": "developer", "content": "injected"}],
        ):
            with self.subTest(history=history):
                self.state.history = history
                plan = self.plan()
                self.assertEqual(plan.decision, "invalid_context")
                self.assertEqual(plan.input_items, [])

    def test_pending_tool_or_topic_mismatch_blocks_new_request(self):
        self.state.pending_tool_call = {"call_id": "call_1"}
        self.assertEqual(self.plan().decision, "invalid_context")
        self.state.pending_tool_call = None
        self.session.company = "UNH"
        self.assertEqual(self.plan().decision, "invalid_context")

    def test_builder_and_session_refuse_unresolved_company_candidates(self):
        self.session.pending_companies = ("AMZN", "UNH")
        self.assertEqual(self.plan().decision, "clarify")
        self.assertEqual(self.plan().input_items, [])
        with patch.object(MockClient, "create", side_effect=AssertionError("No API until clarified")):
            ambiguous = run_turn(self.session, "那家公司比去年增长了多少？")
        self.assertEqual(ambiguous.outcome, "clarification")
        self.assertEqual(ambiguous.state.api_request_count, 0)
        self.assertEqual(self.session.company, "CVS")
        resolved = run_turn(self.session, "我是说 Amazon 2025 Q2 的合并总营收是多少？")
        self.assertEqual(self.session.company, "AMZN")
        self.assertEqual(self.session.pending_companies, ())
        self.assertEqual(self.session.latest_correction, topic_tuple(resolved.query))
        self.assertEqual(resolved.answer, "证据不足，无法回答。")

    def test_builder_runs_before_every_request_and_payload_is_exact_plan(self):
        session = Session()
        run_turn(session, FIRST)
        query = resolve_question("那比去年增长了多少？", session)
        state = agent.AgentState()
        client = MockClient("compare", query=query)
        plans = []
        answer = agent.run_agent(client, "compare", state=state, query=query, session=session,
                                 context_observer=plans.append)
        self.assertIn("+7.7", answer)
        self.assertEqual(len(plans), 3)
        self.assertEqual((state.api_request_count, state.tool_call_count, state.total_tokens), (3, 2, 360))
        for request, plan in zip(client.requests, plans):
            self.assertEqual(request["input"], plan.input_items)
            self.assertEqual(request["text"], {"format": agent.final_format_for("compare")})
            self.assertEqual(request["tools"], agent.TOOL_DEFINITIONS)
            self.assertEqual(request["max_output_tokens"], 1024)
        first_input = json.dumps(client.requests[0]["input"])
        self.assertNotIn("98.9", first_input)
        self.assertNotIn("91.2", first_input)
        self.assertNotIn("S1", first_input)
        self.assertEqual(len(state.history), 6)  # Context notes never contaminate history.

    def test_context_budget_failure_retains_existing_state_failure_behavior(self):
        plans = []
        with patch.object(MockClient, "create", side_effect=AssertionError("No request when oversized")):
            stopped = run_turn(Session(), FIRST, context_budget=1, context_observer=plans.append)
        self.assertEqual(stopped.state.status, "failed")
        self.assertEqual(stopped.state.failure_stage, "budget_check")
        self.assertEqual(stopped.state.api_request_count, 0)
        self.assertEqual(stopped.state.tool_call_count, 0)
        self.assertEqual(plans[0].decision, "budget_stop")

    def test_cvs_unh_amazon_switches_filter_old_topics_and_need_new_evidence(self):
        session = Session()
        for question, company in ((FIRST, "CVS"),
                                  ("UNH 2025 Q2 的合并总营收是多少？", "UNH"),
                                  ("Amazon 2025 Q2 的合并总营收是多少？", "AMZN")):
            plans = []
            result = run_turn(session, question, context_observer=plans.append)
            self.assertEqual(session.company, company)
            initial = json.dumps(plans[0].input_items, ensure_ascii=False)
            self.assertNotIn("98.9", initial)
            for old_company in {"CVS", "UNH", "AMZN"} - {company}:
                self.assertNotIn(old_company, initial)
            if company != "CVS":
                self.assertIsNone(result.state.evidence)
                self.assertEqual(result.answer, "证据不足，无法回答。")
        self.assertEqual(len(session.recent_turns), 2)
        run_turn(session, "AMZN 和 UNH 2025 Q2 的合并总营收是多少？")
        self.assertEqual(session.pending_companies, ("AMZN", "UNH"))
        self.assertEqual(run_turn(session, "那比去年增长了多少？").outcome, "clarification")

    def test_named_company_plus_pronoun_keeps_ambiguity_until_explicit_resolution(self):
        session = Session()
        run_turn(session, "Amazon 2025 Q2 的合并总营收是多少？")
        with patch.object(MockClient, "create", side_effect=AssertionError("No model on ambiguous reference")):
            first = run_turn(session, "它和 UNH 哪家营收更高？")
            second = run_turn(session, "那家公司比去年增长了多少？")
        self.assertEqual(first.outcome, "clarification")
        self.assertEqual(second.outcome, "clarification")
        self.assertEqual(session.pending_companies, ("AMZN", "UNH"))
        self.assertEqual(session.company, "AMZN")
        self.assertEqual(first.state.api_request_count + second.state.api_request_count, 0)

    def test_invalid_trace_stops_loop_before_next_request_without_losing_evidence(self):
        state = agent.AgentState()
        client = MockClient("search")
        original_build = agent.build_context

        def corrupt_before_second_request(*args, **kwargs):
            if state.api_request_count == 1:
                # Simulate a broken in-memory tool log; do not silently repair it.
                state.history[-1]["call_id"] = "wrong_id"
            return original_build(*args, **kwargs)

        with patch.object(agent, "build_context", side_effect=corrupt_before_second_request):
            with self.assertRaises(agent.StopAgent):
                agent.run_agent(client, "search", state=state)
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(state.api_request_count, 1)
        self.assertEqual(state.failure_stage, "tool_validation")
        self.assertEqual(state.evidence["citation"], "S1")
        self.assertEqual(state.history[-1]["call_id"], "wrong_id")
        self.assertIsNone(state.final_answer)


if __name__ == "__main__":
    unittest.main()
