"""Handwritten contract-test responses, independent of the grader's golden labels.

These fixtures prove runner wiring only; never report their scores as GPT accuracy.
"""
from llm_session_demo import FakeUnderstandingClient


def lookup(company="CVS", year=2025, quarter=2, intent="search"):
    return dict(company=company, metric="consolidated_total_revenue", period=dict(year=year, quarter=quarter),
                comparison_period=dict(year=year-1, quarter=quarter) if intent == "compare" else None,
                intent=intent, needs_clarification=False, clarification_question=None)


def clarify():
    return dict(company=None, metric=None, period=None, comparison_period=None, intent=None,
                needs_clarification=True, clarification_question="请明确要查询的一家公司和比较期间。")


def client_for(case_id, turn):
    fixtures = {
        "L01": [lookup()], "L02": [lookup()], "L03": [lookup(), lookup(year=2024)],
        "L04": [clarify(), lookup(intent="compare")], "L05": [clarify()],
        "L06": [lookup(), lookup(company="AMZN")], "L07": [lookup(year=2023)], "L08": [lookup()],
    }
    return FakeUnderstandingClient(fixtures[case_id][turn])
