#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cross-platform E2E runner for three-branch flow")
    parser.add_argument("--offline", action="store_true", help="Run deterministically without network fetches")
    parser.add_argument("--now-iso", default=None, help="Fixed ISO timestamp for deterministic fixture generation")
    parser.add_argument("--keep-run", action="store_true", help="Keep run directory after success")
    return parser.parse_args()


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_pattern_key(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return " ".join(normalized.split())


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(row, separators=(",", ":")) for row in rows)
    path.write_text((content + "\n") if content else "", encoding="utf-8")


def run_cli(data_dir: Path, args: list[str], env_extra: dict[str, str] | None = None) -> dict:
    cmd = [sys.executable, "-m", "orchestrator.cli", "--data-dir", str(data_dir), *args]
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        print(f"[E2E] FAIL command: {' '.join(cmd)}")
        print("[E2E] stderr:")
        print(proc.stderr.strip() or "<empty>")
        print("[E2E] stdout:")
        print(proc.stdout.strip() or "<empty>")
        raise SystemExit(1)

    merged = [line.strip() for line in (proc.stdout + "\n" + proc.stderr).splitlines() if line.strip()]
    for line in reversed(merged):
        if line.startswith("{") or line.startswith("["):
            return json.loads(line)
    print(f"[E2E] FAIL no JSON output for command: {' '.join(cmd)}")
    print(proc.stdout)
    print(proc.stderr)
    raise SystemExit(1)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def prepare_vault(vault_dir: Path) -> None:
    for rel in [
        "00_Index",
        "95_Signals",
        "96_Weekly_Review",
        "96_Weekly_Review/_LTI_Drafts",
        "97_Gate_Decisions",
        "97_Decisions/_RTI_Proposals",
        "06_Archive/COS",
        "01_RTI",
        "02_LTI",
        "RTI",
    ]:
        (vault_dir / rel).mkdir(parents=True, exist_ok=True)


