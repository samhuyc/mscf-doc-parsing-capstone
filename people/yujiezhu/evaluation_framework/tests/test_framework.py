import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import framework


def table(headers=("2025", "2024"), values=("(84.6)", "12.0"), spacer=False):
    gap = "<th></th>" if spacer else ""
    value_gap = "<td></td>" if spacer else ""
    return (f"<table><tr><th>Metric</th><th>{headers[0]}</th>{gap}<th>{headers[1]}</th></tr>"
            f"<tr><td>Profit</td><td>{values[0]}</td>{value_gap}<td>{values[1]}</td></tr></table>")


class MetricTests(unittest.TestCase):
    def test_exact_text_and_numbers(self):
        metrics, _, _ = framework.score_sample({"text": "Profit was (1,200.0)."},
                                                {"status": "success", "text": "Profit was (1,200.0)."}, 0.5)
        self.assertEqual(metrics["text_accuracy"].value, 1)
        self.assertEqual(metrics["numeric_f1"].value, 1)

    def test_percent_before_sentence_period_is_retained(self):
        self.assertEqual(framework.lexical_numbers("Margin was 35.5%."), ["35.5%"])

    def test_failed_output_stays_in_denominator(self):
        metrics, _, _ = framework.score_sample({"text": "some gold"}, {"status": "failed"}, 0.5)
        self.assertEqual(metrics["run_success_rate"].value, 0)
        self.assertEqual(metrics["text_accuracy"].value, 0)

    def test_failed_output_cannot_receive_credit_from_stale_payload(self):
        gold = {"tables": [{"html": table()}]}
        prediction = {"status": "failed", "tables": [{"html": table()}]}
        metrics, _, _ = framework.score_sample(gold, prediction, 0.5)
        self.assertEqual(metrics["table_exact_match"].value, 0)

    def test_blank_spacer_does_not_break_header_association(self):
        ref = {"table_facts": [{"row_label": "Profit", "header_path": ["2025"], "value": "(84.6)"},
                               {"row_label": "Profit", "header_path": ["2024"], "value": "12.0"}]}
        pred = {"status": "success", "tables": [{"html": table(spacer=True)}]}
        metrics, _, _ = framework.score_sample(ref, pred, 0.5)
        self.assertEqual(metrics["associated_value_accuracy"].value, 1)

    def test_swapped_headers_keep_presence_but_fail_association(self):
        ref = {"table_facts": [{"row_label": "Profit", "header_path": ["2025"], "value": "(84.6)"},
                               {"row_label": "Profit", "header_path": ["2024"], "value": "12.0"}]}
        pred = {"status": "success", "text": "Profit (84.6) 12.0",
                "tables": [{"html": table(headers=("2024", "2025"))}]}
        metrics, _, _ = framework.score_sample(ref, pred, 0.5)
        self.assertEqual(metrics["selected_value_presence"].value, 1)
        self.assertEqual(metrics["associated_value_accuracy"].value, 0)

    def test_lost_negative_sign_fails(self):
        ref = {"table_facts": [{"row_label": "Profit", "header_path": ["2025"], "value": "(84.6)"}]}
        pred = {"status": "success", "tables": [{"html": table(values=("84.6", "12.0"))}]}
        metrics, _, _ = framework.score_sample(ref, pred, 0.5)
        self.assertEqual(metrics["negative_value_accuracy"].value, 0)

    def test_layout_is_class_aware(self):
        ref = {"layout": [{"class": "table", "bbox": [0, 0, 10, 10]}]}
        pred = {"status": "success", "layout": [{"class": "figure", "bbox": [0, 0, 10, 10]}]}
        metrics, _, _ = framework.score_sample(ref, pred, 0.5)
        self.assertEqual(metrics["layout_f1"].value, 0)

    def test_metadata_reports_abstention_separately(self):
        ref = {"metadata": {"date": {"value": "2025-12-31", "status": "resolved"},
                            "publication": {"value": None, "status": "not_found"}}}
        pred = {"status": "success", "metadata": {}}
        metrics, _, _ = framework.score_sample(ref, pred, 0.5)
        self.assertEqual(metrics["metadata_exact_match_including_null"].value, 0)
        self.assertEqual(metrics["metadata_supported_value_exact_match"].value, 0)
        self.assertEqual(metrics["metadata_coverage"].value, 0)
        self.assertEqual(metrics["metadata_abstention_rate"].value, 0)
        self.assertEqual(metrics["metadata_missing_prediction_rate"].value, 1)

    def test_explicit_metadata_abstention_can_match_null_gold(self):
        ref = {"metadata": {"date": {"value": None, "status": "not_found"}}}
        pred = {"status": "success", "metadata": {"date": {"value": None, "status": "not_found"}}}
        metrics, _, _ = framework.score_sample(ref, pred, 0.5)
        self.assertEqual(metrics["metadata_exact_match_including_null"].value, 1)
        self.assertEqual(metrics["metadata_status_accuracy"].value, 1)
        self.assertEqual(metrics["metadata_abstention_rate"].value, 1)


class ContractTests(unittest.TestCase):
    def write_jsonl(self, path, rows):
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def test_hash_mismatch_is_rejected(self):
        manifest = [{"id": "x", "document_id": "d", "dataset": "s", "split": "test",
                     "input_kind": "pdf", "source_sha256": "a" * 64}]
        refs = [{"id": "x", "review_status": "human_verified", "text": "x"}]
        preds = [{"id": "x", "parser": "p", "status": "success", "source_sha256": "b" * 64}]
        result = framework.validate_contract(manifest, refs, preds, ROOT)
        self.assertFalse(result["valid"])
        self.assertTrue(any("hash mismatch" in item for item in result["errors"]))

    def test_drafts_are_gated_and_missing_predictions_score_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = root / "manifest.jsonl"; refs = root / "refs.jsonl"; preds = root / "preds.jsonl"
            samples = [
                {"id": "verified", "document_id": "doc", "dataset": "set", "split": "test", "input_kind": "pdf", "source_sha256": "a" * 64},
                {"id": "draft", "document_id": "doc", "dataset": "set", "split": "test", "input_kind": "pdf", "source_sha256": "b" * 64},
            ]
            references = [
                {"id": "verified", "review_status": "human_verified", "text": "gold"},
                {"id": "draft", "review_status": "draft", "text": "draft gold"},
            ]
            predictions = [{"id": "draft", "parser": "p", "status": "success", "source_sha256": "b" * 64, "text": "draft gold"}]
            self.write_jsonl(manifest, samples); self.write_jsonl(refs, references); self.write_jsonl(preds, predictions)
            report = framework.evaluate(manifest, refs, preds)
            self.assertEqual(report["settings"]["selected_references"], 1)
            sample = report["samples"][0]
            self.assertEqual(sample["id"], "verified")
            self.assertEqual(sample["status"], "missing")
            self.assertEqual(sample["metrics"]["text_accuracy"]["value"], 0)


if __name__ == "__main__":
    unittest.main()
