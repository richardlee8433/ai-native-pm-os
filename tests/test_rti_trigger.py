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


def _add_rejected(orchestrator: Orchestrator, *, suffix: str) -> dict[str, str]:
    signal = orchestrator.add_signal(
        source="manual",
        signal_type="governance",
        title=f"Signal {suffix}",
        impact_area=["policy"],
    )
    return orchestrator.create_gate_decision(
        signal_id=signal.id,
        decision="reject",
        priority="Low",
        reason="Repeated failure mode",
    )


def test_rule_of_three_sets_rti_proposal_and_creates_validation_task(tmp_path, monkeypatch) -> None:
    now = FakeNow(dt.datetime(2026, 2, 17, 9, 0, 0, tzinfo=dt.timezone.utc))
    vault_root = tmp_path / "vault"
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(vault_root))
    orchestrator = Orchestrator(tmp_path, now_provider=now)

    first = _add_rejected(orchestrator, suffix="1")
    second = _add_rejected(orchestrator, suffix="2")
    third = _add_rejected(orchestrator, suffix="3")

    assert first["rti_triggered"] is False
    assert second["rti_triggered"] is False
    assert third["rti_triggered"] is True
    assert third["linked_rti_proposal"].startswith("RTI-PROP-20260217-")

    proposal_path = vault_root / "97_Decisions" / "_RTI_Proposals" / f"{third['linked_rti_proposal']}.md"
    assert proposal_path.exists()
    proposal_text = proposal_path.read_text(encoding="utf-8")
    assert "status: draft" in proposal_text
    assert "Pattern Evidence" in proposal_text

    tasks = orchestrator.tasks.read_all()
    validation = [task for task in tasks if task["type"] == "rti_validation"]
    assert len(validation) == 1
    assert validation[0]["id"] == f"ACT-VALIDATE-{third['linked_rti_proposal']}"

    cos_index = json.loads((tmp_path / "cos_index.json").read_text(encoding="utf-8"))
    linked = [entry["linked_rti_proposal"] for entry in cos_index if entry["pattern_key"] == third["pattern_key"]]
    assert len(linked) == 3
    assert all(value == third["linked_rti_proposal"] for value in linked)


def test_rule_of_three_does_not_fire_twice_for_same_pattern(tmp_path, monkeypatch) -> None:
    now = FakeNow(dt.datetime(2026, 2, 17, 9, 30, 0, tzinfo=dt.timezone.utc))
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(tmp_path / "vault"))
    orchestrator = Orchestrator(tmp_path, now_provider=now)

    _add_rejected(orchestrator, suffix="1")
    _add_rejected(orchestrator, suffix="2")
    third = _add_rejected(orchestrator, suffix="3")
    fourth = _add_rejected(orchestrator, suffix="4")

    assert third["linked_rti_proposal"] == fourth["linked_rti_proposal"]
    assert fourth["rti_triggered"] is False

    tasks = [task for task in orchestrator.tasks.read_all() if task["type"] == "rti_validation"]
    assert len(tasks) == 1
