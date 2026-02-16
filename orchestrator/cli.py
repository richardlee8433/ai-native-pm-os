from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from ingest.normalize import MIN_PRIORITY_THRESHOLD, normalize_item_to_signal
from ingest.registry import get_fetcher, load_sources
from ingest.store import append_signals_with_results
from ingest.validation import validate_signal_contract
from orchestrator.vault_ops import resolve_vault_root, write_signal_markdown
from orchestrator.workflow import Orchestrator


def _parse_iso_datetime(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


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

    add_signal = subparsers.add_parser("add_signal", help="Manual Layer-1 signal insertion")
    add_signal.add_argument("--source", required=True)
    add_signal.add_argument("--title", required=True)
    add_signal.add_argument("--url", required=True)
    add_signal.add_argument("--type", required=True, choices=["capability", "research", "governance", "market", "ecosystem"])
    add_signal.add_argument("--content")
    add_signal.add_argument("--priority-score", type=float)

    ingest = subparsers.add_parser("ingest", help="Run Layer 1 intake from source registry")
    ingest.add_argument("--sources", default="ingest/sources.yaml")
    ingest.add_argument("--since-days", type=int, default=7)
    ingest.add_argument("--limit-per-source", type=int, default=5)
    ingest.add_argument("--out", default="orchestrator/data/signals.jsonl")
    ingest.add_argument("--threshold", type=float, default=MIN_PRIORITY_THRESHOLD)
    ingest.add_argument("--vault-root")
    ingest.add_argument(
        "--writeback-signals",
        action="store_true",
        help="Write newly ingested signals as Obsidian notes under 98_Signals",
    )

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


def _run_ingest(args: argparse.Namespace) -> int:
    now_utc = dt.datetime.now(tz=dt.timezone.utc)
    since_cutoff = now_utc - dt.timedelta(days=args.since_days)
    source_cfgs = load_sources(args.sources)

    signals = []
    failures: list[dict[str, str]] = []
    filtered_low_priority = 0
    sequence = 1

    for source_cfg in source_cfgs:
        try:
            fetcher = get_fetcher(source_cfg.type)
            items = fetcher.fetch(source_cfg, limit=args.limit_per_source)
        except Exception as exc:  # noqa: BLE001
            failures.append({"source": source_cfg.id, "error": str(exc)})
            continue

        for item in items:
            published_at = item.get("published_at")
            if published_at and published_at < since_cutoff:
                continue

            signal = normalize_item_to_signal(source_cfg, item, seq_num=sequence, now_utc=now_utc)
            sequence += 1

            if signal.priority_score is not None and signal.priority_score < args.threshold:
                filtered_low_priority += 1
                continue

            try:
                validate_signal_contract(signal)
            except Exception as exc:  # noqa: BLE001
                failures.append({"source": source_cfg.id, "error": f"validation: {exc}"})
                continue
            signals.append(signal)

    written_signals, skipped_dupes = append_signals_with_results(args.out, signals)
    written = len(written_signals)

    vault_paths: list[str] = []
    if args.writeback_signals:
        vault_root = resolve_vault_root(args.vault_root)
        for signal in written_signals:
            vault_paths.append(str(write_signal_markdown(vault_root, signal)))

    report = {
        "new_count": written,
        "skipped_duplicates": skipped_dupes,
        "filtered_low_priority": filtered_low_priority,
        "failed_count": len(failures),
        "out": str(Path(args.out)),
        "failures": failures,
        "vault_written": len(vault_paths),
        "vault_paths": vault_paths[:10],
    }
    print(json.dumps(report))

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    orchestrator = Orchestrator(data_dir=Path(args.data_dir))

    if args.command == "add_signal":
        signal = orchestrator.add_signal(
            source=args.source,
            signal_type=args.type,
            title=args.title,
            content=args.content,
            url=args.url,
            priority_score=args.priority_score,
            impact_area=None,
            timestamp=dt.datetime.now(tz=dt.timezone.utc),
        )
        print(signal.to_json())
        return 0

    if args.command == "ingest":
        return _run_ingest(args)

    if args.command == "signal" and args.signal_command == "add":
        timestamp = _parse_iso_datetime(args.timestamp) if args.timestamp else None
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
        payload = orchestrator.apply_writeback(action_id=args.action_id)
        print(json.dumps(payload))
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
