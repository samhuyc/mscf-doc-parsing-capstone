"""Integrated teaching CLI. Default is explicit Fake Responses, never a paid fallback."""
import argparse
from contextlib import redirect_stdout
from dataclasses import replace
from decimal import Decimal
import io
import json
import logging
import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from api_demo import Limits, MODEL, StopAgent
from llm_session_demo import (QuestionUnderstanding, UNDERSTANDING_INSTRUCTIONS,
                              FakeUnderstandingClient, run_llm_turn, validate_query)
from session_demo import Session, METRIC
from long_term_memory import MemoryRecord, save_memory, utc_timestamp
from state_snapshot import save_state_snapshot
from evaluation.live_runner import BudgetedClient, cost_estimate

ROOT = Path(__file__).resolve().parent
CAPS = dict(requests=32, total_tokens=30000, requests_per_task=4, output_tokens_per_request=1024)
TASK_LIMITS = Limits(requests=4)
STORAGE = ROOT / "artifacts" / "financial_agent"
CAPABILITY_MESSAGE = "Unsupported Capability：当前只支持单家公司、合并总营收查询及上一年同季度增加金额；不支持多公司分析、其他指标或百分比。"


class IntegratedUnderstanding(QuestionUnderstanding):
    """Add scope classification, not amounts; legacy understanding stays available."""
    request_scope: Literal["single_company", "multiple_companies", "ambiguous", "unsupported"]
    candidate_companies: Annotated[list[Annotated[str, Field(pattern=r"^[A-Z]{1,10}$")]], Field(max_length=4)]

    @model_validator(mode="after")
    def check_scope(self):
        candidates = self.candidate_companies
        if len(set(candidates)) != len(candidates):
            raise ValueError("Candidate companies must be unique")
        if self.request_scope == "multiple_companies":
            if len(candidates) < 2 or self.company is not None or self.needs_clarification or self.intent != "unsupported":
                raise ValueError("Explicit multiple-company request is unsupported, not ambiguity")
        elif self.request_scope == "ambiguous":
            if not self.needs_clarification or (len(candidates) > 1 and self.company is not None):
                raise ValueError("Ambiguity cannot select a candidate")
        elif self.needs_clarification:
            raise ValueError("Only ambiguous scope requests clarification")
        elif self.request_scope == "single_company":
            if len(candidates) > 1 or self.intent == "unsupported" or candidates not in ([], [self.company]):
                raise ValueError("Single company interpretation is inconsistent")
        elif self.intent != "unsupported":
            raise ValueError("Unsupported scope must use unsupported intent")
        return self


INTEGRATED_INSTRUCTIONS = UNDERSTANDING_INSTRUCTIONS + (
    " Scope rules refine the earlier multiple-company instruction: an explicit request for both CVS and UNH "
    "is NOT linguistically ambiguous. Set request_scope=multiple_companies, intent=unsupported, company=null, "
    "candidate_companies to the mentioned tickers, needs_clarification=false, clarification_question=null. "
    "Use request_scope=ambiguous only for missing or genuinely ambiguous references/periods/metrics; preserve "
    "known slots and all candidate companies without choosing one. A clear unsupported metric, percentage, "
    "or comparison method uses request_scope=unsupported and intent=unsupported. Unknown report availability "
    "is not a capability judgment: a single-company revenue lookup still goes to Search. "
    "For a supported resolved question use single_company. Session pending_question identifies the unresolved "
    "issue; after explicit user selection resolve that issue, keeping other known slots. Never execute it automatically."
)


def handle_interpretation(parsed, session, state):
    """Python validates scope and stores unresolved slots; it never parses the user's words."""
    blocked = parsed.request_scope in {"multiple_companies", "unsupported"}
    if not blocked and not parsed.needs_clarification:
        try:
            validate_query(parsed)
        except StopAgent:
            blocked = True
    if not blocked and not parsed.needs_clarification:
        return False  # Existing validated query + existing financial loop.
    session.pending_companies = tuple(parsed.candidate_companies)
    # Avoid inheriting the previous company's topic when the new reference is unresolved.
    session.company = parsed.company
    session.metric = parsed.metric
    session.year = parsed.period.year if parsed.period else None
    session.quarter = parsed.period.quarter if parsed.period else None
    session.latest_correction = None
    session.pending_question = ("请明确选择一家候选公司。" if parsed.request_scope == "multiple_companies"
        else "请改为当前支持的任务。" if blocked else parsed.clarification_question)
    state.history = [{"role": "user", "content": state.user_question}]
    state.final_answer = (CAPABILITY_MESSAGE if blocked else parsed.clarification_question)
    return True


