# Final Integration v2 — Historical Offline Delivery Record

Date: 2026-11-10 (America/New_York). This record describes the original integration phase, before later paid evaluations and the English presentation branch. Real API requests during that phase: **0**; model API charges: **0**. Translation does not update its historical results. See [README](README.md) for the current entry point, architecture, and supported scope.

## Work preservation and module inventory

- Work took place on `oli2/final-integration`, without changing main, creating a PR, or pushing during that phase.
- Initial HEAD was `c8004b0`; Session, Context, Memory, Snapshot, evaluation, and integration changes were uncommitted. `git log --all --not HEAD -- people/oli2/financial_research_tool_calling` found no omitted module commits unique to other branches.
- Integration commit `c27f433` appeared during inspection. Additional safeguards were built on it without rewriting it.
- Existing `artifacts/before_*` backups and real-evaluation reports were preserved.
- A full local backup was created outside the repository, containing the Agent directory, uncommitted diff, branch inventory, and verified `all-refs.bundle`. Local backup paths are intentionally omitted from this public document.
- Understanding reuses `llm_session_demo`; Session reuses `session_demo`; context reuses `context_builder`; Memory reuses `long_term_memory`; Snapshot reuses `state_snapshot/json_storage`; tools, State, Loop, Structured Outputs, and Evidence Validation reuse `api_demo/demo`; cross-task budgets reuse `evaluation.live_runner.BudgetedClient`.

## Integration improvements

1. Validate retrieved amount format, unit, source title, page, URL, and citation at the existing tool boundary. Invalid results cannot enter Evidence, model context, or Memory. Retrieval itself was not rewritten.
2. Include Retrieval dependency source, tool definitions, tiktoken, and markdown-it-py versions in the freeze manifest.
3. Use temporary synthetic historical reports in retest/remaining-turn unit tests, avoiding dependence on local ignored live reports.
4. Use a separate v2 output directory, preserving the v1 freeze and all historical evaluations.

## Offline validation at that version

