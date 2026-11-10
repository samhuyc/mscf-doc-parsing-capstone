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
5. 模型选择结束时，返回结构化的答案类型、数值、Citation。
   Python 对照真实工具结果校验，然后渲染中文答案。

为使 Citation 和数字可以可靠核对，这版支持四个固定问题。
答案句子由 Python 模板生成。真实模型负责选择工具、参数和最终答案字段。
通用财务问答需要后续扩大检索与答案校验范围。

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
