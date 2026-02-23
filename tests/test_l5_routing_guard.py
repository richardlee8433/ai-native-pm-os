from __future__ import annotations

import json
from pathlib import Path

from orchestrator import l5_routing_guard as l5
from orchestrator.storage import JSONLStorage


def _write_decision(path: Path, *, decision_type: str, signal_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                f"decision_type: {decision_type}",
                f"signal_id: {signal_id}",
                "---",
                "",
                "# Decision",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _seed_signal(data_dir: Path, signal_id: str) -> None:
    store = JSONLStorage(data_dir / "signals.jsonl")
    store.append({"id": signal_id, "title": "Signal Title", "content": "Signal summary", "impact_area": ["strategy"], "url": "https://example.com"})


def test_route_after_gate_creates_lti_draft_when_approved(tmp_path) -> None:
    vault_root = tmp_path / "vault"
    data_dir = tmp_path / "data"
    signal_id = "SIG-20260223-001"
    decision_id = "DEC-2026-W08-001"

    _seed_signal(data_dir, signal_id)
    decision_path = vault_root / "97_Decisions" / f"{decision_id}.md"
    _write_decision(decision_path, decision_type="ACCEPT", signal_id=signal_id)

    created = l5.route_after_gate_decision(decision_id, data_dir, vault_root)
    assert created

    drafts_path = data_dir / "test_data" / "lti_drafts.jsonl"
    rows = JSONLStorage(drafts_path).read_all()
    assert len(rows) == 1
    assert rows[0]["source_decision_id"] == decision_id
    assert (vault_root / rows[0]["vault_path"]).exists()


def test_route_after_gate_is_idempotent(tmp_path) -> None:
    vault_root = tmp_path / "vault"
    data_dir = tmp_path / "data"
    signal_id = "SIG-20260223-002"
    decision_id = "DEC-2026-W08-002"

    _seed_signal(data_dir, signal_id)
    decision_path = vault_root / "97_Decisions" / f"{decision_id}.md"
    _write_decision(decision_path, decision_type="ACCEPT", signal_id=signal_id)

    l5.route_after_gate_decision(decision_id, data_dir, vault_root)
    l5.route_after_gate_decision(decision_id, data_dir, vault_root)

    rows = JSONLStorage(data_dir / "test_data" / "lti_drafts.jsonl").read_all()
    assert len(rows) == 1


def test_publish_lti_moves_file_and_updates_jsonl(tmp_path) -> None:
    vault_root = tmp_path / "vault"
    data_dir = tmp_path / "data"
    signal_id = "SIG-20260223-003"
    decision_id = "DEC-2026-W08-003"

    _seed_signal(data_dir, signal_id)
    decision_path = vault_root / "97_Decisions" / f"{decision_id}.md"
    _write_decision(decision_path, decision_type="ACCEPT", signal_id=signal_id)
    l5.route_after_gate_decision(decision_id, data_dir, vault_root)

    draft = JSONLStorage(data_dir / "test_data" / "lti_drafts.jsonl").read_all()[0]
    final_path = l5.publish_lti_draft(draft["id"], vault_root, data_dir, reviewer="Lisa", review_notes="ok")

    assert (vault_root / final_path).exists()
    updated = JSONLStorage(data_dir / "test_data" / "lti_drafts.jsonl").read_all()[0]
    assert updated["status"] == "published"


def test_rule_of_three_creates_rti_proposal(tmp_path) -> None:
    vault_root = tmp_path / "vault"
    data_dir = tmp_path / "data"
    pattern_id = "FP-TEST-001"

    cos_index = [
        {"cos_id": "COS-20260223-001", "pattern_key": pattern_id},
        {"cos_id": "COS-20260223-002", "pattern_key": pattern_id},
        {"cos_id": "COS-20260223-003", "pattern_key": pattern_id},
    ]
    (data_dir / "cos_index.json").parent.mkdir(parents=True, exist_ok=True)
    (data_dir / "cos_index.json").write_text(json.dumps(cos_index), encoding="utf-8")

    proposal_id = l5.check_rule_of_three_and_propose_rti(pattern_id, data_dir, vault_root)
    assert proposal_id is not None
    proposals = JSONLStorage(data_dir / "test_data" / "rti_proposals.jsonl").read_all()
    assert proposals[0]["id"] == proposal_id
    assert (vault_root / proposals[0]["vault_path"]).exists()


def test_reject_marks_status_only(tmp_path) -> None:
    vault_root = tmp_path / "vault"
    data_dir = tmp_path / "data"
    signal_id = "SIG-20260223-004"
    decision_id = "DEC-2026-W08-004"

    _seed_signal(data_dir, signal_id)
    decision_path = vault_root / "97_Decisions" / f"{decision_id}.md"
    _write_decision(decision_path, decision_type="ACCEPT", signal_id=signal_id)
    l5.route_after_gate_decision(decision_id, data_dir, vault_root)

    draft = JSONLStorage(data_dir / "test_data" / "lti_drafts.jsonl").read_all()[0]
    l5.reject_lti_draft(draft["id"], data_dir, vault_root, reviewer="Lisa", reason="not ready")

    updated = JSONLStorage(data_dir / "test_data" / "lti_drafts.jsonl").read_all()[0]
    assert updated["status"] == "rejected"
    assert (vault_root / updated["vault_path"]).exists()
