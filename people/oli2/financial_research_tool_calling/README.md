# Financial Research Agent

本目录有两个入口。原有 `demo.py` 演示固定 Mock 决策；新增
`api_demo.py` 使用 Responses API 消息格式，默认以 Mock API Responses 离线运行。
两者共用原有 `search_report()` 和 `calculate()`。

## 运行

在本目录的 PowerShell 中执行。项目已创建独立的、本地忽略的 Python 环境。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 api_demo.py
.\.venv\Scripts\python.exe -B -X utf8 api_demo.py --scenario search
.\.venv\Scripts\python.exe -B -X utf8 api_demo.py --scenario calculate
.\.venv\Scripts\python.exe -B -X utf8 api_demo.py --scenario insufficient
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -v
```

新电脑可用 `python -m venv .venv`，然后执行
`.\.venv\Scripts\python.exe -m pip install -r requirements-openai.txt` 安装依赖。
需要同仓库中已有的 Chunking 索引与公开 CVS 来源元数据。

## Agent Loop

1. Python 把固定场景问题和两个 Tool Definitions 交给模型。
2. 模型返回 `function_call`，选择工具名称及参数。
3. Python 核对名称、参数、数字依据，执行对应的现有函数。
4. Python 用同一个 `call_id` 创建 `function_call_output`，连同之前的
   模型输出送回模型。Reasoning items 也保留在对话中。
5. 模型选择结束时，返回结构化的答案类型、数值、单位、Citation。
   Python 先用 Pydantic 检查结构，再对照真实工具结果校验，最后渲染中文答案。

为使 Citation 和数字可以可靠核对，这版支持四个固定问题。
答案句子由 Python 模板生成。真实模型负责选择工具、参数和最终答案字段。
通用财务问答需要后续扩大检索与答案校验范围。

## Agent State

`AgentState` 把一次任务的信息集中保存在内存中。现有 `run_agent()`
仍返回答案字符串；调用者可传入一个新的 State，以便在成功或失败后查看任务进度。

```python
from api_demo import AgentState, StopAgent, run_agent
from mock_responses import MockClient

state = AgentState()
try:
    answer = run_agent(MockClient("compare"), state=state)
except StopAgent:
    print(state.failure_stage, state.error)
print(state.status, state.api_request_count, state.tool_call_count)
print(state.input_tokens, state.output_tokens, state.total_tokens)
```

- `user_question` 和 `history` 保存问题、成功调用、工具结果和通过校验的最终模型消息。
- `evidence` 保存营收和 Citation，`calculation` 保存计算结果。
- `api_request_count` 在发请求前增加，因此失败请求也计数。
- `tool_call_count` 延续原有轮数含义，在解析、执行调用前增加，包含失败的尝试。
- Token 字段累计 API 已返回的 Usage。失败请求没有返回 Usage 时，计数代表已知用量。
- `status` 从 pending 变为 running，结束时为 completed 或 failed。
- `stage` 标识当前阶段，`pending_tool_call` 在执行前记录工具名、参数和 call_id。
- 成功后清空 pending 调用；失败时保留它，以及之前成功的历史和证据，
  并记录 `failure_stage` 与安全错误信息。外部异常正文会被隐藏。
- `final_answer` 保存通过校验的答案。“证据不足，无法回答”也属于正常完成的结果。

每次任务使用新的 State。调用者持有的对象在函数报错后仍可查看，
进程退出后这些内存数据就会消失。
State 中只放任务数据，API Client、环境变量和 HTTP 凭据不进入 State。

在 CVS compare 的 Fake Responses 中，检索成功后为 1 次请求、1 次工具调用、
120 total tokens；计算成功后为 2 次请求、2 次工具调用、240 total tokens；
答案通过校验后为 3 次请求、2 次工具调用、360 total tokens，
其中 input 300、output 60。这些 Usage 数字由离线模拟响应提供。

## Structured Outputs

`FinancialResearchResult` 定义四个必填字段。金额沿用十进制字符串，
例如 `"98.9"`；算术仍使用现有工具中的 Decimal。

```json
{"kind": "search", "value": "98.9", "unit": "十亿美元", "citation": "S1"}
```

- `kind` 支持 search、compare、calculate、insufficient。
- `value` 是十进制数字字符串，或 null。
- `unit` 支持“十亿美元”、“无单位”，或 null。
- `citation` 使用 S1、S2 等格式，或 null。

证据不足时，后三个字段都必须明确为 null。纯计算使用“无单位”和 null 引用。
字段缺失、多余字段和错误类型都会被本地校验拒绝，数字 98.9 也必须明确写成字符串。

Schema Validation 检查数据是否符合这些结构规则。Pydantic 自动生成
`text.format.schema`，并复用同一个模型检查本地收到的字典。
本地的跨字段状态校验器也检查“证据不足时三个字段均为空”；
这个 Python 校验器的逻辑需要在本地执行。

Evidence Validation 复用 `render_answer()` 的证据核对。
`"999"` 是格式正确的金额，`"S9"` 是格式正确的引用编号，
两者都能通过 Schema Validation，但与真实财报结果不符时会被 Evidence Validation 拒绝。
单位也必须与证据一致。

## 数据与费用边界

- 模型固定为 `gpt-6.1-sol`，请求失败即停止。
- 5 轮 Tool Calling，每轮一个工具；最多 6 次 Responses 请求。
- 每次最多 1,024 output tokens，包含 reasoning tokens；累计预算 12,000 tokens。
- 请求前根据载荷 UTF-8 字节数加余量预留 Token 预算，请求后累计实际 Usage。
  预估可能提前停止；这属于客户端控制，无法撤回已经产生的费用，
  也不构成服务端的美元费用硬上限。
- SDK 自动重试关闭，单次请求超时 30 秒。
- 默认执行使用 Mock API Responses，Usage 数字为模拟值。
- Live 才读取进程环境中的 `OPENAI_API_KEY`。日志过滤 API 异常正文。
- 外传证据限定为公开 CVS 简报两期营收、单位、Citation、来源标题、页码和 URL。
  财报解析、Chunking 和 Retrieval 均在本地执行。
- `store=False` 控制 Response 的存储选项，学校数据政策仍需适用于这些公开证据。

## 第一次 Live Test

先运行上面的离线测试。获得明确的 Live Test 批准后，在继承了
`OPENAI_API_KEY` 的 PowerShell 中执行下面的命令，先测试纯减法。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 api_demo.py --scenario calculate --live --confirm-paid-api
```

这会产生真实 API 费用，通常需要两次 Responses 请求。
Runtime 会自行读取环境变量。遇到访问权限、配额或模型错误会报告 HTTP 状态并停止。
学校 Project 对该模型的访问权限须通过获批的 Live Test 验证。

接口依据见
[Responses Function Calling](https://developers.openai.com/api/docs/guides/function-calling)、
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)、
[GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol)。
