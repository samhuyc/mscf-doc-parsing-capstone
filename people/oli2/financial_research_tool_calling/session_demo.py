"""Bounded, in-memory conversation demo. Fake Responses only; no persistence or live option."""

import argparse
from collections import deque
from dataclasses import dataclass, field
import json
import re
from uuid import uuid4

from api_demo import AgentState, Limits, ResearchQuery, StopAgent, run_agent
from mock_responses import MockClient
from context_builder import topic_tuple

MAX_QUESTION_CHARS = 300
MAX_ANSWER_CHARS = 1500
METRIC = "consolidated_total_revenue"


class ClarificationNeeded(ValueError):
    """Controlled messages for questions outside our deliberately small grammar."""


@dataclass(frozen=True)
class Turn:
    question: str
    resolved_question: str | None
    answer: str
    task_id: str
    outcome: str
    topic: tuple[str, str, int, int] | None = None
    intent: str | None = None


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: uuid4().hex)
    company: str | None = None
    metric: str | None = None
    year: int | None = None
    quarter: int | None = None
    pending_companies: tuple[str, ...] = ()
    pending_question: str | None = None
    latest_correction: tuple[str, str, int, int] | None = None
    recent_turns: deque[Turn] = field(default_factory=lambda: deque(maxlen=2), init=False)

    def remember(self, question, result):
        # Keep two user/assistant exchanges, not two messages or entire AgentStates.
        self.recent_turns.append(Turn(
            question=question[:MAX_QUESTION_CHARS],
            resolved_question=result.query.question if result.query else None,
            answer=result.answer[:MAX_ANSWER_CHARS],
            task_id=result.state.task_id,
            outcome=result.outcome,
            topic=topic_tuple(result.query) if result.query else None,
            intent=result.query.kind if result.query else None,
        ))


@dataclass(frozen=True)
class TurnResult:
    state: AgentState
    query: ResearchQuery | None
    answer: str
    outcome: str
    category: str | None = None


def resolve_question(question: str, session: Session) -> ResearchQuery:
    """Resolve a small documented Chinese grammar; unknown text requires clarification.

    Explicit slots replace the current topic. Omitted slots inherit the topic.
    去年 means the preceding year of that topic, never the computer's current year.
    No amounts or prior assistant answers are used to construct a query.
    """
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_CHARS:
        raise ClarificationNeeded("请提供不超过 300 字的财务问题。")
    text = question.strip().rstrip("？?。").strip()
    if any(word in text for word in ("百分", "%", "％", "增长率", "增幅", "环比")):
        raise ClarificationNeeded("当前 Demo 只计算同比增加金额。请确认要查询金额；百分比和环比暂不支持。")

    # A few aliases aid the lesson; any other company can use an explicit ticker.
    for alias, ticker in (("联合健康", "UNH"), ("苹果", "AAPL"), ("CVS Health", "CVS"),
                          ("Amazon", "AMZN"), ("亚马逊", "AMZN")):
        pattern = rf"(?<![A-Za-z]){re.escape(alias)}(?![A-Za-z])"
        text = re.sub(pattern, ticker, text, flags=re.IGNORECASE)
    periods = list(re.finditer(r"(?<!\d)(20\d{2})\s*年?\s*Q([1-4])(?!\d)", text, re.IGNORECASE))
    if len(periods) > 1:
        raise ClarificationNeeded("发现多个期间。请指定一个当前季度；同比将与上一年同季度比较。")
    year = quarter = None
    if periods:
        period = periods[0]
        year, quarter = int(period[1]), int(period[2])
        text = text[:period.start()] + text[period.end():]

    companies = list(re.finditer(r"(?<![A-Za-z])[A-Za-z]{1,10}(?![A-Za-z])", text))
    linked_reference = re.search(
        r"(?:它|那家公司|这家公司|该公司)\s*(?:和|与|跟)|(?:和|与|跟)\s*(?:它|那家公司|这家公司|该公司)", text,
    )
    if linked_reference and session.company and companies:
        candidates = tuple(dict.fromkeys([session.company, *(match[0].upper() for match in companies)]))[:4]
        if len(candidates) > 1:
            session.pending_companies = candidates
            raise ClarificationNeeded("指代和公司名称涉及多个候选。请一次明确一家公司的 Ticker。")
    if len(companies) > 1:
        session.pending_companies = tuple(dict.fromkeys(match[0].upper() for match in companies))[:4]
        raise ClarificationNeeded("发现多个公司。请一次指定一家公司的 Ticker。")
    company = None
    if companies:
        match = companies[0]
        company = match[0].upper()
        text = text[:match.start()] + text[match.end():]

    if company is None and len(session.pending_companies) > 1:
        raise ClarificationNeeded("尚有多个候选公司，请明确公司 Ticker 后再继续。")

    text = re.sub(r"\s+", "", text)
    correction = text.startswith(("我是说", "更正为"))
    if correction:
        text = re.sub(r"^(?:我是说|更正为)", "", text, count=1)
    text = text.replace("那家公司", "那", 1)
    if text.startswith("请问"):
        text = text[2:]
    metrics = re.findall(r"合并总营收|合并总收入", text)
    if len(metrics) > 1:
        raise ClarificationNeeded("请一次指定一个指标。")
    metric = METRIC if metrics else None
    text = re.sub(r"合并总营收|合并总收入", "", text)
    if "营收" in text:
        if session.metric != METRIC:
            raise ClarificationNeeded("请明确是否指合并总营收；当前 Demo 只支持这一指标。")
        text = text.replace("营收", "", 1)
        metric = METRIC

    compare = re.fullmatch(
        r"(?:那|那么)?的?(?:(?:相比|比)去年(?:同期)?|同比)(?:增加|增长|多)了?多少(?:金额)?", text,
    )
    search = re.fullmatch(r"(?:那|那么|改看|改成|换成|换看)?的?(?:是多少|多少|呢)?", text)
    explicit = company is not None or year is not None or metric is not None
    if compare:
        kind = "compare"
    elif search and (explicit or "多少" in text):
        kind = "search"
    else:
        # In particular, do not silently drop unknown companies, metrics, dates,
        # instructions, comparison bases, or ambiguous plural pronouns such as "they".
        raise ClarificationNeeded(
            "问题存在歧义或超出当前句式。请明确公司 Ticker、季度（如 2025 Q2）、合并总营收，"
            "或询问‘那比去年增长了多少？’。"
        )

    # Only commit explicit slots after the entire sentence has been recognized.
    # An incomplete but unambiguous question can build the topic across turns.
    if company is not None:
        session.company = company
        session.pending_companies = ()
    if year is not None:
        session.year, session.quarter = year, quarter
    if metric is not None:
        session.metric = metric
    if session.latest_correction != topic_tuple(session):
        session.latest_correction = None
    missing = [label for label, value in (
        ("公司 Ticker", session.company), ("指标（合并总营收）", session.metric),
        ("期间（如 2025 Q2）", session.year),
    ) if value is None]
    if session.quarter is None and "期间（如 2025 Q2）" not in missing:
        missing.append("季度")
    if missing:
        raise ClarificationNeeded("请补充：" + "、".join(missing) + "。")
    if correction:
        session.latest_correction = topic_tuple(session)
    return ResearchQuery(session.company, session.metric, session.year, session.quarter, kind)


