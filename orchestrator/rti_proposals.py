from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from orchestrator.vault_ops import RTI_PROPOSALS_DIR

DECISION_DIR_NAME = "97_Decisions"
DECISION_FILENAME_PATTERN = re.compile(r"^DEC-\d{4}-W\d{2}-\d{3}\.md$")
PROPOSAL_FILENAME_TEMPLATE = "RTI-PROP-{signal_id}-v{version}.md"


@dataclass(frozen=True)
class L4Decision:
    decision_type: str | None
    signal_id: str | None
    revision_of: str | None
    decision_id: str


def should_generate_rti(decision: L4Decision) -> bool:
    return (decision.decision_type or "").upper() == "ACCEPT"


def compute_next_version(signal_id: str, proposals_dir: Path) -> int:
    if not proposals_dir.exists():
        return 1

    escaped = re.escape(signal_id)
    pattern = re.compile(rf"^RTI-PROP-{escaped}-v(\d+)\.md$")
    versions: list[int] = []
    for entry in proposals_dir.iterdir():
        if not entry.is_file():
            continue
        match = pattern.match(entry.name)
        if not match:
            continue
        try:
            versions.append(int(match.group(1)))
        except ValueError:
            continue
    return (max(versions) + 1) if versions else 1


def write_rti_proposal(decision: L4Decision, signal_id: str, proposals_dir: Path) -> Path:
    proposals_dir.mkdir(parents=True, exist_ok=True)

    version = compute_next_version(signal_id, proposals_dir)
    target = proposals_dir / PROPOSAL_FILENAME_TEMPLATE.format(signal_id=signal_id, version=version)
    if target.exists():
        version = compute_next_version(signal_id, proposals_dir)
        target = proposals_dir / PROPOSAL_FILENAME_TEMPLATE.format(signal_id=signal_id, version=version)
        if target.exists():
            raise FileExistsError(f"RTI proposal already exists after retry: {target}")

    generated_at = datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    decision_version = decision.revision_of or decision.decision_id

    content = "\n".join(
        [
            "---",
            f"source_decision: {decision.decision_id}",
            f"decision_version: {decision_version}",
            f"signal_id: {signal_id}",
            f"generated_at: {generated_at}",
            "human_approved: false",
            "---",
            "",
            f"# RTI Proposal for {signal_id}",
            "",
            "## Summary",
            "Draft RTI proposal generated from L4 decision.",
            "",
        ]
    )

    _atomic_write(target, content)
    print(f"[RTI] Created proposal: {target}")
    return target


def on_new_l4_decision(decision_path: Path) -> str:
    decision = _parse_decision(decision_path)
    if not should_generate_rti(decision):
        return "no-op"

    if not decision.signal_id:
        message = f"[RTI] ERROR missing signal_id in decision {decision.decision_id}"
        print(message)
        return "error: missing signal_id"

    proposals_dir = _resolve_proposals_dir(decision_path)
    created = write_rti_proposal(decision, decision.signal_id, proposals_dir)
    return f"created: {created}"


def _resolve_proposals_dir(decision_path: Path) -> Path:
    decision_dir = decision_path.parent
    vault_root = decision_dir.parent
    return vault_root / RTI_PROPOSALS_DIR


def _parse_decision(decision_path: Path) -> L4Decision:
    decision_id = decision_path.stem
    lines = decision_path.read_text(encoding="utf-8").splitlines()
    frontmatter = _extract_frontmatter(lines)
    decision_type = frontmatter.get("decision_type")
    signal_id = frontmatter.get("signal_id")
    revision_of = frontmatter.get("revision_of")
    return L4Decision(
        decision_type=(decision_type or "").strip() or None,
        signal_id=(signal_id or "").strip() or None,
        revision_of=(revision_of or "").strip() or None,
        decision_id=decision_id,
    )


def _extract_frontmatter(lines: list[str]) -> dict[str, str]:
    if not lines or lines[0].strip() != "---":
        return {}
    data: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def _atomic_write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as tmp:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_name = tmp.name
    os.replace(tmp_name, target)