def integrated_turn(session, question, client, *, limits=TASK_LIMITS,
                    memory_directory=None, context_observer=None, storage_directory=None):
    if storage_directory is not None:
        memory_directory = Path(storage_directory) / 'memory'
    result = run_llm_turn(session, question, client, limits=limits,
        memory_directory=memory_directory, context_observer=context_observer,
        understanding_model=IntegratedUnderstanding, understanding_instructions=INTEGRATED_INSTRUCTIONS,
        interpretation_handler=handle_interpretation)
    category = ("failed" if result.outcome == "failed" else
                "ambiguity" if result.outcome == "clarification" else
                "unsupported_capability" if result.query is None else
                "insufficient_evidence" if result.state.evidence is None else "answer")
    # Keep historical graders honest: unsupported is not silently converted into clarify.
    outcome = "unsupported" if category == "unsupported_capability" else result.outcome
    result = replace(result, outcome=outcome, category=category)
    session.recent_turns[-1] = replace(session.recent_turns[-1], outcome=outcome)
    if storage_directory is not None:
        try:
            persist_result(result, Path(storage_directory))
        except (ValueError, OSError):
            result = replace(result, outcome='failed', category='persistence_error',
                answer='本地保存失败，Session 已停止；任务执行状态可在内存检查，未自动重试。')
            session.recent_turns[-1] = replace(session.recent_turns[-1], outcome='failed')
    return result


def persist_result(result, directory):
    # Never save raw user text or a free-text model clarification. Approved fields only.
    safe = replace(result.state,
        user_question=result.query.question if result.query else '[问题正文未持久化]',
        final_answer=(result.state.final_answer if result.category in {'answer','insufficient_evidence'}
            else f'任务结果：{result.category}' if result.state.status == 'completed' else None))
    save_state_snapshot(safe, directory / 'snapshots')
    if result.category == 'answer':
        query, evidence = result.query, result.state.evidence
        save_memory(MemoryRecord(schema_version='1', company=query.company, metric=query.metric,
            year=query.year, quarter=query.quarter,
            source={'url': evidence['source_url'], 'page': evidence['page']},
            last_verified_at=utc_timestamp(), snapshot_task_id=result.state.task_id), directory / 'memory')


class IntegratedFakeClient(FakeUnderstandingClient):
    """Explicit fixtures only; never claim these choices are natural language understanding."""
    def create(self, **payload):
        if payload["text"]["format"]["name"] == "financial_question":
            return super().create(**payload)
        if self.delegate is None:
            from mock_responses import MockClient
            parsed = IntegratedUnderstanding.model_validate(self.parsed)
            query = validate_query(parsed)
            self.delegate = MockClient(query.kind, query=query)
        # Parent's delegate branch reuses the original real-tool loop fixtures.
        return super().create(**payload)


def fixture(company="CVS", year=2025, quarter=2, intent="search", **changes):
    return dict(company=company, metric=METRIC, period={"year": year, "quarter": quarter},
        comparison_period={"year": year - 1, "quarter": quarter} if intent == "compare" else None,
        intent=intent, needs_clarification=False, clarification_question=None,
        request_scope="single_company", candidate_companies=[company], **changes)


DEMO_QUESTIONS = (
    "CVS 在 2025 年第二季度的合并总营收是多少？", "那去年同期呢？",
    "那比去年增长了多少？", "我指 2025 Q2 比 2024 Q2",
)


def offline_client(question):
    """Exact example lookup, deliberately NOT the rule-based parser or a pretend LLM."""
    examples = dict(zip(DEMO_QUESTIONS, (
        fixture(), fixture(year=2024),
        {**fixture(), "period": None, "intent": "compare", "request_scope": "ambiguous",
         "needs_clarification": True, "clarification_question": "你指 2025 Q2 比 2024 Q2，还是 2024 Q2 比 2023 Q2？"},
        fixture(intent="compare"))))
    examples.update({
        "CVS 2025 Q2 的合并总营收是多少？": fixture(),
        "Amazon 2025 Q2 的合并总营收是多少？": fixture(company="AMZN"),
        "CVS 2023 Q2 的合并总营收是多少？": fixture(year=2023),
        "CVS 和 UNH 2025 Q2 的合并总营收是多少？": {**fixture(), "company": None,
            "intent": "unsupported", "request_scope": "multiple_companies", "candidate_companies": ["CVS", "UNH"]},
        "先查 CVS": fixture(),
    })
    if question not in examples:
        raise ValueError("离线仅支持已列出的固定示例；任意自然语言需要明确开启 Live。")
    return IntegratedFakeClient(examples[question])


