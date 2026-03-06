from __future__ import annotations

import json
from pathlib import Path

from graph.ops import GraphStore
from promotion.report_generator import generate_promotion_report
from validation_projects.ops import ValidationProjectStore


def _write_evidence_pack(root: Path, *, pack_id: str, outcome: str, recommendation: str) -> None:
    base_dir = root / "avl" / "evidence_packs"
    base_dir.mkdir(parents=True, exist_ok=True)
    pack_path = base_dir / f"{pack_id}.md"
    content = "\n".join(
        [
            "---",
            f"id: {pack_id}",
            "title: VP Evidence",
            "created_at: 2026-03-06T00:00:00Z",
            "updated_at: 2026-03-06T00:00:00Z",
            "hypothesis: H",
            "context: C",
            "method: replay",
            f"outcome: {outcome}",
            "cost_paid: time",
            "failure_modes: none",
            "delta: D",
            f"recommendation: {recommendation}",
            "governance_impact: none",
            "---",
            "",
            "# AVL Evidence Pack",
            "",
        ]
    )
    pack_path.write_text(content, encoding="utf-8")
    index_path = base_dir / "index.json"
    if index_path.exists():
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        payload = {"items": []}
    payload["items"] = [
        item for item in payload.get("items", []) if item.get("id") != pack_id
    ] + [{"id": pack_id, "path": pack_path.relative_to(root).as_posix()}]
    index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _create_vp_with_graph(root: Path, *, graph_id: str, pack_id: str, validation_plan: dict | None = None) -> str:
    vp_store = ValidationProjectStore(root)
    vp = vp_store.init(title="VP", validation_plan=validation_plan)
    vp_store.link_graph(project_id=vp.id, graph_ids=[graph_id])
    vp_store.link_evidence(project_id=vp.id, evidence_ids=[pack_id])
    return vp.id


def test_promotion_report_generation(tmp_path) -> None:
    graph_store = GraphStore(tmp_path)
    graph = graph_store.create(
        node_type="hypothesis",
        title="Hypothesis A",
        content="Validate whether: A",
        validation_plan="system_build",
        extra={
            "core_claim": "Claim A",
            "hypothesis_statement": "Validate whether: A",
            "validation_seed": {"seven_day_validation_idea": "Experiment A", "implementation_options": []},
        },
    )
    pack_id = "AVL-EP-20260306-001"
    _write_evidence_pack(tmp_path, pack_id=pack_id, outcome="pass", recommendation="promote")
    vp_id = _create_vp_with_graph(tmp_path, graph_id=graph.id, pack_id=pack_id)

    result = generate_promotion_report(tmp_path, vp_id=vp_id)
    report_dir = Path(result["report_dir"])
    assert (report_dir / "promotion.json").exists()
    assert (report_dir / "promotion_report.md").exists()
    payload = result["payload"]
    assert "evidence_count" in payload
    assert "validation_plan_metrics_defined" in payload
    assert "validation_plan_success_defined" in payload


def test_promotion_decision_mapping(tmp_path) -> None:
    graph_store = GraphStore(tmp_path)
    graph = graph_store.create(node_type="concept", title="Graph Title")

    pack_id = "AVL-EP-20260306-002"
    _write_evidence_pack(tmp_path, pack_id=pack_id, outcome="fail", recommendation="reject")
    vp_id = _create_vp_with_graph(tmp_path, graph_id=graph.id, pack_id=pack_id)

    result = generate_promotion_report(tmp_path, vp_id=vp_id)
    payload = result["payload"]
    assert payload["promotion_decision"] == "reject"

    _write_evidence_pack(tmp_path, pack_id=pack_id, outcome="partial", recommendation="revise")
    result = generate_promotion_report(tmp_path, vp_id=vp_id)
    payload = result["payload"]
    assert payload["promotion_decision"] == "needs_more_validation"


def test_promotion_multi_pack_aggregation(tmp_path) -> None:
    graph_store = GraphStore(tmp_path)
    graph = graph_store.create(node_type="concept", title="Graph Title")

    pack_a = "AVL-EP-20260306-010"
    pack_b = "AVL-EP-20260306-011"
    _write_evidence_pack(tmp_path, pack_id=pack_a, outcome="pass", recommendation="promote")
    _write_evidence_pack(tmp_path, pack_id=pack_b, outcome="strong_partial", recommendation="promote")

    plan = {
        "claim": "Claim A",
        "experiment_design": "Experiment A",
        "timebox_days": 7,
        "metrics": [{"name": "correction_cycles", "type": "quantitative"}],
        "success_criteria": ["Reduce correction cycles by 20%"],
        "risks": [],
    }
    vp_store = ValidationProjectStore(tmp_path)
    vp = vp_store.init(title="VP", validation_plan=plan)
    vp_store.link_graph(project_id=vp.id, graph_ids=[graph.id])
    vp_store.link_evidence(project_id=vp.id, evidence_ids=[pack_a, pack_b])

    result = generate_promotion_report(tmp_path, vp_id=vp.id)
    payload = result["payload"]
    assert payload["validation_result"]["packs_evaluated"] == 2
    assert payload["validation_result"]["aggregated_outcome"] == "provisional_lti"
    assert payload["promotion_decision"] == "provisional_lti"
