"""Score MinerU Markdown outputs against the FinTabNet pilot references."""

from __future__ import annotations

import argparse
import html
import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self.current_table = None
        self.current_row = None
        self.current_cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.current_table = []
        elif tag == "tr" and self.current_table is not None:
            self.current_row = []
        elif tag in {"td", "th"} and self.current_row is not None:
            self.current_cell = []

    def handle_data(self, data):
        if self.current_cell is not None:
            self.current_cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.current_cell is not None:
            text = normalize("".join(self.current_cell))
            self.current_row.append(text)
            self.current_cell = None
        elif tag == "tr" and self.current_row is not None:
            self.current_table.append(self.current_row)
            self.current_row = None
        elif tag == "table" and self.current_table is not None:
            self.tables.append(self.current_table)
            self.current_table = None


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def parse_tables(content: str) -> list[list[list[str]]]:
    parser = TableParser()
    parser.feed(content)
    if parser.tables:
        return parser.tables
    tables = []
    rows = []
    for line in content.splitlines():
        if re.match(r"^\s*\|.*\|\s*$", line):
            cells = [normalize(cell) for cell in line.strip().strip("|").split("|")]
            if not all(set(cell) <= {"-", ":", " "} for cell in cells):
                rows.append(cells)
        elif rows:
            tables.append(rows)
            rows = []
    if rows:
        tables.append(rows)
    return tables


def reference_table(record: dict) -> list[list[str]]:
    cells = record["cells"][0]
    columns = record["cols"]
    return [
        [normalize("".join(cell["tokens"])) for cell in cells[offset:offset + columns]]
        for offset in range(0, len(cells), columns)
    ]


def numbers(text: str) -> Counter:
    return Counter(re.findall(r"(?<![A-Za-z0-9])[-+]?\d[\d,]*(?:\.\d+)?%?", text))


def score(reference: list[list[str]], prediction: list[list[str]]) -> dict:
    gold_cells = [cell for row in reference for cell in row]
    predicted_cells = [cell for row in prediction for cell in row]
    aligned = sum(a == b for a, b in zip(gold_cells, predicted_cells))
    cell_total = max(len(gold_cells), len(predicted_cells))
    row_exact = sum(a == b for a, b in zip(reference, prediction))
    row_total = max(len(reference), len(prediction))
    gold_numbers = numbers(" ".join(gold_cells))
    predicted_numbers = numbers(" ".join(predicted_cells))
    matched = sum((gold_numbers & predicted_numbers).values())
    numeric_total = sum(gold_numbers.values()) + sum(predicted_numbers.values())
    return {
        "reference_rows": len(reference),
        "predicted_rows": len(prediction),
        "reference_cells": len(gold_cells),
        "predicted_cells": len(predicted_cells),
        "cell_exact_accuracy": aligned / cell_total if cell_total else 0.0,
        "row_exact_accuracy": row_exact / row_total if row_total else 0.0,
        "numeric_f1": 2 * matched / numeric_total if numeric_total else None,
        "structure_exact": reference == prediction,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-dir", type=Path, default=Path("data/fintabnet_otsl_pilot"))
    parser.add_argument("--mineru-dir", type=Path, default=Path("content/fintabnet_pilot/mineru_output"))
    parser.add_argument("--output", type=Path, default=Path("RESULTS.json"))
    args = parser.parse_args()

    rows = [json.loads(line) for line in (args.pilot_dir / "manifest.jsonl").read_text().splitlines() if line.strip()]
    results = []
    for index, record in enumerate(rows):
        sample_id = record["sample_id"]
        markdown = next(args.mineru_dir.glob(f"{sample_id}/**/{sample_id}.md"), None)
        if markdown is None:
            colab_id = f"fintabnet-{index:04d}"
            markdown = next(args.mineru_dir.glob(f"{colab_id}/**/{colab_id}.md"), None)
        result = {"sample_id": sample_id, "status": "failed"}
        if markdown is None:
            result["error"] = "MinerU Markdown output not found"
        else:
            reference_tables = [reference_table(record)]
            predicted_tables = parse_tables(markdown.read_text(encoding="utf-8"))
            if not reference_tables or not predicted_tables:
                result["error"] = f"table missing (reference={len(reference_tables)}, prediction={len(predicted_tables)})"
            else:
                result.update(status="success", **score(reference_tables[0], predicted_tables[0]))
        results.append(result)

    successful = [item for item in results if item["status"] == "success"]
    summary = {"samples": len(results), "successful": len(successful), "failed": len(results) - len(successful)}
    for metric in ("cell_exact_accuracy", "row_exact_accuracy", "numeric_f1"):
        values = [item[metric] for item in successful if item.get(metric) is not None]
        summary[metric] = sum(values) / len(values) if values else None
    output = {"dataset": "docling-project/FinTabNet_OTSL", "split": "test", "summary": summary, "samples": results}
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