The project `.venv` was used because system Python lacked required tiktoken dependencies.

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -v
.\.venv\Scripts\python.exe -B -X utf8 financial_agent.py --demo
.\.venv\Scripts\python.exe -B -X utf8 -m evaluation.final_runner
```

The original 155 tests passed. After integration safeguards, **157/157 passed**, with no failures or skips, in approximately 24 seconds. Detailed output was saved in local ignored `final-tests.log`.

- AgentState: 9; API/Structured Outputs/loop: 22; original tools: 5.
- Context Builder: 15; LLM Session: 15; Rule-based Session: 12.
- Memory: 14; Snapshot: 12.
- CLI integration: 19; final frozen evaluation: 4.
- Original offline evaluation: 5; Live Runner offline checks: 10; remaining-turn selection: 5; output guardrails: 10.

Integration tests covered direct queries, follow-ups, year-over-year amounts, clarification and continuation, company/period changes, multi-company scope limits, genuine reference ambiguity, unsupported metrics/percentages/period comparisons, independent State, Memory revalidation, and Snapshot storage.

Failure tests covered API, schema, tools, evidence fields, final amounts/citations, corrupted storage, failed writes, request/token budgets, and missing/inconsistent/excessive Usage. Errors stopped the Session without retries.

The four-turn CLI produced 98.9 -> 91.2 -> clarification -> +7.7 (USD billions), using 11 simulated requests and 1,320 simulated tokens, with a distinct task ID per turn. Simulated tokens are not real costs.

The complete integration check used 8 scenarios / 11 turns / 28 Fake requests. All turns executed; numerical and citation results were each 7/7. Under unchanged gold, 10/11 turns passed: L05 expected `clarify`, while the new scope classification was `unsupported_capability`, retaining CVS/UNH candidates for selection. The mismatch remained visible; this was not reported as 100% against the old labels.

The separate Rule-based baseline remained 16/18 scenarios across 25 turns. All 16 baseline scenarios passed; E17's natural Chinese quarter and E18's same-quarter-last-year follow-up remained unsupported capability probes. Amount and citation scores were each 11/13; tool selection 23/25; abstention decisions 21/23; execution success 23/25. The two execution failures were intentional tool-error injections whose safe-stop checks passed. This older Rule-based report does not measure the new LLM entry point.

## Fixed-version live evaluation plan at that time

After the final local commit, the plan was to generate `artifacts/evaluation/final_integration_v2/frozen_version.json`, recording code commit, tool hashes/definitions, dependencies, financial inputs, model settings, and environment versions. `verify_frozen()` must pass again before execution; workspace/input/code/environment drift stops execution.

- Model: `gpt-6.1-sol`; `reasoning=low`, `service_tier=default`, `store=False`.
- SDK retries: 0; timeout: 30 seconds. Tools: local Search and Decimal subtraction only.
- Dataset: `financial_research_v1`; SHA-256 `5ab2ab206d41b53115e41df389e38955848a73f074e4ffb6e153549c946dfcd7`.
- Suite: `llm_live_development_v1`; SHA-256 `7227513105e9445f6a4bff1c3df46dbd0fe6c490dc95f58b01aa30815b72ddd4`.
- One complete evaluation: 8 isolated Session scenarios / 11 turns, sharing context within each scenario. No merging scores across code versions.
- Expected requests: 28; whole-suite maximum: 32 requests / 30,000 tokens; per-task maximum: 4 requests / 12,000 tokens; per-response output: 1,024 tokens.
- API, schema, tool, budget, or storage errors stop the suite. No automatic completion of remaining cases or model switching.

Historical pricing checked at that time was $2/million input tokens and $10/million output tokens, with cache pricing separate, from the [official model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol). Previous real Usage suggested **$0.04-$0.08** for the full run; this was not derived from Fake Usage. Pricing all 30,000 tokens at the higher output rate gave a **$0.30 conservative estimate**. This was not a server-side dollar limit; sent requests cannot be undone and missing Usage leaves costs unknown. Recheck pricing before later paid runs.

The paid command required separate user approval for that exact frozen version:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m evaluation.final_runner --live --confirm-paid-api
```

Planned outputs were new JSON/HTML/request traces with per-turn understanding, tools, numbers, citations, error stages, and actual Usage. L05's scope mismatch would be reviewed separately; old gold and historical scores would remain unchanged.

## Known limitations

Evidence covers only public CVS Q2 2025/2024 consolidated revenue. Other companies/periods generally lack sufficient evidence. Multi-company analysis, other metrics, percentage growth, quarter-over-quarter comparisons, downloading reports, trading, and external writes are unsupported.

Local Snapshot/Memory writes serve audit/history purposes. Memory contains no amounts and never automatically becomes Evidence. Session retains two recent turns and disappears on exit; Snapshot cannot resume execution. Memory allows 20 records per topic and needs manual maintenance. Snapshot/Memory writes are individually atomic, not one transaction; a later write failure can leave a valid Snapshot.

The offline CLI accepts fixed fixture questions; arbitrary natural language requires an explicitly approved real GPT session. Code, data, and model settings are frozen, but the model name is not a local weight snapshot. Identical outputs across dates are not guaranteed. The evaluation set is a known development set, not independent out-of-sample evidence; Fake Responses cannot prove real GPT understanding.

## GPT and Python responsibilities

Python creates a fresh State and assembles Session topic, pending clarification, and recent questions. GPT extracts company, metric, periods, and intent. Python validates structure and scope, requesting clarification for ambiguity or explaining unsupported capabilities.

For a supported task, Python retrieves historical source pointers; GPT requests Search; Python retrieves current report data and verifies evidence. For comparisons, GPT requests Calculate and Python performs Decimal arithmetic. GPT submits structured final fields; Python checks amount, unit, and citation, renders the answer, and saves sanitized Snapshot/source Memory.

GPT handles language understanding and tool selection. Python controls execution, arithmetic, evidence validation, budgets, persistence, and safe stopping.
