"""Offline API response fixtures. No client, credential or network access."""

from copy import deepcopy
import json
from types import SimpleNamespace

from openai.types.responses import Response


def response(output, number=1):
    return Response.model_validate({
        "id": f"resp_offline_{number}", "object": "response", "created_at": 0,
        "model": "gpt-6.1-sol", "status": "completed", "output": output,
        "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
        "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
                  "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                  "output_tokens_details": {"reasoning_tokens": 0}},
    })


def tool_response(name, arguments, number=1):
    return response([{
        "type": "function_call", "id": f"fc_{number}", "call_id": f"call_{number}",
        "name": name, "arguments": json.dumps(arguments), "status": "completed",
    }], number)


def final_response(kind, value, citation):
    unit = "无单位" if kind == "calculate" else "十亿美元"
    if kind == "insufficient":
        unit = None
    return response([{
        "type": "message", "id": "msg_offline", "role": "assistant", "status": "completed",
        "content": [{"type": "output_text", "annotations": [],
                     "text": json.dumps(dict(kind=kind, value=value, unit=unit, citation=citation))}],
    }])


class MockClient:
    def __init__(self, scenario="compare"):
        self.scenario = scenario
        self.requests = []
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **payload):
        self.requests.append(deepcopy(payload))
        results = [item for item in payload["input"] if item.get("type") == "function_call_output"]
        if not results:
            if self.scenario == "calculate":
                return tool_response("calculate", {"a": "0.3", "b": "0.2", "operation": "subtract"})
            year = "2023" if self.scenario == "insufficient" else "2025"
            return tool_response("search_report", {
                "question": f"What were CVS consolidated total revenues in 2Q {year} compared with 2Q 2024?"
            })
        last = json.loads(results[-1]["output"])
        if last is None:
            return final_response("insufficient", None, None)
        if self.scenario == "search":
            return final_response("search", last["revenue_2025_q2"], "S1")
        if isinstance(last, dict):
            return tool_response("calculate", {
                "a": last["revenue_2025_q2"], "b": last["revenue_2024_q2"], "operation": "subtract",
            }, 2)
        citation = None if self.scenario == "calculate" else "S1"
        return final_response(self.scenario, last, citation)
