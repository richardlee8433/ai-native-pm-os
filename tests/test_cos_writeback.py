from __future__ import annotations

import datetime as dt
import json

from orchestrator.workflow import Orchestrator


class FakeNow:
    def __init__(self, start: dt.datetime) -> None:
        self.current = start

    def __call__(self) -> dt.datetime:
        value = self.current
        self.current = value + dt.timedelta(seconds=1)
        return value


def test_gate_reject_creates_cos_file_and_index(tmp_path, monkeypatch) -> None:
    now = FakeNow(dt.datetime(2026, 2, 16, 10, 0, 0, tzinfo=dt.timezone.utc))
    vault_root = tmp_path / "vault"
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(vault_root))
    orchestrator = Orchestrator(tmp_path, now_provider=now)

    signal = orchestrator.add_signal(
        source="manual",
        signal_type="market",
        title="Rejected signal",
        content="Summary",
        impact_area=["roadmap", "ops"],
    )

    payload = orchestrator.create_gate_decision(
        signal_id=signal.id,
        decision="reject",
        priority="Low",
        reason="Insufficient evidence",
    )

    cos_path = vault_root / "06_Archive" / "COS" / f"{payload['cos_id']}.md"
    assert cos_path.exists()
    cos_text = cos_path.read_text(encoding="utf-8")
    assert "# COS Case" in cos_text
    assert f"signal_id: {signal.id}" in cos_text
    assert "decision_id:" in cos_text
    assert "pattern_key:" in cos_text

    cos_index = json.loads((tmp_path / "cos_index.json").read_text(encoding="utf-8"))
    assert len(cos_index) == 1
    assert cos_index[0]["cos_id"] == payload["cos_id"]
    assert cos_index[0]["pattern_key"] == payload["pattern_key"]
    assert cos_index[0]["linked_rti"] is None


def test_pattern_key_normalization_and_idempotent_rejection_writeback(tmp_path, monkeypatch) -> None:
    now = FakeNow(dt.datetime(2026, 2, 16, 11, 0, 0, tzinfo=dt.timezone.utc))
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(tmp_path / "vault"))
    orchestrator = Orchestrator(tmp_path, now_provider=now)

    signal = orchestrator.add_signal(
        source="manual",
        signal_type="market",
        title="Normalize",
        impact_area=["Ops", "Roadmap"],
    )

    payload = orchestrator.create_gate_decision(
        signal_id=signal.id,
        decision="reject",
        priority="Low",
        reason="Need Better-Evidence!!",
    )
    assert payload["pattern_key"].startswith("need better evidence|")

    duplicate = orchestrator.handle_rejection(
        signal_id=signal.id,
        decision_id=payload["decision_id"],
        decision_reason="Need Better-Evidence!!",
    )

    assert duplicate["cos_id"] == payload["cos_id"]
    cos_index = json.loads((tmp_path / "cos_index.json").read_text(encoding="utf-8"))
    assert len(cos_index) == 1
