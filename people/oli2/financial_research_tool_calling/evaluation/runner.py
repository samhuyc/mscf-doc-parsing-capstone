"""Deterministic offline evaluation; no gold answers are supplied to the Agent or Fake Model."""

import argparse
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import html
import io
import json
from pathlib import Path
import platform
import re
import socket
import tempfile
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

import api_demo as agent
from demo import REPO_ROOT
import long_term_memory as memory
from mock_responses import MockClient
import session_demo

DATASET = Path(__file__).with_name("dataset_v1.json")
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "evaluation" / "v1"
METRIC = "consolidated_total_revenue"
DEFINITIONS = {
    "answer_accuracy": "分母：gold 要求回答金额的轮次；分子：实际回答的金额、单位和查询条件全部正确。错误澄清/拒答计错。",
    "tool_selection_accuracy": "分母：全部轮次；分子：Fake Model 实际请求的工具名称及顺序与 gold 完全一致。应澄清时必须为空。仅评估脚本驱动的工具流程。",
    "citation_accuracy": "分母：gold 要求带来源财务答案的轮次；分子：用户答案及当前 Evidence 的引用编号、标题、页码和 URL 均匹配 gold。没有回答也计错。",
    "abstention_accuracy": "分母：非故障注入轮次；分子：answer / abstain / clarify 决策正确。既惩罚该拒不拒，也惩罚可以回答却拒答或澄清。",
    "execution_success": "分母：全部轮次；分子：返回 answer / abstain / clarify，且 State 未失败、无未捕获异常。预期工具故障仍计执行失败，但可通过该案例的安全停止要求。",
}


class EvaluationError(ValueError):
    pass


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_dataset(path=DATASET):
    path = Path(path)
    raw = path.read_text(encoding="utf-8")  # Normalize CRLF so a checkout does not change the lock.
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if digest != Path(str(path) + ".sha256").read_text(encoding="ascii").strip():
        raise EvaluationError("冻结 Dataset 的 SHA-256 不匹配；请创建新版本，不要覆盖 v1。")
    data = json.loads(raw)
    if data.get("schema_version") != "1" or not 15 <= len(data.get("cases", [])) <= 20:
        raise EvaluationError("Dataset 版本或案例数量无效。")
    if len({case["id"] for case in data["cases"]}) != len(data["cases"]):
        raise EvaluationError("Dataset 案例 ID 重复。")
    for case in data["cases"]:
        if case["fixture"] not in {None, "stale_memory", "search_failure", "calculate_failure"}:
            raise EvaluationError("未知评估 fixture。")
        for turn in case["turns"]:
            expected = turn["expected"]
            if expected["behavior"] not in {"answer", "abstain", "clarify", "error"}:
                raise EvaluationError("未知 Expected Behavior。")
            if expected["behavior"] == "answer":
                Decimal(expected["value"])
                if expected["source"] not in data["sources"] or expected["unit"] != "十亿美元":
                    raise EvaluationError("财务 gold 缺少单位或来源。")
            elif any(expected[key] is not None for key in ("value", "unit", "source")):
                raise EvaluationError("非回答轮次不能包含虚构金额或引用。")
    return data, digest


def classify(result):
    if result.outcome == "clarification":
        return "clarify"
    if result.outcome == "failed":
        return "error"
    return "abstain" if result.answer == "证据不足，无法回答。" else "answer"