def seed_offline_signals(data_dir: Path, vault_dir: Path, now_iso: str) -> None:
    rows: list[dict] = []
    for i in range(1, 6):
        date_part = now_iso.split("T", 1)[0].replace("-", "")
        sig_id = f"SIG-{date_part}-{i:03d}"
        row = {
            "id": sig_id,
            "source": "offline_fixture",
            "type": "ecosystem",
            "title": f"Offline Signal {i}",
            "content": f"Deterministic offline signal content {i}.",
            "url": f"https://offline.test/signal/{i}",
            "priority_score": round(1.0 - (i * 0.1), 3),
            "impact_area": ["auth"],
            "timestamp": now_iso,
            "gate_status": None,
            "gate_decision_id": None,
            "deepening_task_id": None,
            "deepened": False,
            "deepened_at": None,
        }
        rows.append(row)

        sig_note = vault_dir / "95_Signals" / f"{sig_id}.md"
        sig_note.write_text(
            "\n".join(
                [
                    "---",
                    f"id: {sig_id}",
                    "source: offline_fixture",
                    "type: ecosystem",
                    f"title: Offline Signal {i}",
                    f"url: https://offline.test/signal/{i}",
                    f"timestamp: {now_iso}",
                    "priority_score: 0.9",
                    "---",
                    "",
                    f"# Offline Signal {i}",
                    "",
                    f"Deterministic offline signal content {i}.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    write_jsonl(data_dir / "signals.jsonl", rows)


def append_offline_deepening(data_dir: Path, vault_dir: Path, signal_id: str, now_iso: str) -> None:
    signals_path = data_dir / "signals.jsonl"
    signals = read_jsonl(signals_path)
    for row in signals:
        if row.get("id") == signal_id:
            row["deepened"] = True
            row["deepened_at"] = now_iso
            row["evidence_source_url"] = "offline://fixture"
            row["evidence_hash"] = "offline-evidence-hash"
    write_jsonl(signals_path, signals)

    tasks_path = data_dir / "weekly_tasks.jsonl"
    tasks = read_jsonl(tasks_path)
    task_id = f"ACT-DEEPEN-{signal_id}"
    found = False
    for task in tasks:
        if task.get("id") == task_id:
            task["status"] = "completed"
            task["completed_at"] = now_iso
            found = True
    if not found:
        tasks.append(
            {
                "id": task_id,
                "type": "deepening",
                "signal_id": signal_id,
                "status": "completed",
                "created_at": now_iso,
                "completed_at": now_iso,
            }
        )
    write_jsonl(tasks_path, tasks)

    sig_path = vault_dir / "95_Signals" / f"{signal_id}.md"
    base = sig_path.read_text(encoding="utf-8").rstrip() + "\n\n"
    if "## Deepened Evidence (L3)" not in base:
        base += "## Deepened Evidence (L3)\n\n"
        base += "fetch_status: ok\n"
        base += "source_url: offline://fixture\n"
        base += "excerpt:\n"
        base += "Deterministic offline evidence excerpt.\n"
    sig_path.write_text(base + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    env_offline = os.getenv("E2E_OFFLINE", "0") == "1"
    offline = args.offline or env_offline
    now_iso = args.now_iso or ("2025-01-15T12:00:00Z" if offline else iso_utc_now())

    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = repo_root / ".e2e_runs" / f"run-{run_stamp}"
    data_dir = run_dir / "test_data"
    vault_dir = run_dir / "test_vault"

    print("[E2E] Step 0: prepare isolated directories")
    run_dir.mkdir(parents=True, exist_ok=False)
    data_dir.mkdir(parents=True, exist_ok=True)
    prepare_vault(vault_dir)

    common_env = {"PM_OS_VAULT_ROOT": str(vault_dir)}

    try:
        print("[E2E] Step 1: ingest")
        if offline:
            seed_offline_signals(data_dir, vault_dir, now_iso)
        else:
            source_yaml = run_dir / "sources.yaml"
            source_yaml.write_text(
                "\n".join(
                    [
                        "- id: openai_news",
                        '  name: "OpenAI News"',
                        "  type: rss",
                        '  url: "https://openai.com/news/rss.xml"',
                        "  priority_weight: 1.0",
                        "  signal_type: ecosystem",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            run_cli(
                data_dir,
                [
                    "ingest",
                    "--sources",
                    str(source_yaml),
                    "--since-days",
                    "3650",
                    "--limit-per-source",
                    "5",
                    "--threshold",
                    "0",
                    "--vault-root",
                    str(vault_dir),
                    "--writeback-signals",
                    "--out",
                    str(data_dir / "signals.jsonl"),
                ],
                common_env,
            )

        sig_files = sorted((vault_dir / "95_Signals").glob("SIG-*.md"))
        assert_true(len(sig_files) == 5, "expected exactly 5 SIG markdown files")

        print("[E2E] Step 2: weekly shortlist")
        run_cli(data_dir, ["weekly", "--vault-root", str(vault_dir), "--limit", "3"], common_env)
        weekly_files = list((vault_dir / "96_Weekly_Review").glob("Weekly-Intel-*.md"))
        assert_true(len(weekly_files) >= 1, "expected at least one Weekly-Intel file")

        print("[E2E] Step 3: gate decisions (deferred / approved / reject)")
        signals = read_jsonl(data_dir / "signals.jsonl")
        signals.sort(key=lambda s: float(s.get("priority_score") or 0), reverse=True)
        assert_true(len(signals) >= 3, "need at least 3 signals")
        top_signal_id = signals[0]["id"]
        approve_signal_id = signals[1]["id"]
        reject_signal_id = signals[2]["id"]

        run_cli(
            data_dir,
            [
                "gate",
                "decide",
                "--signal-id",
                top_signal_id,
                "--decision",
                "deferred",
                "--priority",
                "Medium",
                "--reason",
                "E2E deferred test",
            ],
            common_env,
        )

        branch_b = run_cli(
            data_dir,
            [
                "gate",
                "decide",
                "--signal-id",
                approve_signal_id,
                "--decision",
                "approved",
                "--priority",
                "High",
                "--reason",
                "E2E approved test",
            ],
            common_env,
        )

        run_cli(
            data_dir,
            [
                "gate",
                "decide",
                "--signal-id",
                reject_signal_id,
                "--decision",
                "reject",
                "--priority",
                "Low",
                "--reason",
                "E2E reject pattern: auth boundary",
            ],
            common_env,
        )

        print("[E2E] Step 4: deepening")
        expected_task_id = f"ACT-DEEPEN-{approve_signal_id}"
        if offline:
            append_offline_deepening(data_dir, vault_dir, approve_signal_id, now_iso)
        else:
            run_cli(
                data_dir,
                ["deepen", "run", "--signal-id", approve_signal_id, "--vault-root", str(vault_dir), "--force"],
                common_env,
            )

        task_rows = read_jsonl(data_dir / "weekly_tasks.jsonl")
        deep_task = next((t for t in task_rows if t.get("id") == expected_task_id), None)
        assert_true(deep_task is not None, "deepening task should exist")
        assert_true(str(deep_task.get("status")) == "completed", "deepening task should be completed")

        sig_text = (vault_dir / "95_Signals" / f"{approve_signal_id}.md").read_text(encoding="utf-8")
        assert_true("## Deepened Evidence (L3)" in sig_text, "deepened evidence heading missing")

        print("[E2E] Step 5: L5 route and publish LTI")
        decision_id = branch_b["decision_id"]
        run_cli(data_dir, ["route-after-gate", "--decision-id", decision_id, "--vault-dir", str(vault_dir)], common_env)

        lti_drafts_path = data_dir / "test_data" / "lti_drafts.jsonl"
        lti_rows = read_jsonl(lti_drafts_path)
        assert_true(len(lti_rows) == 1, "expected exactly one LTI draft")
        draft = lti_rows[0]
        draft_md = vault_dir / Path(draft["vault_path"])
        assert_true(draft_md.exists(), "LTI draft markdown should exist")

        run_cli(
            data_dir,
            ["publish-lti", "--id", draft["id"], "--reviewer", "E2E", "--notes", "E2E publish", "--vault-dir", str(vault_dir)],
            common_env,
        )
        lti_rows_after = read_jsonl(lti_drafts_path)
        draft_after = next((row for row in lti_rows_after if row.get("id") == draft["id"]), None)
        assert_true(draft_after is not None and draft_after.get("status") == "published", "LTI draft should be published")
        final_lti = vault_dir / Path(draft_after["final_vault_path"])
        assert_true(final_lti.exists(), "published LTI markdown should exist")

        print("[E2E] Step 6: Rule of Three -> RTI proposal")
        reject_reason = "E2E reject pattern: auth boundary"
        for _ in range(2):
            run_cli(
                data_dir,
                [
                    "gate",
                    "decide",
                    "--signal-id",
                    reject_signal_id,
                    "--decision",
                    "reject",
                    "--priority",
                    "Low",
                    "--reason",
                    reject_reason,
                ],
                common_env,
            )

        cos_index_path = data_dir / "cos_index.json"
        cos_index = json.loads(cos_index_path.read_text(encoding="utf-8"))
        pattern_id = normalize_pattern_key(reject_reason) + "|auth"
        same_pattern = [row for row in cos_index if row.get("pattern_key") == pattern_id]
        assert_true(len(same_pattern) >= 3, "expected >= 3 COS entries with same pattern_id")

        run_cli(data_dir, ["rule-of-three", "--pattern-id", pattern_id, "--vault-dir", str(vault_dir)], common_env)

        rti_jsonl = data_dir / "test_data" / "rti_proposals.jsonl"
        rti_rows = read_jsonl(rti_jsonl)
        proposal = next((row for row in rti_rows if row.get("pattern_id") == pattern_id), None)
        assert_true(proposal is not None, "RTI proposal record should exist")
        proposal_path = vault_dir / Path(proposal["vault_path"])
        assert_true(proposal_path.exists(), "RTI proposal markdown should exist")

        print(f"E2E PASS {run_dir}")
        return 0
    except Exception as exc:
        print(f"[E2E] FAIL: {exc}")
        return 1
    finally:
        if not args.keep_run and os.getenv("PM_OS_E2E_SKIP_CLEANUP") != "1":
            shutil.rmtree(run_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
