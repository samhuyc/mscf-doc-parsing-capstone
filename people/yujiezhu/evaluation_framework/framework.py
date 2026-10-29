#!/usr/bin/env python3
"""Auditable, capability-based evaluation for document parsers.

The framework deliberately has no parser/model dependencies.  Adapters write the
JSONL contract described in README.md; this module validates and scores it using
only Python's standard library.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import html
import json
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


FRAMEWORK_VERSION = "1.0.0"
REVIEW_STATES = {"draft", "human_verified", "adjudicated", "excluded"}
RUN_STATES = {"success", "partial", "empty", "failed", "timeout", "missing"}
NUMBER_RE = re.compile(
    r"(?<![\w.])(?:\(\s*)?[+\-−–]?\s*[$£€¥]?\s*[+\-−–]?\s*"
    r"\d+(?:[,，]\d{3})*(?:\.\d+)?\s*(?:%|bn|mn|m|k|pts|p)?\s*\)?(?![\w]|[.,]\d)",
    re.IGNORECASE,
)
WORD_RE = re.compile(r"[a-z]+(?:'[a-z]+)?|[-+]?\d+(?:[,.]\d+)*(?:\.\d+)?%?|[$€£¥]", re.I)


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\u00a0", " ").replace("’", "'").replace("−", "-").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", html.unescape(text)).strip().lower()


def words(value: Any) -> list[str]:
    return [match.group(0).lower() for match in WORD_RE.finditer(normalize(value))]


def lexical_numbers(value: Any) -> list[str]:
    return [re.sub(r"\s+", "", match.group(0).replace("−", "-").replace("–", "-")) for match in NUMBER_RE.finditer(str(value or ""))]


def amount_key(value: Any) -> tuple[str, str, str] | tuple[str, str]:
    """Conservative financial-number key; preserves percent/basis suffixes."""
    raw = re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or ""))).lower()
    raw = raw.replace("−", "-").replace("–", "-").replace("，", ",")
    match = re.fullmatch(r"(\()?([+\-]?)(?:[$£€¥])?([+\-]?)(\d[\d,]*(?:\.\d+)?)(%|bn|mn|m|k|pts|p)?(\))?", raw)
    if not match:
        return ("text", normalize(raw))
    negative = bool(match.group(1) and match.group(6)) or "-" in (match.group(2), match.group(3))
    number = match.group(4).replace(",", "")
    try:
        canonical = format(float(number), ".12g")
    except ValueError:
        canonical = number
    return ("number", ("-" if negative else "") + canonical, match.group(5) or "")


def canonical_operand(value: Any) -> tuple[str, str] | tuple[str, str, str]:
    return amount_key(value)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_jsonl(path: Path) -> str:
    return sha256(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {error}") from error
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_no}: each JSONL record must be an object")
        rows.append(row)
    return rows


def levenshtein(a: list[Any] | str, b: list[Any] | str) -> int:
    if len(a) > len(b):
        a, b = b, a
    previous = list(range(len(a) + 1))
    for row_index, right in enumerate(b, 1):
        current = [row_index]
        for column_index, left in enumerate(a, 1):
            current.append(min(current[-1] + 1, previous[column_index] + 1,
                               previous[column_index - 1] + (left != right)))
        previous = current
    return previous[-1]


@dataclass(frozen=True)
class Metric:
    value: float | None
    numerator: float | None = None
    denominator: float | None = None
    direction: str = "higher"
    note: str | None = None

    def json(self) -> dict[str, Any]:
        return {"value": self.value, "numerator": self.numerator,
                "denominator": self.denominator, "direction": self.direction,
                **({"note": self.note} if self.note else {})}


def ratio(numerator: float, denominator: float, *, direction: str = "higher", note: str | None = None) -> Metric:
    return Metric(numerator / denominator if denominator else None, numerator, denominator, direction, note)


def prf(gold: Counter, predicted: Counter, prefix: str) -> dict[str, Metric]:
    matched = sum((gold & predicted).values())
    ng, np = sum(gold.values()), sum(predicted.values())
    if not ng and not np:
        return {f"{prefix}_precision": Metric(None), f"{prefix}_recall": Metric(None), f"{prefix}_f1": Metric(None)}
    precision = ratio(matched, np) if np else Metric(0.0, 0, 0, note="No predictions for a non-empty reference")
    recall = ratio(matched, ng) if ng else Metric(None)
    f1 = ratio(2 * matched, ng + np)
    return {f"{prefix}_precision": precision, f"{prefix}_recall": recall, f"{prefix}_f1": f1}


@dataclass(frozen=True)
class Cell:
    row: int
    col: int
    rowspan: int
    colspan: int
    text: str
    header: bool = False


@dataclass
class Table:
    cells: list[Cell]
    rows: int
    cols: int

    def ordered_text(self) -> list[str]:
        return [cell.text for cell in sorted(self.cells, key=lambda x: (x.row, x.col))]

    def structure(self) -> list[str]:
        result = []
        for row in range(self.rows):
            result.append("row")
            for cell in sorted((c for c in self.cells if c.row == row), key=lambda x: x.col):
                result.append(f"cell:{cell.rowspan}:{cell.colspan}:{int(cell.header)}")
        return result

    def grid(self) -> list[list[str]]:
        grid = [["" for _ in range(self.cols)] for _ in range(self.rows)]
        for cell in self.cells:
            grid[cell.row][cell.col] = cell.text
        return grid


class _TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[Table] = []
        self.errors: list[str] = []
        self.depth = 0
        self.rows: list[list[tuple[str, int, int, bool]]] = []
        self.row: list[tuple[str, int, int, bool]] | None = None
        self.cell_data: list[str] | None = None
        self.cell_span = (1, 1)
        self.cell_header = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self.rows = []
            else:
                self.errors.append("nested_table")
        elif self.depth == 1 and tag == "tr":
            self.row = []
        elif self.depth == 1 and tag in {"td", "th"} and self.row is not None:
            try:
                rs, cs = int(attrs_dict.get("rowspan") or 1), int(attrs_dict.get("colspan") or 1)
                if not (1 <= rs <= 1000 and 1 <= cs <= 1000):
                    raise ValueError
            except ValueError:
                self.errors.append("invalid_span")
                rs, cs = 1, 1
            self.cell_span, self.cell_header, self.cell_data = (rs, cs), tag == "th", []

    def handle_data(self, data: str) -> None:
        if self.cell_data is not None:
            self.cell_data.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.depth == 1 and tag in {"td", "th"} and self.cell_data is not None and self.row is not None:
            self.row.append((normalize(" ".join(self.cell_data)), *self.cell_span, self.cell_header))
            self.cell_data = None
        elif self.depth == 1 and tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == "table" and self.depth:
            if self.depth == 1:
                self.tables.append(table_from_rows(self.rows))
            self.depth -= 1

    def close(self) -> None:
        super().close()
        if self.depth:
            self.errors.append("unclosed_table")


def table_from_rows(rows: list[list[tuple[str, int, int, bool]]]) -> Table:
    occupied: set[tuple[int, int]] = set()
    cells: list[Cell] = []
    max_col = 0
    for ri, row in enumerate(rows):
        ci = 0
        for text, rowspan, colspan, header_cell in row:
            while (ri, ci) in occupied:
                ci += 1
            cells.append(Cell(ri, ci, rowspan, colspan, text, header_cell))
            occupied.update((r, c) for r in range(ri, ri + rowspan) for c in range(ci, ci + colspan))
            max_col = max(max_col, ci + colspan)
            ci += colspan
    max_row = max([len(rows), *(c.row + c.rowspan for c in cells)], default=0)
    return Table(cells, max_row, max_col)


def table_from_grid(grid: list[list[Any]]) -> Table:
    if not isinstance(grid, list) or any(not isinstance(row, list) for row in grid):
        raise ValueError("table grid must be a list of row lists")
    cells = [Cell(ri, ci, 1, 1, normalize(value), ri == 0)
             for ri, row in enumerate(grid) for ci, value in enumerate(row)]
    return Table(cells, len(grid), max((len(row) for row in grid), default=0))


def parse_tables(value: Any) -> tuple[list[Table], list[str]]:
    if value is None:
        return [], []
    items = value if isinstance(value, list) else [value]
    tables, errors = [], []
    for item in items:
        if isinstance(item, list):
            tables.append(table_from_grid(item))
        elif isinstance(item, dict) and "grid" in item:
            tables.append(table_from_grid(item["grid"]))
        elif isinstance(item, dict) and "html" in item:
            parser = _TableHTMLParser()
            parser.feed(str(item["html"])); parser.close()
            tables.extend(parser.tables); errors.extend(parser.errors)
        elif isinstance(item, str):
            parser = _TableHTMLParser()
            parser.feed(item); parser.close()
            tables.extend(parser.tables); errors.extend(parser.errors)
        else:
            errors.append("unsupported_table_representation")
    return tables, errors


def sequence_similarity(a: list[Any], b: list[Any]) -> float:
    if not a and not b:
        return 1.0
    return max(0.0, 1 - levenshtein(a, b) / max(len(a), len(b)))


def cell_sequence_similarity(a: list[str], b: list[str]) -> float:
    """Ordered cell similarity with character-level substitution cost."""
    if not a and not b:
        return 1.0
    previous = [float(index) for index in range(len(a) + 1)]
    for row_index, right in enumerate(b, 1):
        current = [float(row_index)]
        for column_index, left in enumerate(a, 1):
            maximum = max(len(left), len(right))
            substitution = levenshtein(left, right) / maximum if maximum else 0.0
            current.append(min(current[-1] + 1, previous[column_index] + 1,
                               previous[column_index - 1] + substitution))
        previous = current
    return max(0.0, 1 - previous[-1] / max(len(a), len(b)))


def table_pair_scores(gold: Table, predicted: Table) -> dict[str, Any]:
    gc, pc = Counter(gold.ordered_text()), Counter(predicted.ordered_text())
    content_f1 = 2 * sum((gc & pc).values()) / (sum(gc.values()) + sum(pc.values())) if gc or pc else 1.0
    ordered_content = cell_sequence_similarity(gold.ordered_text(), predicted.ordered_text())
    structure = sequence_similarity(gold.structure(), predicted.structure())
    gold_numbers = Counter((c.row, c.col, c.rowspan, c.colspan, n)
                           for c in gold.cells for n in lexical_numbers(c.text))
    pred_numbers = Counter((c.row, c.col, c.rowspan, c.colspan, n)
                           for c in predicted.cells for n in lexical_numbers(c.text))
    rows_gold, rows_pred = gold.grid(), predicted.grid()
    row_exact = sum(a == b for a, b in zip(rows_gold, rows_pred))
    return {
        "match_score": (content_f1 + ordered_content + structure) / 3,
        "structure": structure,
        "content": ordered_content,
        "cell_matches": sum((gc & pc).values()), "gold_cells": sum(gc.values()), "pred_cells": sum(pc.values()),
        "numeric_matches": sum((gold_numbers & pred_numbers).values()),
        "gold_numbers": sum(gold_numbers.values()), "pred_numbers": sum(pred_numbers.values()),
        "shape_exact": (gold.rows, gold.cols) == (predicted.rows, predicted.cols),
        "table_exact": gold.structure() == predicted.structure() and gold.ordered_text() == predicted.ordered_text(),
        "row_exact": row_exact, "gold_rows": gold.rows, "pred_rows": predicted.rows,
    }


def optimal_pairs(matrix: list[list[float]]) -> list[tuple[int, int]]:
    """Maximum-weight one-to-one pairing; exact for <=16 columns, greedy above."""
    if not matrix or not matrix[0]:
        return []
    transpose = len(matrix) > len(matrix[0])
    working = [list(row) for row in zip(*matrix)] if transpose else matrix
    rows, cols = len(working), len(working[0])
    if cols > 16:
        candidates = sorted(((working[i][j], i, j) for i in range(rows) for j in range(cols)), reverse=True)
        used_i, used_j, pairs = set(), set(), []
        for _, i, j in candidates:
            if i not in used_i and j not in used_j:
                pairs.append((i, j)); used_i.add(i); used_j.add(j)
                if len(pairs) == rows:
                    break
    else:
        states: dict[int, tuple[float, list[tuple[int, int]]]] = {0: (0.0, [])}
        for i in range(rows):
            next_states: dict[int, tuple[float, list[tuple[int, int]]]] = {}
            for mask, (score, pairs_so_far) in states.items():
                for j in range(cols):
                    if mask & (1 << j):
                        continue
                    candidate = (score + working[i][j], pairs_so_far + [(i, j)])
                    new_mask = mask | (1 << j)
                    if new_mask not in next_states or candidate[0] > next_states[new_mask][0]:
                        next_states[new_mask] = candidate
            states = next_states
        pairs = max(states.values(), key=lambda item: item[0])[1]
    return [(j, i) if transpose else (i, j) for i, j in pairs]


def score_tables(gold_value: Any, pred_value: Any) -> tuple[dict[str, Metric], dict[str, Any], list[str]]:
    gold, gold_errors = parse_tables(gold_value)
    predicted, pred_errors = parse_tables(pred_value)
    if gold_errors:
        raise ValueError(f"invalid reference table: {gold_errors}")
    if not gold:
        return {}, {"gold_tables": 0, "predicted_tables": len(predicted)}, pred_errors
    pair_matrix = [[table_pair_scores(g, p) for p in predicted] for g in gold]
    pairs = optimal_pairs([[cell["match_score"] for cell in row] for row in pair_matrix]) if predicted else []
    scored = [pair_matrix[i][j] | {"gold_table": i, "predicted_table": j} for i, j in pairs]
    denominator = max(len(gold), len(predicted))
    cell_matches = sum(x["cell_matches"] for x in scored)
    gold_cells = sum(len(t.cells) for t in gold)
    pred_cells = sum(len(t.cells) for t in predicted)
    numeric_matches = sum(x["numeric_matches"] for x in scored)
    gold_numbers = sum(sum(len(lexical_numbers(c.text)) for c in t.cells) for t in gold)
    pred_numbers = sum(sum(len(lexical_numbers(c.text)) for c in t.cells) for t in predicted)
    metrics = {
        "table_count_similarity": ratio(min(len(gold), len(predicted)), denominator),
        "table_structure_similarity": ratio(sum(x["structure"] for x in scored), denominator),
        "table_content_similarity": ratio(sum(x["content"] for x in scored), denominator),
        "table_shape_accuracy": ratio(sum(x["shape_exact"] for x in scored), len(gold)),
        "table_exact_match": ratio(sum(x["table_exact"] for x in scored), len(gold)),
        "table_row_exact_accuracy": ratio(sum(x["row_exact"] for x in scored),
                                          max(sum(t.rows for t in gold), sum(t.rows for t in predicted))),
    }
    metrics["table_cell_precision"] = ratio(cell_matches, pred_cells) if pred_cells else Metric(0.0, 0, 0)
    metrics["table_cell_recall"] = ratio(cell_matches, gold_cells)
    metrics["table_cell_f1"] = ratio(2 * cell_matches, gold_cells + pred_cells)
    metrics["table_numeric_cell_f1"] = (ratio(2 * numeric_matches, gold_numbers + pred_numbers)
                                         if gold_numbers + pred_numbers else Metric(None))
    details = {"gold_tables": len(gold), "predicted_tables": len(predicted), "pairs": scored}
    return metrics, details, pred_errors


def cells_covering(table: Table, row: int, col: int) -> list[Cell]:
    return [cell for cell in table.cells if cell.row <= row < cell.row + cell.rowspan
            and cell.col <= col < cell.col + cell.colspan]


def score_table_facts(facts: list[dict[str, Any]], tables: list[Table], text: str) -> tuple[dict[str, Metric], list[dict[str, Any]]]:
    if not facts:
        return {}, []
    presence = association = format_match = negative_total = negative_match = 0
    audits = []
    page_numbers = Counter(lexical_numbers(text + " " + " ".join(c.text for t in tables for c in t.cells)))
    for fact in facts:
        value = str(fact["value"])
        lexical = lexical_numbers(value)
        is_present = bool(lexical) and all(page_numbers[item] > 0 for item in lexical)
        presence += is_present
        candidates: list[Cell] = []
        for table in tables:
            row_cells = [c for c in table.cells if normalize(c.text) == normalize(fact["row_label"])]
            if len(row_cells) != 1:
                continue
            target_row = row_cells[0].row
            for col in range(table.cols):
                headers = {c.text for r in range(target_row) for c in cells_covering(table, r, col)}
                if all(any(normalize(header) == normalize(expected) for header in headers)
                       for expected in fact.get("header_path", [])):
                    candidates.extend(c for c in cells_covering(table, target_row, col) if c.row == target_row)
        unique = {(c.row, c.col, c.text): c for c in candidates}
        matched_cells = [c for c in unique.values() if amount_key(c.text) == amount_key(value)]
        associated = len(matched_cells) == 1
        association += associated
        exact = associated and normalize(matched_cells[0].text) == normalize(value)
        format_match += exact
        negative = amount_key(value)[0] == "number" and str(amount_key(value)[1]).startswith("-")
        if negative:
            negative_total += 1
            negative_match += associated
        audits.append({"fact": fact, "present": is_present, "associated": associated,
                       "exact_format": exact, "candidate_count": len(unique)})
    metrics = {
        "selected_value_presence": ratio(presence, len(facts)),
        "associated_value_accuracy": ratio(association, len(facts)),
        "associated_value_format_accuracy": ratio(format_match, len(facts)),
        "negative_value_accuracy": ratio(negative_match, negative_total) if negative_total else Metric(None),
    }
    return metrics, audits


def iou(a: list[float], b: list[float]) -> float:
    if len(a) != 4 or len(b) != 4:
        raise ValueError("bbox must contain [x0, y0, x1, y1]")
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    intersection = ix * iy
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - intersection
    return intersection / union if union else 0.0


def score_layout(gold: list[dict[str, Any]], predicted: list[dict[str, Any]], threshold: float) -> tuple[dict[str, Metric], dict[str, Any]]:
    if not gold:
        return {}, {}
    classes = sorted({str(x["class"]) for x in gold} | {str(x["class"]) for x in predicted})
    totals = Counter(); by_class = {}
    for name in classes:
        gs = [x["bbox"] for x in gold if str(x["class"]) == name]
        ps = [x["bbox"] for x in predicted if str(x["class"]) == name]
        candidates = sorted(((iou(g, p), gi, pi) for gi, g in enumerate(gs) for pi, p in enumerate(ps)), reverse=True)
        used_g, used_p, matched = set(), set(), []
        for overlap, gi, pi in candidates:
            if overlap < threshold:
                break
            if gi not in used_g and pi not in used_p:
                used_g.add(gi); used_p.add(pi); matched.append(overlap)
        values = {"tp": len(matched), "gold": len(gs), "predicted": len(ps), "iou_sum": sum(matched)}
        by_class[name] = values
        totals.update(values)
    matches = totals["tp"]
    metrics = {
        "layout_precision": ratio(matches, totals["predicted"]) if totals["predicted"] else Metric(0.0, 0, 0),
        "layout_recall": ratio(matches, totals["gold"]),
        "layout_f1": ratio(2 * matches, totals["gold"] + totals["predicted"]),
        "layout_mean_matched_iou": ratio(totals["iou_sum"], matches) if matches else Metric(0.0, 0, 0),
    }
    return metrics, {"iou_threshold": threshold, "by_class": by_class}


def score_metadata(gold: dict[str, Any], predicted: dict[str, Any]) -> tuple[dict[str, Metric], list[dict[str, Any]]]:
    if not gold:
        return {}, []
    exact = status_match = supported_match = supported_total = coverage = abstentions = missing = 0
    audits = []
    for field, expected in gold.items():
        expected = expected if isinstance(expected, dict) else {"value": expected, "status": "resolved"}
        present = field in predicted
        actual = predicted.get(field)
        if not present:
            actual = {"value": None, "status": "missing_prediction"}
        elif not isinstance(actual, dict):
            actual = {"value": actual, "status": "resolved" if actual is not None else "not_found"}
        expected_value, actual_value = expected.get("value"), actual.get("value")
        exact += present and actual_value == expected_value
        status_match += present and actual.get("status") == expected.get("status", "resolved")
        if expected_value is not None:
            supported_total += 1; supported_match += present and actual_value == expected_value
        coverage += actual.get("status") == "resolved" and actual_value is not None
        abstentions += present and actual.get("status") in {"not_found", "ambiguous"}
        missing += not present
        audits.append({"field": field, "expected": expected, "actual": actual})
    metrics = {
        "metadata_exact_match_including_null": ratio(exact, len(gold)),
        "metadata_status_accuracy": ratio(status_match, len(gold)),
        "metadata_supported_value_exact_match": ratio(supported_match, supported_total) if supported_total else Metric(None),
        "metadata_coverage": ratio(coverage, len(gold)),
        "metadata_abstention_rate": ratio(abstentions, len(gold), direction="lower"),
        "metadata_missing_prediction_rate": ratio(missing, len(gold), direction="lower"),
    }
    return metrics, audits


def score_sample(reference: dict[str, Any], prediction: dict[str, Any], iou_threshold: float) -> tuple[dict[str, Metric], dict[str, Any], list[str]]:
    status = prediction.get("status", "missing")
    usable = status in {"success", "partial"}
    pred_text = str(prediction.get("text") or "") if usable else ""
    pred_table_value = prediction.get("tables", []) if usable else []
    metrics: dict[str, Metric] = {"run_success_rate": ratio(int(status == "success"), 1)}
    details: dict[str, Any] = {}
    flags: list[str] = []

    if "text" in reference:
        gold_text = str(reference["text"])
        gt, pt = words(gold_text), words(pred_text)
        edits = levenshtein(gt, pt)
        ordered = sum(block.size for block in difflib.SequenceMatcher(None, gt, pt, autojunk=False).get_matching_blocks())
        char_gold, char_pred = normalize(gold_text), normalize(pred_text)
        char_edits = levenshtein(char_gold, char_pred)
        metrics.update({
            "word_error_rate": ratio(edits, len(gt), direction="lower"),
            "text_accuracy": ratio(max(0, len(gt) - edits), len(gt)),
            "reading_order_accuracy": ratio(ordered, len(gt)),
            "character_similarity": ratio(max(0, max(len(char_gold), len(char_pred)) - char_edits),
                                          max(len(char_gold), len(char_pred))),
        })
        gold_numbers, pred_numbers = Counter(lexical_numbers(gold_text)), Counter(lexical_numbers(pred_text))
        metrics.update(prf(gold_numbers, pred_numbers, "numeric"))
        details["numeric_missing"] = dict((gold_numbers - pred_numbers).most_common(10))
        details["numeric_extra"] = dict((pred_numbers - gold_numbers).most_common(10))

    pred_tables, pred_table_errors = parse_tables(pred_table_value)
    if "tables" in reference:
        table_metrics, table_details, errors = score_tables(reference["tables"], pred_table_value)
        metrics.update(table_metrics); details["tables"] = table_details
        flags.extend(errors)
    if pred_table_errors:
        flags.extend(pred_table_errors)

    fact_metrics, fact_details = score_table_facts(reference.get("table_facts", []), pred_tables, pred_text)
    metrics.update(fact_metrics)
    if fact_details:
        details["table_facts"] = fact_details

    searchable_prediction = normalize(pred_text + " " + " ".join(c.text for t in pred_tables for c in t.cells))
    spans = [normalize(x) for x in reference.get("critical_spans", []) if normalize(x)]
    if spans:
        matched = sum(bool(re.search(r"(?<!\w)" + re.escape(span) + r"(?!\w)", searchable_prediction)) for span in spans)
        metrics["critical_span_recall"] = ratio(matched, len(spans))

    operands = [canonical_operand(x) for x in reference.get("arithmetic_operands", [])]
    if operands:
        predicted_operands = Counter(canonical_operand(x) for x in lexical_numbers(searchable_prediction))
        gold_operands = Counter(operands)
        metrics["arithmetic_operand_retention"] = ratio(sum((gold_operands & predicted_operands).values()), sum(gold_operands.values()))

    layout_metrics, layout_details = score_layout(reference.get("layout", []), prediction.get("layout", []) if usable else [], iou_threshold)
    metrics.update(layout_metrics)
    if layout_details:
        details["layout"] = layout_details

    metadata_metrics, metadata_details = score_metadata(reference.get("metadata", {}), prediction.get("metadata", {}) if usable else {})
    metrics.update(metadata_metrics)
    if metadata_details:
        details["metadata"] = metadata_details
    return metrics, details, sorted(set(flags))


def json_pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError("JSON pointer must start with /")
    current = document
    for part in pointer[1:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        current = current[int(key)] if isinstance(current, list) else current[key]
    return current


def validate_evidence(reference: dict[str, Any], manifest: dict[str, Any], root: Path) -> list[str]:
    errors = []
    artifacts = manifest.get("artifacts", {})
    for index, evidence in enumerate(reference.get("evidence", [])):
        label = f"evidence[{index}]"
        name = evidence.get("artifact")
        if name not in artifacts:
            errors.append(f"{label}: unknown artifact {name!r}"); continue
        spec = artifacts[name] if isinstance(artifacts[name], dict) else {"path": artifacts[name]}
        path = (root / spec["path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            errors.append(f"{label}: artifact escapes artifact root"); continue
        if not path.is_file():
            errors.append(f"{label}: artifact missing: {path}"); continue
        if spec.get("sha256") and sha256(path) != spec["sha256"]:
            errors.append(f"{label}: artifact hash mismatch"); continue
        try:
            if "pointer" in evidence:
                source = json_pointer(json.loads(path.read_text(encoding="utf-8")), evidence["pointer"])
            else:
                source = path.read_text(encoding="utf-8")
            source = str(source)
            start, end, quote = int(evidence["start"]), int(evidence["end"]), str(evidence["quote"])
            if start < 0 or end < start or source[start:end] != quote:
                errors.append(f"{label}: quote/offset mismatch")
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"{label}: invalid evidence: {error}")
    return errors


def index_unique(rows: list[dict[str, Any]], key, label: str) -> dict[Any, dict[str, Any]]:
    result = {}
    for row in rows:
        item_key = key(row)
        if item_key in result:
            raise ValueError(f"duplicate {label}: {item_key!r}")
        result[item_key] = row
    return result


def validate_contract(manifest_rows: list[dict[str, Any]], reference_rows: list[dict[str, Any]],
                      prediction_rows: list[dict[str, Any]], artifact_root: Path) -> dict[str, Any]:
    manifests = index_unique(manifest_rows, lambda x: x.get("id"), "manifest id")
    references = index_unique(reference_rows, lambda x: x.get("id"), "reference id")
    predictions = index_unique(prediction_rows, lambda x: (x.get("parser"), x.get("id")), "parser/sample prediction")
    errors, warnings = [], []
    if None in manifests or None in references:
        errors.append("Every manifest and reference needs a non-null id")
    if set(manifests) != set(references):
        errors.append(f"Reference IDs must equal manifest IDs; missing={sorted(set(manifests)-set(references))}, extra={sorted(set(references)-set(manifests))}")
    for sample_id, manifest in manifests.items():
        for field in ("document_id", "dataset", "split", "input_kind", "source_sha256"):
            if field not in manifest:
                errors.append(f"manifest {sample_id}: missing {field}")
        source_hash = manifest.get("source_sha256", "")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", str(source_hash)):
            errors.append(f"manifest {sample_id}: source_sha256 must be a 64-character hexadecimal SHA-256")
        if sample_id in references:
            state = references[sample_id].get("review_status", "draft")
            if state not in REVIEW_STATES:
                errors.append(f"reference {sample_id}: invalid review_status {state!r}")
            if "text" in references[sample_id] and not normalize(references[sample_id]["text"]):
                errors.append(f"reference {sample_id}: text reference must be non-empty; omit it when unavailable")
            errors.extend(f"reference {sample_id}: {error}" for error in validate_evidence(references[sample_id], manifest, artifact_root))
    for (parser_name, sample_id), prediction in predictions.items():
        if not parser_name:
            errors.append(f"prediction {sample_id}: missing parser")
        if sample_id not in manifests:
            errors.append(f"prediction {parser_name}/{sample_id}: sample is not in manifest"); continue
        state = prediction.get("status")
        if state not in RUN_STATES - {"missing"}:
            errors.append(f"prediction {parser_name}/{sample_id}: invalid status {state!r}")
        expected_hash = manifests[sample_id].get("source_sha256")
        if prediction.get("source_sha256") != expected_hash:
            errors.append(f"prediction {parser_name}/{sample_id}: source hash mismatch")
    return {"valid": not errors, "errors": errors, "warnings": warnings,
            "manifest_samples": len(manifests), "references": len(references),
            "predictions": len(predictions), "parsers": sorted({key[0] for key in predictions if key[0]})}


def aggregate_metric_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    names = sorted({name for row in rows for name in row["metrics"]})
    result = {}
    for name in names:
        entries = [row["metrics"][name] for row in rows if name in row["metrics"] and row["metrics"][name].value is not None]
        if not entries:
            result[name] = {"macro": None, "micro": None, "document_macro": None, "applicable_samples": 0}
            continue
        by_document: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            metric = row["metrics"].get(name)
            if metric and metric.value is not None:
                by_document[row["document_id"]].append(metric.value)
        num_entries = [entry for entry in entries if entry.numerator is not None and entry.denominator is not None]
        numerator = sum(entry.numerator or 0 for entry in num_entries)
        denominator = sum(entry.denominator or 0 for entry in num_entries)
        result[name] = {
            "macro": statistics.fmean(entry.value for entry in entries),
            "micro": numerator / denominator if denominator else None,
            "document_macro": statistics.fmean(statistics.fmean(values) for values in by_document.values()),
            "applicable_samples": len(entries), "documents": len(by_document),
            "numerator": numerator if num_entries else None, "denominator": denominator if num_entries else None,
            "direction": entries[0].direction,
        }
    return result


def make_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    timings = [row["runtime_seconds"] for row in rows if isinstance(row.get("runtime_seconds"), (int, float))]
    statuses = Counter(row["status"] for row in rows)
    return {
        "samples": len(rows), "documents": len({row["document_id"] for row in rows}),
        "status_counts": dict(sorted(statuses.items())), "metrics": aggregate_metric_rows(rows),
        "runtime": {"observations": len(timings), "total_seconds": sum(timings) if timings else None,
                    "mean_seconds": statistics.fmean(timings) if timings else None,
                    "median_seconds": statistics.median(timings) if timings else None},
    }


def evaluate(manifest_path: Path, references_path: Path, predictions_path: Path, *,
             include_drafts: bool = False, artifact_root: Path | None = None,
             iou_threshold: float = 0.5, stratify_by: list[str] | None = None) -> dict[str, Any]:
    manifest_rows, reference_rows, prediction_rows = map(read_jsonl, (manifest_path, references_path, predictions_path))
    artifact_root = (artifact_root or manifest_path.parent).resolve()
    validation = validate_contract(manifest_rows, reference_rows, prediction_rows, artifact_root)
    if not validation["valid"]:
        raise ValueError("Contract validation failed:\n- " + "\n- ".join(validation["errors"]))
    manifests = {x["id"]: x for x in manifest_rows}
    references = {x["id"]: x for x in reference_rows}
    predictions = {(x["parser"], x["id"]): x for x in prediction_rows}
    parsers = sorted({x["parser"] for x in prediction_rows})
    if not parsers:
        raise ValueError("No parser names found in predictions")
    allowed = {"human_verified", "adjudicated"} | ({"draft"} if include_drafts else set())
    selected_ids = [sample_id for sample_id in manifests if references[sample_id].get("review_status", "draft") in allowed]
    rows = []
    for parser_name in parsers:
        for sample_id in selected_ids:
            manifest, reference = manifests[sample_id], references[sample_id]
            prediction = predictions.get((parser_name, sample_id), {"id": sample_id, "parser": parser_name, "status": "missing"})
            metrics, details, flags = score_sample(reference, prediction, iou_threshold)
            rows.append({
                "parser": parser_name, "id": sample_id, "document_id": manifest["document_id"],
                "dataset": manifest["dataset"], "split": manifest["split"], "input_kind": manifest["input_kind"],
                "attributes": manifest.get("attributes", {}), "review_status": reference.get("review_status", "draft"),
                "status": prediction.get("status", "missing"), "runtime_seconds": prediction.get("runtime_seconds"),
                "metrics": metrics, "details": details, "flags": flags,
            })
    summary = {parser_name: make_group([row for row in rows if row["parser"] == parser_name]) for parser_name in parsers}
    strata = {}
    for field in stratify_by or ["dataset", "input_kind"]:
        values = sorted({str(row.get(field, row["attributes"].get(field, "unknown"))) for row in rows})
        strata[field] = {}
        for value in values:
            selected = [row for row in rows if str(row.get(field, row["attributes"].get(field, "unknown"))) == value]
            strata[field][value] = {parser_name: make_group([row for row in selected if row["parser"] == parser_name])
                                     for parser_name in parsers}
    serial_rows = [{**row, "metrics": {name: metric.json() for name, metric in row["metrics"].items()}} for row in rows]
    return {
        "framework_version": FRAMEWORK_VERSION,
        "evaluation_status": "scored" if selected_ids else "no_reviewed_references",
        "notes": [
            "No composite score is computed; metric families answer different questions.",
            "Missing/failed predictions remain in every applicable denominator.",
            "N/A means the reference did not support that metric, not perfect performance.",
            "Custom diagnostics are not official dataset leaderboard metrics unless explicitly reproduced and version-matched.",
        ],
        "settings": {"include_drafts": include_drafts, "iou_threshold": iou_threshold,
                     "selected_references": len(selected_ids), "total_references": len(reference_rows)},
        "provenance": {"manifest_sha256": sha256_jsonl(manifest_path),
                       "references_sha256": sha256_jsonl(references_path),
                       "predictions_sha256": sha256_jsonl(predictions_path),
                       "scorer_sha256": sha256(Path(__file__))},
        "validation": validation, "summary": summary, "strata": strata, "samples": serial_rows,
    }


def write_summary_csv(report: dict[str, Any], path: Path) -> None:
    rows = []
    for parser_name, group in report["summary"].items():
        for metric_name, metric in group["metrics"].items():
            rows.append({"parser": parser_name, "metric": metric_name, **metric})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        fields = ["parser", "metric", "direction", "macro", "micro", "document_macro",
                  "applicable_samples", "documents", "numerator", "denominator"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "score"):
        command = subparsers.add_parser(name)
        command.add_argument("manifest", type=Path)
        command.add_argument("references", type=Path)
        command.add_argument("predictions", type=Path)
        command.add_argument("--artifact-root", type=Path)
    score_parser = subparsers.choices["score"]
    score_parser.add_argument("--output", type=Path, required=True)
    score_parser.add_argument("--summary-csv", type=Path)
    score_parser.add_argument("--include-drafts", action="store_true")
    score_parser.add_argument("--iou-threshold", type=float, default=0.5)
    score_parser.add_argument("--stratify-by", action="append", default=[])
    args = parser.parse_args()

    manifest, references, predictions = map(read_jsonl, (args.manifest, args.references, args.predictions))
    root = (args.artifact_root or args.manifest.parent).resolve()
    if args.command == "validate":
        result = validate_contract(manifest, references, predictions, root)
        print(json.dumps(result, indent=2))
        if not result["valid"]:
            raise SystemExit(1)
        return
    if not 0 < args.iou_threshold <= 1:
        parser.error("--iou-threshold must be in (0, 1]")
    report = evaluate(args.manifest, args.references, args.predictions,
                      include_drafts=args.include_drafts, artifact_root=root,
                      iou_threshold=args.iou_threshold, stratify_by=args.stratify_by or None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.summary_csv:
        write_summary_csv(report, args.summary_csv)
    print(json.dumps({"evaluation_status": report["evaluation_status"], "settings": report["settings"],
                      "parsers": {name: {"samples": group["samples"], "status_counts": group["status_counts"]}
                                  for name, group in report["summary"].items()}}, indent=2))


if __name__ == "__main__":
    cli()