def score_turn(expected, observed, sources):
    """Independent deterministic grader: checks visible answer and fixed gold, not render_answer()."""
    actual_behavior = observed["behavior"]
    query_ok = expected["query"] is None or observed["query"] == expected["query"]
    checks = {"expected_behavior": actual_behavior == expected["behavior"], "query": query_ok}
    scores = {name: None for name in DEFINITIONS}
    if expected["behavior"] == "answer":
        # This v1 grader supports the existing Chinese answer contract only.
        number = re.search(r"(?:为\s*|约\s*)([+-]?\d+(?:\.\d+)?)\s*十亿美元", observed["answer"])
        try:
            amount_ok = number is not None and Decimal(number[1]) == Decimal(expected["value"])
        except InvalidOperation:
            amount_ok = False
        scores["answer_accuracy"] = bool(actual_behavior == "answer" and amount_ok and query_ok
                                          and expected["unit"] in observed["answer"])
        source = sources[expected["source"]]
        evidence = observed["evidence"] or {}
        page = re.search(r"PDF 第\s*(\d+)\s*页", observed["answer"])
        citations = set(re.findall(r"\[(S\d+)\]", observed["answer"]))
        urls = set(re.findall(r"https?://\S+", observed["answer"]))
        scores["citation_accuracy"] = bool(
            actual_behavior == "answer" and citations == {source["citation"]} and urls == {source["url"]}
            and page is not None and int(page[1]) == source["page"] and source["title"] in observed["answer"]
            and evidence.get("citation") == source["citation"] and evidence.get("page") == source["page"]
            and evidence.get("source_url") == source["url"] and evidence.get("source_title") == source["title"]
        )
    scores["tool_selection_accuracy"] = [call["name"] for call in observed["tool_calls"]] == expected["tools"]
    if expected["behavior"] != "error":
        scores["abstention_accuracy"] = actual_behavior == expected["behavior"]
    scores["execution_success"] = actual_behavior != "error" and observed["unhandled_error"] is None
    if expected["behavior"] == "error":
        checks["safe_failure"] = (observed["failure_stage"] == expected["failure_stage"]
                                  and observed["final_answer"] is None and observed["unhandled_error"] is None)
    if expected["behavior"] in {"abstain", "clarify"}:
        checks["no_financial_claim"] = not re.search(r"[+-]?\d+(?:\.\d+)?\s*十亿美元|\[S\d+\]", observed["answer"])
    if "pending_companies" in expected:
        checks["ambiguous_candidates"] = observed["pending_companies"] == expected["pending_companies"]
    if expected.get("stale_memory"):
        initial = observed["contexts"][0] if observed["contexts"] else {}
        matches = initial.get("historical_context", [])
        checks["stale_memory_revalidated"] = bool(
            matches and all(match["is_stale"] and match["requires_revalidation"] for match in matches)
            and observed["tool_calls"] and observed["tool_calls"][0]["name"] == "search_report"
            and observed["tool_calls"][0]["status"] == "returned" and observed["evidence"] is not None
        )
    # Expected injected faults are correct case behavior despite a failed execution metric.
    scored_checks = {name: value for name, value in scores.items()
                     if value is not None and not (name == "execution_success" and expected["behavior"] == "error")}
    failures = [name for name, value in {**checks, **scored_checks}.items() if not value]
    return {"scores": scores, "checks": checks, "passed": not failures, "failed_checks": failures}


def aggregate(turns):
    metrics = {}
    for name, definition in DEFINITIONS.items():
        eligible = [turn["evaluation"]["scores"][name] for turn in turns
                    if turn["evaluation"]["scores"][name] is not None]
        numerator, denominator = sum(eligible), len(eligible)
        metrics[name] = {"correct": numerator, "eligible": denominator,
                         "percent": round(100 * numerator / denominator, 2) if denominator else None,
                         "definition": definition}
    return metrics


