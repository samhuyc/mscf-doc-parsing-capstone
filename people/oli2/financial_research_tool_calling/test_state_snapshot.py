from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError

import api_demo as agent
from mock_responses import MockClient
import state_snapshot as snapshots


class StateSnapshotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.enterContext(redirect_stdout(io.StringIO()))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")))
        self.enterContext(patch("openai.OpenAI", side_effect=AssertionError("Live client forbidden")))

    def run_task(self, scenario="compare"):
        state = agent.AgentState()
        agent.run_agent(MockClient(scenario), scenario, state=state)
        return state

    def test_save_load_public_answer_and_usage_without_mutating_state(self):
        state = self.run_task()
        before = deepcopy(state)
        path = snapshots.save_state_snapshot(state, self.directory)
        loaded = snapshots.load_state_snapshot(path)
        self.assertEqual(state, before)
        self.assertEqual(loaded.task_id, state.task_id)
        self.assertEqual(loaded.user_question, agent.SCENARIOS["compare"])
        self.assertEqual(loaded.status, "completed")
        self.assertEqual(loaded.final_answer, state.final_answer)
        self.assertIn("+7.7", loaded.final_answer)
        self.assertIn("[S1]", loaded.final_answer)
        self.assertIn(agent.PUBLIC_REPORT, loaded.final_answer)
        self.assertEqual((loaded.tool_call_count, loaded.api_request_count), (2, 3))
        self.assertEqual(loaded.token_usage.model_dump(), {
            "input_tokens": 300, "output_tokens": 60, "total_tokens": 360,
        })
        self.assertEqual(loaded.schema_version, "1")
        self.assertIsNone(loaded.failure_stage)

    def test_failed_tool_and_exhausted_budget_can_be_saved(self):
        state = agent.AgentState()
        with patch.object(agent, "calculate", side_effect=RuntimeError("PRIVATE_BODY")):
            with self.assertRaises(agent.StopAgent):
                agent.run_agent(MockClient(), state=state)
        loaded = snapshots.load_state_snapshot(snapshots.save_state_snapshot(state, self.directory))
        self.assertEqual(loaded.status, "failed")
        self.assertEqual(loaded.failure_stage, "tool_execution")
        self.assertEqual((loaded.tool_call_count, loaded.api_request_count), (2, 2))
        self.assertIsNone(loaded.final_answer)

        budget_state = agent.AgentState()
        with self.assertRaises(agent.StopAgent):
            agent.run_agent(MockClient(), limits=replace(agent.Limits(), total_tokens=100), state=budget_state)
        loaded = snapshots.load_state_snapshot(snapshots.save_state_snapshot(budget_state, self.directory))
        self.assertEqual(loaded.failure_stage, "budget_check")
        self.assertEqual(loaded.api_request_count, 0)

    def test_pending_running_and_insufficient_states(self):
        state = agent.AgentState()
        path = snapshots.save_state_snapshot(state, self.directory)
        self.assertEqual(snapshots.load_state_snapshot(path).status, "pending")
        original = agent.execute_tool

        def execute(*args):
            path = snapshots.save_state_snapshot(state, self.directory)
            loaded = snapshots.load_state_snapshot(path)
            self.assertEqual(loaded.status, "running")
            self.assertEqual(loaded.stage, "tool_execution")
            self.assertIsNone(loaded.final_answer)
            return original(*args)

        with patch.object(agent, "execute_tool", side_effect=execute):
            agent.run_agent(MockClient("insufficient"), "insufficient", state=state)
        loaded = snapshots.load_state_snapshot(snapshots.save_state_snapshot(state, self.directory))
        self.assertEqual(loaded.status, "completed")
        self.assertEqual(loaded.final_answer, "证据不足，无法回答。")

    def test_projection_excludes_private_fields_and_raw_errors(self):
        state = self.run_task("calculate")
        marker = "SYNTHETIC_PRIVATE_DATA_NOT_A_REAL_SECRET"
        state.history.append({"content": marker})
        state.evidence = {"report_body": marker}
        state.pending_tool_call = {"arguments": marker}
        state.error = marker
        state.credential = marker  # Even unexpected attributes must not be serialized.
        path = snapshots.save_state_snapshot(state, self.directory)
        raw = path.read_text(encoding="utf-8")
        self.assertNotIn(marker, raw)
        self.assertEqual(set(json.loads(raw)), {
            "schema_version", "task_id", "user_question", "status", "stage",
            "tool_call_count", "api_request_count", "token_usage", "final_answer", "failure_stage",
        })

    def test_corrupt_json_invalid_encoding_duplicate_keys_and_oversize_rejected(self):
        path = self.directory / "corrupt.json"
        for content in (
            b'{"schema_version":', b'\xff', b'[]',
            b'{"schema_version":"1","schema_version":"2"}',
            b" " * (snapshots.MAX_SNAPSHOT_BYTES + 1),
        ):
            with self.subTest(content=content[:40]):
                path.write_bytes(content)
                with self.assertRaises(snapshots.SnapshotError):
                    snapshots.load_state_snapshot(path)
        with self.assertRaises(snapshots.SnapshotError):
            snapshots.load_state_snapshot(self.directory / "missing.json")

    def test_incompatible_missing_wrong_types_and_inconsistent_fields_rejected(self):
        path = snapshots.save_state_snapshot(self.run_task(), self.directory)
        original = json.loads(path.read_text(encoding="utf-8"))
        cases = [
            {"schema_version": "2"}, {"schema_version": 1}, {"schema_version": True},
            {"tool_call_count": "2"}, {"tool_call_count": True}, {"tool_call_count": -1},
            {"task_id": "../outside"}, {"final_answer": None}, {"status": "failed"},
            {"unexpected": "value"}, {"failure_stage": "api_request"},
            {"token_usage": {"input_tokens": 300, "output_tokens": 60, "total_tokens": 999}},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                path.write_text(json.dumps(original | changes), encoding="utf-8")
                with self.assertRaises(snapshots.SnapshotError):
                    snapshots.load_state_snapshot(path)
        for field in original:
            data = dict(original)
            del data[field]
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(snapshots.SnapshotError):
                snapshots.load_state_snapshot(path)

    def test_invalid_state_is_rejected_before_any_write(self):
        state = agent.AgentState(task_id="../escape")
        with self.assertRaises(snapshots.SnapshotError):
            snapshots.save_state_snapshot(state, self.directory)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_atomic_replace_failure_preserves_previous_snapshot_and_cleans_temp(self):
        state = agent.AgentState()
        path = snapshots.save_state_snapshot(state, self.directory)
        previous = path.read_bytes()
        agent.run_agent(MockClient("calculate"), "calculate", state=state)

        def interrupted(source, destination):
            self.assertEqual(Path(source).parent, path.parent)
            self.assertEqual(Path(destination), path)
            self.assertEqual(snapshots.load_state_snapshot(source).status, "completed")
            self.assertEqual(path.read_bytes(), previous)
            raise OSError("SIMULATED_INTERRUPTION_PRIVATE_DETAILS")

        with patch.object(snapshots.os, "replace", side_effect=interrupted):
            with self.assertRaises(snapshots.SnapshotError) as caught:
                snapshots.save_state_snapshot(state, self.directory)
        self.assertNotIn("PRIVATE_DETAILS", str(caught.exception))
        self.assertEqual(path.read_bytes(), previous)
        self.assertEqual(list(self.directory.iterdir()), [path])
        snapshots.save_state_snapshot(state, self.directory)
        self.assertEqual(snapshots.load_state_snapshot(path).status, "completed")

    def test_flush_failure_never_publishes_a_partial_file(self):
        with patch.object(snapshots.os, "fsync", side_effect=OSError("disk failure")):
            with self.assertRaises(snapshots.SnapshotError):
                snapshots.save_state_snapshot(agent.AgentState(), self.directory)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_two_tasks_are_isolated_even_with_same_question(self):
        first = self.run_task("calculate")
        second = self.run_task("calculate")
        first_path = snapshots.save_state_snapshot(first, self.directory)
        before = first_path.read_bytes()
        second_path = snapshots.save_state_snapshot(second, self.directory)
        self.assertNotEqual(first.task_id, second.task_id)
        self.assertNotEqual(first_path, second_path)
        self.assertEqual(first_path.read_bytes(), before)
        self.assertEqual(snapshots.load_state_snapshot(second_path).task_id, second.task_id)
        self.assertEqual(len(list(self.directory.glob("*.json"))), 2)

    def test_load_is_read_only_and_cannot_resume_the_agent(self):
        path = snapshots.save_state_snapshot(self.run_task(), self.directory)
        with patch.object(agent, "execute_tool", side_effect=AssertionError("Tools forbidden")):
            with patch.object(MockClient, "create", side_effect=AssertionError("API calls forbidden")):
                loaded = snapshots.load_state_snapshot(path)
                with self.assertRaises(ValidationError):
                    loaded.status = "running"
                with self.assertRaises(ValidationError):
                    loaded.token_usage.total_tokens = 0
                with self.assertRaises(agent.StopAgent):
                    agent.run_agent(MockClient(), state=loaded)

    def test_fresh_process_loads_without_importing_agent_or_sdk(self):
        path = snapshots.save_state_snapshot(self.run_task("calculate"), self.directory)
        script = (
            "import sys; from state_snapshot import load_state_snapshot; "
            "record = load_state_snapshot(sys.argv[1]); "
            "assert 'api_demo' not in sys.modules; assert 'openai' not in sys.modules; "
            "print(record.task_id); print(record.final_answer)"
        )
        process = subprocess.run(
            [sys.executable, "-B", "-X", "utf8", "-c", script, str(path)],
            cwd=Path(__file__).resolve().parent, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn(path.stem, process.stdout)
        self.assertIn("0.1", process.stdout)


if __name__ == "__main__":
    unittest.main()
