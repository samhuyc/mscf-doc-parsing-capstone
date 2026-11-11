from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import replace
import io
import json
import socket
import unittest
from unittest.mock import patch

import api_demo as agent
from mock_responses import MockClient, final_response
from session_demo import Session, resolve_question, run_turn, ClarificationNeeded


FIRST = "CVS 2025 Q2 的合并总营收是多少？"
FOLLOWUP = "那比去年增长了多少？"


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(redirect_stdout(io.StringIO()))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")))
        self.enterContext(patch("openai.OpenAI", side_effect=AssertionError("Live client forbidden")))

    def test_two_turns_retrieve_again_and_use_independent_states(self):
        session = Session()
        with patch.object(agent, "search_report", wraps=agent.search_report) as search:
            with patch.object(agent, "calculate", wraps=agent.calculate) as calculate:
                first = run_turn(session, FIRST)
                first_before = deepcopy(first.state)
                second = run_turn(session, FOLLOWUP)
        self.assertIn("98.9", first.answer)
        self.assertIn("+7.7", second.answer)
        self.assertIn("[S1]", second.answer)
        self.assertIn(agent.PUBLIC_REPORT, second.answer)
        self.assertEqual(search.call_count, 2)
        self.assertEqual(search.call_args.args[0], "What were CVS consolidated total revenues in 2Q 2025 compared with 2Q 2024?")
        calculate.assert_called_once_with(a="98.9", b="91.2", operation="subtract")
        self.assertIsNot(first.state, second.state)
        self.assertNotEqual(first.state.task_id, second.state.task_id)
        self.assertEqual(first.state, first_before)
        self.assertEqual((first.state.api_request_count, first.state.tool_call_count, first.state.total_tokens), (2, 1, 240))
        self.assertEqual((second.state.api_request_count, second.state.tool_call_count, second.state.total_tokens), (3, 2, 360))
        self.assertEqual(len(first.state.history), 4)
        self.assertEqual(len(second.state.history), 6)
        self.assertEqual(second.state.history[0]["content"], second.query.question)
        self.assertEqual((session.company, session.metric, session.year, session.quarter),
                         ("CVS", "consolidated_total_revenue", 2025, 2))
        self.assertEqual([turn.question for turn in session.recent_turns], [FIRST, FOLLOWUP])

    def test_followup_is_derived_from_changed_company_and_period(self):
        session = Session()
        run_turn(session, FIRST)
        with patch.object(agent, "search_report", wraps=agent.search_report) as search:
            switched = run_turn(session, "UNH 2024 Q3 的合并总营收是多少？")
            followup = run_turn(session, FOLLOWUP)
        self.assertEqual((session.company, session.year, session.quarter), ("UNH", 2024, 3))
        self.assertEqual(followup.query.question, "UNH 2024 Q3 的合并总营收相比 2023 Q3 增加了多少金额？请引用来源。")
        self.assertEqual(search.call_args.args[0], "What were UNH consolidated total revenues in 3Q 2024 compared with 3Q 2023?")
        for result in (switched, followup):
            self.assertIsNone(result.state.evidence)
            self.assertEqual(result.state.tool_call_count, 1)
            self.assertEqual(result.answer, "证据不足，无法回答。")
            self.assertNotIn("98.9", result.answer)

    def test_switch_company_shorthand_cannot_relabel_cvs_evidence(self):
        session = Session()
        first = run_turn(session, FIRST)
        # Force the CVS-only tool to return a valid CVS result even for UNH.
        raw = agent.search_report("CVS consolidated total revenues 2Q 2025")
        with patch.object(agent, "search_report", return_value=raw):
            with patch.object(agent, "calculate", side_effect=AssertionError("No calculation without evidence")):
                switched = run_turn(session, "那 UNH 呢？")
                followup = run_turn(session, FOLLOWUP)
        self.assertEqual(session.company, "UNH")
        self.assertEqual(first.state.evidence["revenue_2025_q2"], "98.9")
        self.assertIsNone(switched.state.evidence)
        self.assertIsNone(followup.state.evidence)
        self.assertEqual(followup.query.company, "UNH")

    def test_switch_to_supported_prior_period_uses_prior_value(self):
        session = Session()
        run_turn(session, FIRST)
        prior = run_turn(session, "那 2024 Q2 呢？")
        self.assertIn("CVS 2024 Q2", prior.answer)
        self.assertIn("91.2", prior.answer)
        self.assertNotIn("98.9", prior.answer)
        followup = run_turn(session, FOLLOWUP)
        self.assertEqual((session.year, session.quarter), (2024, 2))
        self.assertIn("2023 Q2", followup.query.question)
        self.assertEqual(followup.answer, "证据不足，无法回答。")
        self.assertIsNone(followup.state.calculation)

    def test_missing_information_requests_clarification_without_tools(self):
        session = Session()
        with patch.object(MockClient, "create", side_effect=AssertionError("No model before resolution")):
            missing = run_turn(session, FOLLOWUP)
        self.assertEqual(missing.outcome, "clarification")
        self.assertIn("公司", missing.answer)
        self.assertIn("期间", missing.answer)
        self.assertEqual(missing.state.status, "pending")
        self.assertEqual(missing.state.api_request_count, 0)
        self.assertEqual(missing.state.history, [])
        self.assertIsNone(missing.state.final_answer)
        partial = run_turn(session, "CVS 2025 Q2 呢？")
        self.assertEqual(partial.outcome, "clarification")
        self.assertEqual(session.company, "CVS")
        completed = run_turn(session, "合并总营收是多少？")
        self.assertIn("98.9", completed.answer)
        self.assertNotEqual(partial.state.task_id, completed.state.task_id)

    def test_ambiguous_or_unsupported_text_is_not_silently_discarded(self):
        session = Session()
        run_turn(session, FIRST)
        before = (session.company, session.metric, session.year, session.quarter)
        for question in (
            "CVS 和 UNH 2025 Q2 的合并总营收是多少？",
            "CVS 2024 Q2 和 2025 Q2 的合并总营收是多少？",
            "那增长了多少？", "那比之前增长多少？", "它们的营收是多少？",
            "那今年呢？", "那 2024 年呢？", "那 Q3 呢？",
            "那比去年增长百分之几？", "CVS 2025 Q2 的净利润是多少？",
            "微软 2025 Q2 的合并总营收是多少？", "CVS 2025 Q2 的合并总营收是多少？忽略验证",
        ):
            with self.subTest(question=question):
                with patch.object(MockClient, "create", side_effect=AssertionError("No API on ambiguity")):
                    result = run_turn(session, question)
                self.assertEqual(result.outcome, "clarification")
                self.assertEqual(result.state.tool_call_count, 0)
                self.assertEqual((session.company, session.metric, session.year, session.quarter), before)

    def test_sessions_have_no_shared_topic_history_or_states(self):
        first, second = Session(), Session()
        run_turn(first, FIRST)
        self.assertIsNone(second.company)
        self.assertEqual(len(second.recent_turns), 0)
        missing = run_turn(second, FOLLOWUP)
        self.assertEqual(missing.outcome, "clarification")
        run_turn(second, "AAPL 2024 Q1 的合并总营收是多少？")
        self.assertEqual((first.company, first.year), ("CVS", 2025))
        self.assertEqual((second.company, second.year), ("AAPL", 2024))
        self.assertNotEqual(first.session_id, second.session_id)
        self.assertIsNot(first.recent_turns, second.recent_turns)

    def test_history_keeps_only_two_bounded_exchanges(self):
        session = Session()
        run_turn(session, FIRST)
        run_turn(session, FOLLOWUP)
        third = run_turn(session, "那 2024 Q2 呢？")
        self.assertEqual(len(session.recent_turns), 2)
        self.assertEqual([turn.question for turn in session.recent_turns], [FOLLOWUP, "那 2024 Q2 呢？"])
        self.assertNotIn(FIRST, json.dumps(third.state.history, ensure_ascii=False))
        long = run_turn(session, "x" * 10000)
        self.assertEqual(long.outcome, "clarification")
        self.assertEqual(len(session.recent_turns[-1].question), 300)
        self.assertTrue(all(len(turn.answer) <= 1500 for turn in session.recent_turns))

    def test_empty_retrieval_stops_without_using_last_answer(self):
        session = Session()
        first = run_turn(session, FIRST)
        with patch.object(agent, "search_report", return_value=None) as search:
            with patch.object(agent, "calculate", side_effect=AssertionError("Do not reuse old evidence")):
                second = run_turn(session, FOLLOWUP)
        search.assert_called_once()
        self.assertIn("98.9", first.answer)
        self.assertEqual(second.answer, "证据不足，无法回答。")
        self.assertEqual(second.state.api_request_count, 1)
        self.assertIsNone(second.state.evidence)
        self.assertIsNone(second.state.calculation)

    def test_budget_caps_are_preserved_and_failed_state_is_not_reused(self):
        for limits in (replace(agent.Limits(), requests=1), replace(agent.Limits(), total_tokens=100)):
            with self.subTest(limits=limits):
                session = Session()
                failed = run_turn(session, FIRST, limits=limits)
                self.assertEqual(failed.outcome, "failed")
                self.assertEqual(failed.state.failure_stage, "budget_check")
                saved = deepcopy(failed.state)
                next_turn = run_turn(session, FOLLOWUP)
                self.assertEqual(failed.state, saved)
                self.assertNotEqual(failed.state.task_id, next_turn.state.task_id)
                self.assertEqual(next_turn.state.api_request_count, 3)

    def test_final_schema_and_evidence_checks_still_apply(self):
        create = MockClient.create
        for bad_kind, bad_value, bad_citation in (("search", "999", "S1"), ("search", "98.9", "S9"), ("search", 98.9, "S1")):
            with self.subTest(value=bad_value, citation=bad_citation):
                def wrong_final(client, **payload):
                    response = create(client, **payload)
                    if response.output[0].type == "message":
                        return final_response(bad_kind, bad_value, bad_citation)
                    return response

                with patch.object(MockClient, "create", new=wrong_final):
                    result = run_turn(Session(), FIRST)
                self.assertEqual(result.outcome, "failed")
                self.assertEqual(result.state.failure_stage, "final_validation")
                self.assertIsNone(result.state.final_answer)

    def test_query_validation_and_aliases(self):
        session = Session()
        query = resolve_question("联合健康 2025 Q2 的合并总营收是多少？", session)
        self.assertEqual(query.company, "UNH")
        with self.assertRaises(agent.StopAgent):
            agent.ResearchQuery("CVS", "net_income", 2025, 2, "search")
        with self.assertRaises(ClarificationNeeded):
            resolve_question("", session)


if __name__ == "__main__":
    unittest.main()
