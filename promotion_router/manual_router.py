from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path
from typing import Any

from orchestrator.vault_ops import write_lti_markdown
from pm_os_contracts.models import LTI_NODE


def route_manual_promotion(
    *,
    evidence_pack_path: Path,
    vault_root: Path,
    source_graph_nodes: list[str] | None = None,
    use_v41_promotion: bool | None = None,
) -> dict[str, Any]:
    enabled = _resolve_flag(use_v41_promotion)
    if not enabled:
        return {"skipped": True, "reason": "use_v41_promotion disabled"}

    evidence = _read_frontmatter(evidence_pack_path)
    outcome = (evidence.get("outcome") or "").strip().lower()
    recommendation = (evidence.get("recommendation") or "").strip().lower()
    governance_impact = (evidence.get("governance_impact") or "").strip().lower()
    pack_id = evidence.get("id") or evidence_pack_path.stem

    created: dict[str, Any] = {"lti_created": None, "rti_review_created": None}

    if outcome in {"pass", "strong_partial"} and recommendation == "promote":
        lti_id = _next_lti_id(vault_root)
        now = dt.datetime.now(tz=dt.timezone.utc)
        lti_node = LTI_NODE(
            id=lti_id,
            title=evidence.get("title") or f"Provisional LTI {lti_id}",
            series="LTI-1.x",
            status="under_review",
            summary=evidence.get("delta") or "Provisional LTI from AVL evidence.",
            linked_evidence=[pack_id],
            validation_status="provisional",
            source_graph_nodes=source_graph_nodes or [],
            validation_evidence_packs=[pack_id],
        )
        path = write_lti_markdown(
            vault_root,
            lti_node,
            source_task_id="AVL-PROMOTION",
            updated_at=now.replace(microsecond=0).isoformat(),
            human_approved=False,
        )
        created["lti_created"] = str(path)

    if governance_impact in {"review", "triggers"}:
        review_path = _write_rti_review(
            vault_root=vault_root,
            evidence_pack_id=pack_id,
            governance_impact=governance_impact,
        )
        created["rti_review_created"] = str(review_path)

    return created


def _resolve_flag(value: bool | None) -> bool:
    if value is not None:
        return value
    env = os.getenv("PMOS_USE_V41_PROMOTION", "false").strip().lower()
    return env in {"1", "true", "yes", "on"}


def _read_frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
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


def _next_lti_id(vault_root: Path) -> str:
    candidates = []
    for root in [vault_root / "02_LTI", vault_root / "96_Weekly_Review" / "_LTI_Drafts"]:
        if not root.exists():
            continue
        for path in root.rglob("LTI-*.md"):
            match = re.match(r"LTI-(\d+)\.(\d+)", path.stem)
            if not match:
                continue
            major, minor = int(match.group(1)), int(match.group(2))
            candidates.append((major, minor))
    if not candidates:
        return "LTI-1.0"
    major, minor = max(candidates)
    return f"LTI-{major}.{minor + 1}"


def _write_rti_review(*, vault_root: Path, evidence_pack_id: str, governance_impact: str) -> Path:
    now = dt.datetime.now(tz=dt.timezone.utc).replace(microsecond=0)
    date_key = now.strftime("%Y%m%d")
    review_dir = vault_root / "97_Decisions" / "_RTI_Reviews"
    review_dir.mkdir(parents=True, exist_ok=True)
    existing = list(review_dir.glob(f"RTI-REVIEW-{date_key}-*.md"))
    review_id = f"RTI-REVIEW-{date_key}-{len(existing) + 1:03d}"
    target = review_dir / f"{review_id}.md"
    content = "\n".join(
        [
            "---",
            f"id: {review_id}",
            "type: rti_review",
            f"evidence_pack_id: {evidence_pack_id}",
            f"governance_impact: {governance_impact}",
            f"created_at: {now.isoformat()}Z".replace("+00:00Z", "Z"),
            "status: pending",
            "---",
            "",
            "# RTI Review Proposal",
            "",
            "## Evidence Pack",
            evidence_pack_id,
            "",
        ]
    )
    target.write_text(content, encoding="utf-8")
    return target
