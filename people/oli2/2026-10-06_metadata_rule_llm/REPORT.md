# Metadata extraction — October 7 Barclays discussion

**Result:** one parser-agnostic implementation now compares Rule, LLM and Hybrid
on all six sponsor documents and all three saved parser outputs. Development-reference
exact match is **70/90 (77.8%) for Rule**, **73/90 (81.1%) for validated LLM**, and
**80/90 (88.9%) for Hybrid**. Resolved-field coverage is **52/90 (57.8%) for Rule**,
**62/90 (68.9%) for validated LLM**, and **65/90 (72.2%) for Hybrid**. Exact match
measures correctness against the current references, while coverage measures how
often the extractor returns a resolved value. These figures combine draft pilot
issuer labels with provisional O6 labels and are development-set observations,
not held-out benchmark accuracy.

## Problem and existing baseline

The sponsor asks for “Metadata extraction (rule based & LLM based)”. Last week's
O6 1.1.0 used one manually fixed parser per document and four fields. It matched
24 provisional decisions, including six expected nulls. It was not a three-parser
benchmark. This experiment imports its unchanged, hash-checked generic rules and
retains candidate ranking, exclusions, exact evidence and explicit abstention.

Sam's October 5 pilot has metadata references but scores only evidence-text
retention; field accuracy is intentionally null because existing `metadata.json`
contains manifest-supplied answers. The new evaluator scores independent saved
predictions. No teammate or historical experiment files were changed.

## Architecture and canonical schema

All 18 exports were verified, including page counts, physical ordering, hashes,
run status and Markdown reconstruction: 140 pages per parser. PyMuPDF and MinerU
have the same page wrapper but different native payloads; native data is excluded.
One adapter supplies full permitted page Markdown and the genuine embedded PDF
title to the same Rule and LLM implementations. IDs, paths, supplied source titles,
labels and prior predictions are unavailable as semantic model input.

The five decisions are `issuer`, `document_type`, structural `reporting_period`,
`reporting_period_end`, and `document_date`. O6 `reference_period` / `reference_date`
map to the middle two; pilot `annual_accounts` maps to `annual_financial_statements`.
Every decision carries value, resolved/ambiguous/not_found status, method, exact
source/page/span evidence and diagnostics. Q2/H1 never authorizes an assumed end date.

Rule adds a conservative generic cover legal-entity / explicit issuer-label
strategy. LLM uses OpenAI `gpt-4.1-mini-2025-04-14`, temperature 0, strict JSON,
no tools and no rule predictions. Hybrid retains resolved rules and uses validated
LLM values only for unresolved fields, preserving disagreements explicitly.

## Experiment design

Nine configurations, not nine implementations. PyMuPDF was exercised first,
then exactly the same code ran over MinerU OCR and VLM. The final results use
18 real model responses; an earlier six-call schema smoke batch is archived.
Date-policy validation was strengthened after failure inspection and applied to
the same cached responses. The quotation-only results remain available, making
the development change visible. No parser reruns or selective “best answer” reruns.

Accuracy below is exact value/status match out of six documents. Issuer uses the
pilot's draft labels; the other columns use O6's provisional labels. Both reference
sets were known during development and are separately scored in JSON. End/document
date accuracy includes expected nulls. There are no independently reviewed pilot
metadata labels and no statistical-significance claim.

## Rule results

| Parser | Issuer | Type | Period | Period end | Document date | Resolved fields |
|---|---:|---:|---:|---:|---:|---:|
| PyMuPDF4LLM | 1/6 | 5/6 | 5/6 | 5/6 | 6/6 | 16/30 |
| MinerU OCR | 2/6 | 6/6 | 6/6 | 6/6 | 5/6 | 19/30 |
| MinerU VLM | 2/6 | 6/6 | 5/6 | 5/6 | 5/6 | 17/30 |

Where non-null dates are expected, period-end matches are 3/4, 4/4, 3/4;
document-date matches are 2/2, 1/2, 1/2, respectively. Issuer abstention is deliberate:
brand recognition, inline company/title splitting and entity linking are outside
the narrow rule. Overall abstention is 38/90; six fields are ambiguous.

## LLM results

| Parser | Issuer | Type | Period | Period end | Document date | Resolved fields |
|---|---:|---:|---:|---:|---:|---:|
| PyMuPDF4LLM | 4/6 | 4/6 | 3/6 | 6/6 | 6/6 | 20/30 |
| MinerU OCR | 4/6 | 5/6 | 5/6 | 5/6 | 5/6 | 21/30 |
| MinerU VLM | 5/6 | 5/6 | 6/6 | 5/6 | 5/6 | 21/30 |

Non-null period-end matches: 4/4, 3/4, 3/4; document-date matches: 2/2, 1/2, 1/2.
All 18 main raw responses satisfy the value/schema contract. Of 82 proposed
resolved values, 11 field decisions fail quotation validation; another nine fail
the explicit-date/cover-date policy, leaving 62 resolved fields. Twelve of 121
proposed quotes fail exact source membership. Final abstention is 28/90, with no
model-returned ambiguous decisions in this run. Abstention includes validator rejection.

## Hybrid results

| Parser | Issuer | Type | Period | Period end | Document date | Resolved fields |
|---|---:|---:|---:|---:|---:|---:|
| PyMuPDF4LLM | 4/6 | 5/6 | 5/6 | 6/6 | 6/6 | 21/30 |
| MinerU OCR | 4/6 | 6/6 | 6/6 | 6/6 | 5/6 | 23/30 |
| MinerU VLM | 5/6 | 6/6 | 6/6 | 5/6 | 5/6 | 21/30 |