def run_turn(session: Session, question: str, *, limits: Limits = Limits(),
             context_budget=12000, context_observer=None, memory_directory=None) -> TurnResult:
    """Always allocate a fresh State. Only this task's resolved question enters the loop."""
    state = AgentState()
    print(f"\n新任务 {state.task_id}：pending，工具 0，请求 0，Tokens 0")
    try:
        query = resolve_question(question, session)
    except ClarificationNeeded as error:
        # Clarification is a conversation outcome, not a fabricated financial answer.
        # The financial task remains pending and has never entered the Agent Loop.
        state.user_question = question[:MAX_QUESTION_CHARS] if isinstance(question, str) else ""
        result = TurnResult(state, None, str(error), "clarification")
    else:
        print("补全后的问题：" + query.question)
        try:
            answer = run_agent(MockClient(query.kind, query=query), query.kind, limits, state=state, query=query,
                               session=session, context_budget=context_budget, context_observer=context_observer,
                               memory_directory=memory_directory)
            result = TurnResult(state, query, answer, "completed")
        except StopAgent:
            result = TurnResult(state, query, state.error or "任务安全停止。", "failed")
    session.remember(question if isinstance(question, str) else "", result)
    if result.outcome != "completed":
        print(result.answer)
    print("State 摘要：", json.dumps({
        "task_id": state.task_id, "status": state.status, "stage": state.stage,
        "tool_call_count": state.tool_call_count, "api_request_count": state.api_request_count,
        "input_tokens": state.input_tokens, "output_tokens": state.output_tokens,
        "total_tokens": state.total_tokens, "history_items": len(state.history),
    }, ensure_ascii=False))
    print("Session 摘要：", json.dumps({
        "company": session.company, "metric": session.metric,
        "year": session.year, "quarter": session.quarter,
        "pending_companies": session.pending_companies, "latest_correction": session.latest_correction,
        "recent_turns": [{"question": turn.question, "task_id": turn.task_id,
                          "outcome": turn.outcome} for turn in session.recent_turns],
    }, ensure_ascii=False))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interactive", action="store_true", help="Ask supported questions in one in-memory session")
    args = parser.parse_args()
    print("OFFLINE Session：Fake Responses + 真实本地工具；增长多少指同比增加金额。")
    print("只保存最近两轮问答；退出即清空 Session；不读写 Snapshot。")
    session = Session()
    if args.interactive:
        while True:
            try:
                question = input("\n问题（输入 exit 退出）：")
            except (EOFError, KeyboardInterrupt):
                break
            if question.strip().lower() == "exit":
                break
            run_turn(session, question)
    else:
        for question in ("CVS 2025 Q2 的合并总营收是多少？", "那比去年增长了多少？"):
            print("\n用户：" + question)
            run_turn(session, question)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
