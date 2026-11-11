"""Deterministic context selection. No model calls, evidence creation or state mutations."""

from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Literal
from long_term_memory import MemoryStoreError, memory_context_items


@dataclass(frozen=True)
class ContextPlan:
    decision: Literal["ready", "clarify", "budget_stop", "invalid_context"]
    input_items: list[dict]
    estimated_input_tokens: int = 0
    selected_task_ids: tuple[str, ...] = ()
    omitted: tuple[str, ...] = ()
    message: str | None = None
    memory_task_ids: tuple[str, ...] = ()


def topic_tuple(value):
    return (value.company, value.metric, value.year, value.quarter)


def topic_data(topic):
    return dict(zip(("company", "metric", "year", "quarter"), topic))


def build_understanding_context(state, payload, limits, question, session, *, context_budget=12000):
    """Only bounded topic metadata and user questions; never prior answers/evidence.

    Use a view for the existing Context Builder so its budget uses the same task's
    usage. This does not create another task or reset the actual State.
    """
    reference = {
        "current_topic": topic_data(topic_tuple(session)),
        "pending_companies": list(session.pending_companies[:4]),
        "pending_question": session.pending_question[:200] if session.pending_question else None,
        "recent_turns": [
            {"question": turn.question[:300], "topic": topic_data(turn.topic) if turn.topic else None,
             "intent": turn.intent, "outcome": turn.outcome}
            for turn in list(session.recent_turns)[-2:]
        ],
        "reference_only": True,
    }
    view = deepcopy(state)
    view.user_question = json.dumps({"session": reference, "user_question": question}, ensure_ascii=False)
    view.history = [{"role": "user", "content": view.user_question}]
    return build_context(view, payload, limits, context_budget=context_budget)


def _valid_trace(state):
    """One initial question, then original response items and serial call/output pairs."""
    if not state.history or state.history[0] != {"role": "user", "content": state.user_question}:
        return False
    if state.pending_tool_call is not None:
        return False  # Never send another model request while a tool is unfinished.
    pending = None
    seen = set()
    for item in state.history[1:]:
        if not isinstance(item, dict):
            return False
        kind = item.get("type")
        if kind == "function_call":
            call_id = item.get("call_id")
            if (pending is not None or not isinstance(call_id, str) or not call_id
                    or call_id in seen or item.get("name") not in {"search_report", "calculate"}
                    or not isinstance(item.get("arguments"), str)):
                return False
            seen.add(call_id)
            pending = call_id
        elif kind == "function_call_output":
            if pending is None or item.get("call_id") != pending or not isinstance(item.get("output"), str):
                return False
            pending = None
        elif kind == "message":
            if item.get("role") != "assistant":
                return False
        elif kind != "reasoning":
            return False
    return pending is None


def build_context(state, payload, limits, *, query=None, session=None, context_budget=12000,
                  historical_memory=()):
    """Project confirmed slots; keep the current trace intact; shed optional history first.

    The estimate deliberately retains the loop's original UTF-8 bytes + 1024 rule.
    It covers the complete request payload, not just input messages, and is not
    an exact tokenizer count or a claim about the model's context-window size.
    """
    if session is not None and len(session.pending_companies) > 1:
        return ContextPlan("clarify", [], message="存在多个候选公司，请先明确公司 Ticker。")
    if not _valid_trace(state):
        return ContextPlan("invalid_context", [], message="当前任务工具记录缺失、重复或顺序不正确，已停止。")
    if type(context_budget) is not int or not 1 <= context_budget <= 12000:
        return ContextPlan("budget_stop", [], message="Context Budget 必须在 1 到 12000 之间。")

    notes = None
    optional = None
    selected = ()
    omitted = []
    if session is not None:
        if query is None or topic_tuple(query) != topic_tuple(session) or state.user_question != query.question:
            return ContextPlan("invalid_context", [], message="当前问题与已确认 Session 主题不一致，已停止。")
        topic = topic_tuple(query)
        notes = {"context_kind": "confirmed_topic", "topic": topic_data(topic), "not_financial_evidence": True}
        if session.latest_correction == topic:
            # Store only confirmed slots, never the original sentence or a claimed amount.
            notes["necessary_user_correction"] = topic_data(topic)
        related = [turn for turn in session.recent_turns
                   if turn.topic == topic and turn.outcome == "completed" and turn.intent in {"search", "compare"}]
        if related:
            last = related[-1]
            optional = {"topic": topic_data(last.topic), "intent": last.intent, "reference_only": True}
            selected = (last.task_id,)
        if len(session.recent_turns) > len(selected):
            omitted.append("unrelated_or_older_turns")
        if session.recent_turns:
            omitted.append("old_answers_amounts_and_tool_records")

    memory_items = []
    if historical_memory:
        if query is None or state.user_question != query.question:
            return ContextPlan("invalid_context", [], message="历史记忆缺少已确认的当前查询条件。")
        try:
            memory_items = memory_context_items(historical_memory, query)
        except MemoryStoreError:
            return ContextPlan("invalid_context", [], message="历史记忆 Context 未通过校验。")
        if len(memory_items) < len(historical_memory):
            omitted.append("historical_memory_filtered_or_limited")
        if notes is None and memory_items:
            notes = {"context_kind": "confirmed_topic", "topic": topic_data(topic_tuple(query)),
                     "not_financial_evidence": True}

    def assemble(include_optional):
        items = deepcopy(state.history)
        if notes is not None:
            data = deepcopy(notes)
            if include_optional and optional is not None:
                data["previous_topic_confirmation"] = optional
            if memory_items:
                data["historical_context"] = deepcopy(memory_items)
            # Reference data has user-level authority and precedes the current question.
            items.insert(0, {"role": "user", "content": json.dumps(data, ensure_ascii=False)})
        estimate = len(json.dumps({**payload, "input": items}, ensure_ascii=False).encode("utf-8")) + 1024
        return items, estimate

    def fits(estimate):
        return (estimate <= context_budget
                and state.total_tokens + estimate + limits.output_tokens <= limits.total_tokens)

    items, estimate = assemble(True)
    include_optional = True
    if not fits(estimate) and optional is not None:
        omitted.append("optional_history_budget")
        selected = ()
        include_optional = False
        items, estimate = assemble(include_optional)
    while not fits(estimate) and memory_items:
        if "historical_memory_budget" not in omitted:
            omitted.append("historical_memory_budget")
        memory_items.pop()  # Least preferred record first; never trim current tool records.
        items, estimate = assemble(include_optional)
    if not fits(estimate):
        return ContextPlan("budget_stop", [], estimate, selected, tuple(omitted),
                           "必需 Context 或下一次请求可能超过预算，已停止。")
    return ContextPlan("ready", items, estimate, selected, tuple(omitted),
                       memory_task_ids=tuple(item["record"]["snapshot_task_id"] for item in memory_items))
