"""Two-process persistence lesson. Save uses Fake Responses only; read never runs tools."""

import argparse
from pathlib import Path

from state_snapshot import SnapshotError, load_state_snapshot, save_state_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    save = commands.add_parser("save", help="Run an offline task and save its summary")
    save.add_argument("--scenario", choices=("compare", "search", "calculate", "insufficient"), default="compare")
    read = commands.add_parser("read", help="Read a summary without executing the agent")
    read.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "save":
            from api_demo import AgentState, StopAgent, run_agent
            from mock_responses import MockClient

            print("OFFLINE：Fake Responses，真实本地工具；Usage 为模拟值。")
            state = AgentState()
            try:
                run_agent(MockClient(args.scenario), args.scenario, state=state)
            except StopAgent:
                print(f"任务停止，失败阶段：{state.failure_stage}")
            path = save_state_snapshot(state)
            print(f"Snapshot 已保存：{path}")
            print("进程即将退出。请用 read 命令启动新进程读取。")
            return 1 if state.status == "failed" else 0
        snapshot = load_state_snapshot(args.path)
        print("只读取历史摘要；本进程没有执行 Agent、Tool Call 或 API 请求。")
        print(snapshot.model_dump_json(indent=2))
        return 0
    except SnapshotError as error:
        print(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
