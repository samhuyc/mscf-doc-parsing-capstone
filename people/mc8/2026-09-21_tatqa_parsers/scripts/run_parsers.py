#!/usr/bin/env python3
"""Run PyMuPDF4LLM and plain PyMuPDF on rendered TAT-QA contexts."""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import traceback
from pathlib import Path

import pymupdf
import pymupdf4llm


ROOT = Path(__file__).resolve().parents[1]
PARSERS = ("pymupdf4llm", "pymupdf")


def markdown_to_text(markdown: str) -> str:
    lines = []
    for original in markdown.splitlines():
        line = original.strip()
        if not line:
            continue
        if re.fullmatch(r"\|?(?:\s*:?-{3,}:?\s*\|)+\s*", line):
            continue
        if line.startswith("|") and line.endswith("|"):
            line = " ".join(cell.strip() for cell in line[1:-1].split("|") if cell.strip())
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = line.replace("**", "").replace("__", "")
        line = re.sub(r"!\[[^]]*\]\([^)]*\)", "", line)
        line = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", line)
        if line:
            lines.append(line)
    return "\n".join(lines)


def markdown_tables(markdown: str) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for original in [*markdown.splitlines(), ""]:
        line = original.strip()
        is_table_row = line.startswith("|") and line.endswith("|")
        if is_table_row:
            cells = [cell.strip() for cell in line[1:-1].split("|")]
            if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                continue
            current.append(cells)
        elif current:
            tables.append(current)
            current = []
    return tables


def parse_pymupdf4llm(source: Path) -> tuple[str, str, list[list[list[str]]]]:
    markdown = pymupdf4llm.to_markdown(str(source), show_progress=False)
    return markdown, markdown_to_text(markdown), markdown_tables(markdown)


def parse_pymupdf(source: Path) -> tuple[str, str, list[list[list[str]]]]:
    page_text = []
    tables: list[list[list[str]]] = []
    with pymupdf.open(source) as document:
        for page in document:
            page_text.append(page.get_text("text", sort=True))
            finder = page.find_tables(strategy="lines_strict")
            for table in finder.tables:
                tables.append(
                    [["" if cell is None else str(cell) for cell in row] for row in table.extract()]
                )
    text = "\n".join(page_text)
    return text, text, tables


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("parsers", nargs="*", metavar="PARSER")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data" / "tatqa" / "dev" / "manifest.csv")
    parser.add_argument("--pdf-dir", type=Path, default=ROOT / "data" / "tatqa" / "dev" / "pdfs")
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    unknown = set(args.parsers) - set(PARSERS)
    if unknown:
        parser.error(f"unknown parser(s): {', '.join(sorted(unknown))}; choose from {', '.join(PARSERS)}")
    rows = list(csv.DictReader(args.manifest.open(encoding="utf-8")))

    implementations = {
        "pymupdf4llm": parse_pymupdf4llm,
        "pymupdf": parse_pymupdf,
    }
    for parser_name in (args.parsers or PARSERS):
        output_dir = args.output_root / parser_name
        output_dir.mkdir(parents=True, exist_ok=True)
        previous_path = output_dir / "runtime.csv"
        previous = {}
        if previous_path.exists():
            previous = {
                row["context_uid"]: row
                for row in csv.DictReader(previous_path.open(encoding="utf-8"))
                if row.get("context_uid")
            }
        timings = []
        for index, row in enumerate(rows, start=1):
            uid = row["context_uid"]
            destination = output_dir / f"{uid}.json"
            if destination.exists() and destination.stat().st_size > 0 and not args.force:
                timings.append(previous.get(uid, {
                    "parser": parser_name, "context_uid": uid, "seconds": "",
                    "status": "output_present", "error": "",
                }))
                continue
            print(f"{parser_name} [{index:03d}/{len(rows)}] {uid}", flush=True)
            started = time.perf_counter()
            status, error = "ok", ""
            try:
                raw, text, tables = implementations[parser_name](args.pdf_dir / row["pdf_name"])
                payload = {"parser": parser_name, "context_uid": uid, "raw": raw, "text": text, "tables": tables}
                destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as exc:
                status = "error"
                error = f"{type(exc).__name__}: {exc}"
                traceback.print_exc()
                destination.write_text(json.dumps({"parser": parser_name, "context_uid": uid, "error": error}), encoding="utf-8")
            timings.append({
                "parser": parser_name,
                "context_uid": uid,
                "seconds": f"{time.perf_counter() - started:.6f}",
                "status": status,
                "error": error,
            })
        with previous_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["parser", "context_uid", "seconds", "status", "error"])
            writer.writeheader()
            writer.writerows(timings)


if __name__ == "__main__":
    main()
