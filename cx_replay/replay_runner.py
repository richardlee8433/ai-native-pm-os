from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from pm_os_contracts.models import AVL_EVIDENCE_PACK

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def run_fixture(*, fixture_id: str, root: Path) -> dict[str, Any]:
    fixture = _load_fixture(fixture_id)
    now = dt.datetime.now(tz=dt.timezone.utc).replace(microsecond=0)
    now_iso = now.isoformat().replace("+00:00", "Z")

    pack_id = _next_avl_id(root, now.date())
    file_name = _next_cx_filename(root, now.date())

    outcome = fixture.get("outcome", "partial")
    recommendation = fixture.get("recommendation") or _recommendation_from_outcome(outcome)

    evidence_pack = {
        "id": pack_id,
        "title": fixture.get("title", fixture_id),
        "created_at": now_iso,
        "updated_at": now_iso,
        "hypothesis": fixture.get("hypothesis", ""),
        "context": fixture.get("context", ""),
        "method": "replay",
        "outcome": outcome,
        "cost_paid": fixture.get("cost_paid", ""),
        "failure_modes": fixture.get("failure_modes", ["unknown"]),
        "delta": fixture.get("delta", ""),
        "recommendation": recommendation,
        "governance_impact": fixture.get("governance_impact", "none"),
        "validator": "cx_replay_stub",
        "fixture_id": fixture_id,
    }

    AVL_EVIDENCE_PACK.model_validate(evidence_pack)

    output_dir = root / "avl" / "evidence_packs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / file_name
    output_path.write_text(_render_markdown(evidence_pack), encoding="utf-8")

    return {"path": str(output_path), "evidence_pack": evidence_pack}


def _load_fixture(fixture_id: str) -> dict[str, Any]:
    fixture_path = FIXTURES_DIR / f"{fixture_id}.json"
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_id}")
    return json.loads(fixture_path.read_text(encoding="utf-8-sig"))


def _recommendation_from_outcome(outcome: str) -> str:
    outcome_lower = outcome.strip().lower()
    if outcome_lower in {"pass", "strong_partial"}:
        return "promote"
    if outcome_lower == "partial":
        return "revise"
    return "archive"


def _next_avl_id(root: Path, day: dt.date) -> str:
    date_key = day.strftime("%Y%m%d")
    prefix = f"AVL-EP-{date_key}-"
    existing = []
    index_path = root / "avl" / "evidence_packs" / "index.json"
    if index_path.exists():
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        existing = [item["id"] for item in payload.get("items", []) if item["id"].startswith(prefix)]
    return f"{prefix}{len(existing) + 1:03d}"


def _next_cx_filename(root: Path, day: dt.date) -> str:
    date_key = day.strftime("%Y")
    prefix = f"VAL-CX-{date_key}-"
    output_dir = root / "avl" / "evidence_packs"
    existing = [path.stem for path in output_dir.glob(f"{prefix}*.md")]
    return f"{prefix}{len(existing) + 1:03d}.md"


def _render_markdown(pack: dict[str, Any]) -> str:
    lines = [
        "---",
        f"id: {pack['id']}",
        f"title: {pack['title']}",
        f"created_at: {pack['created_at']}",
        f"updated_at: {pack['updated_at']}",
        f"hypothesis: {pack['hypothesis']}",
        f"context: {pack['context']}",
        f"method: {pack['method']}",
        f"outcome: {pack['outcome']}",
        f"cost_paid: {pack['cost_paid']}",
        "failure_modes:",
    ]
    for failure in pack["failure_modes"]:
        lines.append(f"  - {failure}")
    lines.extend(
        [
            f"delta: {pack['delta']}",
            f"recommendation: {pack['recommendation']}",
            f"governance_impact: {pack['governance_impact']}",
            f"validator: {pack['validator']}",
            f"fixture_id: {pack['fixture_id']}",
            "---",
            "",
            "# AVL Evidence Pack",
            "",
            "## Hypothesis",
            pack["hypothesis"],
            "",
            "## Context",
            pack["context"],
            "",
            "## Method",
            pack["method"],
            "",
            "## Outcome",
            pack["outcome"],
            "",
            "## Cost Paid",
            pack["cost_paid"],
            "",
            "## Failure Modes",
            "\n".join(f"- {failure}" for failure in pack["failure_modes"]),
            "",
            "## Delta",
            pack["delta"],
            "",
            "## Recommendation",
            pack["recommendation"],
            "",
            "## Governance Impact",
            pack["governance_impact"],
            "",
        ]
    )
    return "\n".join(lines)