def run_case(case, dataset):
    session = session_demo.Session()
    results = []
    clock = datetime.fromisoformat(dataset["evaluation_clock"].replace("Z", "+00:00"))
    original_create, original_execute, original_search_memory = MockClient.create, agent.execute_tool, agent.search_memory
    with tempfile.TemporaryDirectory(prefix="agent_evaluation_") as folder, ExitStack() as stack:
        memory_dir = None
        if case["fixture"] == "stale_memory":
            memory_dir = Path(folder) / "memory"
            source = dataset["sources"]["cvs_q2"]
            memory.save_memory(memory.MemoryRecord(
                schema_version="1", company="CVS", metric=METRIC, year=2025, quarter=2,
                source={"url": source["url"], "page": source["page"]},
                last_verified_at="2026-10-01T12:00:00Z", snapshot_task_id="0" * 31 + "1",
            ), memory_dir)
        stack.enter_context(patch.object(agent, "search_memory", side_effect=lambda *args, **kwargs:
                                         original_search_memory(*args, **kwargs, now=clock)))
        if case["fixture"] == "search_failure":
            stack.enter_context(patch.object(agent, "search_report", side_effect=OSError("Injected evaluation search failure")))
        elif case["fixture"] == "calculate_failure":
            stack.enter_context(patch.object(agent, "calculate", side_effect=ArithmeticError("Injected evaluation calculation failure")))

        for index, turn in enumerate(case["turns"], 1):
            calls, requests, contexts = [], [], []

            def observe_create(client, **payload):
                response = original_create(client, **payload)
                requests.append({"response_types": [item.type for item in response.output],
                                 "simulated_usage": {"input_tokens": response.usage.input_tokens,
                                                     "output_tokens": response.usage.output_tokens,
                                                     "total_tokens": response.usage.total_tokens}})
                for item in response.output:
                    if item.type == "function_call":
                        calls.append({"name": item.name, "call_id": item.call_id,
                                      "arguments": json.loads(item.arguments), "status": "requested",
                                      "result": None, "error_type": None})
                return response

            def observe_execute(name, arguments, *args, **kwargs):
                event = calls[-1]
                try:
                    value = original_execute(name, arguments, *args, **kwargs)
                    event.update(status="returned", result=deepcopy(value))
                    return value
                except Exception as error:
                    event.update(status="failed", error_type=type(error).__name__)
                    raise

            def observe_context(plan):
                historical = []
                if plan.input_items and plan.input_items[0].get("role") == "user":
                    try:
                        notes = json.loads(plan.input_items[0]["content"])
                        if isinstance(notes, dict):
                            historical = notes.get("historical_context", [])
                    except (ValueError, TypeError):
                        pass
                contexts.append({"decision": plan.decision, "omitted": list(plan.omitted),
                                 "estimated_input_tokens": plan.estimated_input_tokens,
                                 "historical_context": historical})

            result = None
            unhandled = None
            # Fix only random identifiers, not financial decisions; task IDs remain distinct.
            task_id = uuid5(NAMESPACE_URL, f"{dataset['dataset_id']}/{case['id']}/{index}")
            with redirect_stdout(io.StringIO()), patch.object(agent, "uuid4", return_value=task_id), \
                    patch.object(MockClient, "create", new=observe_create), \
                    patch.object(agent, "execute_tool", side_effect=observe_execute):
                try:
                    result = session_demo.run_turn(session, turn["question"], memory_directory=memory_dir,
                                                   context_observer=observe_context)
                except Exception as error:
                    unhandled = type(error).__name__  # Never persist arbitrary exception bodies.

            state = result.state if result else None
            query = result.query if result else None
            observed = {
                "behavior": classify(result) if result else "error", "answer": result.answer if result else "未捕获异常，详情已隐藏。",
                "query": {field: getattr(query, field) for field in ("company", "year", "quarter", "kind")} if query else None,
                "state_status": state.status if state else None, "task_id": state.task_id if state else str(task_id),
                "final_answer": state.final_answer if state else None, "evidence": deepcopy(state.evidence) if state else None,
                "failure_stage": state.failure_stage if state else None, "error": state.error if state else None,
                "unhandled_error": unhandled, "pending_companies": list(session.pending_companies),
                "tool_calls": calls, "api_request_count": state.api_request_count if state else len(requests),
                "simulated_token_usage": {key: sum(request["simulated_usage"][key] for request in requests)
                                          for key in ("input_tokens", "output_tokens", "total_tokens")},
                "requests": requests, "contexts": contexts,
            }
            # Gold enters only here, after the actual task finished.
            results.append({"turn": index, "question": turn["question"], "expected": turn["expected"],
                            "observed": observed, "evaluation": score_turn(turn["expected"], observed, dataset["sources"])})
    return {"id": case["id"], "category": case["category"], "track": case["track"], "fixture": case["fixture"],
            "description": case["description"], "passed": all(turn["evaluation"]["passed"] for turn in results), "turns": results}


