#!/usr/bin/env python3
"""Generate the sponsor-pilot parser comparison chart from Sam's saved results."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path


HERE = Path(__file__).resolve().parent
PEOPLE = HERE.parents[1]
PILOT = PEOPLE / "samhu" / "2026-10-05_pilot_benchmark"
SPONSOR = PEOPLE / "samhu" / "2026-09-29_sponsor_samples"
OUTPUT = HERE / "mineru_vs_pymupdf4llm_comparison.svg"

PARSERS = (
    ("mineru_ocr", "MinerU OCR", "#D66B3D"),
    ("mineru_vlm", "MinerU VLM", "#6659A5"),
    ("pymupdf4llm", "PyMuPDF4LLM", "#087F72"),
)

GROUPS = (
    (
        "TABLE UNDERSTANDING",
        (
            ("associated_value_accuracy", "Correct value in correct cell", "133 cells"),
            ("row_header_resolved", "Row and header uniquely resolved", "133 cells"),
            ("table_detected_by_row_labels", "Reference table located", "11 tables"),
            ("explicit_header_span_accuracy", "Selected merged headers retained", "2 assertions"),
        ),
    ),
    (
        "FINANCIAL NUMBER FIDELITY",
        (
            ("selected_value_presence", "Expected table number appears", "128 values"),
            ("negative_value_accuracy", "Negative values correct in cell", "18 negatives"),
            ("inline_currency_unit_accuracy", "Inline currency / unit retained", "23 cells"),
            ("unit_evidence_retention", "Table-wide unit wording retained", "11 labels"),
            ("complete_matrix_numeric_recall", "Complete-matrix numeric recall", "58 values"),
        ),
    ),
    (
        "TEXT & DOCUMENT ORGANIZATION",
        (
            ("text_span_retention", "Selected text retained", "8 spans"),
            ("footnote_text_retention", "Footnote wording retained", "5 footnotes"),
            ("reading_order_accuracy", "Selected reading order correct", "7 pairs"),
            ("metadata_evidence_retention", "Metadata evidence wording retained", "18 fields"),
            ("visual_label_value_sequence", "Visual label/value sequence retained", "5 cards"),
        ),
    ),
)


def svg_text(x: float, y: float, value: str, *, size: int = 18, weight: int = 400,
             fill: str = "#173033", anchor: str = "start", family: str = "Inter,Arial,sans-serif") -> str:
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{escape(value)}</text>')


def main() -> None:
    preliminary = json.loads((PILOT / "results" / "preliminary.json").read_text(encoding="utf-8"))
    runtime_rows = json.loads((SPONSOR / "evaluation" / "metrics.json").read_text(encoding="utf-8"))["aggregate"]
    runtimes = {row["parser"]: row["elapsed_seconds"] for row in runtime_rows}

    width, height = 1500, 1960
    label_x, chart_x, chart_width = 55, 510, 820
    bar_height, bar_gap, row_gap = 12, 5, 26
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#F5F2EA"/>',
        f'<rect x="0" y="0" width="18" height="{height}" fill="#087F72"/>',
        svg_text(55, 70, "Sponsor PDF parser comparison", size=40, weight=750),
        svg_text(55, 108, "MinerU OCR · MinerU VLM · PyMuPDF4LLM", size=23, weight=500, fill="#496063"),
        svg_text(55, 142, "October 5 pilot summaries · higher is better for all quality metrics shown", size=17, fill="#667779"),
    ]

    legend_x = 745
    for index, (_, name, color) in enumerate(PARSERS):
        x = legend_x + index * 235
        parts.append(f'<rect x="{x}" y="66" width="18" height="18" rx="3" fill="{color}"/>')
        parts.append(svg_text(x + 28, 81, name, size=16, weight=600))

    y = 205
    for group_name, metrics in GROUPS:
        parts.append(f'<rect x="40" y="{y - 25}" width="1405" height="42" rx="7" fill="#E2EAE6"/>')
        parts.append(svg_text(55, y + 4, group_name, size=17, weight=750, fill="#315A57"))
        y += 55

        for metric_key, label, scope in metrics:
            parts.append(svg_text(label_x, y + 13, label, size=17, weight=600))
            parts.append(svg_text(label_x, y + 35, scope, size=13, fill="#708083"))

            for tick in range(0, 101, 25):
                x = chart_x + chart_width * tick / 100
                parts.append(f'<line x1="{x}" y1="{y - 9}" x2="{x}" y2="{y + 51}" stroke="#D9DEDA" stroke-width="1"/>')
                if metric_key == metrics[0][0]:
                    parts.append(svg_text(x, y - 15, f"{tick}%", size=12, fill="#718083", anchor="middle"))

            for parser_index, (parser_key, _, color) in enumerate(PARSERS):
                metric = preliminary["aggregate"][parser_key][metric_key]
                value = metric["value"]
                bar_y = y + parser_index * (bar_height + bar_gap)
                parts.append(f'<rect x="{chart_x}" y="{bar_y}" width="{chart_width}" height="{bar_height}" rx="6" fill="#E7E4DC"/>')
                if value is not None:
                    value_width = chart_width * value
                    parts.append(f'<rect x="{chart_x}" y="{bar_y}" width="{value_width:.2f}" height="{bar_height}" rx="6" fill="{color}"/>')
                    passed = metric.get("passed", metric.get("numerator"))
                    total = metric.get("total", metric.get("denominator"))
                    detail = f"{value:.0%}"
                    if passed is not None and total is not None:
                        detail += f"  ({passed}/{total})"
                    parts.append(svg_text(chart_x + chart_width + 16, bar_y + 11, detail, size=13, weight=650, fill=color))
                else:
                    parts.append(svg_text(chart_x + 8, bar_y + 11, "N/A", size=12, fill="#7D8584"))
            y += bar_height * 3 + bar_gap * 2 + row_gap
        y += 25

    runtime_y = y
    parts.append(f'<rect x="40" y="{runtime_y - 25}" width="1405" height="42" rx="7" fill="#E2EAE6"/>')
    parts.append(svg_text(55, runtime_y + 4, "OBSERVED FULL-DOCUMENT RUNTIME", size=17, weight=750, fill="#315A57"))
    parts.append(svg_text(55, runtime_y + 42, "Six sponsor PDFs · 140 pages · September 29 runs · lower is better", size=15, fill="#667779"))

    max_runtime = max(runtimes.values())
    runtime_bar_x, runtime_width = 510, 820
    runtime_y += 66
    for index, (parser_key, name, color) in enumerate(PARSERS):
        seconds = runtimes[parser_key]
        by = runtime_y + index * 42
        parts.append(svg_text(55, by + 15, name, size=16, weight=600))
        parts.append(f'<rect x="{runtime_bar_x}" y="{by}" width="{runtime_width}" height="18" rx="8" fill="#E7E4DC"/>')
        parts.append(f'<rect x="{runtime_bar_x}" y="{by}" width="{runtime_width * seconds / max_runtime:.2f}" height="18" rx="8" fill="{color}"/>')
        parts.append(svg_text(runtime_bar_x + runtime_width + 16, by + 15,
                              f"{seconds:.1f}s  ({seconds / 60:.1f} min)", size=14, weight=650, fill=color))

    note_y = runtime_y + 155
    parts.append(f'<rect x="40" y="{note_y}" width="1405" height="145" rx="10" fill="#FFF0D6" stroke="#D89A3D" stroke-width="2"/>')
    parts.append(svg_text(65, note_y + 35, "Interpret with care", size=19, weight=750, fill="#824C12"))
    parts.append(svg_text(65, note_y + 66, "All 54 reference records are assistant-authored drafts; 0/54 are currently human-verified.", size=17, weight=600, fill="#694B2A"))
    parts.append(svg_text(65, note_y + 94, "The checks cover selected regions, not every fact on all 140 pages. No composite score or overall winner is claimed.", size=16, fill="#694B2A"))
    parts.append(svg_text(65, note_y + 120, "Runtime and quality come from saved local runs; parser configurations include different OCR and model pathways.", size=16, fill="#694B2A"))

    footer_y = note_y + 185
    parts.append(svg_text(55, footer_y, "Sources", size=16, weight=750, fill="#315A57"))
    parts.append(svg_text(55, footer_y + 25, "Quality: samhu/2026-10-05_pilot_benchmark/results/preliminary.json", size=13, fill="#68787A"))
    parts.append(svg_text(55, footer_y + 47, "Runtime: samhu/2026-09-29_sponsor_samples/evaluation/metrics.json", size=13, fill="#68787A"))
    parts.append(svg_text(1445, footer_y + 47, "Generated by evaluation_framework", size=13, fill="#68787A", anchor="end"))
    parts.append("</svg>")

    OUTPUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
