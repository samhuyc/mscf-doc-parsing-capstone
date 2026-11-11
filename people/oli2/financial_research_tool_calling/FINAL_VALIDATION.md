# Final Integration v2 — 离线交付记录

日期：2026-11-10（America/New_York）。本轮真实 API 请求：0；未产生模型 API 费用。
统一入口、架构图、支持范围与启动方式见 [README](README.md)。

## 工作保护与模块确认

- 分支为 `oli2/final-integration`，未修改 main，未创建 PR 或推送。
- 初始 HEAD 为 `c8004b0`；Session、Context、Memory、Snapshot、评估和整合入口当时有未提交成果。
  分支审计 `git log --all --not HEAD -- people/oli2/financial_research_tool_calling` 未发现遗漏的独有模块提交。
- 检查期间出现整合提交 `c27f433`，本次在其上追加补强，不改写它。
- 原有 `artifacts/before_*` 阶段备份及真实评估报告全部保留。
- 额外完整备份：`C:/Users/oscar/Documents/CMU/Mini 5/Capstone-backups/final-integration-20261110-230031/`。
  包含 Agent 目录、未提交 diff、分支清单与 `all-refs.bundle`；Git bundle 校验通过。
- 问题理解复用 `llm_session_demo`；Session 复用 `session_demo`；上下文复用 `context_builder`；
  Memory 复用 `long_term_memory`；Snapshot 复用 `state_snapshot/json_storage`；
  工具、State、Loop、Structured Outputs、Evidence Validation 复用 `api_demo/demo`；
  跨任务预算复用 `evaluation.live_runner.BudgetedClient`。

## 这次补强

1. 在既有工具执行边界校验检索返回的金额格式、单位、来源标题、页码、URL、Citation。
   不合法的结果不能进入本轮 Evidence、模型上下文或 Memory；不重新实现 Retrieval。
2. 冻结记录新增 Retrieval 依赖源码、工具定义、tiktoken 和 markdown-it-py 版本。
3. 历史重测与剩余评估的单元测试改用临时合成报告，使回归不依赖本机被忽略的真实报告。
4. v2 使用独立输出目录，保留 v1 的冻结记录及所有旧评估。

## 离线测试

