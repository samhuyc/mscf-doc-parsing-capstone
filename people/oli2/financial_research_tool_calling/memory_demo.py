"""Cross-process memory lesson: explicit save, read-only search, and a new offline task."""

import argparse
from pathlib import Path

from long_term_memory import MEMORY_DIR, MemoryRecord, MemoryStoreError, save_memory, search_memory, utc_timestamp
from state_snapshot import SNAPSHOT_DIR, SnapshotError, save_state_snapshot

METRIC = "consolidated_total_revenue"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("save", "search", "ask"):
        command = commands.add_parser(name)
        command.add_argument("--directory", type=Path, default=MEMORY_DIR)
        if name == "save":
            command.add_argument("--snapshot-directory", type=Path, default=SNAPSHOT_DIR)
        else:
            command.add_argument("--company", help="Ticker; search defaults to CVS and UNH, ask to CVS")
    args = parser.parse_args()
    try:
        if args.command == "search":
            print("只查询本地 Memory；不导入 Agent、不执行工具、不读取 Snapshot、不调用 API。")
            for company in ([args.company.upper()] if args.company else ["CVS", "UNH"]):
                matches = search_memory(company, METRIC, 2025, 2, directory=args.directory)
                print(f"{company} / 合并总营收 / 2025 Q2：匹配 {len(matches)} 条")
                for match in matches:
                    print(match.model_dump_json(indent=2))
            return 0

        from session_demo import Session, run_turn

        print("OFFLINE：Fake Responses + 真实本地工具，Usage 为模拟值，无真实 API 费用。")
        if args.command == "save":
            result = run_turn(Session(), "CVS 2025 Q2 的合并总营收是多少？")
            if result.outcome != "completed" or result.state.evidence is None:
                print("没有本任务的已验证证据，未保存 Memory。")
                return 1
            verified_at = utc_timestamp()  # Immediately after this task's Evidence Validation.
            snapshot = save_state_snapshot(result.state, args.snapshot_directory)
            query, evidence = result.query, result.state.evidence
            record = MemoryRecord(
                schema_version="1", company=query.company, metric=query.metric,
                year=query.year, quarter=query.quarter,
                source={"url": evidence["source_url"], "page": evidence["page"]},
                last_verified_at=verified_at, snapshot_task_id=result.state.task_id,
            )
            path = save_memory(record, args.directory)
            print(f"Snapshot：{snapshot}\nMemory：{path}")
            print(record.model_dump_json(indent=2))
            print("保存结束，进程退出。请启动新进程运行 search。")
            return 0

        def show_memory(plan):
            print(f"ContextPlan：{plan.decision}；历史任务：{plan.memory_task_ids}；省略：{plan.omitted}")

        company = args.company.upper() if args.company else "CVS"
        result = run_turn(Session(), f"{company} 2025 Q2 的合并总营收是多少？",
                          memory_directory=args.directory, context_observer=show_memory)
        return 1 if result.outcome != "completed" else 0
    except (MemoryStoreError, SnapshotError) as error:
        print(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
