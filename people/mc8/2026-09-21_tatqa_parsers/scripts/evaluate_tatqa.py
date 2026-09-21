#!/usr/bin/env python3
"""Evaluate parser fidelity on the official English TAT-QA dev contexts."""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import statistics
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARSERS = ("pymupdf4llm", "pymupdf")


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\u00a0", " ").replace("’", "'").replace("–", "-").replace("—", "-").lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9%$€£().,'+\-/ ]", "", text)
    return text.strip()


def tokens(value: object) -> list[str]:
    return re.findall(r"[a-z]+(?:'[a-z]+)?|[-+]?\d+(?:[,.]\d+)*(?:\.\d+)?%?|[$€£]", normalize(value))


def levenshtein(reference: list[str], prediction: list[str]) -> int:
    if len(reference) > len(prediction):
        reference, prediction = prediction, reference
    previous = list(range(len(reference) + 1))
    for row_index, predicted in enumerate(prediction, start=1):
        current = [row_index]
        for column_index, expected in enumerate(reference, start=1):
            current.append(min(
                current[-1] + 1,
                previous[column_index] + 1,
                previous[column_index - 1] + (expected != predicted),
            ))
        previous = current
    return previous[-1]


def ordered_token_matches(reference: list[str], prediction: list[str]) -> int:
    """Order-preserving token matches (Ratcliff/Obershelp matching blocks)."""
    matcher = difflib.SequenceMatcher(None, reference, prediction, autojunk=False)
    return sum(block.size for block in matcher.get_matching_blocks())


def multiset_counts(expected: list[str], predicted: list[str]) -> tuple[int, int, int]:
    expected_counter = Counter(item for item in expected if item)
    predicted_counter = Counter(item for item in predicted if item)
    true_positive = sum((expected_counter & predicted_counter).values())
    return true_positive, sum(predicted_counter.values()), sum(expected_counter.values())


def flatten_tables(tables: list[list[list[str]]]) -> list[str]:
    return [normalize(cell) for table in tables for row in table for cell in row if normalize(cell)]


def table_shape(table: list[list[str]]) -> tuple[int, int]:
    return len(table), max((len(row) for row in table), default=0)


def f1(tp: int, predicted: int, expected: int) -> float:
    precision = tp / predicted if predicted else 0.0
    recall = tp / expected if expected else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def exact_answers(question: dict) -> list[str]:
    if question["answer_type"] not in {"span", "multi-span"}:
        return []
    answer = question["answer"]
    values = answer if isinstance(answer, list) else [answer]
    return [normalize(value) for value in values if normalize(value)]


def canonical_number(value: str) -> str:
    value = value.replace(",", "").rstrip("%")
    try:
        number = float(value)
    except ValueError:
        return value
    return f"{number:.12g}"


def derivation_operands(question: dict) -> list[str]:
    if question["answer_type"] != "arithmetic":
        return []
    return [canonical_number(value) for value in re.findall(r"\d[\d,.]*%?", question.get("derivation", ""))]


