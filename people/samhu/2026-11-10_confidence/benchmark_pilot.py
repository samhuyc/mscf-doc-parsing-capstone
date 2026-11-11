"""Replay cached team outputs from one Git revision; never run or change a parser."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import types

from confidence import (agreement_signal, document_summary, evaluate_grouped,
                        native_summary, paddle_lines)

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PILOT = "people/samhu/2026-10-05_pilot_benchmark"
SPONSOR = "people/samhu/2026-09-29_sponsor_samples"
PADDLE = "people/mc8/2026-10-28_paddleocr"
PARSERS = ("mineru_ocr", "mineru_vlm", "pymupdf4llm", "pymupdf4llm_vlm", "paddleocr_ppstructurev3")
TARGET = "pilot_associated_amount_v1"


class Snapshot:
    def __init__(self, revision):
        self.revision = subprocess.check_output(
            ["git", "rev-parse", "--verify", revision + "^{commit}"], cwd=REPO, text=True).strip()
        self.hashes = {}

    def read(self, path):
        data = subprocess.check_output(["git", "show", f"{self.revision}:{path}"], cwd=REPO)
        self.hashes[path] = hashlib.sha256(data).hexdigest()
        return data.decode("utf-8")

    def json(self, path):
        return json.loads(self.read(path))

    def adapter(self):
        # Reuse the existing adapter unchanged, including its strict matching rules.
        module = types.ModuleType("pilot_adapter")
        module.__file__ = str(REPO / PILOT / "benchmark.py")
        exec(compile(self.read(PILOT + "/benchmark.py"), module.__file__, "exec"), module.__dict__)
        return module


def query_from_label(label):
    """Only schema/location inputs cross the prediction boundary; values are removed."""
    return {"rows": [{"label": r["label"]} for r in label["rows"]],
            "columns": [{"header_path": c["header_path"]} for c in label["columns"]]}


def extract_fields(adapter, markdown, query):
    tables, errors = adapter.extract_tables(adapter.soup_for(markdown))
    table, table_reason = adapter.choose_table(tables, query)
    found = []
    for row in query["rows"]:
        for column in query["columns"]:
            cell, reason = adapter.locate_cell(table, row["label"], column["header_path"])
            text = cell["text"] if cell is not None else None
            found.append({"text": text, "value_key": adapter.amount_key(text) if text is not None else None,
                          "reason": table_reason or reason, "table_parse_errors": errors})
    return found


def cached_path(document, parser):
    if parser == "paddleocr_ppstructurev3":
        return f"{PADDLE}/results/parsed/{document}/{parser}"
    if parser == "pymupdf4llm_vlm":
        return f"{PILOT}/results/parsed/{document}/{parser}"
    return f"{SPONSOR}/results/{document}/{parser}"


def collect(snapshot, include_drafts=False):
    adapter = snapshot.adapter()
    all_labels = [json.loads(line) for line in snapshot.read(PILOT + "/labels.jsonl").splitlines() if line.strip()]
    documents = {d["id"]: d for d in snapshot.json(PILOT + "/documents.json")}
    labels = [l for l in all_labels if l["kind"] == "table" and
              (l["review_status"] in {"human_verified", "adjudicated"} or
               include_drafts and l["review_status"] == "draft")]
    cache, rows, native, runs = {}, [], [], []
    for label in labels:
        doc, page = label["document"], label["page"]
        if documents[doc]["sha256"] != label["source_sha256"]:
            raise ValueError("Reference source hash mismatch")
        found = {}
        query = query_from_label(label)
        for parser in PARSERS:
            if (doc, parser) not in cache:
                payload = snapshot.json(cached_path(doc, parser) + "/pages.json")
                if payload["source_sha256"] != label["source_sha256"] or payload["parser"] != parser:
                    raise ValueError("Cached prediction source/parser mismatch")
                pages = payload["pages"]
                if len({p["page"] for p in pages}) != len(pages):
                    raise ValueError("Duplicate physical page ID")
                cache[doc, parser] = {p["page"]: p for p in pages}
                run = snapshot.json(cached_path(doc, parser) + "/run.json")
                runs.append({"document": doc, "parser": parser,
                             **{k: run[k] for k in ("versions", "settings", "model_config", "vlm_backend", "status") if k in run}})
            entry = cache[doc, parser].get(page)
            found[parser] = extract_fields(adapter, entry["markdown"] if entry else "", query)
        # Compute every inference-time signal before reading reference values.
        signals = {}
        for parser in PARSERS:
            signals[parser] = [agreement_signal(f["value_key"],
                [found[p][i]["value_key"] for p in PARSERS if p != parser])
                for i, f in enumerate(found[parser])]
        expected = [v for row in label["rows"] for v in row["values"]]
        for parser in PARSERS:
            for i, (field, signal) in enumerate(zip(found[parser], signals[parser])):
                rows.append({"id": f'{label["id"]}/cell{i+1}', "document": doc,
                    "group": "rolls_royce" if doc.startswith("rolls_royce_") else doc,
                    "source_sha256": label["source_sha256"], "page": page, "parser": parser,
                    "configuration_id": "five_cached_pipelines_" + snapshot.revision,
                    "target": TARGET, "level": "field", "review_status": label["review_status"],
                    "actual": field["text"], "reason": field["reason"],
                    "table_parse_errors": field["table_parse_errors"], **signal,
                    "correct": int(field["value_key"] is not None and field["value_key"] == adapter.amount_key(expected[i]))})
    # Native Paddle line-score diagnostics on labeled table pages, not field accuracy.
    for doc, page in sorted({(l["document"], l["page"]) for l in labels}):
        raw = snapshot.json(cached_path(doc, "paddleocr_ppstructurev3") + f"/raw/page_{page:03}.json")
        lines = paddle_lines(raw)
        native.append({"document": doc, "page": page,
                       "scope": "all retained OCR lines on selected table page",
                       **native_summary([line["native_score"] for line in lines])})
    return rows, native, runs


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def run(revision, output, include_drafts=False):
    snapshot = Snapshot(revision)
    rows, native, runs = collect(snapshot, include_drafts)
    report = evaluate_grouped(rows, include_drafts=include_drafts) if rows else {
        "reports": {}, "predictions": [], "folds": [], "deployment_validated": False}
    by_doc = defaultdict(list)
    for row in report["predictions"]:
        by_doc[row["parser"], row["document"]].append(row)
    document_reports = [{"parser": parser, "document": doc, **document_summary(items),
                         "observed_requested_field_accuracy": sum(x["correct"] for x in items) / len(items)}
                        for (parser, doc), items in sorted(by_doc.items())]
    document_errors = {}
    for parser in PARSERS:
        available = [r for r in document_reports if r["parser"] == parser and r["expected_requested_field_accuracy"] is not None]
        document_errors[parser] = {"n_documents": len(available), "mae":
            sum(abs(r["expected_requested_field_accuracy"] - r["observed_requested_field_accuracy"]) for r in available) / len(available)
            if available else None}
    report.update({"source_revision": snapshot.revision, "input_sha256": snapshot.hashes,
        "code_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in (HERE / "confidence.py", HERE / "benchmark_pilot.py")},
        "label_status": "draft_exploratory" if include_drafts else "reviewed_only",
        "scope": "Declared pilot table cells; amount/sign/suffix association, not all document content or currency/scale correctness",
        "n_fields": len(rows), "n_documents": len({r["document"] for r in rows}),
        "n_issuer_groups": len({r["group"] for r in rows}), "parser_roster": list(PARSERS),
        "native_paddle_diagnostics": native, "parser_runs": runs, "documents": document_reports,
        "document_accuracy_prediction": document_errors,
        "hosted_calls": 0, "parser_reruns": 0})
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "predictions.json", report.pop("predictions"))
    write_json(output / "summary.json", report)
    lines = ["# Confidence pilot replay", "",
             f'Source commit: `{snapshot.revision}`. Labels: **{report["label_status"]}**.', "",
             f'{len(rows)} requested parser/field pairs; {report["n_documents"]} documents; {report["n_issuer_groups"]} issuer groups.', "",
             "Probabilities are experimental held-out estimates. These are selected draft references, not production calibration.", "",
             "| Parser | Scored/requested | Requested-field accuracy | Raw Brier | Base-rate Brier | Calibrated Brier | ECE | AUROC |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, data in report["reports"].items():
        metric = data["held_out_calibrated"]
        fmt = lambda v: "N/A" if v is None else f"{v:.4f}"
        lines.append(f'| {name.split(" / ")[0]} | {data["scored_fields"]}/{data["requested_fields"]} | '
                     f'{data["requested_field_accuracy"]:.1%} | {fmt(data["raw_diagnostic_as_probability"]["brier"])} | '
                     f'{fmt(data["training_base_rate"]["brier"])} | {fmt(metric["brier"])} | {fmt(metric["ece"])} | {fmt(metric["auroc"])} |')
    lines += ["", "Brier/ECE/AUROC use only the scored, resolved fields. Missing/ambiguous cells remain in requested-field accuracy and score coverage. Empty evaluations are unavailable, never perfect.", "",
              "The raw score is a fixed parser-support diagnostic treated as a probability only for comparison. A separate sigmoid is fitted per parser using other issuer groups; both Rolls-Royce reports always stay together. The constant baseline uses the same training groups. No hyperparameters or review thresholds were selected on test folds.", "",
              "See summary.json for reliability bins, risk/coverage curves (relative to scored fields), fold provenance, native Paddle diagnostics and document summaries. Multiply curve coverage by score coverage to obtain coverage of all requested fields.", "",
              "This retrospective selection uses reference row/header names as the requested schema. It is not blind field discovery, full-document completeness, or an official benchmark submission. Cached MinerU VLM run metadata identifies MinerU 3.4.5 with MinerU2.5-Pro-2605-1.2B weights; no new inference or token-logprob collection was performed. Related parser pipelines can make the same mistake. Review labels and collect fresh issuer-disjoint examples before deployment.", ""]
    (output / "SUMMARY.md").write_text("\n".join(lines))
    print("\n".join(lines[:14]))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--revision", default="0baababc2652757982ae5898500a1c72409c4848")
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument("--include-drafts", action="store_true")
    args = cli.parse_args()
    run(args.revision, args.output, args.include_drafts)
