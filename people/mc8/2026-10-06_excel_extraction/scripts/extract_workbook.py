#!/usr/bin/env python3
"""Extract one or more Excel workbooks to canonical JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from excel_parser import extract_workbook  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbooks", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for workbook in args.workbooks:
        payload = extract_workbook(workbook)
        destination = args.output_dir / f"{workbook.stem}.json"
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(destination)


if __name__ == "__main__":
    main()
