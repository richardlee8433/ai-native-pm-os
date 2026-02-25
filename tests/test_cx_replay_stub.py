from __future__ import annotations

from pathlib import Path

from cx_replay.replay_runner import run_fixture
from pm_os_contracts.models import AVL_EVIDENCE_PACK
from promotion_router.manual_router import route_manual_promotion


def test_cx_replay_fixture_generates_valid_evidence_pack(tmp_path: Path) -> None:
    result = run_fixture(fixture_id="cx-case-001", root=tmp_path)

    pack = result["evidence_pack"]
    AVL_EVIDENCE_PACK.model_validate(pack)

    pack_path = Path(result["path"])
    assert pack_path.exists()

    vault_root = tmp_path / "vault"
    routed = route_manual_promotion(
        evidence_pack_path=pack_path,
        vault_root=vault_root,
        source_graph_nodes=["GRAPH-CONCEPT-20260225-001"],
        use_v41_promotion=True,
    )

    assert routed["lti_created"] is not None
    assert Path(routed["lti_created"]).exists()
    assert routed["rti_review_created"] is not None
    assert Path(routed["rti_review_created"]).exists()
