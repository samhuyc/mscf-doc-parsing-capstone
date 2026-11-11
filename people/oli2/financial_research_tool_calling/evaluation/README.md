# Offline Agent Evaluation v1

Run from the Demo directory in PowerShell:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m evaluation.runner
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -v
```

The first command is end-to-end task evaluation, not unittest. Default Git-ignored output is `artifacts/evaluation/v1/`: `report.html` (metrics, per-turn results, error analysis, expandable traces), `report.json` (machine-readable results), and `tool_traces.jsonl` (tools, arguments, results, exception types, simulated Usage). Use `--output <directory>` for a separate report. Exit 0 means report generation completed, not that every case passed. `--fail-on-failure` returns 1 for a gold mismatch; configuration/file errors return 2. This runner has no Live option and blocks network connections and OpenAI client construction.

Documentation and report labels are English. Original Chinese dataset questions, gold labels, units, and raw observed answers remain unchanged. English descriptions below are explanatory translations, not replacement evaluation inputs. Later sections document historical evaluation stages; their plans and results belong to their respective code versions.

## Verify tool coverage before freezing the dataset

Manual review covered `demo.py` table extraction and fixed document filter, `api_demo.py` evidence-scope checks, Session grammar, and the real index's Consolidated Results table, Total Revenues row, and source metadata.

Gold comes from the public CVS Health 2025 Q2 Earnings Presentation, physical PDF page 6, chunk `cvs_2025q2:section:d25757c94c9016b6ab4f`. Reported revenue is 98.9 billion for Q2 2025 and 91.2 billion for Q2 2024; the 7.7 billion difference uses these rounded figures. These are not unrounded dollar-level financial-statement amounts.

Current tools cannot answer UNH, Amazon, CVS Q2 2023, CVS Q3 2025, or comparisons missing prior-year data. Such cases have null value/unit/source and test appropriate abstention rather than invented financial gold.

`dataset_v1.json` freezes 18 scenarios / 25 scored turns: 16 baseline cases and 2 capability probes. Every turn specifies behavior, amount/unit/source or null, tool sequence, and query conditions. Setup turns are scored too. The two probes have clear Chinese wording and objectively supported answers; a parser limitation does not justify changing their labels to clarification.

This is not an independent holdout: cases were written after reviewing the program. Do not infer general accuracy on unseen tasks. The `.sha256` lock hashes normalized UTF-8/LF text. Changed standards require a new dataset version and lock, not replacement of v1. Gold is never generated from the current tool output. Reports include dataset, code, index, and metadata fingerprints. Input drift sets `inputs_match_frozen=false`; scoring can continue, but the result is not a same-environment comparison.

## Metric denominators

All metrics use turns as the scoring unit. N/A turns are excluded, not counted correct.

- **Answer Accuracy:** turns whose gold requires an amount. Decimal value, unit, company/period/intent must all match. Incorrect clarification or refusal remains incorrect and stays in the denominator.
- **Tool Selection Accuracy:** all turns. Actual Fake-requested tool names and order must exactly match gold, including no tools for clarification. Failed attempts count in the sequence. Arguments/results are logged separately; this measures scripted orchestration, not GPT autonomy.
- **Citation Accuracy:** turns requiring sourced financial answers. The answer and current Evidence must match citation ID, title, page, and URL. Merely including `[S1]` is insufficient; missing answers count wrong.
- **Abstention Accuracy:** all turns except injected tool failures. The answer/abstain/clarify decision must match gold. Both unsupported answers and unnecessary refusals/clarifications are penalized.
- **Execution success:** all turns. Return answer/abstain/clarify without failed State or an uncaught exception. An injected tool failure still counts as an execution failure, even when the case passes its safe-stop requirement.

A scenario passes only when every turn satisfies behavior, applicable metrics, and extra checks such as stale markers, ambiguity candidates, and failure stage. It is not the average of the five metrics. Baseline and probe results are reported separately.

## Reproducibility and isolation

Each scenario gets a new Session. Memory fixtures use isolated temporary directories that are cleaned afterward, never existing user Memory/Snapshots. The evaluation clock is fixed at `2026-11-10T12:00:00Z`; stale Memory was last checked on `2026-10-01`. Task IDs are deterministic per scenario/turn but distinct across tasks. Reports omit wall-clock times and random temporary paths. Identical code, dependencies, and index should produce byte-identical reports.

Normal cases use actual local Search and Calculate. Only E15/E16 inject their stated tool exceptions; normal financial data and calculations are not replaced. Traces store calls, arguments, results, and error types, excluding arbitrary exception bodies, HTTP credentials, and redirected raw console text. Gold is given only to the grader after execution; the Agent/Fake Model receives questions and normal context, not expected fields.

## Three different evaluation layers

**Unit Testing** checks functions, schemas, budgets, and safety contracts. The original 85 tests were preserved at this lesson stage, with additional grader tests. Later stages added more tests.

**Offline Agent Evaluation** runs frozen tasks through rules, Session, Context, Memory, real local tools, and final validation. This original runner measures that layer.

**Real LLM Evaluation** is needed to measure GPT's interpretation, autonomous tool selection, actual Usage, latency, and cost. It was not performed in this original offline lesson. Fake tool choices are scripted, and simulated tokens must not be priced as real API costs.

The baseline's main limitation was understanding clear expressions such as a natural-language quarter or "the same quarter last year," especially distinguishing a prior-year lookup from a year-over-year increase. The lesson recorded these limitations without changing production logic to improve scores.

## Real LLM Evaluation: small development suite

This is a separate evaluation route, not a replacement for the Rule-based offline benchmark.
`dataset_v1.json` and its lock remain unchanged. `live_suite_v1.json` has its own SHA-256 lock:
6 original cases (E01/E17/E18/E09/E07/E11), plus 2 development scenarios referencing existing
behavior/amount/source labels. The suite contains 8 cases and 11 scored turns. Questions already
used for debugging and these new paraphrases are NOT an independent out-of-sample test.
No gold labels enter the LLM prompt. Offline fixtures are explicit contract-test data and their
scores cannot be claimed as real GPT performance.

Run only the offline runner validation from the Demo directory:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m evaluation.live_runner
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -q
```

