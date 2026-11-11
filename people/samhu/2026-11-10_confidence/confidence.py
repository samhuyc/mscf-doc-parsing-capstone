"""Offline confidence signals and calibration. No parser or hosted-model calls."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

VERSION = "confidence-v1"


def probability(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a numeric probability")
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Probability must be finite and within [0, 1]")
    return float(value)


def native_summary(scores):
    """Summaries are diagnostic statistics, never sequence correctness probabilities."""
    values = [probability(s) for s in scores]
    return {"count": len(values), "mean": sum(values) / len(values) if values else None,
            "minimum": min(values) if values else None,
            "geometric_mean": (0.0 if 0 in values else math.exp(sum(map(math.log, values)) / len(values)))
            if values else None, "calibrated": False}


def paddle_lines(payload):
    """PaddleOCR 3 OCR / PP-StructureV3 overall_ocr_res JSON, not token logits."""
    body = payload.get("res", payload)
    body = body.get("overall_ocr_res", body)
    if "rec_texts" not in body or "rec_scores" not in body:
        raise ValueError("Expected Paddle rec_texts and rec_scores")
    texts, scores = body["rec_texts"], body["rec_scores"]
    if len(texts) != len(scores) or not all(isinstance(t, str) for t in texts):
        raise ValueError("Invalid Paddle text/score alignment")
    return [{"text": t, "native_score": probability(s), "level": "line",
             "score_kind": "paddle_rec_score", "p_correct": None}
            for t, s in zip(texts, scores)]


def token_logprob_summary(logprobs):
    """Selected autoregressive token log probabilities, including their length."""
    values = list(logprobs)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or
           not math.isfinite(v) or v > 0 for v in values):
        raise ValueError("Token log probabilities must be finite and <= 0")
    return {"count": len(values), "sum_logprob": sum(values) if values else None,
            "mean_logprob": sum(values) / len(values) if values else None,
            "geometric_mean": math.exp(sum(values) / len(values)) if values else None,
            "p_correct": None}


def agreement_signal(value, peers):
    """Call with canonically normalized values; None means unresolved, not blank.

    The denominator includes configured peers with missing output. This measures
    support, not conditional agreement among only the successful peers.
    """
    peers = list(peers)
    available = sum(v is not None for v in peers)
    matches = sum(v is not None and v == value for v in peers) if value is not None else 0
    score = (1 + matches) / (1 + len(peers)) if value is not None and peers else None
    return {"raw_score": score, "score_kind": "parser_support_v1",
            "peer_count": len(peers), "available_peers": available,
            "matching_peers": matches, "resolved": value is not None,
            "p_correct": None}


def sigmoid(z):
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


def validate_rows(rows):
    seen = set()
    source_groups = {}
    for r in rows:
        for key in ("id", "document", "group", "parser", "configuration_id", "score_kind", "target", "source_sha256"):
            if not isinstance(r.get(key), str) or not r[key]:
                raise ValueError(f"Missing string {key}")
        identity = (r["parser"], r["id"])
        if identity in seen:
            raise ValueError(f"Duplicate prediction {identity}")
        seen.add(identity)
        source = r["source_sha256"]
        if source in source_groups and source_groups[source] != r["group"]:
            raise ValueError("One source cannot appear in different split groups")
        source_groups[source] = r["group"]
        if r.get("raw_score") is not None:
            probability(r["raw_score"])
        if "correct" in r and (type(r["correct"]) is not int or r["correct"] not in (0, 1)):
            raise ValueError("correct must be integer 0 or 1")


def signature(row):
    return tuple(row[k] for k in ("parser", "score_kind", "target", "configuration_id"))


def fit(rows, *, include_drafts=False):
    """Fit ridge-regularized sigmoid(a * raw_score + b), with a fixed penalty.

    This is a fitted probability estimate, not a claim of validated calibration.
    The raw feature is fixed before evaluation, so no separate predictor training
    set is needed. Future learned features need train/calibration/test partitions.
    """
    validate_rows(rows)
    selected = [r for r in rows if r.get("raw_score") is not None]
    if not selected:
        raise ValueError("No scored calibration rows")
    if len({signature(r) for r in selected}) != 1:
        raise ValueError("Fit separately by parser, signal kind and target")
    if any("correct" not in r for r in selected):
        raise ValueError("Calibration requires correctness labels")
    if any(r.get("review_status") not in {"human_verified", "adjudicated"} for r in selected) and not include_drafts:
        raise ValueError("Unverified labels require --include-drafts")
    x, y = [r["raw_score"] for r in selected], [r["correct"] for r in selected]
    # Beta(1,1) baseline remains finite even when a training fold has one class.
    base = (sum(y) + 1) / (len(y) + 2)
    a, b = 0.0, math.log(base / (1 - base))
    mode = "constant_one_class" if len(set(y)) == 1 else "sigmoid"
    if mode == "sigmoid":
        for _ in range(2500):
            errors = [sigmoid(a * v + b) - target for v, target in zip(x, y)]
            da = sum(e * v for e, v in zip(errors, x)) / len(x) + 0.01 * a
            db = sum(errors) / len(x) + 0.001 * b
            a, b = a - 0.5 * da, b - 0.5 * db
            if max(abs(da), abs(db)) < 1e-9:
                break
    return {"version": VERSION, "signature": list(signature(selected[0])), "a": a, "b": b,
            "mode": mode, "baseline": base, "n": len(y), "groups": sorted({r["group"] for r in selected}),
            "sources": sorted({r["source_sha256"] for r in selected}),
            "label_status": "draft_exploratory" if any(r.get("review_status") not in
                {"human_verified", "adjudicated"} for r in selected) else "reviewed",
            "deployment_validated": False}


def predict(model, row):
    if model.get("version") != VERSION or tuple(model["signature"]) != signature(row):
        raise ValueError("Model version, parser, signal or correctness target mismatch")
    if row.get("raw_score") is None:
        return None
    return sigmoid(model["a"] * probability(row["raw_score"]) + model["b"])


def metrics(labels, scores, bins=10):
    y, p = list(labels), [probability(s) for s in scores]
    if len(y) != len(p) or any(type(v) is not int or v not in (0, 1) for v in y):
        raise ValueError("Aligned binary labels and probabilities required")
    if type(bins) is not int or bins <= 0:
        raise ValueError("bins must be a positive integer")
    if not y:
        return {"n": 0, "accuracy": None, "brier": None, "log_loss": None,
                "ece": None, "auroc": None, "reliability": [], "risk_coverage": []}
    n = len(y)
    reliability = []
    for i in range(bins):
        indices = [j for j, v in enumerate(p) if min(int(v * bins), bins - 1) == i]
        if indices:
            reliability.append({"lower": i / bins, "upper": (i + 1) / bins, "n": len(indices),
                                "confidence": sum(p[j] for j in indices) / len(indices),
                                "accuracy": sum(y[j] for j in indices) / len(indices)})
    positive, negative = [p[i] for i in range(n) if y[i]], [p[i] for i in range(n) if not y[i]]
    auc = sum((a > b) + 0.5 * (a == b) for a in positive for b in negative) / (len(positive) * len(negative)) if positive and negative else None
    curve = []
    # Ties enter together; no favorable label-dependent sorting within ties.
    for threshold in sorted(set(p), reverse=True):
        accepted = [i for i in range(n) if p[i] >= threshold]
        curve.append({"threshold": threshold, "accepted": len(accepted), "coverage": len(accepted) / n,
                      "error_rate": sum(1 - y[i] for i in accepted) / len(accepted)})
    return {"n": n, "accuracy": sum(y) / n,
            "brier": sum((a - b) ** 2 for a, b in zip(p, y)) / n,
            "log_loss": -sum(t * math.log(max(v, 1e-15)) + (1-t) * math.log(max(1-v, 1e-15)) for t, v in zip(y, p)) / n,
            "ece": sum(b["n"] * abs(b["confidence"] - b["accuracy"]) for b in reliability) / n,
            "auroc": auc, "reliability": reliability, "risk_coverage": curve}


def evaluate_grouped(rows, *, include_drafts=False):
    """Leave-one-issuer-group-out calibration; no field/page/engine split leakage."""
    validate_rows(rows)
    if any("correct" not in r for r in rows):
        raise ValueError("Evaluation requires labels for every requested field")
    if not include_drafts and any(r.get("review_status") not in {"human_verified", "adjudicated"} for r in rows):
        raise ValueError("Unverified evaluation labels require --include-drafts")
    if len({r["group"] for r in rows}) < 2:
        raise ValueError("At least two independent document groups are required")
    predictions, folds = [], []
    for group in sorted({r["group"] for r in rows}):
        for sig in sorted({signature(r) for r in rows}):
            train = [r for r in rows if r["group"] != group and signature(r) == sig]
            test = [r for r in rows if r["group"] == group and signature(r) == sig]
            if not test:
                continue
            model = fit(train, include_drafts=include_drafts) if any(r.get("raw_score") is not None for r in train) else None
            scored_test = [r for r in test if r.get("raw_score") is not None] if model else []
            folds.append({"held_out_group": group, "signature": list(sig), "model": model,
                          "held_out_metrics": metrics([r["correct"] for r in scored_test],
                                                      [predict(model, r) for r in scored_test])})
            for r in test:
                predictions.append({**r, "p_correct": predict(model, r) if model else None,
                                    "baseline": model["baseline"] if model and r.get("raw_score") is not None else None})
    reports = {}
    for sig in sorted({signature(r) for r in rows}):
        subset = [r for r in predictions if signature(r) == sig]
        scored = [r for r in subset if r["p_correct"] is not None]
        labels = [r["correct"] for r in scored]
        reports[" / ".join(sig)] = {
            "requested_fields": len(subset), "scored_fields": len(scored),
            "score_coverage": len(scored) / len(subset),
            "requested_field_accuracy": sum(r["correct"] for r in subset) / len(subset),
            "raw_diagnostic_as_probability": metrics(labels, [r["raw_score"] for r in scored]),
            "training_base_rate": metrics(labels, [r["baseline"] for r in scored]),
            "held_out_calibrated": metrics(labels, [r["p_correct"] for r in scored])}
    return {"protocol": "leave_one_issuer_group_out", "folds": folds, "reports": reports,
            "predictions": predictions, "deployment_validated": False}


def document_summary(rows):
    """Expected accuracy over declared requested fields, NOT P(entire PDF correct)."""
    probabilities = [probability(r["p_correct"]) for r in rows if r.get("p_correct") is not None]
    n = len(rows)
    return {"requested_fields": n, "scored_fields": len(probabilities),
            "score_coverage": len(probabilities) / n if n else None,
            "mean_scored_field_probability": sum(probabilities) / len(probabilities) if probabilities else None,
            "expected_requested_field_accuracy": sum(probabilities) / n if n and
                all(r.get("p_correct") is not None or r.get("resolved") is False for r in rows) else None,
            "probability_all_correct": None}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True)
    for name in ("fit", "score", "evaluate"):
        p = commands.add_parser(name)
        p.add_argument("input", type=Path, help="JSON array of records")
        p.add_argument("--output", type=Path, required=True)
        if name != "score":
            p.add_argument("--include-drafts", action="store_true")
        else:
            p.add_argument("--model", type=Path, required=True)
    args = cli.parse_args()
    rows = json.loads(args.input.read_text())
    validate_rows(rows)
    if args.command == "fit":
        result = fit(rows, include_drafts=args.include_drafts)
    elif args.command == "evaluate":
        result = evaluate_grouped(rows, include_drafts=args.include_drafts)
    else:
        model = json.loads(args.model.read_text())
        result = [{**r, "p_correct": predict(model, r), "deployment_validated": False} for r in rows]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
