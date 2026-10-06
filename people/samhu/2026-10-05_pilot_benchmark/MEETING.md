# Wednesday, October 7 — sponsor evaluation pilot

**What to show:** a working, inexpensive evaluation pipeline that distinguishes retaining a number from retaining its financial meaning in a table.

## Five-minute walkthrough

1. Open `review/index.html`. Show the three separate questions: table parsing, number retention, text/organization.
2. Open the source gallery. Expand CVS page 6: the original slide is beside its row/year/value references. EDF page 3 illustrates nested headers; the two scanned-account documents cover OCR-heavy material.
3. Open the number review, then the table review. Nearly all selected numeric values appear somewhere on the page, while fewer are recoverable under the correct row/header. Explain that unresolved matches can reflect both output structure and the strict adapter.
4. Show text/organization briefly. The small sample checks wording, notes and a few order pairs; it does not claim complete semantic understanding.
5. Mention the optional teammate review workspace. A teammate can approve references or flag corrections later; no manual review is required to demonstrate the current preliminary pipeline.

## What was delivered

- Six sponsor PDFs, 140 inventoried pages, 18 pages with selected reference regions.
- 54 assistant-authored label records, including 11 table references / 133 cell expectations.
- Deterministic scoring of existing MinerU OCR, MinerU VLM and PyMuPDF4LLM exports; no LLM answer filler.
- Separate metrics, source evidence, inspectable failures and reproducible input/label/scorer hashes.
- Offline HTML reports and an optional review/export/import workflow.
- Zero hosted model calls or parser reruns for this pilot; scoring takes about one second.

## What the meeting should not overclaim

The references are preliminary, not independently human-verified gold. These six documents were already used during development. Exact header/row matching can reject facts a person could reconstruct. The comparisons describe the saved parser/export configurations, including Tesseract and layout analysis for PyMuPDF4LLM. There is no overall ranking or document-wide hallucination score.

## Suggested next decisions

- Have teammates spot-check a few high-impact reference tables and unresolved associations.
- Agree which semantic relationships to add next: footnote attachment, units/basis, or visual card associations.
- Freeze the label/adapter version before a broader model comparison, and reserve fresh documents for a later held-out test.

[Open the report guide](review/index.html) · [Reproduction and methodology](README.md)