The normal fake path has 28 simulated requests. `run_llm_turn()` bypasses the Rule-based Parser;
real mode uses the same LLM Understanding, Context Builder, tools and Evidence Validation.
Cases have isolated Sessions; turns inside a case share Session but always allocate new AgentStates.
A suite-wide client wrapper counts every Understanding/Tool Loop request across all tasks.

### Fixed cases and expected behavior

- L01 / E01: direct CVS 2025 Q2 revenue: 98.9, Search, source S1 page 6.
- L02 / E17: natural Chinese quarter: same value and source.
- L03 / E18: CVS 2025 Q2 followed by the original Chinese follow-up meaning "What about the same quarter last year?": 98.9 then 91.2; Search each turn.
- L04 / development: a Chinese question meaning "How much did CVS consolidated revenue increase?" needs period clarification;
  the correction meaning "I mean Q2 2025 compared with Q2 2024" then requires Search → Calculate, 7.7, S1 page 6.
- L05 / E09: CVS and UNH in one question: clarify company, no financial tools.
- L06 / E07: CVS then Amazon: answer CVS, Search then abstain for Amazon; no invented Amazon gold.
- L07 / E11: CVS 2023 Q2: Search then abstain; no numerical gold.
- L08 / development: a Chinese paraphrase requesting CVS consolidated revenue for Q2 2025, with amount and source:
  same independently sourced 98.9 and S1 page 6 from E01.

### Scoring denominators

- Intent Understanding Accuracy: all 11 planned turns. Resolved company, metric, period,
  comparison period and intent must match; ambiguous turns must require clarification.
- Tool Selection Accuracy: all 11 turns; requested tool names/order must match, including an
  empty list when clarification is required. Argument correctness is separately enforced by Python.
- Numerical Accuracy: 7 turns requiring numerical answers; amount, unit and query must match.
- Citation Accuracy: those same 7 financial-answer turns; actual answer and current Evidence
  must match citation/title/page/URL. Missing answers do not disappear from the denominator.
- Clarification Appropriateness: all 11 turns; correct clarify/not-clarify decision. Separately
  count 2 required clarifications, correctly requested clarifications and unnecessary clarifications.
  Wording quality is retained for manual review, not automatically treated as semantically proved.
- Abstention Accuracy: all 11 turns; correct answer/abstain/clarify decision. Two turns require
  abstention. Unnecessary refusal or clarification counts as incorrect.

