# O6: Rule, LLM and Hybrid metadata extraction

Since last week, the frozen O6 1.1.0 rules now run through one canonical adapter
across all six sponsor documents and all three parser outputs. An independent LLM
extractor and rule-first Hybrid use that same permitted representation. No parser-
specific extractors, source-title hints or benchmark labels enter model requests.

All nine configurations ran: 18 Rule predictions, 18 real LLM calls and 18 Hybrid
resolutions. The schema now includes issuer and retains structured reporting
period, exact end date, document date, abstention and auditable source evidence.
An earlier six-call contract smoke test is retained separately.

- **Development-reference exact match:** Rule 70/90 (77.8%); validated LLM 73/90
  (81.1%); Hybrid 80/90 (88.9%). These combine draft pilot issuer labels with
  provisional O6 labels and are not held-out benchmark accuracy.
- **Coverage:** Rule 52/90 fields (57.8%); validated LLM 62/90 (68.9%); Hybrid 65/90
  (72.2%). Exact match measures correctness against the current references;
  coverage measures how often the extractor returns a resolved value.
- **Issuer exact match:** Rule 5/18 versus Hybrid 13/18 against draft pilot names.
  Legal entity versus brand and OCR spelling remain unresolved policy issues.
- **Rules still matter:** Hybrid retains rules in four resolved disagreements,
  including press release versus presentation. It adds 13 values, mostly issuers.
- **Evidence needs validation:** 11 LLM decisions fail exact quotations; nine more
  fail date-support policy. Genuine quotations can still support the wrong meaning.
  Original quotation-only results remain visible; final results replay the same calls.
- **Parser effects remain:** PyMuPDF loses a scanned cover; MinerU ordering/heading
  changes produce comparative-period and cover-date ties. There is no overall winner.

Main LLM batch: about $0.15 estimated, 75.9 seconds of provider calls. Including the
six-call smoke batch: 24 calls, about $0.20. No parsers reran. All 34 old and 52 new
tests pass, including offline replay of all 54 predictions. Historical experiments
and teammate files are unchanged.

**Proposed next step:** agree issuer naming, freeze the contract, and label fresh
documents independently. Carry validated metadata into page/section chunks for
issuer/period-filtered retrieval, statement routing and disagreement-based review.
Current labels are provisional development references, not held-out gold.

- [Sponsor report](../../people/oli2/2026-10-06_metadata_rule_llm/REPORT.md)
- [Code and exact reproduction commands](../../people/oli2/2026-10-06_metadata_rule_llm/README.md)
- [Machine-readable comparison](../../people/oli2/2026-10-06_metadata_rule_llm/results/evaluation/comparison.json)
