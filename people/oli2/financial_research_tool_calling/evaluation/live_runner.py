"""Versioned live-LLM evaluation. Default: offline runner contract check, NEVER paid."""
import argparse
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import html
import io
import json
import logging
import os
from pathlib import Path
import socket
from unittest.mock import patch

import api_demo as agent
from demo import REPO_ROOT
from llm_session_demo import QuestionUnderstanding, run_llm_turn
from session_demo import Session
from evaluation.runner import EvaluationError, classify, file_hash, load_dataset, score_turn

SUITE = Path(__file__).with_name("live_suite_v1.json")
OUT = SUITE.parent.parent / "artifacts" / "evaluation" / "llm_live_v1"
PRIOR_REPORT = OUT / "live_20261111T032436Z" / "report.json"
REMAINING_TURNS = (("L05", 1), ("L06", 1), ("L06", 2), ("L07", 1), ("L08", 1))
REMAINING_CAPS = dict(requests=14, total_tokens=16000, requests_per_task=4, output_tokens_per_request=1024)
DEFINITIONS = {
    "intent_understanding_accuracy": "Denominator: all planned turns. Company, metric, period, comparison period and intent must match, or clarification must be correctly required.",
    "tool_selection_accuracy": "Denominator: all planned turns. Requested tool names and order must match exactly; argument correctness is checked separately.",
    "numerical_accuracy": "Denominator: turns requiring numerical answers. Amount, unit and query must match; unnecessary clarification or refusal is incorrect.",
    "citation_accuracy": "Denominator: turns requiring financial answers. Answer and current Evidence must match citation ID, source, page and URL.",
    "clarification_appropriateness": "Denominator: all planned turns. Clarify only when required; execution errors and unrun turns count as incorrect.",
    "abstention_accuracy": "Denominator: all planned turns. Answer/abstain/clarify must match gold; unnecessary refusal or clarification is incorrect.",
}
PRICING = {"model": agent.MODEL, "tier": "default", "currency": "USD", "checked_date": "2026-11-10",
           "input_per_million": "2", "cached_per_million": "0.10", "cache_write_per_million": "2.50",
           "output_per_million": "10", "source": "https://developers.openai.com/api/docs/models/gpt-6.1-sol"}


def load_suite(path=SUITE):
    dataset, digest = load_dataset()
    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    suite_hash = hashlib.sha256(raw.encode()).hexdigest()
    if suite_hash != Path(str(path) + ".sha256").read_text(encoding="ascii").strip():
        raise EvaluationError("Live suite integrity check failed.")
    suite = json.loads(raw)
    if suite["schema_version"] != "1" or suite["dataset_sha256"] != digest:
        raise EvaluationError("Live suite does not match the original frozen dataset.")
    if not 6 <= len(suite["cases"]) <= 8:
        raise EvaluationError("The live suite requires 6-8 scenarios.")
    by_id = {case["id"]: case for case in dataset["cases"]}
    expanded = []
    for case in suite["cases"]:
        if "frozen_case" in case:
            turns = deepcopy(by_id[case["frozen_case"]]["turns"])
        else:
            turns = [{"question": turn["question"], "expected": deepcopy(
                by_id[turn["gold_ref"][0]]["turns"][turn["gold_ref"][1]]["expected"])} for turn in case["turns"]]
        expanded.append({**case, "turns": turns})
    suite["cases"] = expanded
    fingerprints = {name: file_hash(REPO_ROOT / name) for name in dataset["pinned_inputs"]}
    if fingerprints != dataset["pinned_inputs"]:
        raise EvaluationError("Local report inputs differ from the frozen version; evaluation stopped.")
    return suite, dataset, suite_hash


