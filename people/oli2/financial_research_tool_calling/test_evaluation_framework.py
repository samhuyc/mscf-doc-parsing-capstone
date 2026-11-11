from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from evaluation.runner import DATASET, EvaluationError, aggregate, evaluate, load_dataset, render_report, score_turn, write_report


class EvaluationFrameworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset, cls.digest = load_dataset()
        cls.selected = ["E01", "E14", "E15", "E17"]
        cls.report = evaluate(cls.dataset, cls.digest, cls.selected)

    def test_dataset_lock_scope_and_unknown_company_gold(self):
        self.assertEqual(len(self.dataset["cases"]), 18)
        self.assertEqual(sum(len(case["turns"]) for case in self.dataset["cases"]), 25)
        for case in self.dataset["cases"]:
            for turn in case["turns"]:
                expected = turn["expected"]
                if expected["query"] and expected["query"]["company"] in {"UNH", "AMZN"}:
                    self.assertEqual(expected["behavior"], "abstain")
                    self.assertIsNone(expected["value"])
                    self.assertIsNone(expected["source"])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "dataset_v1.json"
            path.write_text(DATASET.read_text(encoding="utf-8") + " ", encoding="utf-8")
            Path(str(path) + ".sha256").write_text(self.digest, encoding="ascii")
            with self.assertRaises(EvaluationError):
                load_dataset(path)

    def test_grader_rejects_wrong_amount_unit_citation_query_and_overclarification(self):
        turn = self.report["cases"][0]["turns"][0]
        self.assertTrue(turn["evaluation"]["passed"])
        for old, new, metric in (
            ("98.9", "999", "answer_accuracy"),
            ("十亿美元", "百万美元", "answer_accuracy"),
            ("[S1]", "[S9]", "citation_accuracy"),
            ("#page=6", "#page=7", "citation_accuracy"),
        ):
            observed = deepcopy(turn["observed"])
            observed["answer"] = observed["answer"].replace(old, new)
            graded = score_turn(turn["expected"], observed, self.dataset["sources"])
            self.assertFalse(graded["scores"][metric])
        observed = deepcopy(turn["observed"])
        observed["query"]["year"] = 2024
        self.assertFalse(score_turn(turn["expected"], observed, self.dataset["sources"])["scores"]["answer_accuracy"])
        observed.update(behavior="clarify", answer="请明确问题。")
        graded = score_turn(turn["expected"], observed, self.dataset["sources"])
        for metric in ("answer_accuracy", "citation_accuracy", "abstention_accuracy"):
            self.assertFalse(graded["scores"][metric])

    def test_metric_denominators_and_expected_fault_are_not_hidden(self):
        metrics = self.report["metrics"]
        self.assertEqual((metrics["answer_accuracy"]["correct"], metrics["answer_accuracy"]["eligible"]), (2, 3))
        self.assertEqual((metrics["citation_accuracy"]["correct"], metrics["citation_accuracy"]["eligible"]), (2, 3))
        self.assertEqual((metrics["tool_selection_accuracy"]["correct"], metrics["tool_selection_accuracy"]["eligible"]), (3, 4))
        self.assertEqual((metrics["abstention_accuracy"]["correct"], metrics["abstention_accuracy"]["eligible"]), (2, 3))
        self.assertEqual((metrics["execution_success"]["correct"], metrics["execution_success"]["eligible"]), (3, 4))
        fault = next(case for case in self.report["cases"] if case["id"] == "E15")
        self.assertTrue(fault["passed"])
        self.assertFalse(fault["turns"][0]["evaluation"]["scores"]["execution_success"])
        empty = aggregate([])
        self.assertTrue(all(item["eligible"] == 0 and item["percent"] is None for item in empty.values()))

    def test_repeated_runs_and_reports_are_identical_and_html_escapes_text(self):
        second = evaluate(self.dataset, self.digest, self.selected)
        self.assertEqual(second, self.report)
        with tempfile.TemporaryDirectory() as folder:
            first_dir, second_dir = Path(folder) / "first", Path(folder) / "second"
            write_report(self.report, first_dir)
            write_report(second, second_dir)
            for name in ("report.json", "report.html", "tool_traces.jsonl"):
                self.assertEqual((first_dir / name).read_bytes(), (second_dir / name).read_bytes())
        escaped = deepcopy(self.report)
        escaped["cases"][0]["turns"][0]["question"] = "<script>alert(1)</script>"
        rendered = render_report(escaped)
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_stale_memory_and_fault_traces_are_observed_not_gold_substitutions(self):
        stale = next(case for case in self.report["cases"] if case["id"] == "E14")["turns"][0]
        observed = stale["observed"]
        historical = observed["contexts"][0]["historical_context"][0]
        self.assertTrue(historical["is_stale"])
        self.assertTrue(historical["requires_revalidation"])
        self.assertEqual(observed["tool_calls"][0]["name"], "search_report")
        self.assertEqual(observed["tool_calls"][0]["result"]["revenue_2025_q2"], "98.9")
        self.assertNotEqual(observed["task_id"], historical["record"]["snapshot_task_id"])
        fault = next(case for case in self.report["cases"] if case["id"] == "E15")["turns"][0]["observed"]
        self.assertEqual(fault["tool_calls"][0]["status"], "failed")
        self.assertEqual(fault["tool_calls"][0]["error_type"], "OSError")
        self.assertEqual(fault["failure_stage"], "tool_execution")
        self.assertIsNone(fault["final_answer"])
        self.assertNotIn("Injected evaluation search failure", json.dumps(fault))


if __name__ == "__main__":
    unittest.main()
