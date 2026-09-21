#!/usr/bin/env python3
"""Render the official English TAT-QA contexts as deterministic PDFs."""

from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data" / "tatqa" / "raw" / "tatqa_dataset_dev.json"
DEFAULT_OUTPUT = ROOT / "data" / "tatqa" / "dev"


CSS = """
@page { size: A4; margin: 0; }
body { font-family: sans-serif; font-size: 9.5pt; line-height: 1.25; color: #111; }
p { margin: 0 0 8pt 0; }
table { border-collapse: collapse; width: 100%; margin-top: 8pt; }
td { border: 0.6pt solid #333; padding: 3pt; vertical-align: top; }
"""


def context_html(item: dict) -> str:
    """Preserve benchmark content without adding synthetic headings or labels."""
    paragraphs = "".join(
        f"<p>{html.escape(str(paragraph['text']))}</p>"
        for paragraph in sorted(item["paragraphs"], key=lambda row: row["order"])
    )
    rows = []
    for row in item["table"]["table"]:
        cells = "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row)
        rows.append(f"<tr>{cells}</tr>")
    return f"<body>{paragraphs}<table>{''.join(rows)}</table></body>"


def render_pdf(item: dict, destination: Path) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    story = pymupdf.Story(context_html(item), user_css=CSS)
    writer = pymupdf.DocumentWriter(str(destination))
    media_box = pymupdf.paper_rect("a4")
    content_box = media_box + (36, 36, -36, -36)

    def rect_function(_page_number: int, _filled: pymupdf.Rect):
        return media_box, content_box, None

    story.write(writer, rect_function)
    writer.close()
    with pymupdf.open(destination) as document:
        return len(document)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, help="Optional deterministic prefix for smoke tests")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    dataset = json.loads(args.source.read_text(encoding="utf-8"))
    if args.limit is not None:
        dataset = dataset[: args.limit]
    pdf_dir = args.output_dir / "pdfs"
    rows = []
    for index, item in enumerate(dataset, start=1):
        uid = item["table"]["uid"]
        pdf_name = f"{uid}.pdf"
        destination = pdf_dir / pdf_name
        if args.force or not destination.exists() or destination.stat().st_size == 0:
            print(f"[{index:03d}/{len(dataset)}] rendering {uid}", flush=True)
            page_count = render_pdf(item, destination)
        else:
            with pymupdf.open(destination) as document:
                page_count = len(document)
        table = item["table"]["table"]
        rows.append(
            {
                "context_uid": uid,
                "pdf_name": pdf_name,
                "language": "english",
                "pages": page_count,
                "paragraphs": len(item["paragraphs"]),
                "table_rows": len(table),
                "table_columns": max((len(row) for row in table), default=0),
                "questions": len(item["questions"]),
            }
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = args.output_dir / "manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} English contexts to {manifest}")


if __name__ == "__main__":
    main()