def select_remaining(suite, suite_hash, prior_path=None):
    """Select whole, previously unexecuted Sessions. No State restore or gold edit."""
    prior_path = Path(PRIOR_REPORT if prior_path is None else prior_path)
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    if (prior.get("evaluation_type") != "real_llm_evaluation"
            or prior.get("dataset_sha256") != suite["dataset_sha256"]
            or prior.get("suite_sha256") != suite_hash):
        raise EvaluationError("Historical live evaluation does not match the frozen suite; selection stopped.")
    pending = {(row["case_id"], row["turn"]): row for row in prior["turns"]
               if row["observed"]["behavior"] == "not_run" and not row["observed"]["executed"]}
    if set(pending) != set(REMAINING_TURNS):
        raise EvaluationError("Historical unrun turns do not match the approved five remaining turns; selection stopped.")
    selected = deepcopy(suite)
    selected["cases"] = [case for case in selected["cases"]
                         if case["id"] in {case_id for case_id, _ in REMAINING_TURNS}]
    selected_ids = []
    for case in selected["cases"]:
        for index, turn in enumerate(case["turns"], 1):
            key = (case["id"], index)
            if key not in pending or any(turn[field] != pending[key][field] for field in ("question", "expected")):
                raise EvaluationError("Remaining questions, golden labels or Session prerequisites do not match.")
            selected_ids.append(key)
    if tuple(selected_ids) != REMAINING_TURNS:
        raise EvaluationError("Remaining-turn order does not match.")
    selected["caps"] = deepcopy(REMAINING_CAPS)
    selected["scope"] += " Remaining five turns only, current code version; NOT a combined multi-version score."
    selected["selection"] = {
        "mode": "remaining_five", "turn_ids": [f"{case}.{turn}" for case, turn in selected_ids],
        "parent_suite_sha256": suite_hash, "source_report": str(prior_path),
        "source_report_sha256": file_hash(prior_path), "fresh_sessions": True,
        "context_note": "L06.1 was not executed previously; it establishes the Session for Amazon in L06.2. No completed State/evidence is reused.",
        "label_audit": "L05 explicitly asks about two companies. Its frozen clarify label represents single-company scope, not necessarily linguistic ambiguity; review separately without relabeling.",
    }
    selected["selection"]["selection_sha256"] = hashlib.sha256(json.dumps(
        {"cases": selected["cases"], "caps": selected["caps"], "parent": suite_hash},
        ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return selected


class BudgetedClient:
    """One suite-wide counter shared across every Session and every task.

    Only safe response projections are recorded; never headers, keys or SDK errors.
    """
    def __init__(self, caps, *, understanding_model=QuestionUnderstanding):
        self.caps, self.delegate, self.events = caps, None, []
        self.understanding_model = understanding_model
        self.input_tokens = self.output_tokens = self.total_tokens = 0
        self.stopped = False
        self.responses = self

    def create(self, **payload):
        estimate = len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) + 1024
        if (self.stopped or len(self.events) >= self.caps["requests"]
                or self.total_tokens + estimate + payload["max_output_tokens"] > self.caps["total_tokens"]):
            self.stopped = True
            raise agent.StopAgent("The evaluation request or token budget is insufficient.")
        if (payload["model"] != agent.MODEL or payload.get("service_tier") != "default"
                or not 1 <= payload["max_output_tokens"] <= self.caps["output_tokens_per_request"]):
            self.stopped = True
            raise agent.StopAgent("The model or output limit does not match the approved evaluation configuration.")
        event = {"request": len(self.events) + 1, "stage": payload["text"]["format"]["name"],
                 "usage": None, "understanding": None, "tool_calls": [], "error": None,
                 "estimated_input_tokens": estimate}
        self.events.append(event)
        try:
            response = self.delegate.responses.create(**payload)
        except Exception as error:
            self.stopped = True
            event["error"] = type(error).__name__
            raise  # The existing Agent hides arbitrary external error details.
        usage = response.usage
        if usage is None:
            self.stopped = True
            raise agent.StopAgent("The API did not return Usage; the entire evaluation stopped and cost is unknown.")
        counts = [getattr(usage, key, None) for key in ("input_tokens", "output_tokens", "total_tokens")]
        if (any(type(value) is not int or value < 0 for value in counts)
                or counts[0] + counts[1] != counts[2]):
            self.stopped = True
            raise agent.StopAgent("Usage counts are invalid; further requests stopped and cost is unknown.")
        event["usage"] = {key: getattr(usage, key) for key in ("input_tokens", "output_tokens", "total_tokens")}
        details = usage.input_tokens_details
        event["usage"].update(cached_tokens=getattr(details, "cached_tokens", None),
                              cache_write_tokens=getattr(details, "cache_write_tokens", None))
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.total_tokens += usage.total_tokens
        for item in response.output:
            if item.type == "function_call":
                try:
                    arguments = json.loads(item.arguments)
                except (ValueError, TypeError):
                    arguments = "invalid JSON (body omitted)"
                event["tool_calls"].append({"name": item.name, "call_id": item.call_id,
                                             "arguments": arguments, "result": None})
        if event["stage"] == "financial_question":
            try:
                event["understanding"] = self.understanding_model.model_validate_json(response.output_text).model_dump()
            except ValueError:
                event["error"] = "invalid_understanding_schema"
        if (self.total_tokens > self.caps["total_tokens"] or response.status != "completed"
                or usage.output_tokens > payload["max_output_tokens"]):
            self.stopped = True
        # Return even on an overage/incomplete response so AgentState also records usage,
        # then stops through its existing validation. No subsequent request is allowed.
        return response


def grade(expected, observed, sources):
    legacy = score_turn(expected, observed, sources)
    parsed = observed["understanding"]
    if expected["behavior"] == "clarify":
        intent_ok = bool(parsed and parsed["needs_clarification"])
    else:
        query = expected["query"]
        intent_ok = bool(parsed and not parsed["needs_clarification"] and
            parsed["company"] == query["company"] and parsed["metric"] == "consolidated_total_revenue" and
            parsed["intent"] == query["kind"] and parsed["period"] == {"year": query["year"], "quarter": query["quarter"]} and
            parsed["comparison_period"] == ({"year": query["year"] - 1, "quarter": query["quarter"]} if query["kind"] == "compare" else None))
    base = legacy["scores"]
    scores = dict(intent_understanding_accuracy=intent_ok,
                  tool_selection_accuracy=base["tool_selection_accuracy"] if observed["executed"] else False,
                  numerical_accuracy=base["answer_accuracy"], citation_accuracy=base["citation_accuracy"],
                  clarification_appropriateness=bool(observed["behavior"] in {"answer", "abstain", "clarify"} and
                      (observed["behavior"] == "clarify") == (expected["behavior"] == "clarify")),
                  abstention_accuracy=base["abstention_accuracy"])
    failures = [key for key, value in scores.items() if value is False]
    if legacy["checks"].get("no_financial_claim") is False:
        failures.append("no_financial_claim")
    return {"scores": scores, "passed": not failures, "failed_checks": failures,
            "legacy_evaluation": legacy}


def cost_estimate(events, live):
    if not live:
        return {"usd": None, "note": "Simulated Usage cannot be converted into actual API cost."}
    total = Decimal(0)
    for event in events:
        usage = event["usage"]
        if usage is None or usage["cached_tokens"] is None or usage["cache_write_tokens"] is None:
            return {"usd": None, "note": "Some requests did not return complete Usage; cost is unknown."}
        ordinary = usage["input_tokens"] - usage["cached_tokens"] - usage["cache_write_tokens"]
        if ordinary < 0:
            return {"usd": None, "note": "Cache usage counts are inconsistent; cost cannot be reliably estimated."}
        total += (Decimal(ordinary) * Decimal(PRICING["input_per_million"])
                  + Decimal(usage["cached_tokens"]) * Decimal(PRICING["cached_per_million"])
                  + Decimal(usage["cache_write_tokens"]) * Decimal(PRICING["cache_write_per_million"])
                  + Decimal(usage["output_tokens"]) * Decimal(PRICING["output_per_million"])) / 1000000
    return {"usd": str(total), "note": "Estimated from returned Usage and frozen Standard rates; the school invoice is authoritative."}


def evaluate(suite, dataset, suite_hash, *, live_client=None, fake_factory=None, caps=None,
             turn_runner=None, understanding_model=QuestionUnderstanding):
    live = live_client is not None
    from evaluation.live_fixtures import client_for
    factory = fake_factory or client_for
    budget = BudgetedClient(caps or suite["caps"], understanding_model=understanding_model)
    run_turn = turn_runner or run_llm_turn
    rows, stopped = [], False
    with ExitStack() as stack:
        if not live:
            stack.enter_context(patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")))
            stack.enter_context(patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden")))
            stack.enter_context(patch("openai.OpenAI", side_effect=AssertionError("Live forbidden")))
        for case in suite["cases"]:
            session = Session()  # Cases isolated; turns within a case retain their context.
            for index, turn in enumerate(case["turns"]):
                start = len(budget.events)
                result = None
                if not stopped:
                    budget.delegate = live_client if live else factory(case["id"], index)
                    with redirect_stdout(io.StringIO()):
                        result = run_turn(session, turn["question"], budget,
                            limits=agent.Limits(requests=suite["caps"]["requests_per_task"]))
                    stopped = budget.stopped or result.outcome == "failed"
                events = budget.events[start:]
                calls = [call for event in events for call in event["tool_calls"]]
                state = result.state if result else None
                if state:
                    outputs = {item["call_id"]: json.loads(item["output"]) for item in state.history
                               if item.get("type") == "function_call_output"}
                    for call in calls:
                        call["result"] = outputs.get(call["call_id"])
                query = result.query if result else None
                observed = {"executed": result is not None, "behavior": (
                    "unsupported" if result and result.category == "unsupported_capability"
                    else classify(result) if result else "not_run"),
                    "category": result.category if result else None,
                    "answer": result.answer if result else "Not executed because a prior error or budget limit stopped the run.",
                    "query": {key: getattr(query, key) for key in ("company", "year", "quarter", "kind")} if query else None,
                    "understanding": next((event["understanding"] for event in events if event["stage"] == "financial_question"), None),
                    "tool_calls": calls, "evidence": state.evidence if state else None,
                    "failure_stage": state.failure_stage if state else None, "final_answer": state.final_answer if state else None,
                    "final_validation_diagnostic": deepcopy(state.final_validation_diagnostic) if state else None,
                    "unhandled_error": None, "pending_companies": list(session.pending_companies), "contexts": [],
                    "task_id": state.task_id if state else None, "requests": deepcopy(events)}
                rows.append({"case_id": case["id"], "turn": index+1, "question": turn["question"],
                             "expected": turn["expected"], "observed": observed,
                             "evaluation": grade(turn["expected"], observed, dataset["sources"])})
                print(f"{case['id']}.{index+1}: {observed['behavior']} ({len(events)} requests)")
    metrics = {}
    for name, definition in DEFINITIONS.items():
        values = [row["evaluation"]["scores"][name] for row in rows if row["evaluation"]["scores"][name] is not None]
        metrics[name] = {"correct": sum(values), "eligible": len(values),
                         "percent": round(100*sum(values)/len(values), 2) if values else None, "definition": definition}
    failures = []
    for row in rows:
        checks = row["evaluation"]["failed_checks"]
        if not checks:
            continue
        if not row["observed"]["executed"]:
            analysis = "Not run after an earlier stop: this reduces coverage but is not evidence of a model interpretation error."
        elif row["observed"]["failure_stage"] in {"api_request", "response_validation", "budget_check"}:
            analysis = "Check budgets and API responses first; diagnose execution failures separately from semantic errors."
        elif "intent_understanding_accuracy" in checks:
            analysis = "Understanding differs from gold: inspect period references, metric selection and unnecessary clarification."
        elif "tool_selection_accuracy" in checks:
            analysis = "Tool order differs after understanding: check Search -> Calculate and premature answers."
        else:
            analysis = "Compare tool results, final amount and source; schema validity does not establish factual accuracy."
        failures.append({"case_id":row["case_id"],"turn":row["turn"],"checks":checks,
                         "stage":row["observed"]["failure_stage"],"analysis":analysis})
    return {"evaluation_type": "real_llm_evaluation" if live else "offline_runner_contract_check",
            "suite_id": suite["suite_id"], "suite_sha256": suite_hash, "dataset_sha256": suite["dataset_sha256"],
            "selection": deepcopy(suite.get("selection", {"mode": "full_suite"})),
            "scope": suite["scope"], "model": agent.MODEL, "caps": budget.caps,
            "code_fingerprints": {str(p.relative_to(SUITE.parent.parent)): file_hash(p)
                for p in list(SUITE.parent.parent.glob('*.py')) + list(SUITE.parent.glob('*.py'))},
            "case_count": len(suite["cases"]), "planned_turns": len(rows),
            "executed_turns": sum(row["observed"]["executed"] for row in rows), "stopped_early": stopped,
            "requests": len(budget.events), "usage_kind": "actual" if live else "simulated",
            "usage": dict(input_tokens=budget.input_tokens, output_tokens=budget.output_tokens, total_tokens=budget.total_tokens),
            "cost": cost_estimate(budget.events, live), "pricing": PRICING, "metrics": metrics,
            "clarifications": {"required": sum(row["expected"]["behavior"] == "clarify" for row in rows),
                "correct": sum(row["expected"]["behavior"] == row["observed"]["behavior"] == "clarify" for row in rows),
                "unnecessary": sum(row["expected"]["behavior"] != "clarify" and row["observed"]["behavior"] == "clarify" for row in rows)},
            "failures": failures, "turns": rows,
            "legacy_contract_failures": [{"case_id": row["case_id"], "turn": row["turn"],
                "checks": row["evaluation"]["legacy_evaluation"]["failed_checks"]}
                for row in rows if not row["evaluation"]["legacy_evaluation"]["passed"]],
            "limitations": ["Development/regression set including debugging questions, not an independent out-of-sample test.",
                "Unrun items remain in planned denominators and count as incorrect; coverage is reported to avoid inflated scores after early stopping.",
                "Frozen gold is unchanged. legacy_evaluation retains implementation checks such as pending_companies; semantic metrics do not depend on that Python field.",
                "The 18-scenario/25-turn Rule-based Offline Evaluation is separate; its overall percentages are not directly comparable with this suite.",
                "Fake contract checks validate the runner only; real GPT capability requires real_llm_evaluation results.",
                "Clarification metrics assess whether clarification is appropriate, not the semantic quality of its wording; review recorded questions manually.",
                "Standard-rate cost estimates are not server-enforced dollar limits; cost is unknown when failures return no Usage."]}


def write_report(report, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    esc = lambda value: html.escape(str(value))
    title = "Real GPT Evaluation" if report["evaluation_type"] == "real_llm_evaluation" else "OFFLINE Contract Check — NOT GPT Evaluation"
    metrics = ''.join(f"<li>{esc(name)}: {v['correct']}/{v['eligible']} — {esc(v['definition'])}</li>" for name,v in report['metrics'].items())
    details = ''.join(f"<details><summary>{row['case_id']}.{row['turn']} {esc(row['question'])} — {esc(row['observed']['behavior'])}</summary><pre>{esc(json.dumps(row,ensure_ascii=False,indent=2))}</pre></details>" for row in report['turns'])
    page = f"<!doctype html><meta charset='utf-8'><title>{title}</title><style>body{{font:16px/1.6 system-ui;max-width:1100px;margin:40px auto;padding:20px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}details{{margin:16px 0}}</style><h1>{title}</h1><p>{esc(report['scope'])}</p><p>Coverage {report['executed_turns']}/{report['planned_turns']}; Requests {report['requests']}; {esc(report['usage_kind'])} Usage {esc(report['usage'])}</p><p>Cost: {esc(report['cost'])}</p><ul>{metrics}</ul><h2>Error Analysis</h2><pre>{esc(json.dumps(report['failures'],ensure_ascii=False,indent=2))}</pre><h2>Legacy contract diagnostics (original labels preserved)</h2><pre>{esc(json.dumps(report['legacy_contract_failures'],ensure_ascii=False,indent=2))}</pre>{details}<h2>Limitations</h2><pre>{esc(json.dumps(report['limitations'],ensure_ascii=False,indent=2))}</pre>"
    (directory / "report.html").write_text(page, encoding="utf-8")
    (directory / "requests.jsonl").write_text(''.join(json.dumps({"case_id":row['case_id'],"turn":row['turn'],**event},ensure_ascii=False)+'\n' for row in report['turns'] for event in row['observed']['requests']),encoding='utf-8')
    return directory / "report.html"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-paid-api", action="store_true")
    parser.add_argument("--remaining", action="store_true", help="Only previously unexecuted L05-L08 (5 turns)")
    args = parser.parse_args()
    if args.live and not args.confirm_paid_api:
        print("Paid execution was not confirmed; no key was read and no request was sent.")
        return 1
    for name in ("openai", "httpx", "httpx2", "httpcore"):
        logging.getLogger(name).disabled = True
    suite, dataset, digest = load_suite()
    if args.remaining:
        suite = select_remaining(suite, digest)
    if args.live:
        from openai import OpenAI
        with OpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url="https://api.openai.com/v1", max_retries=0, timeout=30.0) as client:
            report = evaluate(suite, dataset, digest, live_client=client)
        prefix = "remaining_live_" if args.remaining else "live_"
        directory = OUT / (prefix + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    else:
        report = evaluate(suite, dataset, digest)
        directory = OUT / ("remaining_offline_contract_check" if args.remaining else "offline_contract_check")
    print(write_report(report, directory))
    print(json.dumps({"type":report['evaluation_type'],"requests":report['requests'],"usage":report['usage'],"cost":report['cost']},ensure_ascii=False))
    return 1 if report['stopped_early'] else 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception:
        print("Evaluation configuration or initialization failed; execution stopped and external error details are hidden.")
        exit_code = 1
    raise SystemExit(exit_code)