If stopped early, unrun applicable turns stay in planned denominators and count as incorrect;
coverage is also explicit. Unrun turns are not evidence of a model capability failure.
`legacy_evaluation` keeps the complete original grader output. For E09 it also checks
`pending_companies`, a Python implementation detail not currently populated by the LLM Session.
That diagnostic is preserved and reported separately; the original gold is never rewritten.
The new semantic metrics evaluate the clarification decision rather than that internal field.

### Paid run: requires a new explicit approval

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m evaluation.live_runner --live --confirm-paid-api
```

Model stays gpt-6.1-sol, Standard, SDK retries=0, timeout=30 seconds per request.
Each task: at most 4 requests and 12000 total tokens. Each response: max 1024 output tokens.
Whole suite: max 32 requests and 30000 total tokens, with pre-request estimates and actual usage
accounting. Any API/task failure stops the entire suite; no retry, model fallback or Fake fallback.
Expected requests: 28; extra model requests may exhaust the suite cap before all cases finish.
Using prior smoke-test usage as a rough guide, budget approximately $0.05–$0.10 for a normal run.
At Standard output rate $10/million, pricing all 30000 budgeted tokens at this highest token rate
is a conservative $0.30 estimate, NOT a server-enforced dollar limit. Client-side input estimates
can differ from billed usage; missing Usage leaves cost unknown. Known cached/write tokens are
priced separately. Rates and source are frozen in `live_runner.PRICING`; recheck before later runs.

Reports are separated:

- Existing Rule-based Offline Evaluation: `artifacts/evaluation/v1/` (18 cases / 25 turns).
- Runner contract check only: `artifacts/evaluation/llm_live_v1/offline_contract_check/`.
- Actual GPT run only after approval: `artifacts/evaluation/llm_live_v1/live_<UTC timestamp>/`.

Each new report contains report.json, report.html and requests.jsonl with parsed understanding,
requested tools/arguments/results, per-request usage and failure analysis. No credentials,
headers, arbitrary SDK error bodies or full model reasoning are persisted. Reports are Git-ignored.
Do not compare overall percentages from the 18-case offline benchmark against this 8-case live
suite as if they were the same sample; compare shared questions separately when diagnosing errors.


## Remaining five turns after the compare guardrail retest

Use `--remaining` to select only L05.1, L06.1, L06.2, L07.1 and L08.1 from the unchanged
frozen suite. Selection verifies the prior real report's suite/dataset hashes, exact questions,
gold labels and not_run status. It fails closed if this no longer matches the planned five turns.
The prior report is read-only. The selector does not restore AgentState or copy previous evidence.
L06.1 was never executed in the interrupted evaluation; it is required as the first turn of the
company-switch Session before Amazon in L06.2. No L01-L04 task is replayed.

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m evaluation.live_runner --remaining
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -q
```

Offline expected trace: clarify (1 request), CVS answer (3), Amazon abstain (2), unsupported
2023 quarter abstain (2), natural-language revenue answer (3): 11 simulated requests.
The subset has 5 intent/tool/decision scoring opportunities and 2 numerical/citation answers.
Fake outcomes verify runner wiring only, not model performance or actual costs.

After a separate explicit approval, the only intended paid command is:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m evaluation.live_runner --remaining --live --confirm-paid-api
```

Limits are narrowed to 14 requests and 16000 total tokens across all five turns, at most 4 requests
per task, at most 1024 output tokens per request. The existing per-task 12000-token cap also remains.
Model stays gpt-6.1-sol, Standard, retries=0. Task/API/budget errors stop the entire subset; any final
validation failure is retained in the sanitized diagnostic. No automatic correction or retry.

Reports go to `remaining_offline_contract_check/` or `remaining_live_<UTC>/`, never into old report
folders. Selection metadata carries the parent suite hash, source report hash, selected-turn hash
and scope audit. Report code_fingerprints identify the actual current version. L05's label still
reflects single-company scope; review true ambiguity versus multi-company scope separately.

Present these as three separate cohorts, with no merged Evaluation Score:

1. Old broad-kind-schema version: 6 executed turns, 17 API requests, 11076 tokens;
   compare failed final kind validation, five planned turns were not run.
2. Guardrail version's single Compare retest: 4 API requests, 2873 tokens, correct compare and 7.7.
3. Guardrail version's remaining-five evaluation: pending explicit Live approval; only Fake checks
   have run at preparation time. Final readiness for integration must be judged after actual outcomes,
   while retaining single-company scope and limited local CVS evidence as explicit constraints.
