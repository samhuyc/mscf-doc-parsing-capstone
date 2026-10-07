# Metadata extraction: Rule, LLM and Hybrid

October 6 experiment for the October 7 Barclays meeting. Start with [REPORT.md](REPORT.md)
or the [weekly summary](../../../weekly/2026-10-07/oli2-metadata.md).
All nine parser/method configurations were executed on six sponsor documents.
The final 54 predictions are reproducible offline from saved real model responses.

## Reproduce

Python 3.10+ and Git are required; tested on Windows with Python 3.13.7.
The only package dependency is `jsonschema`. No PDFs, parser installation, OCR,
GPU, OpenAI SDK or API key are needed for cached reproduction. From this folder:

```powershell
python -m pip install -r requirements.txt
python -B -m unittest discover -s tests -v
python -B -m unittest discover -s ../2026-09-29_metadata_extraction/tests -v
python -B run.py --output results/reproduce --methods rule llm hybrid --offline --cache results/cache
python -B evaluate.py --predictions results/reproduce/predictions --output results/reproduce/evaluation --include-drafts
```

Use a fresh output directory each time. Existing prediction and evaluation files
are never overwritten. CLI output directories must stay inside this new experiment.
Test discovery should run the two experiments in **separate Python processes**:
their historical top-level module names overlap.

The pilot exists on remote main but was absent from this working branch. The
evaluator reads its labels directly from the pinned Git object
`1d20388864e7015cbc2318478b82c73772143ae3`, without merging, checking out or modifying
Sam's files. If the object is missing on a fresh clone:

```powershell
git fetch origin
git cat-file -e 1d20388864e7015cbc2318478b82c73772143ae3
```

To evaluate only reviewed pilot labels, omit `--include-drafts` and use a fresh
evaluation directory. There are currently **zero** reviewed metadata labels:
the resulting accuracy denominators are zero and rates are `null`, not 100%.
O6's provisional cohort also requires `--include-drafts`.

For a new live comparison, configure `OPENAI_API_KEY` outside Git, then run:

```powershell
python -B run.py --output results/live-repeat --methods rule llm hybrid
python -B evaluate.py --predictions results/live-repeat/predictions --output results/live-repeat/evaluation --include-drafts
```

This makes up to 18 hosted calls and incurs API charges. Default provider/model:
OpenAI Responses, `gpt-4.1-mini-2025-04-14`, temperature 0, output limit 6,000
tokens, no tools, no conversation history and `store=false`. Full documents are
sent without truncation. Swapping `--model` changes the cache identity; unsupported
model settings fail visibly. No automatic retry or provider fallback is used.
Authentication/quota failures stop the batch; missing/failed rows remain in metric
denominators. Providers implement the small `Provider` protocol in `providers.py`.
The standard-library HTTPS adapter avoids dependence on a particular SDK version.

To stage the experiment, use `--parsers pymupdf4llm`, then
`--parsers mineru_ocr mineru_vlm` into the same fresh output root. Methods can also
be staged: `--methods rule`, then `--methods llm`, then `--methods hybrid`.
Hybrid consumes the saved Rule and LLM predictions with matching source/parser
fingerprints; it makes no additional model calls. Primary comparison always runs
the independent LLM for every document, so disagreement can be observed.

## Repository audit and frozen dependencies

The starting working tree was clean on `oli2-metadata`, revision `13e08ea`.
There were no applicable `AGENTS.md` files. `git fetch origin` supplied the missing
October 5 pilot for read-only inspection. O6, Sam's benchmark, all parser outputs
and existing weekly notes remain unchanged.

All 18 export folders have `pages.json`, `metadata.json`, `document.md`, and
successful `run.json`; each parser has 140 physical pages. The common page schema
is version 1, with `parser`, `source_sha256`, `page_numbering`, and `pages`.
Each page has `page`, `markdown`, `native`, `text_chars`, and `confidence`.
MinerU `native` contains `page_idx`; PyMuPDF `native` also carries rich metadata,
including source paths. These are **not equivalent semantic inputs** and are excluded.

`metadata.json` separates `source.metadata.title`, obtained from `doc.metadata`
in Sam's `prepare.py`, from human-supplied `source.title`, IDs and URLs. Only the
embedded title is permitted, following O6's existing policy. Generated heading
indexes, native metadata, timestamps and manifest titles are not searched.
The embedded title may still be stale; this experiment does not prove its truth.

`input_manifest.json` pins LF-normalized hashes of all four files for all 18 inputs.
The adapter verifies parser/source identities, successful status, counts,
contiguous physical pages, and exact `document.md` reconstruction and hash.
Missing inputs fail explicitly, with no parser fallback. Original PDFs are not
opened or independently rehashed; their identities come from the frozen exports.

`baseline_bridge.py` imports only O6 `inputs.py` and `rules.py`, checking their
pinned hashes before import. It does not import O6's manifest, labels or evaluator.
The original fixed-parser experiment and its 1.1.0 results remain reproducible.

## Architecture and files

```text
18 frozen exports -> adapters.py -> identical permitted page/title representation
                                  |-> rule_extractor.py (O6 1.1.0 + issuer)
                                  |-> llm_extractor.py -> provider -> validators
                                  `-> hybrid.py (rule first, validated fallback)
                                           |
