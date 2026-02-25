from __future__ import annotations

from pathlib import Path

from avl.ops import EvidencePackStore
from promotion_router.manual_router import route_manual_promotion


def _fill_pack(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    updates = {
        "hypothesis:": "hypothesis: Test hypothesis",
        "context:": "context: Real context",
        "method:": "method: project_cycle",
        "outcome:": "outcome: pass",
        "cost_paid:": "cost_paid: time=2d",
        "failure_modes:": "failure_modes: none",
        "delta:": "delta: Improved loop",
        "recommendation:": "recommendation: promote",
        "governance_impact:": "governance_impact: review",
    }
    for key, value in updates.items():
        text = text.replace(key, value, 1)
    path.write_text(text, encoding="utf-8")


def test_manual_promotion_router_creates_lti_and_rti_review(tmp_path) -> None:
    vault_root = tmp_path / "vault"
    store = EvidencePackStore(tmp_path)
    record = store.create(title="Pack for promotion")
    pack_path = tmp_path / record.path
    _fill_pack(pack_path)

    result = route_manual_promotion(
        evidence_pack_path=pack_path,
        vault_root=vault_root,
        source_graph_nodes=["GRAPH-CONCEPT-20260224-001"],
        use_v41_promotion=True,
    )

    assert result["lti_created"] is not None
    lti_path = Path(result["lti_created"])
    assert lti_path.exists()
    lti_text = lti_path.read_text(encoding="utf-8")
    assert "validation_status: provisional" in lti_text
    assert "source_graph_nodes" in lti_text

    assert result["rti_review_created"] is not None
    review_path = Path(result["rti_review_created"])
    assert review_path.exists()