def reference_text(item: dict) -> str:
    paragraphs = [paragraph["text"] for paragraph in sorted(item["paragraphs"], key=lambda row: row["order"])]
    cells = [str(cell) for row in item["table"]["table"] for cell in row if str(cell).strip()]
    return "\n".join([*paragraphs, *cells])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "data" / "tatqa" / "raw" / "tatqa_dataset_dev.json")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data" / "tatqa" / "dev" / "manifest.csv")
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    by_uid = {item["table"]["uid"]: item for item in dataset}
    manifest = list(csv.DictReader(args.manifest.open(encoding="utf-8")))
    page_rows = []
    parser_rows = []

    for parser_name in PARSERS:
        runtime_path = args.output_root / parser_name / "runtime.csv"
        timings = {row["context_uid"]: row for row in csv.DictReader(runtime_path.open(encoding="utf-8"))}
        totals = Counter()
        runtimes = []
        successes = 0
        shape_matches = 0
        context_table_exact = 0
        for manifest_row in manifest:
            uid = manifest_row["context_uid"]
            item = by_uid[uid]
            prediction_path = args.output_root / parser_name / f"{uid}.json"
            payload = json.loads(prediction_path.read_text(encoding="utf-8")) if prediction_path.exists() else {}
            prediction_text = payload.get("text", "")
            prediction_tables = payload.get("tables", [])
            status = timings.get(uid, {}).get("status", "not_run")
            successful = bool(prediction_text) and status in {"ok", "output_present"}
            successes += int(successful)
            if timings.get(uid, {}).get("seconds"):
                runtimes.append(float(timings[uid]["seconds"]))

            expected_tokens = tokens(reference_text(item))
            predicted_tokens = tokens(prediction_text)
            word_edits = levenshtein(expected_tokens, predicted_tokens)
            ordered_matches = ordered_token_matches(expected_tokens, predicted_tokens)
            totals["word_edits"] += word_edits
            totals["reference_words"] += len(expected_tokens)
            totals["ordered_matches"] += ordered_matches

            expected_table = item["table"]["table"]
            expected_cells = flatten_tables([expected_table])
            predicted_cells = flatten_tables(prediction_tables)
            cell_tp, cell_predicted, cell_expected = multiset_counts(expected_cells, predicted_cells)
            totals["cell_tp"] += cell_tp
            totals["cell_predicted"] += cell_predicted
            totals["cell_expected"] += cell_expected
            shape_match = any(table_shape(table) == table_shape(expected_table) for table in prediction_tables)
            shape_matches += int(shape_match)
            exact_table = any(
                [[normalize(cell) for cell in row] for row in table]
                == [[normalize(cell) for cell in row] for row in expected_table]
                for table in prediction_tables
            )
            context_table_exact += int(exact_table)

            normalized_prediction = normalize(prediction_text)
            prediction_numbers = {
                canonical_number(value)
                for value in re.findall(r"(?<![a-z])\d[\d,.]*%?(?![a-z])", normalized_prediction)
            }
            extractive_total = extractive_retained = 0
            operand_total = operand_retained = 0
            for question in item["questions"]:
                answers = exact_answers(question)
                if answers:
                    extractive_total += 1
                    extractive_retained += int(all(answer in normalized_prediction for answer in answers))
                operands = derivation_operands(question)
                operand_total += len(operands)
                operand_retained += sum(operand in prediction_numbers for operand in operands)
            totals["extractive_total"] += extractive_total
            totals["extractive_retained"] += extractive_retained
            totals["operand_total"] += operand_total
            totals["operand_retained"] += operand_retained

            page_rows.append({
                "parser": parser_name,
                "context_uid": uid,
                "pages": manifest_row["pages"],
                "questions": manifest_row["questions"],
                "word_error_rate": word_edits / len(expected_tokens) if expected_tokens else 0.0,
                "text_accuracy_from_wer": max(0.0, 1 - word_edits / len(expected_tokens)) if expected_tokens else 1.0,
                "reading_order_accuracy": ordered_matches / len(expected_tokens) if expected_tokens else 1.0,
                "table_cell_f1": f1(cell_tp, cell_predicted, cell_expected),
                "table_shape_match": int(shape_match),
                "table_exact_match": int(exact_table),
                "extractive_answer_retention": extractive_retained / extractive_total if extractive_total else "",
                "arithmetic_operand_retention": operand_retained / operand_total if operand_total else "",
                "runtime_seconds": timings.get(uid, {}).get("seconds", ""),
                "run_status": status,
            })

        word_error_rate = totals["word_edits"] / totals["reference_words"]
        parser_rows.append({
            "parser": parser_name,
            "contexts": len(manifest),
            "successful_contexts": successes,
            "questions": sum(int(row["questions"]) for row in manifest),
            "word_error_rate": word_error_rate,
            "text_accuracy_from_wer": max(0.0, 1 - word_error_rate),
            "reading_order_accuracy": totals["ordered_matches"] / totals["reference_words"],
            "table_cell_precision": totals["cell_tp"] / totals["cell_predicted"] if totals["cell_predicted"] else 0.0,
            "table_cell_recall": totals["cell_tp"] / totals["cell_expected"] if totals["cell_expected"] else 0.0,
            "table_cell_f1": f1(totals["cell_tp"], totals["cell_predicted"], totals["cell_expected"]),
            "table_shape_accuracy": shape_matches / len(manifest),
            "table_exact_match": context_table_exact / len(manifest),
            "extractive_answer_retention": totals["extractive_retained"] / totals["extractive_total"],
            "arithmetic_operand_retention": totals["operand_retained"] / totals["operand_total"],
            "mean_seconds_per_context": statistics.fmean(runtimes),
            "median_seconds_per_context": statistics.median(runtimes),
        })

    args.results_dir.mkdir(parents=True, exist_ok=True)
    for path, rows in [
        (args.results_dir / "metrics_by_context.csv", page_rows),
        (args.results_dir / "metrics_by_parser.csv", parser_rows),
    ]:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(path)


if __name__ == "__main__":
    main()
