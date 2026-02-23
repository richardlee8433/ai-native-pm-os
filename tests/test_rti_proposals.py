from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator import rti_proposals


def _write_decision(path: Path, *, decision_type: str, signal_id: str | None, revision_of: str | None = None) -> None:
    lines = [
        "---",
        f"decision_type: {decision_type}",
    ]
    if signal_id is not None:
        lines.append(f"signal_id: {signal_id}")
    if revision_of:
        lines.append(f"revision_of: {revision_of}")
    lines.extend(["---", "", "# Decision", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def test_accept_creates_v1(tmp_path) -> None:
    vault_root = tmp_path
    decision = vault_root / "97_Decisions" / "DEC-2026-W08-001.md"
    _write_decision(decision, decision_type="ACCEPT", signal_id="SIG-123")

    status = rti_proposals.on_new_l4_decision(decision)
    proposals_dir = vault_root / "97_Decisions" / "_RTI_Proposals"
    created = proposals_dir / "RTI-PROP-SIG-123-v1.md"

    assert status.startswith("created:")
    assert created.exists()


def test_accept_again_creates_v2(tmp_path) -> None:
    vault_root = tmp_path
    decision1 = vault_root / "97_Decisions" / "DEC-2026-W08-001.md"
    decision2 = vault_root / "97_Decisions" / "DEC-2026-W08-002.md"
    _write_decision(decision1, decision_type="ACCEPT", signal_id="SIG-123")
    _write_decision(decision2, decision_type="ACCEPT", signal_id="SIG-123", revision_of="DEC-2026-W08-001")

    rti_proposals.on_new_l4_decision(decision1)
    rti_proposals.on_new_l4_decision(decision2)

    proposals_dir = vault_root / "97_Decisions" / "_RTI_Proposals"
    assert (proposals_dir / "RTI-PROP-SIG-123-v1.md").exists()
    assert (proposals_dir / "RTI-PROP-SIG-123-v2.md").exists()


def test_malformed_filename_ignored(tmp_path) -> None:
    proposals_dir = tmp_path / "97_Decisions" / "_RTI_Proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    (proposals_dir / "RTI-PROP-SIG-123-vx.md").write_text("bad", encoding="utf-8")

    version = rti_proposals.compute_next_version("SIG-123", proposals_dir)
    assert version == 1


def test_collision_triggers_retry(tmp_path, monkeypatch) -> None:
    proposals_dir = tmp_path / "97_Decisions" / "_RTI_Proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    existing = proposals_dir / "RTI-PROP-SIG-123-v2.md"
    existing.write_text("existing", encoding="utf-8")

    calls = {"count": 0}

    def fake_next_version(signal_id: str, proposals_dir: Path) -> int:
        calls["count"] += 1
        return 2 if calls["count"] == 1 else 3

    monkeypatch.setattr(rti_proposals, "compute_next_version", fake_next_version)

    decision = rti_proposals.L4Decision(
        decision_type="ACCEPT",
        signal_id="SIG-123",
        revision_of=None,
        decision_id="DEC-2026-W08-003",
    )
    created = rti_proposals.write_rti_proposal(decision, "SIG-123", proposals_dir)
    assert created.name == "RTI-PROP-SIG-123-v3.md"


def test_reject_no_op(tmp_path) -> None:
    vault_root = tmp_path
    decision = vault_root / "97_Decisions" / "DEC-2026-W08-003.md"
    _write_decision(decision, decision_type="REJECT", signal_id="SIG-123")

    status = rti_proposals.on_new_l4_decision(decision)
    proposals_dir = vault_root / "97_Decisions" / "_RTI_Proposals"

    assert status == "no-op"
    assert not proposals_dir.exists()


def test_missing_signal_id_no_write(tmp_path) -> None:
    vault_root = tmp_path
    decision = vault_root / "97_Decisions" / "DEC-2026-W08-004.md"
    _write_decision(decision, decision_type="ACCEPT", signal_id=None)

    status = rti_proposals.on_new_l4_decision(decision)
    proposals_dir = vault_root / "97_Decisions" / "_RTI_Proposals"

    assert status == "error: missing signal_id"
    assert not proposals_dir.exists()


def test_directory_auto_created(tmp_path) -> None:
    vault_root = tmp_path
    decision = vault_root / "97_Decisions" / "DEC-2026-W08-005.md"
    _write_decision(decision, decision_type="ACCEPT", signal_id="SIG-999")

    rti_proposals.on_new_l4_decision(decision)
    proposals_dir = vault_root / "97_Decisions" / "_RTI_Proposals"
    assert proposals_dir.exists()