def evaluate(dataset, digest, case_ids=None):
    selected = [case for case in dataset["cases"] if case_ids is None or case["id"] in case_ids]
    if not selected or (case_ids is not None and set(case_ids) != {case["id"] for case in selected}):
        raise EvaluationError("未知或空的案例选择。")
    # Guard the complete evaluation, including accidental client construction and network calls.
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden in evaluation")), \
            patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden in evaluation")), \
            patch("openai.OpenAI", side_effect=AssertionError("Live client forbidden in evaluation")):
        cases = [run_case(case, dataset) for case in selected]
    turns = [turn for case in cases for turn in case["turns"]]
    fingerprints = {path: file_hash(REPO_ROOT / path) for path in dataset["pinned_inputs"]}
    code_paths = sorted(Path(__file__).resolve().parents[1].glob("*.py")) + sorted(Path(__file__).parent.glob("*.py"))
    code_hashes = {path.relative_to(Path(__file__).resolve().parents[1]).as_posix(): file_hash(path) for path in code_paths}
    failures = []
    for case in cases:
        for turn in case["turns"]:
            if not turn["evaluation"]["passed"]:
                actual = turn["observed"]["behavior"]
                explanation = ("可回答且信息明确的问题被要求澄清；当前 Python 规则未覆盖该表达。"
                               if turn["expected"]["behavior"] == "answer" and actual == "clarify"
                               else "实际行为未满足冻结 gold，请查看工具轨迹、金额、引用与失败阶段。")
                failures.append({"case_id": case["id"], "turn": turn["turn"], "question": turn["question"],
                                 "failed_checks": turn["evaluation"]["failed_checks"], "analysis": explanation})
    return {
        "schema_version": "1", "evaluation_type": "offline_agent_evaluation", "dataset_id": dataset["dataset_id"],
        "dataset_sha256": digest, "evaluation_clock": dataset["evaluation_clock"], "python_version": platform.python_version(),
        "dataset_scope": "full" if case_ids is None else "subset", "input_fingerprints": fingerprints,
        "inputs_match_frozen": fingerprints == dataset["pinned_inputs"], "code_fingerprints": code_hashes,
        "case_count": len(cases), "turn_count": len(turns), "passed_cases": sum(case["passed"] for case in cases),
        "metrics": aggregate(turns),
        "tracks": {track: {"cases": sum(case["track"] == track for case in cases),
                           "passed": sum(case["passed"] for case in cases if case["track"] == track),
                           "metrics": aggregate([turn for case in cases if case["track"] == track for turn in case["turns"]])}
                   for track in sorted({case["track"] for case in cases})},
        "simulated_token_usage": {key: sum(turn["observed"]["simulated_token_usage"][key] for turn in turns)
                                  for key in ("input_tokens", "output_tokens", "total_tokens")},
        "simulated_api_requests": sum(turn["observed"]["api_request_count"] for turn in turns),
        "real_api_requests": 0, "cost_note": "Token Usage 全部来自 Fake Responses，不能换算为真实模型成本。",
        "limitations": ["Fake Model 的工具策略预先写好，Tool Selection Accuracy 不是 GPT 的自主选择能力。",
                        "仅有 CVS 简报两期四舍五入数值；没有 UNH/Amazon 财务 gold。",
                        "18 个手工案例，不是随机样本或独立 holdout，不能推断一般任务成功率。",
                        "金额 grader 依赖当前中文输出格式；改变输出格式应版本化 grader。",
                        "两个工具故障是明确注入的实验条件，不是此次运行发现的生产故障。"],
        "failures": failures, "cases": cases,
    }


def render_report(report):
    esc = lambda value: html.escape(str(value))
    metrics = "".join(f"<tr><td>{esc(name)}</td><td>{item['correct']}/{item['eligible']}</td>"
                      f"<td>{item['percent'] if item['percent'] is not None else 'N/A'}%</td><td>{esc(item['definition'])}</td></tr>"
                      for name, item in report["metrics"].items())
    rows, details = [], []
    for case in report["cases"]:
        for turn in case["turns"]:
            actual, grade = turn["observed"], turn["evaluation"]
            rows.append(f"<tr><td>{case['id']}.{turn['turn']}</td><td>{esc(turn['question'])}</td>"
                        f"<td>{esc(turn['expected']['behavior'])} → {esc(actual['behavior'])}</td>"
                        f"<td>{esc(', '.join(call['name'] for call in actual['tool_calls']) or '无')}</td>"
                        f"<td>{'PASS' if grade['passed'] else 'FAIL'}</td></tr>")
        details.append(f"<details><summary>{case['id']} · {esc(case['description'])}</summary>"
                       f"<pre>{esc(json.dumps(case, ensure_ascii=False, indent=2))}</pre></details>")
    failures = "".join(f"<li>{item['case_id']}.{item['turn']}：{esc(item['analysis'])}"
                       f" 检查项：{esc(', '.join(item['failed_checks']))}</li>" for item in report["failures"]) or "<li>没有 gold 不匹配。</li>"
    limits = "".join(f"<li>{esc(item)}</li>" for item in report["limitations"])
    return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Offline Agent Evaluation v1</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;max-width:1150px;margin:40px auto;padding:0 20px;color:#18212b}}
