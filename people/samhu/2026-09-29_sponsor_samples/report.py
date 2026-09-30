"""Render measured results and methodology into the meeting report."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LABELS = {'mineru_ocr':'MinerU OCR', 'mineru_vlm':'MinerU local VLM', 'pymupdf4llm':'PyMuPDF4LLM (no OCR)'}

def main():
    data = json.loads((ROOT/'evaluation/metrics.json').read_text())
    sources = json.loads((ROOT/'source_manifest.json').read_text())
    rows = data['documents']
    parts = ['''# Sponsor PDF parsing — September 30, 2026 meeting

Six sponsor PDFs, 140 physical pages, three parser configurations. Full-document results are organized by document, then parser. Start with the [visual comparison](evaluation/REVIEW.html), [concrete source-level examples](OBSERVATIONS.md), [per-document CSV](evaluation/metrics.csv), or [complete metrics and failed-row evidence](evaluation/metrics.json).

## Runtime and coverage

These are single-run local wall times on an Apple M1 Pro with 16 GiB RAM, including process startup and model loading, excluding source downloads, common-format export and evaluation. MinerU weights were already cached. The parser configurations ran sequentially; ordinary development, output checks and diagnostic scoring overlapped parts of the batches, so these are observed end-to-end costs, not isolated latency measurements or a controlled throughput benchmark. No hosted inference API was used.

| Configuration | Completed documents | Pages with transcribed text | Total seconds | Minutes | Pages/sec |
|---|---:|---:|---:|---:|---:|''']
    for a in data['aggregate']:
        parts.append(f"| {LABELS[a['parser']]} | {a['completed']}/{a['documents']} | {a['nonempty_pages']}/{a['pages']} | {a['elapsed_seconds']:.1f} | {a['elapsed_seconds']/60:.2f} | {a['pages_per_second']:.2f} |")
    parts.append('''
Completion means the process returned a valid page export, not that its text is correct. PyMuPDF4LLM can complete an image-only document with no transcribed text. Its overall throughput therefore cannot be read as OCR throughput.

| Document | Pages | MinerU OCR seconds | MinerU VLM seconds | PyMuPDF4LLM seconds |
|---|---:|---:|---:|---:|''')
    for source in sources:
        group = {r['parser']:r for r in rows if r['document']==source['id']}
        seconds = ' | '.join(f"{group[p]['elapsed_seconds']:.1f}" if group[p]['elapsed_seconds'] is not None else '—' for p in LABELS)
        parts.append(f"| [{source['title']}]({source['url']}) | {source['pages']} | {seconds} |")
    parts.append('''
## Initial quality checks

The assistant visually transcribed three financial rows per document from the original rendered pages before inspecting parser predictions: **18 rows / 50 values**. The exact checks are in [checks.json](checks.json). This is a small, deliberately selected diagnostic set, not independent expert gold or an unbiased model ranking.

- **Selected-value recall:** how many expected numeric tokens occur on the correct source page, preserving currency, signs, grouping, decimals and percentages; whitespace is ignored. Duplicates within a check count as a multiset. This can pass when a number appears in the wrong row.
- **Exact row-cell rate:** whether a corresponding HTML table row has the expected complete ordered value-cell sequence. A leading note column is ignored. Missing tables, concatenated labels/cells and reversed value order fail. Repeated identical rows may match any occurrence. Headers, units, unrelated extra rows and global precision are not scored.
- **Coverage:** pages with any transcribed text, separately from process completion. A nonempty page can still have major omissions.

| Configuration | Selected values retained | Exact financial rows |
|---|---:|---:|''')
    for a in data['aggregate']:
        group = [r for r in rows if r['parser']==a['parser']]
        values = sum(r['checked_values_retained'] for r in group)
        exact = sum(r['checked_rows_exact'] for r in group)
        parts.append(f"| {LABELS[a['parser']]} | {values}/50 ({values/50:.0%}) | {exact}/18 ({exact/18:.0%}) |")
    parts.append('''
| Document | OCR values / rows | VLM values / rows | PyMuPDF4LLM values / rows |
|---|---|---|---|''')
    for source in sources:
        group = {r['parser']:r for r in rows if r['document']==source['id']}
        cells = ' | '.join(f"{group[p]['checked_values_retained']}/{group[p]['checked_values_total']} values; {group[p]['checked_rows_exact']}/3 rows" for p in LABELS)
        parts.append(f"| {source['id']} | {cells} |")
    parts.append('''
Keep scan and digital-PDF results separate:

| Input type | Configuration | Text pages | Selected values | Exact rows |
|---|---|---:|---:|---:|''')
    for kind, ids in [('Image-only', {'hippodrome_2025','peterborough_2025'}), ('Digital PDF', {s['id'] for s in sources}-{'hippodrome_2025','peterborough_2025'})]:
        for p in LABELS:
            group = [r for r in rows if r['document'] in ids and r['parser']==p]
            parts.append(f"| {kind} | {LABELS[p]} | {sum(r['nonempty_pages'] for r in group)}/{sum(r['pages'] for r in group)} | {sum(r['checked_values_retained'] for r in group)}/{sum(r['checked_values_total'] for r in group)} | {sum(r['checked_rows_exact'] for r in group)}/{sum(r['checked_rows_total'] for r in group)} |")
    parts.append('''
## Text-layer diagnostics, not accuracy

For the four digital PDFs only, `metrics.csv` includes page-matched multiset word recall and numeric-token F1 against direct PDF text extraction. These help flag missing content. They do not verify reading order, table associations or source truth and inherently favor native-text extraction. The two image-only filings have no such reference; their diagnostics are `null`, not zero or perfect. HTML-table counts are descriptive, not a score.

## Output index

Each link opens the common `document.md`. Adjacent `pages.json` retains 1-based physical page provenance; `metadata.json` retains PDF metadata, embedded bookmarks and a separately labeled heading index. `run.json` records settings, versions, hashes, timestamps and timings. Raw predictions are retained without manual correction.

| Document | MinerU OCR | MinerU VLM | PyMuPDF4LLM |
|---|---|---|---|''')
    for source in sources:
        name = source['id']
        links = ' | '.join(f'[{p}](results/{name}/{p}/document.md)' for p in LABELS)
        parts.append(f'| {name} | {links} |')
    parts.append('''
## Meeting discussion

1. **Metadata and table of contents:** CVS has 12 embedded outline entries and the Rolls-Royce presentation has 25; the other four files have none. EDF and both Companies House scans have blank PDF title fields. File metadata alone is therefore incomplete. A separately labeled parser-heading index is also exported; it does not prove a correct document hierarchy. Preserve the distinction between embedded outlines, extracted contents pages and generated headings.
2. **Chunking:** use the exported physical page chunks as an auditable baseline. Next compare heading/paragraph chunks while keeping tables intact and carrying page, entity, period, unit and source hashes. Evaluate retrieval separately from transcription.
3. **Financial statements:** table cells must preserve row labels, year/segment columns, signs and units. The selected-row checks expose association errors that page-level number recall misses. A future labeled sample should score cell positions and header paths, with no automatic numerical repair before evaluation.
4. **Excel:** no spreadsheets were supplied, so no Excel results are claimed. A separate workbook sample should preserve sheets, ranges, formulas versus cached values, merged cells and units instead of treating Excel as a PDF.
5. **Confidence:** common `confidence` is deliberately `null`. A model's OCR probability is not calibrated document accuracy and is not comparable to a rule-based parser. Begin with visible flags (empty text, missing table rows, numeric mismatches, inconsistent totals); calibrate any confidence estimate on held-out documents before publishing a percentage.
6. **Benchmark aggregation:** keep text, table structure, numeric associations and runtime separate. For a larger labeled set, report per-document macro averages and totals, retain failures in denominators, stratify digital/scanned inputs and split by issuer/document. Bootstrap documents, not individual rows, for uncertainty.

## Connection to previous benchmarks

The earlier [OmniDocBench/FinCriticalED pilot](../2026-09-20_evaluation/REPORT.md) already separates text, numeric-token, table and critical-field diagnostics. The team's [TAT-QA experiment](../../mc8/2026-09-21_tatqa%20parsers%20evaluation/REPORT.md) motivates checking financial evidence retention. Those labeled-dataset scores have **not** been rerun or mixed into these sponsor-PDF results. No official TEDS, OmniDocBench aggregate, FinCriticalED semantic score or TAT-QA answer score is claimed.

## Reproduction and limitations

See [README](README.md), [pinned dependencies](requirements-lock.txt), [source manifest](source_manifest.json) and [validation](evaluation/validation.json). MinerU 3.4.5 uses the existing local PDF-Extract-Kit and MinerU2.5-Pro-2605-1.2B snapshots recorded in each run. OCR is forced on CPU; VLM uses local MLX. Formula recognition and generative image analysis are disabled. PyMuPDF4LLM 0.2.9 / PyMuPDF 1.28.2 uses native text, `lines_strict` tables and no OCR/layout extension, matching the teammate's version baseline; this is not a test of newer OCR-enabled PyMuPDF4LLM configurations.

Small sample, one run per configuration, no independent annotation adjudication, no complete document gold and no calibrated confidence. High selected-value retention alone cannot establish correct financial extraction. Full raw MinerU intermediates and source PDFs remain local and are reproducible from the manifest; portable Markdown/JSON, linked image assets and the six review-page images are tracked.
''')
    (ROOT/'REPORT.md').write_text('\n'.join(parts))

if __name__ == '__main__':
    main()