run.py -> frozen predictions/*.jsonl --------+
                                           v
pilot Git labels + O6 labels ----------> evaluate.py -> separate metric JSON
```

- `config.py`, `schema.py`: paths, model settings, canonical and model contracts.
- `adapters.py`: input validation, permitted representation, source-span validation.
- `rule_extractor.py`: maps O6's four decisions without changing candidate ranking;
  adds a deliberately narrow standalone cover legal-entity / `Issuer:` rule.
- `llm_extractor.py`, `providers.py`, `prompts/`: independent extraction and cache.
- `evidence_policy.py`: necessary date-support checks, shared with Hybrid.
- `hybrid.py`: rule-first resolution; retains both values/reasons on disagreement.
- `evaluate.py`: the only production module that reads reference labels.
- `tests/`: 52 tests, including 54-prediction offline replay and leakage tests.

## Canonical field and evidence contract

See [metadata.schema.json](metadata.schema.json) and [llm.schema.json](llm.schema.json).
`schema.py` is their source of truth; tests detect drift.

- `issuer`: supported reporting entity or brand text; no issuer alias dictionary.
- `document_type`: the six O6 types. `annual_accounts` normalizes to
  `annual_financial_statements` in evaluation; unaudited statements stay distinct.
- `reporting_period`: `{year, kind, number}`; kind `year`, `half` or `quarter`.
  Number is null for years and when a fiscal half/quarter number is not explicit.
- `reporting_period_end`: explicitly supported ISO date, formerly O6 `reference_date`.
- `document_date`: ISO cover publication/announcement/presentation-event date;
  excludes filing, signature, approval and as-of dates.

Every decision has `value`, `status`, `method`, `evidence`, and `diagnostics`.
Resolved decisions require a value and evidence; `ambiguous` / `not_found` require
null values. Evidence identifies page versus embedded title, physical page (null
for title), exact quote, JSON pointer and Unicode character offsets `[start,end)`.
`original_quote` retains the exact original source slice. File identity lives in
record provenance. Repeated model quotes use the first exact occurrence on the
declared page; this is source membership, not unique semantic localization.

Both extractors receive identical full page Markdown and embedded-title content.
Image syntax, comments, link destinations and HTML attributes are masked with
spaces while preserving newlines/offsets; visible link text and table/heading
structure remain. No doc ID, filename, manifest description, reference answer,
prior rule output, or parser-specific hint enters the model request. Rule code
does not branch on parser identity. Provenance retains identities outside that
request. The original strings retained by the adapter are used only to audit spans.

The model contract treats document content as untrusted data and allows abstention.
Malformed JSON, missing fields or invalid value types reject the entire response.
Invalid quotations reject the affected field. Date checks reject a value absent
from quoted date tokens, and reject document-date evidence outside the cover or
with recognized administrative/reporting-end context. They reuse only O6's generic
date tokenizer/parser, never its predicted decisions. These are necessary checks,
not complete semantic entailment or prompt-injection defenses.

## Evaluation and metrics

The pilot's `benchmark.py` deliberately leaves `metadata_field_accuracy` null:
existing parser `metadata.json` contains source-manifest values, not independent
metadata predictions. Its existing evidence-retention score searches expected
text and cannot substitute for extraction accuracy.

The new evaluator reads already-frozen predictions, then references. It reports
two distinct preliminary cohorts, never pooled as independent observations:

- Pilot: 18 draft labels. Issuer and type have six labels each. Three Q/H labels
  map to structural reporting periods; three ISO-date labels map to period ends.
  ISO dates alone do not annotate fiscal period kind. No document-date labels exist.
- O6: 24 provisional labels covering type, complete reporting period, period end
  and document date for all six documents. Expected nulls remain meaningful.

Issuer comparison normalizes Unicode, casing and whitespace, not punctuation,
legal suffixes or corporate identity. This exposes brand/legal-entity disagreement.
Exact match requires value and status; supported-value accuracy restricts the
denominator to non-null reference values. Coverage counts resolved values over
all expected fields, including unlabeled fields; abstention and ambiguity are
separate. Missing predictions are failures, not successful null predictions.
Schema validity, exact evidence membership, raw LLM rejection rates, cross-parser
decision/resolved agreement, and conditional Rule/LLM agreement are separate.
Semantic hallucination rate remains null: no exhaustive semantic annotations exist.

## Saved results and version history

```text
results/
  predictions/<parser>/{rule,llm,hybrid}.jsonl  # final validation 1.0.2
  evaluation/{rule,llm,hybrid,comparison}.json
  cache/<content-hash>.json                   # 18 real responses, prompt 1.0.1
  runs/*.json                                # code/input/runtime provenance
  contract_smoke/                             # first 6 live PyMuPDF calls, prompt 1.0.0
  quote_only/                                 # 18-call evaluation before date-policy checks
  validation.json                            # observed checks and audit totals
```

The six-call smoke batch exposed a missing provider-side ISO date constraint.
Prompt/schema 1.0.1 added it without changing the rule engine. The 18-call batch
then exposed violations of the already-declared date policy despite real quotes.
Validation 1.0.2 added generic contract gates, tested on synthetic cases, and replayed
the **same** 18 cached responses. No model was rerun to select better answers.
The original smoke and quotation-only predictions/evaluations are retained.
These are development iterations, not held-out evidence for the new gates.

Cache keys include permitted-text hash, provider/model, settings, prompt version/
hash and schema hash. Response checksums and identity are verified before replay;
the current validator always runs again. Cache does not stand in for fresh inference.
Resources distinguish original response calls/tokens/cost from calls this run;
final replay made zero calls. The `quote_only` run records original live latencies.
24 hosted calls total: six smoke plus 18 main comparison. No parser reruns.

Implementation references: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)
and [the pinned model's settings/pricing](https://developers.openai.com/api/docs/models/gpt-4.1-mini).
Cost is a dated list-price estimate, not a billing statement. Temperature zero
reduces variation but does not promise bit-for-bit future model reproducibility.