table{{border-collapse:collapse;width:100%;margin:20px 0}}td,th{{border:1px solid #d6dce2;padding:9px;text-align:left}}
th{{background:#edf1f5}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:16px;font-size:13px}}
details{{border-top:1px solid #d6dce2;padding:12px 0}}small{{color:#536170}}</style>
<h1>Financial Research Agent · Offline Evaluation v1</h1>
<p>{report['case_count']} 个场景 / {report['turn_count']} 个评分轮次；通过 {report['passed_cases']}/{report['case_count']} 个场景。
Baseline {report['tracks'].get('baseline', {}).get('passed', 0)}/{report['tracks'].get('baseline', {}).get('cases', 0)}；
Capability probes {report['tracks'].get('capability_probe', {}).get('passed', 0)}/{report['tracks'].get('capability_probe', {}).get('cases', 0)}。</p>
<p><strong>全部使用 Fake Responses + 本地工具，真实 API 请求为 0。</strong>{esc(report['cost_note'])}</p>
<p>模拟请求 {report['simulated_api_requests']} 次；模拟 Usage：{esc(report['simulated_token_usage'])}。
输入文件与冻结版本一致：{report['inputs_match_frozen']}。</p>
<small>Dataset SHA-256：{report['dataset_sha256']}；固定评估时钟：{report['evaluation_clock']}（不是运行时间）。</small>
<h2>总体指标</h2><table><tr><th>指标</th><th>分子/分母</th><th>百分比</th><th>适用范围与定义</th></tr>{metrics}</table>
<h2>失败案例分析</h2><ul>{failures}</ul>
<p>执行成功率会把注入的工具故障计为失败；正确安全停止仍可通过相应场景。N/A 项不进入相应指标分母。</p>
<h2>逐题结果</h2><table><tr><th>场景.轮次</th><th>用户问题</th><th>预期 → 实际</th><th>工具请求顺序</th><th>结果</th></tr>{''.join(rows)}</table>
<h2>局限性与评估层级</h2><ul>{limits}</ul>
<p>Unit Testing 检查局部约束；本报告的 Offline Agent Evaluation 检查冻结任务的端到端表现；
Real LLM Evaluation 才能衡量真实模型理解、工具选择、延迟与实际 Usage。本次未执行 Real LLM Evaluation。</p>
<h2>逐场景轨迹</h2>{''.join(details)}</html>"""


def write_report(report, directory=OUTPUT_DIR):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (directory / "report.html").write_text(render_report(report), encoding="utf-8")
    traces = [{"case_id": case["id"], "turn": turn["turn"], "fixture": case["fixture"],
               **{key: turn["observed"][key] for key in ("tool_calls", "simulated_token_usage", "failure_stage", "error", "unhandled_error")}}
              for case in report["cases"] for turn in case["turns"]]
    (directory / "tool_traces.jsonl").write_text("".join(json.dumps(trace, ensure_ascii=False, sort_keys=True) + "\n" for trace in traces), encoding="utf-8")
    return directory / "report.html"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--fail-on-failure", action="store_true", help="Return nonzero when any frozen case fails")
    args = parser.parse_args()
    try:
        dataset, digest = load_dataset()
        report = evaluate(dataset, digest)
        path = write_report(report, args.output)
    except (EvaluationError, OSError, ValueError, KeyError):
        print("Evaluation 未完成：Dataset、运行文件或输出配置检查失败。未回显异常内容。")
        return 2
    print(f"Offline Evaluation：{report['passed_cases']}/{report['case_count']} 场景通过，{report['turn_count']} 个评分轮次。")
    for name, item in report["metrics"].items():
        print(f"{name}: {item['correct']}/{item['eligible']} = {item['percent']}%")
    print(f"模拟 Usage：{report['simulated_token_usage']}；不是实际成本。真实 API 请求：0。")
    print(f"Report：{path}")
    return 1 if args.fail_on_failure and report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