使用项目 `.venv`，因为系统默认 Python 未安装本项目所需 tiktoken。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -v
.\.venv\Scripts\python.exe -B -X utf8 financial_agent.py --demo
.\.venv\Scripts\python.exe -B -X utf8 -m evaluation.final_runner
```

原有 155 项测试通过；补强后 **157/157 通过**，无失败、无跳过，完整运行耗时约 24 秒。
逐项输出保存在 `final-tests.log`（本地忽略）。模块分布：

- AgentState 9；API/Structured Outputs/工具循环 22；原始工具 5。
- Context Builder 15；LLM Session 15；规则 Session 12。
- Memory 14；Snapshot 12。
- CLI 集成 19；最终冻结评估 4。
- 原离线评估 5；Live Runner 的离线检查 10；剩余轮次选择 5；输出 Guardrails 10。

CLI 集成覆盖直接查询、连续追问、同比金额、澄清后继续、公司/期间切换、双公司范围限制、
真正的指代歧义、不支持的指标/百分比/比较期间，以及独立 State、Memory 重新验证、Snapshot。
错误覆盖 API、Schema、工具、证据字段、最终金额/引用、存储损坏、写入失败、请求/Token 预算、
缺失/矛盾/超限 Usage；错误后无自动重试，Session 停止。

四轮 CLI 演示结果：98.9 → 91.2 → 澄清 → +7.7（十亿美元），
共 11 次模拟请求、1320 个模拟 Tokens；每轮 task_id 不同。模拟 Tokens 不能换算实际费用。

完整集成回归使用 8 场景 / 11 轮、28 次 Fake 请求，11 轮均执行，数值和引用各 7/7。
旧 gold 下 10/11 轮通过：唯一差异 L05 原标注 `clarify`，新语义是 `unsupported_capability`，
保存 CVS/UNH 候选并等待用户选择；这符合当前需求。保留标签与评分差异，不把它宣传成旧分数 100%。

原规则解析器独立回归仍为 16/18 场景（25 轮）：16 个 baseline 场景全部通过；
E17 中文季度、E18 “去年同期”两项能力探针仍失败，与原有限规则能力一致。
金额与引用各 11/13；工具选择 23/25；拒答决策 21/23；执行成功 23/25。
执行成功率中的两次失败是预设工具故障注入，安全停止检查通过。
这份旧规则报告不能当成新 LLM 入口的实际表现。

## 固定版本与真实评估计划

最终本地提交后生成 `artifacts/evaluation/final_integration_v2/frozen_version.json`。
该文件是代码 Commit、工具哈希/定义、源码依赖、财报输入、模型配置和运行依赖版本的完整记录。
后续执行前必须重新通过 `verify_frozen()`；工作区、输入、代码或运行环境漂移就停止。

- 模型 `gpt-6.1-sol`，`reasoning=low`、`service_tier=default`、`store=False`。
- SDK 重试 0，超时 30 秒；工具仅本地 Search 与 Decimal 减法。
- Dataset：`financial_research_v1`，SHA-256 `5ab2ab206d41b53115e41df389e38955848a73f074e4ffb6e153549c946dfcd7`。
- Suite：`llm_live_development_v1`，SHA-256 `7227513105e9445f6a4bff1c3df46dbd0fe6c490dc95f58b01aa30815b72ddd4`。
- 全量单次评估：8 个独立 Session 场景 / 11 轮，同场景内保留必要上下文；不拼接不同代码版本得分。
- 预期 28 次请求；上限 32 次、30000 总 Tokens；每题 4 次/12000 Tokens，每次 1024 输出 Tokens。
- API、Schema、工具、预算、存储错误会停止整组；不会自动补跑剩余题或更换模型。

官方价格为每百万输入 $2、输出 $10（缓存另计），核对来源：
[GPT-6.1 Sol 官方文档](https://developers.openai.com/api/docs/models/gpt-6.1-sol)。
根据既有两组历史 Usage 的量级推算，本次完整运行预计约 **$0.04–$0.08**，不是 Fake Usage 推算。
30,000 Tokens 全按较高输出单价计算是 **$0.30 保守估算**；客户端预算不是服务端账单硬限额，
已发出请求无法撤回，缺少 Usage 的失败请求成本未知。

只有用户明确批准本次固定版本全量评估后，才执行：

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m evaluation.final_runner --live --confirm-paid-api
```

输出新的 JSON/HTML/请求轨迹、逐轮 Understanding/工具/数值/Citation 指标、错误阶段和实际 Usage。
L05 范围差异单列；模型错误和运行错误分开报告，不修改旧 gold，不合并历史分数。

## 已知限制

仅有 CVS 2025/2024 Q2 合并总营收公开简报证据；其他公司/期间通常返回证据不足。
不支持多公司分析、净利润等其他指标、百分比、环比、下载新报表、交易或外部写操作。
允许的本地 Snapshot/Memory 写入只用于审计与历史线索；Memory 不保存金额，不自动成为 Evidence。
Session 仅两轮短期上下文，退出即丢失；Snapshot 不能恢复执行。每主题 Memory 最多 20 条，需人工维护。
Snapshot 和 Memory 分别原子写入，非跨文件事务；第二步失败可能留下合法 Snapshot。
离线 CLI 只接受已公开的固定问题，任意自然语言需要获批后的真实 GPT。
冻结的是代码、数据和模型配置；官方模型名并非本地权重快照，无法保证跨日期输出完全相同。
评估集是已见过的开发集，不能证明样本外能力，Fake Responses 也不能证明 GPT 已正确理解问题。

## GPT 与 Python 分工

用户输入问题后，Python 创建新 State，并把 Session 中的主题、待澄清项和最近问题整理成上下文。
GPT 提取公司、指标、期间和意图；Python 检查格式与范围：歧义就问清楚，能力不支持就解释限制。
能执行时，Python 取出历史来源线索，GPT 请求 Search；Python 重新检索当前财报并验证证据。
需要同比时，GPT 请求 Calculate，Python 用 Decimal 计算。GPT 提交最终结构化结果，
Python 再核对金额、单位和 Citation，渲染答案并保存脱敏 Snapshot/来源 Memory。
GPT 负责语言理解和工具选择；Python 负责真实执行、算术、证据核实、预算及安全停止。
