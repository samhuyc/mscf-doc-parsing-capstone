#!/usr/bin/env python3
"""Transparent PDF parsing baseline using pdfplumber."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pdfplumber


def clean_text(text: str | None) -> str:
    """Normalize blank lines while preserving the extracted reading order."""
    if not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines()]
    result: list[str] = []
    previous_blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank and previous_blank:
            continue
        result.append(line)
        previous_blank = is_blank
    return "\n".join(result).strip()


def table_to_markdown(table: list[list[str | None]]) -> str:
    """Convert one pdfplumber table into a simple Markdown table."""
    rows = [[(cell or "").replace("\n", " ").strip() for cell in row] for row in table]
    rows = [row for row in rows if any(cell for cell in row)]
    if not rows:
        return ""

    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    header = normalized[0]
    separator = ["---"] * width
    body = normalized[1:]

    def format_row(row: list[str]) -> str:
        return "| " + " | ".join(row) + " |"

    return "\n".join([format_row(header), format_row(separator), *(format_row(row) for row in body)])


def point_in_bbox(x: float, y: float, bbox: tuple[float, float, float, float]) -> bool:
    """Return whether a point lies inside a pdfplumber bounding box."""
    x0, top, x1, bottom = bbox
    return x0 <= x <= x1 and top <= y <= bottom


def parse_pdf(pdf_path: Path) -> dict[str, Any]:
    """Extract page text, words, tables, and basic page metadata."""
    document: dict[str, Any] = {
        "source": str(pdf_path),
        "page_count": 0,
        "pages": [],
    }

    with pdfplumber.open(pdf_path) as pdf:
        document["page_count"] = len(pdf.pages)
        for page_number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            table_objects = page.find_tables()
            table_bboxes = [table.bbox for table in table_objects]
            filtered_page = page.filter(
                lambda character: character.get("object_type") != "char"
                or not any(
                    point_in_bbox(
                        (character["x0"] + character["x1"]) / 2,
                        (character["top"] + character["bottom"]) / 2,
                        bbox,
                    )
                    for bbox in table_bboxes
                )
            )
            text = clean_text(filtered_page.extract_text())
            tables = [table.extract() for table in table_objects]
            document["pages"].append(
                {
                    "page_number": page_number,
                    "width": page.width,
                    "height": page.height,
                    "text": text,
                    "word_count": len(words),
                    "narrative_word_count": len(filtered_page.extract_words(use_text_flow=True)),
                    "words": words,
                    "table_bboxes": table_bboxes,
                    "tables": tables,
                }
            )

    return document


def document_to_markdown(document: dict[str, Any]) -> str:
    """Create readable Markdown with page boundaries and extracted tables."""
    sections = [f"# Parsed PDF\n\nSource: `{document['source']}`"]
    for page in document["pages"]:
        section = [f"## Page {page['page_number']}"]
        if page["text"]:
            section.append(page["text"])
        for table_number, table in enumerate(page["tables"], start=1):
            markdown_table = table_to_markdown(table)
            if markdown_table:
                section.extend([f"### Table {table_number}", markdown_table])
        sections.append("\n\n".join(section))
    return "\n\n---\n\n".join(sections) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse a PDF into Markdown and JSON with pdfplumber.")
    parser.add_argument("pdf", type=Path, help="Path to the input PDF")
    parser.add_argument("--output-dir", type=Path, default=Path("output"), help="Directory for generated files")
    args = parser.parse_args()

    if not args.pdf.is_file():
        parser.error(f"PDF not found: {args.pdf}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    document = parse_pdf(args.pdf)
    stem = args.pdf.stem
    (args.output_dir / f"{stem}.json").write_text(json.dumps(document, indent=2, ensure_ascii=True), encoding="utf-8")
    (args.output_dir / f"{stem}.md").write_text(document_to_markdown(document), encoding="utf-8")
    print(f"Parsed {document['page_count']} pages from {args.pdf}")
    print(f"Wrote {args.output_dir / (stem + '.md')}")
    print(f"Wrote {args.output_dir / (stem + '.json')}")


if __name__ == "__main__":
    main()
