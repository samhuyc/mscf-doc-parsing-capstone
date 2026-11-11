"""Run a fixed financial question through two real Python tools and a Mock Model."""

from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sys
from xml.etree import ElementTree

CHUNKING_DIR = Path(__file__).resolve().parent.parent / "2026-10-28_chunking"
INDEX_DIR = CHUNKING_DIR / "results" / "final"
REPO_ROOT = CHUNKING_DIR.parents[2]
sys.path.insert(0, str(CHUNKING_DIR))

from retrieval import Retriever, load_chunks


USER_QUESTION = "CVS 2025 Q2 的合并总营收相比 2024 Q2 增加了多少？"
SEARCH_QUESTION = "What were CVS total revenues in 2Q 2025 compared with 2Q 2024?"
DOCUMENT_ID = "cvs_2025q2"


def read_revenues(content: str) -> tuple[str, str] | None:
    """Read the two amounts only when the table identifies both periods and the unit."""
    for markup in re.findall(r"<table>.*?</table>", content, re.DOTALL):
        try:
            table = ElementTree.fromstring(markup)
        except ElementTree.ParseError:
            continue
        rows = table.findall("tr")
        if not rows:
            continue
        headings = [" ".join("".join(cell.itertext()).split()) for cell in rows[0].findall("th")]
        if len(headings) != 3 or not headings[0].endswith("In billions, except per share amounts"):
            continue
        periods = headings[1:]
        if set(periods) != {"2Q 2025", "2Q 2024"}:
            continue

        for row in rows[1:]:
            cells = [cell.text.strip() if cell.text else "" for cell in row.findall("td")]
            if len(cells) != 3 or cells[0] != "Total Revenues":
                continue
            if all(re.fullmatch(r"\$[0-9]+(?:\.[0-9]+)?", value) for value in cells[1:]):
                amounts = dict(zip(periods, cells[1:]))
                return amounts["2Q 2025"][1:], amounts["2Q 2024"][1:]
    return None


def search_report(question: str) -> dict | None:
    """Search the saved Capstone index for citable evidence for this demo."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question 必须是非空字符串。")

    retriever = Retriever(load_chunks(INDEX_DIR))
    for _, chunk in retriever.search(question, document_id=DOCUMENT_ID, top_k=3):
        if chunk["section_path"][-1:] != ["Consolidated Results"]:
            continue
        amounts = read_revenues(chunk["content"])
        pages = {span["page"] for span in chunk["source_spans"]}
        if amounts is None or len(pages) != 1:
            continue

        page = pages.pop()
        metadata_path = (REPO_ROOT / chunk["source_artifact"]).with_name("metadata.json")
        source = json.loads(metadata_path.read_text(encoding="utf-8"))["source"]
        if source["id"] != DOCUMENT_ID or not source["title"] or not source["url"]:
            continue
        return {
            "revenue_2025_q2": amounts[0],
            "revenue_2024_q2": amounts[1],
            "unit": "十亿美元",
            "citation": "S1",
            "document_id": chunk["document_id"],
            "chunk_id": chunk["chunk_id"],
            "page": page,
            "source_title": source["title"],
            "source_url": f"{source['url']}#page={page}",
        }
    return None


def calculate(a: str, b: str, operation: str) -> str:
    """Subtract two decimal strings, in the order a - b."""
    if operation != "subtract":
        raise ValueError("本 Demo 的 operation 只支持 subtract。")
    if not isinstance(a, str) or not isinstance(b, str):
        raise ValueError("a 和 b 必须是十进制数字字符串。")
    try:
        left, right = Decimal(a), Decimal(b)
    except InvalidOperation as error:
        raise ValueError("a 和 b 必须是有效数字。") from error
    if not left.is_finite() or not right.is_finite():
        raise ValueError("a 和 b 必须是有限数字。")
    return format(left - right, "f")


# Mock Model: prewritten decisions. The operands come from the search result.
def mock_search_call() -> dict:
    return {"name": "search_report", "arguments": {"question": SEARCH_QUESTION}}


def mock_calculation_call(evidence: dict) -> dict:
    return {
        "name": "calculate",
        "arguments": {
            "a": evidence["revenue_2025_q2"],
            "b": evidence["revenue_2024_q2"],
            "operation": "subtract",
        },
    }


def mock_final_answer(evidence: dict, difference: str) -> str:
    current = evidence["revenue_2025_q2"]
    previous = evidence["revenue_2024_q2"]
    unit = evidence["unit"]
    return (
        f"CVS 2025 Q2 合并总营收为 {current} {unit}，2024 Q2 为 {previous} {unit}。\n"
        f"按简报显示的数值计算，同比变动约 {Decimal(difference):+f} {unit}（{current} − {previous}）。\n"
        f"[{evidence['citation']}] {evidence['source_title']}，PDF 第 {evidence['page']} 页\n"
        f"{evidence['source_url']}"
    )


# Python Runtime: dispatch the request and return the result to the caller.
TOOLS = {"search_report": search_report, "calculate": calculate}


def run_tool(call: dict) -> dict | str | None:
    name = call["name"]
    arguments = call["arguments"]
    if name not in TOOLS:
        raise ValueError(f"未知工具 {name}。")
    print(f"\nTool Call {name}")
    print("参数", json.dumps(arguments, ensure_ascii=False))
    result = TOOLS[name](**arguments)
    print("返回", json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> int:
    print("用户问题", USER_QUESTION)
    try:
        evidence = run_tool(mock_search_call())
    except (OSError, KeyError, ValueError) as error:
        print(f"\n无法回答。读取财报证据失败（{error}）。")
        return 1
    if evidence is None:
        print("\n证据不足，无法回答。")
        return 1

    difference = run_tool(mock_calculation_call(evidence))
    print("\n最终回答")
    print(mock_final_answer(evidence, difference))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
