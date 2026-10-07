#!/usr/bin/env python3
"""Run Level 1 reconstruction and Level 2 financial-record survival checks."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import openpyxl


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from excel_parser import extract_workbook  # noqa: E402


def direct_json_value(value: Any) -> Any:
    """Independent JSON normalization for the direct-read comparison."""

    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value)


def level_one(workbook_path: Path) -> dict[str, Any]:
    canonical = extract_workbook(workbook_path)
    formulas = openpyxl.load_workbook(workbook_path, data_only=False)
    cached = openpyxl.load_workbook(workbook_path, data_only=True)
    checks = 0
    mismatches: list[dict[str, Any]] = []
    try:
        for sheet_payload in canonical["workbook"]["sheets"]:
            sheet_name = sheet_payload["name"]
            formula_sheet = formulas[sheet_name]
            cached_sheet = cached[sheet_name]
            by_coordinate = {
                cell["coordinate"]: cell for cell in sheet_payload["cells"]
            }
            for table in sheet_payload["tables"]:
                for coordinate in table["cell_coordinates"]:
                    serialized = by_coordinate[coordinate]
                    direct_value = direct_json_value(formula_sheet[coordinate].value)
                    checks += 1
                    if serialized["value"] != direct_value:
                        mismatches.append(
                            {
                                "sheet": sheet_name,
                                "table": table["id"],
                                "coordinate": coordinate,
                                "field": "value",
                                "expected": direct_value,
                                "actual": serialized["value"],
                            }
                        )
                    if serialized["formula"] is not None:
                        direct_cached = direct_json_value(cached_sheet[coordinate].value)
                        checks += 1
                        if serialized["cached_value"] != direct_cached:
                            mismatches.append(
                                {
                                    "sheet": sheet_name,
                                    "table": table["id"],
                                    "coordinate": coordinate,
                                    "field": "cached_value",
                                    "expected": direct_cached,
                                    "actual": serialized["cached_value"],
                                }
                            )
        passed = checks - len(mismatches)
        return {
            "workbook": workbook_path.name,
            "checks": checks,
            "passed": passed,
            "accuracy": passed / checks if checks else 1.0,
            "mismatches": mismatches,
        }
    finally:
        formulas.close()
        cached.close()


def level_two(annotation_path: Path) -> dict[str, Any]:
    gold = json.loads(annotation_path.read_text(encoding="utf-8"))
    canonical = extract_workbook(annotation_path.parent / gold["workbook"])
    sheets = {sheet["name"]: sheet for sheet in canonical["workbook"]["sheets"]}

    label_survival = 0
    label_coordinates = 0
    value_checks = 0
    value_matches = 0
    complete_records = 0
    failures: list[dict[str, Any]] = []
    for record in gold["records"]:
        sheet = sheets[record["sheet"]]
        cells = {cell["coordinate"]: cell for cell in sheet["cells"]}
        label_exists = any(cell["value"] == record["label"] for cell in sheet["cells"])
        label_at_coordinate = (
            cells.get(record["label_coordinate"], {}).get("value") == record["label"]
        )
        label_survival += int(label_exists)
        label_coordinates += int(label_at_coordinate)
        record_values_match = True
        for expected in record["values"]:
            value_checks += 1
            actual = cells.get(expected["coordinate"], {}).get(expected["field"])
            matched = actual == expected["expected"]
            value_matches += int(matched)
            record_values_match = record_values_match and matched
            if not matched:
                failures.append(
                    {
                        "sheet": record["sheet"],
                        "label": record["label"],
                        "coordinate": expected["coordinate"],
                        "field": expected["field"],
                        "expected": expected["expected"],
                        "actual": actual,
                    }
                )
        if label_at_coordinate and record_values_match:
            complete_records += 1

    record_count = len(gold["records"])
    return {
        "workbook": gold["workbook"],
        "records": record_count,
        "line_item_survival": label_survival / record_count if record_count else 1.0,
        "coordinate_accuracy": label_coordinates / record_count if record_count else 1.0,
        "value_accuracy": value_matches / value_checks if value_checks else 1.0,
        "complete_record_accuracy": complete_records / record_count if record_count else 1.0,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures", type=Path, default=ROOT / "fixtures", help="fixture directory"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "results" / "evaluation.json"
    )
    args = parser.parse_args()

    workbooks = sorted(args.fixtures.glob("*.xlsx"))
    if not workbooks:
        parser.error("no .xlsx fixtures found; run scripts/generate_fixtures.py first")
    result = {
        "level_1": [level_one(path) for path in workbooks],
        "level_2": level_two(args.fixtures / "gold_annotations.json"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))

    if any(item["accuracy"] != 1.0 for item in result["level_1"]):
        raise SystemExit(1)
    if result["level_2"]["complete_record_accuracy"] != 1.0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
