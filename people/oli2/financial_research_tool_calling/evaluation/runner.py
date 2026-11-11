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
    "answer_accuracy": "Denominator: turns requiring an amount. Numerator: correct amount, unit and query. Incorrect clarification or refusal counts as wrong.",
    "tool_selection_accuracy": "Denominator: all turns. Numerator: Fake-requested tool names and order match gold, with no tools for clarification. This measures scripted orchestration only.",
    "citation_accuracy": "Denominator: turns requiring sourced financial answers. Numerator: answer and current Evidence match citation ID, title, page and URL. Missing answers count wrong.",
    "abstention_accuracy": "Denominator: turns without injected faults. Numerator: correct answer/abstain/clarify decision. Both unsupported answers and unnecessary refusal or clarification are penalized.",
    "execution_success": "Denominator: all turns. Numerator: answer/abstain/clarify without failed State or uncaught exceptions. Injected faults count as execution failures but can pass safe-stop case requirements.",
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
        raise EvaluationError("Frozen dataset SHA-256 mismatch; create a new version instead of overwriting v1.")
    data = json.loads(raw)
    if data.get("schema_version") != "1" or not 15 <= len(data.get("cases", [])) <= 20:
        raise EvaluationError("Invalid dataset version or case count.")
    if len({case["id"] for case in data["cases"]}) != len(data["cases"]):
        raise EvaluationError("Duplicate dataset case IDs.")
    for case in data["cases"]:
        if case["fixture"] not in {None, "stale_memory", "search_failure", "calculate_failure"}:
            raise EvaluationError("Unknown evaluation fixture.")
        for turn in case["turns"]:
            expected = turn["expected"]
            if expected["behavior"] not in {"answer", "abstain", "clarify", "error"}:
                raise EvaluationError("Unknown expected behavior.")
            if expected["behavior"] == "answer":
                Decimal(expected["value"])
                if expected["source"] not in data["sources"] or expected["unit"] != "十亿美元":
                    raise EvaluationError("Financial gold is missing its unit or source.")
            elif any(expected[key] is not None for key in ("value", "unit", "source")):
                raise EvaluationError("Non-answer turns must not contain invented amounts or citations.")
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
                "behavior": classify(result) if result else "error", "answer": result.answer if result else "Unhandled exception; details are hidden.",
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
        raise EvaluationError("Unknown or empty case selection.")
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
                explanation = ("An answerable, unambiguous question triggered clarification because the Python rules do not cover its wording."
                               if turn["expected"]["behavior"] == "answer" and actual == "clarify"
                               else "Observed behavior differs from frozen gold; inspect tools, amounts, citations and failure stage.")
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
        "real_api_requests": 0, "cost_note": "All token Usage comes from Fake Responses and cannot be priced as real model cost.",
        "limitations": ["Fake tool decisions are scripted; Tool Selection Accuracy does not measure autonomous GPT behavior.",
                        "Only two rounded CVS presentation figures are available; there is no UNH/Amazon financial gold.",
                        "The 18 manually authored cases are not a random sample or independent holdout and do not establish general task accuracy.",
                        "The amount grader depends on the legacy Chinese answer format; changing that format requires a versioned grader.",
                        "The two tool faults are explicit test injections, not production failures discovered in this run."],
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
                        f"<td>{esc(', '.join(call['name'] for call in actual['tool_calls']) or 'none')}</td>"
                        f"<td>{'PASS' if grade['passed'] else 'FAIL'}</td></tr>")
        details.append(f"<details><summary>{case['id']} · {esc(case['description'])}</summary>"
                       f"<pre>{esc(json.dumps(case, ensure_ascii=False, indent=2))}</pre></details>")
    failures = "".join(f"<li>{item['case_id']}.{item['turn']}：{esc(item['analysis'])}"
                       f" Checks: {esc(', '.join(item['failed_checks']))}</li>" for item in report["failures"]) or "<li>No gold mismatches.</li>"
    limits = "".join(f"<li>{esc(item)}</li>" for item in report["limitations"])
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Offline Agent Evaluation v1</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;max-width:1150px;margin:40px auto;padding:0 20px;color:#18212b}}
table{{border-collapse:collapse;width:100%;margin:20px 0}}td,th{{border:1px solid #d6dce2;padding:9px;text-align:left}}
th{{background:#edf1f5}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:16px;font-size:13px}}
details{{border-top:1px solid #d6dce2;padding:12px 0}}small{{color:#536170}}</style>
<h1>Financial Research Agent · Offline Evaluation v1</h1>
<p>{report['case_count']} scenarios / {report['turn_count']} scored turns; passed {report['passed_cases']}/{report['case_count']} scenarios.
Baseline {report['tracks'].get('baseline', {}).get('passed', 0)}/{report['tracks'].get('baseline', {}).get('cases', 0)}；
Capability probes {report['tracks'].get('capability_probe', {}).get('passed', 0)}/{report['tracks'].get('capability_probe', {}).get('cases', 0)}。</p>
<p><strong>All cases use Fake Responses and local tools. Real API requests: 0.</strong>{esc(report['cost_note'])}</p>
<p>Simulated requests: {report['simulated_api_requests']}; simulated Usage: {esc(report['simulated_token_usage'])}。
Inputs match the frozen version: {report['inputs_match_frozen']}。</p>
<small>Dataset SHA-256: {report['dataset_sha256']}; fixed evaluation clock: {report['evaluation_clock']} (not the execution time).</small>
<h2>Overall metrics</h2><table><tr><th>Metric</th><th>Correct/eligible</th><th>Percentage</th><th>Scope and definition</th></tr>{metrics}</table>
<h2>Failure analysis</h2><ul>{failures}</ul>
<p>Execution success counts injected tool faults as failures; correct safe stopping can still pass the scenario. N/A items are excluded from metric denominators.</p>
<h2>Per-turn results</h2><table><tr><th>Case.turn</th><th>User question</th><th>Expected -> observed</th><th>Requested tool order</th><th>Result</th></tr>{''.join(rows)}</table>
<h2>Limitations and evaluation layers</h2><ul>{limits}</ul>
<p>Unit Testing checks local contracts; this Offline Agent Evaluation checks end-to-end performance on frozen tasks;
Real LLM Evaluation measures actual model understanding, tool selection, latency and Usage. No Real LLM Evaluation was performed in this run.</p>
<h2>Per-scenario traces</h2>{''.join(details)}</html>"""


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
        print("Evaluation did not complete: dataset, runtime files or output configuration checks failed. Error details are hidden.")
        return 2
    print(f"Offline Evaluation: {report['passed_cases']}/{report['case_count']} scenarios passed; {report['turn_count']} scored turns.")
    for name, item in report["metrics"].items():
        print(f"{name}: {item['correct']}/{item['eligible']} = {item['percent']}%")
    print(f"Simulated Usage: {report['simulated_token_usage']}; not actual cost. Real API requests: 0.")
    print(f"Report: {path}")
    return 1 if args.fail_on_failure and report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
