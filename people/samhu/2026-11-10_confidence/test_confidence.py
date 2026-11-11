import copy
import json
import math
import unittest

from confidence import (agreement_signal, document_summary, evaluate_grouped, fit,
                        metrics, native_summary, paddle_lines, predict, probability,
                        token_logprob_summary, validate_rows)


def row(i, score, correct, group="a", **changes):
    return {"id": str(i), "document": group, "group": group, "source_sha256": group,
            "parser": "fixture", "configuration_id": "fixture-v1", "score_kind": "fixture", "target": "exact",
            "raw_score": score, "correct": correct, "review_status": "human_verified", **changes}


class SignalTests(unittest.TestCase):
    def test_invalid_probabilities_are_not_silently_clipped(self):
        for value in (True, "0.9", -0.01, 1.01, math.nan, math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                probability(value)

    def test_native_empty_zero_and_log_underflow(self):
        self.assertIsNone(native_summary([])["mean"])
        self.assertEqual(native_summary([1, 0])["geometric_mean"], 0)
        self.assertAlmostEqual(native_summary([0.25, 1])["geometric_mean"], 0.5)
        summary = token_logprob_summary([-1000] * 100)
        self.assertEqual(summary["sum_logprob"], -100000)
        self.assertIsNone(summary["p_correct"])
        self.assertIsNone(token_logprob_summary([])["mean_logprob"])
        with self.assertRaises(ValueError):
            token_logprob_summary([0.1])

    def test_paddle_scope_and_alignment(self):
        lines = paddle_lines({"res": {"overall_ocr_res": {"rec_texts": ["£12"], "rec_scores": [0.99]}}})
        self.assertEqual(lines[0]["level"], "line")
        self.assertIsNone(lines[0]["p_correct"])
        with self.assertRaises(ValueError):
            paddle_lines({"rec_texts": ["x"], "rec_scores": []})
        with self.assertRaises(ValueError):
            paddle_lines({"layout_score": 1})

    def test_agreement_missing_is_not_blank(self):
        self.assertIsNone(agreement_signal(None, [None, None])["raw_score"])
        self.assertIsNone(agreement_signal("0", [])["raw_score"])
        self.assertEqual(agreement_signal("", ["", None])["raw_score"], 2/3)
        signal = agreement_signal("0", ["-", None])
        self.assertEqual(signal["raw_score"], 1/3)
        self.assertEqual(signal["available_peers"], 1)
        self.assertIsNone(signal["p_correct"])

    def test_consensus_does_not_claim_truth(self):
        self.assertEqual(agreement_signal("wrong", ["wrong"])["raw_score"], 1)
        self.assertEqual(metrics([0], [1])["brier"], 1)


class CalibrationTests(unittest.TestCase):
    def test_calibration_improves_known_overconfidence(self):
        # Independent synthetic groups with 50% correctness at a raw score of 0.99.
        train = [row(i, 0.99, i % 2) for i in range(40)]
        model = fit(train)
        test = [row(i, 0.99, i % 2, "new") for i in range(40)]
        calibrated = metrics([r["correct"] for r in test], [predict(model, r) for r in test])
        self.assertLess(calibrated["brier"], metrics([r["correct"] for r in test], [0.99]*40)["brier"])
        self.assertAlmostEqual(predict(model, test[0]), 0.5, delta=0.02)
        self.assertEqual(predict(json.loads(json.dumps(model)), test[0]), predict(model, test[0]))

    def test_drafts_and_incompatible_models_rejected(self):
        rows = [row(1, 0.9, 1, review_status="draft")]
        with self.assertRaises(ValueError):
            fit(rows)
        model = fit(rows, include_drafts=True)
        self.assertFalse(model["deployment_validated"])
        with self.assertRaises(ValueError):
            predict(model, row(2, 0.9, 1, parser="different"))
        with self.assertRaises(ValueError):
            predict(model, row(2, 0.9, 1, target="different"))
        with self.assertRaises(ValueError):
            predict(model, row(2, 0.9, 1, configuration_id="different"))

    def test_one_class_small_sample_and_missing(self):
        model = fit([row(1, 0.99, 1)])
        self.assertEqual(model["mode"], "constant_one_class")
        self.assertAlmostEqual(predict(model, row(2, 0.99, 1)), 2/3)
        self.assertIsNone(predict(model, row(3, None, 0)))
        with self.assertRaises(ValueError):
            fit([row(1, None, 0)])

    def test_group_leakage_and_duplicate_guards(self):
        with self.assertRaises(ValueError):
            validate_rows([row(1, 0.9, 1), row(2, 0.8, 0, "b", source_sha256="a")])
        with self.assertRaises(ValueError):
            validate_rows([row(1, 0.9, 1), row(1, 0.8, 0)])
        with self.assertRaises(ValueError):
            evaluate_grouped([row(1, 0.9, 1)])

    def test_held_out_labels_cannot_change_their_predictions(self):
        rows = [row(f"{g}{i}", 0.2 + 0.6*(i % 2), i % 2, g) for g in ("a", "b", "c") for i in range(8)]
        before = evaluate_grouped(rows)
        altered = copy.deepcopy(rows)
        for r in altered:
            if r["group"] == "a":
                r["correct"] = 1-r["correct"]
        after = evaluate_grouped(altered)
        self.assertEqual([r["p_correct"] for r in before["predictions"] if r["group"] == "a"],
                         [r["p_correct"] for r in after["predictions"] if r["group"] == "a"])
        for f in before["folds"]:
            self.assertNotIn(f["held_out_group"], f["model"]["groups"])
            self.assertNotIn(f["held_out_group"], f["model"]["sources"])


class MetricsTests(unittest.TestCase):
    def test_hand_computed_metrics(self):
        result = metrics([0, 1], [0.25, 0.75], bins=2)
        self.assertAlmostEqual(result["brier"], 0.0625)
        self.assertAlmostEqual(result["ece"], 0.25)
        self.assertAlmostEqual(result["log_loss"], -math.log(0.75))
        self.assertEqual(result["auroc"], 1)

    def test_ties_empty_single_class_endpoints(self):
        result = metrics([0, 1], [0.5, 0.5])
        self.assertEqual(result["auroc"], 0.5)
        self.assertEqual(len(result["risk_coverage"]), 1)
        self.assertEqual(result["risk_coverage"][0]["coverage"], 1)
        self.assertIsNone(metrics([], [])["accuracy"])
        self.assertIsNone(metrics([1], [1])["auroc"])
        self.assertEqual(metrics([0, 1], [0, 1])["ece"], 0)
        with self.assertRaises(ValueError):
            metrics([1], [0.5, 0.5])

    def test_document_mean_is_not_all_correct_probability(self):
        report = document_summary([{"p_correct": 0.9}, {"p_correct": 0.9}])
        self.assertEqual(report["expected_requested_field_accuracy"], 0.9)
        self.assertIsNone(report["probability_all_correct"])
        report = document_summary([{"p_correct": 0.8}, {"p_correct": None, "resolved": False}])
        self.assertEqual(report["expected_requested_field_accuracy"], 0.4)
        self.assertEqual(report["score_coverage"], 0.5)
        self.assertIsNone(document_summary([{"p_correct": None, "resolved": True}])["expected_requested_field_accuracy"])
        self.assertIsNone(document_summary([])["expected_requested_field_accuracy"])


if __name__ == "__main__":
    unittest.main()
