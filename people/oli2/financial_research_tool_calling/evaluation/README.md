# Offline Agent Evaluation v1

在 Demo 目录的 PowerShell 运行：

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m evaluation.runner
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -v
```

第一条命令是端到端任务评估，不是 unittest。默认输出到 Git 忽略的
`artifacts/evaluation/v1/`：`report.html`（总体指标、逐题结果、失败分析和展开轨迹）、
`report.json`（机器可读结果）、`tool_traces.jsonl`（逐轮工具名/参数/结果/异常类型和模拟用量）。
可以使用 `--output <目录>` 保存另一次报告。默认退出码 0 表示报告生成完成，不代表所有任务通过；
`--fail-on-failure` 在任一 gold 不匹配时退出 1，配置或文件错误退出 2。
没有 Live 选项；Runner 禁止网络连接及构造 OpenAI Client。

## 先核对支持范围，再冻结 Dataset

人工检查了 `demo.py` 的表格抽取、固定 document filter、`api_demo.py` 的证据范围检查、
Session 句式，以及真实索引的 Consolidated Results 表头、Total Revenues 行和来源 metadata。
Gold 来源为公开 CVS Health 2025 Q2 Earnings Presentation，物理 PDF 第 6 页，
Chunk `cvs_2025q2:section:d25757c94c9016b6ab4f`。
表格金额为 2025 Q2 的 98.9、2024 Q2 的 91.2 十亿美元；差额 7.7 也按这些四舍五入数值计算。
不能把它们当成以美元为单位的未四舍五入精确报表金额。

当前工具不能回答 UNH、Amazon、CVS 2023 Q2、CVS 2025 Q3 或缺失上一年数据的同比问题。
这些案例的 value/unit/source 均为 null，评价的是正确拒答，不虚构财务 gold。

`dataset_v1.json` 冻结 18 个场景、25 个评分轮次，包含 16 个 baseline 场景和 2 个 capability probes。
每轮都有明确的 Expected Behavior、金额/单位/来源或 null、工具顺序、查询条件；
多轮场景的前置轮次同样评分，不隐藏 setup 的失败。
两个 probe 是信息明确且有客观财务答案的中文表达；当前语法不支持它们也不能将 gold 改为澄清。
这不是独立 holdout：案例是在阅读当前程序后人工编写，不能据此推断未知任务总体准确率。

`.sha256` 校验文件以 UTF-8、LF 规范化后的文本计算，防止运行时悄悄改 gold。
新增或改变标准应创建 dataset_v2 和新 lock，不覆盖 v1。程序不会从本次工具输出生成正确答案。
报告记录 Dataset hash、代码指纹及本地索引/metadata 指纹；输入变化会明确显示
`inputs_match_frozen=false`，仍运行评分，但不能当作同一环境的直接对照。

## 五个指标的分母

全部以“轮次”为评分单位，N/A 不进入分母，也不算正确。

- **Answer Accuracy**：gold 要求金额答案的轮次。金额（Decimal 比较）、单位、公司/期间/意图均正确才算对。
  可回答问题被澄清或拒答仍计错，不从分母中移除。
- **Tool Selection Accuracy**：全部轮次。实际 Fake Response 请求的工具名与顺序必须完全匹配 gold，
  应澄清时必须没有工具请求。失败的工具尝试也计入序列；参数和结果单独记录，最终结果另行评分。
- **Citation Accuracy**：gold 要求带来源财务答案的轮次。答案中的 Citation、标题、页码、URL，
  以及本任务 Evidence 的相应字段都要匹配冻结来源。只出现 `[S1]` 不够，没回答也计错。
- **Abstention Accuracy**：非工具故障注入轮次。answer/abstain/clarify 三种决策必须正确，
  同时惩罚错误回答与不必要的拒答/澄清。它不是“拒答越多越好”的比例。
- **执行成功率**：全部轮次。成功返回 answer/abstain/clarify 且没有任务失败或未捕获异常算成功。
  注入故障导致的安全停止也计执行失败；故障案例仍可因为符合预期安全行为而整体 PASS。

“场景通过”要求该场景所有轮次满足行为、适用指标和额外检查（如过时标记、歧义候选、失败阶段）。
它不是五个指标的平均数。报告单独展示 baseline 与 probes，避免把已知支持句式的通过率当成通用能力。

## 可重复与隔离

每个场景新建 Session，Memory fixture 使用独立临时目录，退出后清理，不读取用户现有记忆或 Snapshot。
固定评估时钟为 2026-11-10T12:00:00Z，过时 Memory 的核对时间为 2026-10-01。
任务 ID 采用场景/轮次确定生成，仍保持各任务不同；报告不含墙钟时间或随机临时路径。
相同代码、依赖和索引连续运行应得到字节一致的三个报告文件。

普通案例调用真实本地 Search 和 Calculate。只有 E15/E16 明确对相应工具注入异常，
不替换正常案例的真实证据或计算值。记录 Tool Call、参数、结果及错误类型；
不保存任意异常正文、HTTP 凭据或被重定向的控制台原文。
Gold 只交给完成后的 grader；Agent/Fake Model 收到用户问题及正常上下文，不收到 expected 字段。

## 三种评估不能混为一谈

**Unit Testing** 验证函数、Schema、预算和安全约束。原有 85 项测试保持不变，另加 grader 的测试。

**Offline Agent Evaluation** 运行冻结任务，测量当前规则解析、Session、Context、Memory、
真实本地检索/计算以及答案验证如何共同表现。本框架就是这一层。

**Real LLM Evaluation** 才能测量真实 GPT 对表达的理解、自主工具选择、真实 Usage、延迟和费用。
本次未进行。Fake Model 的策略已预设，Tool Selection Accuracy 不能代表 GPT 的真实能力。
所有 Token Usage 是模拟值，不能按真实模型价格换算费用。

当前最值得改进的是用户问题解析：覆盖“2025 年第二季度”和“那去年同期呢？”这类清晰表达，
特别区分“上一年同期金额”与“同比增加金额”。本轮只记录问题，不修改生产逻辑使指标变好。


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
- L03 / E18: CVS 2025 Q2 followed by “那去年同期呢？”: 98.9 then 91.2; Search each turn.
- L04 / development: “CVS 的合并总营收增长了多少？” needs period clarification;
  “我指 2025 Q2 比 2024 Q2” then requires Search → Calculate, 7.7, S1 page 6.
- L05 / E09: CVS and UNH in one question: clarify company, no financial tools.
- L06 / E07: CVS then Amazon: answer CVS, Search then abstain for Amazon; no invented Amazon gold.
- L07 / E11: CVS 2023 Q2: Search then abstain; no numerical gold.
- L08 / development: “想了解 CVS 二〇二五年第二季的合并总收入，请给出金额及来源。”:
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
