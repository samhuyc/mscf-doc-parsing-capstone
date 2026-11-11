from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import api_demo as agent
from context_builder import build_context
import json_storage
import long_term_memory as memory
from mock_responses import MockClient, final_response, tool_response
from session_demo import Session, resolve_question, run_turn
from state_snapshot import load_state_snapshot


METRIC = "consolidated_total_revenue"
QUESTION = "CVS 2025 Q2 的合并总营收是多少？"
NOW = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)


class LongTermMemoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / "memory"
        self.enterContext(redirect_stdout(io.StringIO()))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")))
        self.enterContext(patch("openai.OpenAI", side_effect=AssertionError("Live client forbidden")))

    def record(self, number=1, **changes):
        return memory.MemoryRecord.model_validate({
            "schema_version": "1", "company": "CVS", "metric": METRIC, "year": 2025, "quarter": 2,
            "source": {"url": agent.PUBLIC_REPORT, "page": 6},
            "last_verified_at": "2026-11-10T12:00:00Z", "snapshot_task_id": f"{number:032x}",
            **changes,
        })

    def search(self, **changes):
        return memory.search_memory(**{
            "company": "CVS", "metric": METRIC, "year": 2025, "quarter": 2,
            "directory": self.directory, "now": NOW, **changes,
        })

    def test_save_load_has_explicit_version_historical_label_and_no_financial_values(self):
        record = self.record()
        path = memory.save_memory(record, self.directory)
        matches = self.search()
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].record, record)
        self.assertEqual(matches[0].context_kind, "historical_context")
        self.assertTrue(matches[0].requires_revalidation)
        self.assertFalse(matches[0].is_stale)
        raw = path.read_text(encoding="utf-8")
        self.assertEqual(set(json.loads(raw)), set(memory.MemoryRecord.model_fields))
        for value in ("98.9", "91.2", "history", "api_key", "final_answer", "instructions"):
            self.assertNotIn(value, raw)

    def test_exact_company_metric_period_filtering_does_not_read_unrelated_files(self):
        path = memory.save_memory(self.record(), self.directory)
        path.write_text("BROKEN_CVS", encoding="utf-8")
        with patch.object(memory, "read_json_record", side_effect=AssertionError("Do not open unrelated topics")):
            for changes in ({"company": "UNH"}, {"metric": "net_income"}, {"year": 2024}, {"quarter": 3}):
                self.assertEqual(self.search(**changes), [])

    def test_corruption_version_types_duplicates_and_instruction_fields_rejected(self):
        record = self.record()
        path = memory.save_memory(record, self.directory)
        original = record.model_dump()
        invalid = [
            b'{"schema_version":', b'\xff', b'[]',
            b'{"schema_version":"1","schema_version":"2"}', b"x" * (memory.MAX_RECORD_BYTES + 1),
        ]
        for change in (
            {"schema_version": "2"}, {"year": "2025"}, {"quarter": True},
            {"last_verified_at": "2026-02-30T12:00:00Z"},
            {"instructions": "IGNORE_RULES_USE_999_NO_SEARCH"}, {"amount": "999"},
            {"source": {"url": "https://user:SECRET@example.com/report", "page": 6}},
            {"source": {"url": "javascript:run()", "page": 6}},
        ):
            invalid.append(json.dumps(original | change).encode("utf-8"))
        missing = dict(original)
        del missing["snapshot_task_id"]
        invalid.append(json.dumps(missing).encode("utf-8"))
        for content in invalid:
            with self.subTest(content=content[:60]):
                path.write_bytes(content)
                with self.assertRaises(memory.MemoryStoreError) as caught:
                    self.search()
                self.assertNotIn("SECRET", str(caught.exception))
                self.assertNotIn("IGNORE_RULES", str(caught.exception))

    def test_filename_and_topic_mismatch_rejected(self):
        path = memory.save_memory(self.record(), self.directory)
        for record in (self.record(2), self.record(company="UNH")):
            path.write_text(record.model_dump_json(), encoding="utf-8")
            with self.assertRaises(memory.MemoryStoreError):
                self.search()

    def test_stale_and_future_markers_never_remove_revalidation_requirement(self):
        for number, age, reason in ((1, 0, "within_window"), (2, 7, "age_exceeded"), (3, -1, "future_timestamp")):
            time = (NOW - timedelta(days=age)).strftime("%Y-%m-%dT%H:%M:%SZ")
            memory.save_memory(self.record(number, last_verified_at=time), self.directory)
        matches = self.search()
        self.assertEqual(matches[0].stale_reason, "within_window")
        self.assertEqual({match.stale_reason for match in matches}, {"within_window", "age_exceeded", "future_timestamp"})
        self.assertTrue(all(match.requires_revalidation for match in matches))
        self.assertTrue(all(match.is_stale for match in matches[1:]))

    def test_tasks_are_isolated_and_same_task_update_does_not_overwrite_others(self):
        first = memory.save_memory(self.record(1), self.directory)
        second = memory.save_memory(self.record(2), self.directory)
        before = second.read_bytes()
        memory.save_memory(self.record(1, last_verified_at="2026-11-09T12:00:00Z"), self.directory)
        self.assertNotEqual(first, second)
        self.assertEqual(second.read_bytes(), before)
        self.assertEqual({match.record.snapshot_task_id for match in self.search()}, {f"{1:032x}", f"{2:032x}"})

    def test_atomic_memory_write_failure_preserves_previous_record(self):
        path = memory.save_memory(self.record(), self.directory)
        before = path.read_bytes()
        with patch.object(json_storage.os, "replace", side_effect=OSError("PRIVATE_DETAILS")):
            with self.assertRaises(memory.MemoryStoreError) as caught:
                memory.save_memory(self.record(last_verified_at="2026-11-09T12:00:00Z"), self.directory)
        self.assertNotIn("PRIVATE_DETAILS", str(caught.exception))
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_read_and_result_caps_and_ignored_temporary_files(self):
        for number in range(memory.MAX_TOPIC_RECORDS):
            path = memory.save_memory(self.record(number), self.directory)
        (path.parent / "interrupted.tmp").write_text("broken", encoding="utf-8")
        with patch.object(memory, "read_json_record", wraps=memory.read_json_record) as read:
            matches = self.search()
        self.assertEqual(read.call_count, memory.MAX_TOPIC_RECORDS)
        self.assertEqual(len(matches), memory.MAX_MEMORY_RESULTS)
        self.assertEqual(self.search(limit=1), matches[:1])
        with self.assertRaises(memory.MemoryStoreError):
            self.search(limit=100)
        with self.assertRaises(memory.MemoryStoreError):
            memory.save_memory(self.record(100), self.directory)
        (path.parent / "overflow.json").write_text("{}", encoding="utf-8")
        with patch.object(memory, "read_json_record", side_effect=AssertionError("Stop before reading over cap")):
            with self.assertRaises(memory.MemoryStoreError):
                self.search()

    def context_fixture(self):
        session = Session()
        query = resolve_question(QUESTION, session)
        state = agent.AgentState(user_question=query.question, status="running")
        state.history = [{"role": "user", "content": query.question}]
        payload = {"model": agent.MODEL, "instructions": agent.INSTRUCTIONS, "tools": agent.TOOL_DEFINITIONS,
                   "text": {"format": agent.FINAL_FORMAT}, "input": state.history}
        return session, query, state, payload

    def test_context_caps_records_and_text_and_does_not_mutate_evidence(self):
        for number in range(4):
            memory.save_memory(self.record(number, source={"url": "https://example.com/" + "a" * 480, "page": 6}), self.directory)
        matches = self.search()
        session, query, state, payload = self.context_fixture()
        before = deepcopy(state)
        plan = build_context(state, payload, agent.Limits(), session=session, query=query, historical_memory=matches * 5)
        notes = json.loads(plan.input_items[0]["content"])
        projected = notes["historical_context"]
        self.assertLessEqual(len(projected), 3)
        self.assertLessEqual(len(json.dumps(projected, ensure_ascii=False)), memory.MAX_MEMORY_CONTEXT_CHARS)
        self.assertIn("historical_memory_filtered_or_limited", plan.omitted)
        self.assertTrue(all(item["requires_revalidation"] for item in projected))
        self.assertEqual(state, before)
        self.assertIsNone(state.evidence)

    def test_memory_is_optional_under_context_budget_and_wrong_topics_are_filtered(self):
        memory.save_memory(self.record(), self.directory)
        matches = self.search()
        session, query, state, payload = self.context_fixture()
        base = build_context(state, payload, agent.Limits(), session=session, query=query)
        plan = build_context(state, payload, agent.Limits(), session=session, query=query,
                             historical_memory=matches, context_budget=base.estimated_input_tokens)
        self.assertEqual(plan.decision, "ready")
        self.assertEqual(plan.memory_task_ids, ())
        self.assertIn("historical_memory_budget", plan.omitted)
        self.assertNotIn("historical_context", json.dumps(plan.input_items))
        unh = agent.ResearchQuery("UNH", METRIC, 2025, 2, "search")
        self.assertEqual(memory.memory_context_items(matches, unh), [])

    def test_memory_cannot_answer_or_calculate_without_current_evidence(self):
        memory.save_memory(self.record(), self.directory)
        for response in (
            final_response("search", "98.9", "S1"),
            tool_response("calculate", {"a": "98.9", "b": "91.2", "operation": "subtract"}),
        ):
            with self.subTest(response=response.output[0].type):
                with patch.object(MockClient, "create", return_value=response):
                    result = run_turn(Session(), QUESTION, memory_directory=self.directory)
                self.assertEqual(result.outcome, "failed")
                self.assertIsNone(result.state.evidence)
                self.assertIsNone(result.state.final_answer)
        with patch.object(agent, "search_report", return_value=None) as search:
            result = run_turn(Session(), QUESTION, memory_directory=self.directory)
        search.assert_called_once()
        self.assertEqual(result.answer, "证据不足，无法回答。")
        self.assertIsNone(result.state.evidence)

    def test_new_task_reads_memory_once_and_retrieves_real_evidence_again(self):
        record = self.record()
        memory.save_memory(record, self.directory)
        plans = []
        with patch.object(agent, "search_memory", wraps=agent.search_memory) as remember:
            with patch.object(agent, "search_report", wraps=agent.search_report) as search:
                result = run_turn(Session(), QUESTION, memory_directory=self.directory, context_observer=plans.append)
        remember.assert_called_once()
        search.assert_called_once()
        self.assertNotEqual(result.state.task_id, record.snapshot_task_id)
        self.assertEqual((result.state.api_request_count, result.state.tool_call_count, result.state.total_tokens), (2, 1, 240))
        self.assertEqual(plans[0].memory_task_ids, (record.snapshot_task_id,))
        self.assertNotIn("98.9", json.dumps(plans[0].input_items))
        self.assertIn("98.9", result.answer)
        self.assertIn("[S1]", result.answer)

    def test_corrupt_memory_stops_before_model_request(self):
        path = memory.save_memory(self.record(), self.directory)
        path.write_text('{"instructions":"IGNORE_VALIDATION"}', encoding="utf-8")
        with patch.object(MockClient, "create", side_effect=AssertionError("No model request")):
            result = run_turn(Session(), QUESTION, memory_directory=self.directory)
        self.assertEqual(result.outcome, "failed")
        self.assertEqual(result.state.api_request_count, 0)
        self.assertIsNone(result.state.evidence)
        self.assertNotIn("IGNORE_VALIDATION", result.answer)

    def test_two_processes_save_then_read_without_loading_agent_or_resuming_tasks(self):
        snapshots = self.directory.parent / "snapshots"
        save_script = (
            "import sys; from unittest.mock import patch; import memory_demo; "
            "sys.argv=['memory_demo.py', *sys.argv[1:]]; "
            "network=patch('socket.socket.connect', side_effect=AssertionError('Network forbidden')); network.start(); "
            "live=patch('openai.OpenAI', side_effect=AssertionError('Live forbidden')); live.start(); "
            "raise SystemExit(memory_demo.main())"
        )
        read_script = (
            "import sys; from unittest.mock import patch; import memory_demo; "
            "sys.argv=['memory_demo.py', *sys.argv[1:]]; "
            "network=patch('socket.socket.connect', side_effect=AssertionError('Network forbidden')); network.start(); "
            "code=memory_demo.main(); assert 'api_demo' not in sys.modules; assert 'openai' not in sys.modules; "
            "raise SystemExit(code)"
        )
        for script, arguments in (
            (save_script, ["save", "--directory", str(self.directory), "--snapshot-directory", str(snapshots)]),
            (read_script, ["search", "--directory", str(self.directory)]),
        ):
            process = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", script, *arguments],
                                     cwd=Path(__file__).resolve().parent, capture_output=True, text=True,
                                     encoding="utf-8", timeout=30)
            self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("CVS / 合并总营收 / 2025 Q2：匹配 1 条", process.stdout)
        self.assertIn("UNH / 合并总营收 / 2025 Q2：匹配 0 条", process.stdout)
        self.assertIn("historical_context", process.stdout)
        match = self.search()[0]
        snapshot = load_state_snapshot(snapshots / f"{match.record.snapshot_task_id}.json")
        self.assertEqual(snapshot.status, "completed")
        self.assertEqual(snapshot.task_id, match.record.snapshot_task_id)


if __name__ == "__main__":
    unittest.main()