ENGLISH_DEMO_QUESTIONS = (
    "What was CVS's consolidated revenue in Q2 2025?",
    "What about the same quarter last year?",
    "How much did it increase year over year?",
    "I mean Q2 2025 compared with Q2 2024.",
)
ENGLISH_CLARIFICATION = (
    "Do you mean Q2 2025 versus Q2 2024, or Q2 2024 versus Q2 2023?"
)


def english_demo_fixtures():
    """Scripted interpretations only. Amounts still come from the real local tools."""
    return (
        fixture(), fixture(year=2024),
        {**fixture(), 'period': None, 'intent': 'compare', 'request_scope': 'ambiguous',
         'needs_clarification': True, 'clarification_question': ENGLISH_CLARIFICATION},
        fixture(intent='compare'),
    )


def english_demo_answer(result):
    """Display already-validated task results without changing State, evidence or grading."""
    if result.category == 'persistence_error':
        return 'Local snapshot or memory storage failed. The session has stopped; no retry was attempted.'
    if result.outcome == 'failed':
        stages = {
            'initialization': 'Task initialization failed',
            'budget_check': 'The request or token budget could not accommodate another step',
            'api_request': 'The response request failed or was blocked by the shared budget',
            'response_validation': 'Response or usage validation failed',
            'final_validation': 'Structured output or financial answer validation failed',
            'tool_validation': 'Tool call validation failed',
            'tool_execution': 'Tool execution or evidence validation failed',
            'state_update': 'Task state update failed',
        }
        message = stages.get(result.state.failure_stage, 'The task failed')
        return f'{message}. The session has stopped; no retry was attempted. Sensitive error details are omitted.'
    if result.category == 'ambiguity':
        # This fixed demo's third interpretation uses this exact English clarification.
        return ENGLISH_CLARIFICATION
    if result.category == 'insufficient_evidence':
        return 'Insufficient evidence: the available reports do not support an answer.'
    if result.category == 'unsupported_capability':
        return ('Unsupported capability: this demo supports consolidated revenue for one company '
                'and year-over-year changes in revenue amounts, not multi-company analysis or percentages.')
    if result.category != 'answer' or result.state.status != 'completed' or result.query is None:
        raise ValueError('No validated financial result is available for display.')
    evidence, query = result.state.evidence, result.query
    if query.kind == 'search':
        amount = evidence[query.revenue_key]
        answer = f'{query.company} Q{query.quarter} {query.year} consolidated revenue: ${amount} billion.'
    else:
        amount = Decimal(result.state.calculation)
        direction = 'increase' if amount >= 0 else 'decrease'
        answer = (f'Year-over-year {direction}: approximately ${abs(amount):f} billion '
                  f'(Q{query.quarter} {query.year} versus Q{query.quarter} {query.year - 1}).\n'
                  'Calculated from the rounded figures in the earnings presentation.')
    return (f"{answer}\n[{evidence['citation']}] {evidence['source_title']}, PDF page {evidence['page']}\n"
            f"{evidence['source_url']}")


def run_english_demo():
    """Offline presentation adapter; the underlying Agent and its safety checks are unchanged."""
    print('OFFLINE DEMO: scripted Fake Responses with real local report retrieval and Decimal arithmetic.')
    print('No live GPT requests, API key access, or API charges. Financial amounts are shown in USD billions.')
    print('Limits: 4 requests per task; 32 requests and 30,000 tokens per session; 1,024 output tokens per request.')
    print('Sanitized snapshots and verified research topics are saved locally; full conversations are not saved.')
    app = None
    try:
        app = FinancialAgent()
        for question, parsed in zip(ENGLISH_DEMO_QUESTIONS, english_demo_fixtures()):
            print(f'\nUser: {question}')
            result = app.ask(question, fake_client=IntegratedFakeClient(parsed))
            print(f'Assistant [{result.category}]: {english_demo_answer(result)}')
            print(json.dumps({'task_id': result.state.task_id, 'requests': result.state.api_request_count,
                'tool_calls': result.state.tool_call_count, 'simulated_tokens': result.state.total_tokens}))
            if app.stopped:
                return 1
        return 0
    except Exception:
        # Never echo arbitrary exception text, which may contain Chinese or credentials.
        print('The offline demo could not complete. Execution has stopped; no retry was attempted. '
              'Sensitive error details are omitted.')
        return 1
    finally:
        if app is not None:
            summary = app.summary()
            summary['cost'] = {'usd': None, 'note': 'Simulated token usage is not a real API cost.'}
            print('Session summary: ' + json.dumps(summary))


