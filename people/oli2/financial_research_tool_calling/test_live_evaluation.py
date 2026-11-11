from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation import live_runner as runner
from evaluation.live_fixtures import client_for


class LiveEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite, cls.dataset, cls.digest = runner.load_suite()
        with redirect_stdout(io.StringIO()):
            cls.report = runner.evaluate(cls.suite, cls.dataset, cls.digest)

    def setUp(self):
        self.enterContext(redirect_stdout(io.StringIO()))

    def test_manifest_keeps_original_gold_and_rejects_modification(self):
        cases = {case["id"]:case for case in self.dataset["cases"]}
        for case in self.suite["cases"]:
            if "frozen_case" in case:
                self.assertEqual(case["turns"], cases[case["frozen_case"]]["turns"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"suite.json"
            path.write_bytes(runner.SUITE.read_bytes())
            Path(str(path)+".sha256").write_bytes(Path(str(runner.SUITE)+".sha256").read_bytes())
            runner.load_suite(path)
            path.write_text(path.read_text(encoding="utf-8").replace("L01", "L99"),encoding="utf-8")
            with self.assertRaises(runner.EvaluationError):
                runner.load_suite(path)

    def test_denominators_labels_traces_and_legacy_diagnostics(self):
        report = self.report
        self.assertEqual(report["evaluation_type"], "offline_runner_contract_check")
        self.assertEqual((report["case_count"],report["planned_turns"],report["requests"]),(8,11,28))
        self.assertEqual(report["usage"],dict(input_tokens=2800,output_tokens=560,total_tokens=3360))
        self.assertIsNone(report["cost"]["usd"])
        for name, metric in report["metrics"].items():
            expected = 7 if name in {"numerical_accuracy","citation_accuracy"} else 11
            self.assertEqual(metric["eligible"],expected)
            self.assertEqual(metric["correct"],expected)
        self.assertEqual(report["clarifications"],dict(required=2,correct=2,unnecessary=0))
        self.assertEqual(report["legacy_contract_failures"],[{"case_id":"L05","turn":1,"checks":["ambiguous_candidates"]}])
        comparison = next(row for row in report["turns"] if row["case_id"]=="L04" and row["turn"]==2)
        self.assertEqual([call["name"] for call in comparison["observed"]["tool_calls"]],["search_report","calculate"])
        self.assertEqual(comparison["observed"]["tool_calls"][-1]["result"],"7.7")
        self.assertEqual(len({row["observed"]["task_id"] for row in report["turns"]}),11)

    def test_grader_rejects_wrong_intent_amount_citation_and_extra_clarification(self):
        row = self.report["turns"][0]
        for field, value, metric in (
            ("answer",row["observed"]["answer"].replace("98.9","999"),"numerical_accuracy"),
            ("answer",row["observed"]["answer"].replace("[S1]","[S9]"),"citation_accuracy"),
            ("behavior","clarify","clarification_appropriateness"),
            ("tool_calls",[],"tool_selection_accuracy")):
            observed=deepcopy(row["observed"])
            observed[field]=value
            self.assertFalse(runner.grade(row["expected"],observed,self.dataset["sources"])["scores"][metric])
        observed=deepcopy(row["observed"])
        observed["understanding"]["period"]["year"]=2024
        self.assertFalse(runner.grade(row["expected"],observed,self.dataset["sources"])["scores"]["intent_understanding_accuracy"])

    def test_suite_cap_stops_paid_attempts_and_does_not_shrink_denominators(self):
        caps={**self.suite["caps"],"requests":1}
        report=runner.evaluate(self.suite,self.dataset,self.digest,caps=caps)
        self.assertEqual(report["requests"],1)
        self.assertTrue(report["stopped_early"])
        self.assertEqual(report["executed_turns"],1)
        self.assertEqual(report["metrics"]["intent_understanding_accuracy"]["eligible"],11)
        self.assertEqual(report["metrics"]["numerical_accuracy"]["eligible"],7)
        self.assertEqual(report["metrics"]["tool_selection_accuracy"]["correct"],0)

    def test_token_cap_stops_before_network_and_api_error_stops_entire_suite(self):
        report=runner.evaluate(self.suite,self.dataset,self.digest,caps={**self.suite["caps"],"total_tokens":100})
        self.assertEqual(report["requests"],0)
        self.assertTrue(report["stopped_early"])
        def broken(case_id,index):
            client=client_for(case_id,index)
            client.create=lambda **payload: (_ for _ in ()).throw(RuntimeError("private credential body"))
            return client
        report=runner.evaluate(self.suite,self.dataset,self.digest,fake_factory=broken)
        self.assertEqual(report["requests"],1)
        self.assertEqual(report["executed_turns"],1)
        self.assertNotIn("private credential",json.dumps(report))
        events=report["turns"][0]["observed"]["requests"]
        self.assertIsNone(runner.cost_estimate(events,True)["usd"])

    def test_gold_never_sent_and_rule_parser_never_used(self):
        clients=[]
        def observed_factory(case_id,index):
            client=client_for(case_id,index)
            clients.append(client)
            return client
        with patch("session_demo.resolve_question",side_effect=AssertionError("Rule parser forbidden")):
            runner.evaluate(self.suite,self.dataset,self.digest,fake_factory=observed_factory)
        for client in clients:
            for request in client.requests:
                self.assertNotIn('"expected"',json.dumps(request))
                self.assertNotIn('"gold_ref"',json.dumps(request))
            initial=client.requests[0]
            self.assertEqual(initial["text"]["format"]["name"],"financial_question")
            self.assertNotIn("98.9",json.dumps(initial["input"]))

    def test_cost_math_handles_cache_and_never_prices_fake_usage(self):
        events=[{"usage":dict(input_tokens=1000,output_tokens=100,total_tokens=1100,cached_tokens=100,cache_write_tokens=100)}]
        self.assertEqual(runner.cost_estimate(events,True)["usd"],"0.00286")
        self.assertIsNone(runner.cost_estimate(events,False)["usd"])
        self.assertIsNone(runner.cost_estimate([{"usage":None}],True)["usd"])

    def test_unnecessary_clarification_and_wrong_abstention_fail(self):
        for row in self.report["turns"]:
            if row["expected"]["behavior"] == "answer":
                observed=deepcopy(row["observed"])
                observed["behavior"]="clarify"
                grade=runner.grade(row["expected"],observed,self.dataset["sources"])
                self.assertFalse(grade["scores"]["clarification_appropriateness"])
                self.assertFalse(grade["scores"]["abstention_accuracy"])
            if row["expected"]["behavior"] == "abstain":
                observed=deepcopy(row["observed"])
                observed["behavior"]="answer"
                self.assertFalse(runner.grade(row["expected"],observed,self.dataset["sources"])["scores"]["abstention_accuracy"])

    def test_reports_escape_text_and_never_overwrite_old_baseline(self):
        report=deepcopy(self.report)
        report["turns"][0]["question"]="<script>test</script>"
        with tempfile.TemporaryDirectory() as directory:
            path=runner.write_report(report,directory)
            content=path.read_text(encoding="utf-8")
            self.assertIn("NOT GPT Evaluation",content)
            self.assertNotIn("<script>",content)
            self.assertIn("&lt;script&gt;",content)
            self.assertEqual(len((Path(directory)/"requests.jsonl").read_text(encoding="utf-8").splitlines()),28)

    def test_live_needs_confirmation_before_key_access_or_client(self):
        with patch("sys.argv",["live_runner.py","--live"]), \
                patch("openai.OpenAI",side_effect=AssertionError("No client")), \
                patch.object(runner.os,"environ",{}):
            self.assertEqual(runner.main(),1)


if __name__ == "__main__":
    unittest.main()
