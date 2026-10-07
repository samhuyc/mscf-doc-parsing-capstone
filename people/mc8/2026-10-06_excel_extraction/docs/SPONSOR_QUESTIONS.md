# Sponsor questions and non-blocking defaults

These questions should be confirmed with the sponsor, but none blocks the v1
implementation.

1. **Which Excel files form the real test set?**
   Default: use generated edge-case fixtures and one hand-labeled financial
   statement until approved or shareable sponsor files are available.
2. **Should formulas, displayed values, or both be retained?**
   Default: retain both formula text and raw cached values; flag missing caches;
   never calculate formulas in Python.
3. **Is the expected output raw tables, normalized financial statements, or
   both?**
   Default: emit canonical cells and detected raw tables only. Use a small
   annotation file to measure line-item survival without defining an ontology.
4. **What schema and accuracy metric should be used?**
   Default: use `schema/workbook.schema.json`; require 100% Level 1 table
   reconstruction and report Level 2 line-item survival, coordinate accuracy,
   value accuracy, and complete-record accuracy separately.

Useful follow-ups are whether hidden sheets should be passed downstream,
whether macro-enabled `.xlsm` files are in scope, and whether formulas should
be recalculated externally before ingestion. The current parser preserves
hidden content and VBA packages when reading `.xlsm`, but does not inspect VBA.
