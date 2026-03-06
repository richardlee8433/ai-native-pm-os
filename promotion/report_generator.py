from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from avl.ops import EvidencePackStore
from graph.ops import GraphStore
from validation_projects.ops import ValidationProjectStore


def generate_promotion_report(root: Path, *, vp_id: str) -> dict[str, Any]:
    vp_store = ValidationProjectStore(root)
    project = vp_store.get(vp_id)
    graph_ids = project.get("linked_graph_nodes") or []
    evidence_ids = project.get("linked_evidence_packs") or []

    graph = None
    if graph_ids:
        graph = GraphStore(root).get(graph_ids[0])

    evidence_items = [_load_evidence(root, pack_id) for pack_id in evidence_ids]

    promotion_id = _next_promotion_id(root)
    now_iso = dt.datetime.now(tz=dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    plan = project.get("validation_plan") or {}
    claim = plan.get("claim") or (graph or {}).get("core_claim") or (graph or {}).get("hypothesis_statement") or ""
    experiment = plan.get("experiment_design") or ""
    summary = {
        "claim": claim or "n/a",
        "experiment_design": experiment or "n/a",
        "evidence_packs": evidence_ids,
    }

    metrics_evaluated = _metrics_list(plan.get("metrics"))
    success_criteria = plan.get("success_criteria") or []
    metrics_defined = bool(metrics_evaluated)
    success_defined = bool(success_criteria)

    aggregated_outcome, aggregated_decision = _aggregate_evidence(evidence_items)
    evidence_outcome = aggregated_outcome
    validation_result = {
        "metrics_evaluated": metrics_evaluated,
        "evidence_outcome": evidence_outcome,
        "evidence_packs": evidence_ids,
        "aggregated_outcome": aggregated_outcome,
        "packs_evaluated": len(evidence_ids),
    }

    promotion_decision = _governed_decision(
        aggregated_decision,
        metrics_defined=metrics_defined,
        success_defined=success_defined,
    )
    confidence_level = _map_confidence(aggregated_outcome)

    payload = {
        "promotion_id": promotion_id,
        "vp_id": vp_id,
        "source_graph_nodes": graph_ids,
        "validation_summary": summary,
        "validation_result": validation_result,
        "confidence_level": confidence_level,
        "promotion_decision": promotion_decision,
        "timestamp": now_iso,
        "evidence_count": len(evidence_ids),
        "validation_plan_metrics_defined": metrics_defined,
        "validation_plan_success_defined": success_defined,
    }

    report_dir = root / "promotion_reports" / promotion_id
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "promotion.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (report_dir / "promotion_report.md").write_text(
        _render_report_md(payload, graph_id=graph_ids[0] if graph_ids else None, evidence_ids=evidence_ids),
        encoding="utf-8",
    )
    return {"promotion_id": promotion_id, "report_dir": str(report_dir), "payload": payload}


def _load_evidence(root: Path, pack_id: str) -> dict[str, str]:
    store = EvidencePackStore(root)
    item = store.find_by_id(pack_id)
    if not item:
        return {}
    path = root / item["path"]
    if not path.exists():
        return {}
    payload = store.read_frontmatter(path)
    payload["id"] = pack_id
    return payload


def _metrics_list(metrics: Any) -> list[str]:
    if not metrics:
        return []
    output: list[str] = []
    if isinstance(metrics, list):
        for metric in metrics:
            if isinstance(metric, dict):
                name = metric.get("name")
                if name:
                    output.append(name)
            elif isinstance(metric, str):
                output.append(metric)
    return output


def _aggregate_evidence(evidence_items: list[dict[str, str]]) -> tuple[str, str]:
    if not evidence_items:
        return "inconclusive", "needs_more_validation"
    decisions = [_classify_pack(item) for item in evidence_items]
    if any(decision == "reject" for decision in decisions):
        return "reject", "reject"
    if all(decision == "positive" for decision in decisions):
        return "provisional_lti", "provisional_lti"
    return "inconclusive", "needs_more_validation"


def _classify_pack(evidence: dict[str, str]) -> str:
    outcome = (evidence.get("outcome") or "").strip().lower()
    recommendation = (evidence.get("recommendation") or "").strip().lower()
    if outcome in {"pass", "strong_partial"} and recommendation == "promote":
        return "positive"
    if outcome in {"fail"} or recommendation in {"reject", "archive"}:
        return "reject"
    return "inconclusive"


def _governed_decision(aggregated_decision: str, *, metrics_defined: bool, success_defined: bool) -> str:
    if aggregated_decision == "reject":
        return "reject"
    if aggregated_decision == "provisional_lti" and metrics_defined and success_defined:
        return "provisional_lti"
    return "needs_more_validation"


def _map_confidence(outcome: str) -> str:
    if outcome == "provisional_lti":
        return "high"
    if outcome == "pass":
        return "high"
    if outcome == "strong_partial":
        return "medium"
    if outcome == "partial":
        return "low"
    return "low"


def _next_promotion_id(root: Path) -> str:
    base_dir = root / "promotion_reports"
    base_dir.mkdir(parents=True, exist_ok=True)
    year = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y")
    existing = [path.name for path in base_dir.glob("PR-????-???") if path.name.startswith(f"PR-{year}-")]
    return f"PR-{year}-{len(existing) + 1:03d}"


def _render_report_md(payload: dict[str, Any], *, graph_id: str | None, evidence_ids: list[str]) -> str:
    summary = payload.get("validation_summary") or {}
    result = payload.get("validation_result") or {}
    decision = payload.get("promotion_decision")
    decision_line = _decision_line(decision)

    lines = [
        "# Promotion Report",
        "",
        "## VP",
        payload.get("vp_id", "n/a"),
        "",
        "## Source Graph",
        graph_id or "n/a",
        "",
        "## Claim",
        summary.get("claim") or "n/a",
        "",
        "## Experiment",
        summary.get("experiment_design") or "n/a",
        "",
        "## Evidence",
        ", ".join(evidence_ids) if evidence_ids else "n/a",
        "",
        "## Validation Result",
        result.get("evidence_outcome") or "n/a",
        "",
        "## Confidence",
        payload.get("confidence_level") or "n/a",
        "",
        "## Promotion Decision",
        decision_line,
        "",
    ]
    return "\n".join(lines)


def _decision_line(decision: str | None) -> str:
    if decision == "provisional_lti":
        return "Promoted to LTI provisional"
    if decision == "reject":
        return "Rejected"
    if decision == "needs_more_validation":
        return "Needs more validation"
    return "n/a"