class FinancialAgent:
    """One bounded process/session. No automatic retries, recovery, or previous evidence reuse."""
    def __init__(self, *, live_client=None, directory=STORAGE, caps=None, persist=True):
        self.session = Session()
        self.live_client = live_client
        self.directory, self.persist = Path(directory), persist
        selected = dict(CAPS if caps is None else caps)
        if set(selected) != set(CAPS) or any(type(v) is not int or not 1 <= v <= CAPS[k] for k,v in selected.items()):
            raise ValueError("预算只能在默认上限以内设置正整数。")
        self.budget = BudgetedClient(selected, understanding_model=IntegratedUnderstanding)
        self.stopped = False

    def ask(self, question, *, fake_client=None, context_observer=None):
        if self.stopped or self.budget.stopped:
            raise StopAgent("本 Session 已停止；不会自动重试。")
        if self.live_client is not None and fake_client is not None:
            raise StopAgent("Live 不能混入 Fake Responses。")
        self.budget.delegate = self.live_client if self.live_client is not None else (
            fake_client if fake_client is not None else offline_client(question))
        # Old teaching printouts include raw arguments. Do not persist or echo them here.
        with redirect_stdout(io.StringIO()):
            result = integrated_turn(self.session, question, self.budget,
                limits=Limits(requests=self.budget.caps['requests_per_task'],
                    output_tokens=self.budget.caps['output_tokens_per_request']),
                memory_directory=self.directory / 'memory', context_observer=context_observer,
                storage_directory=self.directory if self.persist else None)
        self.stopped = result.outcome == 'failed' or self.budget.stopped
        return result

    def summary(self):
        return dict(model=MODEL, requests=len(self.budget.events), input_tokens=self.budget.input_tokens,
            output_tokens=self.budget.output_tokens, total_tokens=self.budget.total_tokens,
            usage_kind='actual' if self.live_client is not None else 'simulated',
            cost=cost_estimate(self.budget.events, self.live_client is not None))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    demos = parser.add_mutually_exclusive_group()
    demos.add_argument('--demo', action='store_true', help='Run the four fixed teaching questions')
    demos.add_argument('--demo-en', action='store_true', help='Run the four English offline presentation questions')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--confirm-paid-api', action='store_true')
    args = parser.parse_args(argv)
    if args.demo_en:
        if args.live or args.confirm_paid_api:
            print('--demo-en is offline only. Remove --live and --confirm-paid-api; no API key was read or request sent.')
            return 1
        return run_english_demo()
    if args.live and not args.confirm_paid_api:
        print('Live 需要 --confirm-paid-api；未读取密钥或发送请求。')
        return 1
    for name in ('openai', 'httpx', 'httpx2', 'httpcore'):
        logging.getLogger(name).disabled = True

    def chat(client=None):
        app = FinancialAgent(live_client=client)
        print('LIVE：真实 API，费用与预算跨所有轮次累计。' if client is not None else
              'OFFLINE：固定 Fake Responses + 真实本地工具。模拟 Usage，无费用；不是自然语言模型。')
        print('每题最多 4 次请求；本进程最多 32 次、30000 Tokens；单次最多 1024 Output Tokens。')
        print('自动保存脱敏 Snapshot 与已核实主题 Memory；不保存完整对话。exit 退出。')
        if client is None:
            print('固定示例：' + ' / '.join(DEMO_QUESTIONS))
        questions = iter(DEMO_QUESTIONS) if args.demo else None
        while True:
            try:
                question = next(questions) if questions is not None else input('\n问题：')
            except (StopIteration, EOFError, KeyboardInterrupt):
                break
            if question.strip().lower() == 'exit':
                break
            try:
                result = app.ask(question)
            except ValueError as error:  # Only controlled fixture-selection errors.
                print(error)
                continue
            print(f'[{result.category}] {result.answer}')
            print(json.dumps({'task_id':result.state.task_id,'requests':result.state.api_request_count,
                'tools':result.state.tool_call_count,'tokens':result.state.total_tokens},ensure_ascii=False))
            if app.stopped:
                break
        print(json.dumps(app.summary(), ensure_ascii=False))
        return 1 if app.stopped else 0

    if not args.live:
        return chat()
    try:
        from openai import OpenAI
        with OpenAI(api_key=os.environ['OPENAI_API_KEY'], base_url='https://api.openai.com/v1',
                    max_retries=0, timeout=30.0) as client:
            return chat(client)
    except Exception:
        print('Live 配置或运行失败，已停止；敏感异常详情隐藏，未返回 Usage 的费用未知。')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
