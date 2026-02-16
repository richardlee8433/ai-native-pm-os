from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from orchestrator.workflow import Orchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PM-OS orchestrator CLI")
    parser.add_argument("--data-dir", default="orchestrator/data", help="Directory containing orchestrator JSONL files")

    subparsers = parser.add_subparsers(dest="command", required=True)

    signal_parser = subparsers.add_parser("signal")
    signal_sub = signal_parser.add_subparsers(dest="signal_command", required=True)

    signal_add = signal_sub.add_parser("add")
    signal_add.add_argument("--source", required=True)
    signal_add.add_argument("--type", required=True, choices=["capability", "research", "governance", "market", "ecosystem"])
    signal_add.add_argument("--title")
    signal_add.add_argument("--content")
    signal_add.add_argument("--url")
    signal_add.add_argument("--priority-score", type=float)
    signal_add.add_argument("--impact-area", action="append")
    signal_add.add_argument("--timestamp", help="ISO-8601 timestamp")

    signal_top = signal_sub.add_parser("top")
    signal_top.add_argument("--limit", type=int, default=3)

    action_parser = subparsers.add_parser("action")
    action_sub = action_parser.add_subparsers(dest="action_command", required=True)
    action_generate = action_sub.add_parser("generate")
    action_generate.add_argument("--goal")
    action_generate.add_argument("--type", default="strategic_design", choices=["tech_prototype", "strategic_design", "content_creation", "task_tracking"])
    action_generate.add_argument("--signal-id")

    writeback_parser = subparsers.add_parser("writeback")
    writeback_sub = writeback_parser.add_subparsers(dest="writeback_command", required=True)
    writeback_apply = writeback_sub.add_parser("apply")
    writeback_apply.add_argument("--action-id")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    orchestrator = Orchestrator(data_dir=Path(args.data_dir))

    if args.command == "signal" and args.signal_command == "add":
        timestamp = dt.datetime.fromisoformat(args.timestamp) if args.timestamp else None
        signal = orchestrator.add_signal(
            source=args.source,
            signal_type=args.type,
            title=args.title,
            content=args.content,
            url=args.url,
            priority_score=args.priority_score,
            impact_area=args.impact_area,
            timestamp=timestamp,
        )
        print(signal.to_json())
        return 0

    if args.command == "signal" and args.signal_command == "top":
        top = [s.to_dict() for s in orchestrator.top_signals(args.limit)]
        print(json.dumps(top))
        return 0

    if args.command == "action" and args.action_command == "generate":
        task = orchestrator.generate_action(goal=args.goal, action_type=args.type, signal_id=args.signal_id)
        print(task.to_json())
        return 0

    if args.command == "writeback" and args.writeback_command == "apply":
        lti_node = orchestrator.apply_writeback(action_id=args.action_id)
        print(lti_node.to_json())
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