Across the three parser outputs, Hybrid has **80/90 exact matches (88.9%)** against
the current development references and **65/90 resolved fields (72.2% coverage)**.
These are complementary metrics: exact match rewards correct abstention when the
reference is null, while coverage counts only resolved values.

Hybrid adds **13 values**: 11 issuers, one period and one explicit end date.
Eight added issuers match the draft names; three differ by legal-entity identity
or OCR spelling. Both added temporal values match the provisional references.
Non-null period-end matches are 4/4, 4/4, 3/4; document-date matches stay 2/2, 1/2,
1/2. Abstention is 25/90, including four ambiguous decisions.

There are four disagreements among 49 fields where both methods resolve a value:
two incomplete half-period objects and two press-release/presentation conflicts.
Hybrid retains the rule in all four. It makes no new model calls; dependency costs
still apply. Every document has at least one rule abstention, so document-level
fallback gating would save **zero** calls on this sample. Field-level usefulness
and call savings are different questions.

All final records pass schema checks. Exact selected-evidence membership is
282/282 for Rule, 92/92 for LLM and 260/260 for Hybrid, after rejection. This does
**not** imply zero semantic hallucinations; that rate is not measurable from these
partial labels. Values can cite genuine text with the wrong meaning.

## Parser sensitivity and failure analysis

The same rules produce different results because upstream structure changes:

- **Hippodrome/PyMuPDF:** page 1 is only `j rua`. Cover type and issuer evidence
  are lost, and later comparative periods compete. LLM recovers issuer and explicit
  year-end from later text; its malformed quotations still prevent type/period recovery.
- **Rolls-Royce release/MinerU:** cover ordering moves the event date beyond the
  rule's high-priority window, tying it with comparative table dates. VLM also
  flattens period headings so H1 2025 competes with H1 2026. Rules abstain. Hybrid
  repairs the VLM period but not its exact end or publication date.
- **Quotation membership versus meaning:** raw LLMs inferred June 30 from Q2,
  used Peterborough's page-3 approval date, and used a presentation's page-14
  “as of” date. The original prompt already prohibited these. Quotation-only Hybrid
  reached 74/90 coverage while worsening date accuracy. Generic date validation
  rejects nine such values, reducing final coverage to 65/90. This post-inspection
  change requires fresh held-out validation; both result versions are preserved.
- **Type and entity scope:** LLM calls the release a presentation in both MinerU
  versions despite a press-release embedded title. EDF's licensed legal entity is
  not the pilot's brand label “EDF”; “Rolls-Royce” versus its legal name is likewise
  an annotation-policy question. No issuer aliases or OCR repair were added to scores.

All-three-parser decision agreement for reporting period is Rule 4/6, LLM 3/6,
Hybrid 5/6; for period end it is 4/6, 5/6, 5/6. Agreement includes shared abstentions;
resolved-only stability is separately available in JSON. LLM does not consistently
reduce parser sensitivity. With one response per input, parser and model variation
cannot be completely disentangled.

## Latency, cost and validation

The original 18-call main batch used **351,067 input + 6,728 output tokens**, about
**75.9 seconds** inside provider calls and **$0.1512 estimated cost**. Original Rule
extraction total was about **1.02 seconds**; this excludes input loading and parser
runtime. Hybrid resolution added about 0.16 seconds, in addition to its dependencies.
Timings are single-run observations, not controlled throughput estimates.

The six-call smoke batch cost about $0.0524: **24 total hosted calls, about $0.2036**.
Final revalidation and integration replay made no new calls. Price assumptions are
$0.40/M input, $0.10/M cached input and $1.60/M output, checked October 6 against
[official model pricing](https://developers.openai.com/api/docs/models/gpt-4.1-mini);
these are estimates, not invoice data. No failures were hidden behind another provider.

**34/34 old O6 tests and 52/52 new tests pass.** Tests cover the requested adversarial
cases, poisoned input identities/titles/paths, all three export formats, LLM contract
failures, date-policy violations, Hybrid conflicts, label isolation and offline
replay of all 54 final predictions. Injection tests verify prompt separation and
contract rejection, not broad real-model resistance to prompt injection.

## Barclays / downstream implications and next steps

Propagate validated document decisions into chunk metadata, alongside immutable
source hash, physical page and section. Preserve field statuses/evidence; route
unresolved or conflicting cases to review rather than filling nulls silently.

```python
chunk.metadata = {
    "issuer": document.issuer,
    "reporting_period": document.reporting_period,
    "document_type": document.document_type,
    "document_date": document.document_date,
    "source": source_sha256, "page": physical_page, "section": section,
}
```

This connects metadata to the agenda's chunking/RAG, table-of-contents enrichment,
financial-statement extraction, confidence monitoring and benchmark work. It enables
issuer/period prefilters, document routing, source-based duplicate detection and
version candidates, section-aware chunks and auditable financial-table retrieval.
Metadata alone does not establish section hierarchy, table associations or calibrated
confidence. Excel inputs need workbook/sheet/range provenance; none were supplied.

Next: agree brand-versus-legal-entity labels; freeze the current contracts; evaluate
on new issuer/document families with independent annotation; compare another model
and repeated seeds/settings without changing parser inputs; measure retrieval gains
and human-review burden. Six previously inspected documents cannot establish generalization.

[Reproduction and metric definitions](README.md) · [Rule evaluation](results/evaluation/rule.json) ·
[LLM evaluation](results/evaluation/llm.json) · [Hybrid evaluation](results/evaluation/hybrid.json) ·
[Parser/extractor comparison](results/evaluation/comparison.json)
