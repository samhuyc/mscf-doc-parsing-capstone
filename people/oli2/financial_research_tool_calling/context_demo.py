"""Inspect exactly selected inputs in a deterministic, offline CVS -> UNH -> Amazon tour."""

import json

from api_demo import MODEL
from session_demo import Session, run_turn


def show_context(plan):
    print("ContextPlan：", json.dumps({
        "decision": plan.decision,
        "estimated_input_tokens": plan.estimated_input_tokens,
        "selected_task_ids": plan.selected_task_ids,
        "omitted": plan.omitted,
        "message": plan.message,
    }, ensure_ascii=False))
    print("即将发送给 Fake Responses 的 input（与请求一致）：")
    print(json.dumps(plan.input_items, ensure_ascii=False, indent=2))


def main():
    print("确定性 Context Builder：Python 规则，不是 LLM 自然语言理解。")
    print(f"全部请求使用 Fake Responses（模型标签 {MODEL}），无真实 API、密钥读取或费用。")
    print("每次请求另带原有 INSTRUCTIONS、两个 Tool Definitions 和 FinancialResearchResult Schema。")
    session = Session()
    for question in (
        "CVS 2025 Q2 的合并总营收是多少？",
        "那比去年增长了多少？",
        "UNH 2025 Q2 的合并总营收是多少？",
        "我是说 UNH 2024 Q2 的合并总营收是多少？",
        "Amazon 2025 Q2 的合并总营收是多少？",
        "它和 UNH 哪家营收更高？",
        "那家公司比去年增长了多少？",
        "我是说 Amazon 2025 Q2 的合并总营收是多少？",
    ):
        print("\n用户：" + question)
        print("请求前 Session：", json.dumps({
            "company": session.company, "metric": session.metric,
            "year": session.year, "quarter": session.quarter,
            "pending_companies": session.pending_companies,
            "recent_questions": [turn.question for turn in session.recent_turns],
        }, ensure_ascii=False))
        run_turn(session, question, context_observer=show_context)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
