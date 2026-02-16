from __future__ import annotations

import datetime as dt

from orchestrator.workflow import Orchestrator


class FakeNow:
    def __init__(self, start: dt.datetime) -> None:
        self.current = start

    def __call__(self) -> dt.datetime:
        value = self.current
        self.current = value + dt.timedelta(seconds=1)
        return value


def test_manual_workflow_signal_action_writeback(tmp_path) -> None:
    now = FakeNow(dt.datetime(2026, 2, 16, 10, 0, 0, tzinfo=dt.timezone.utc))
    orchestrator = Orchestrator(tmp_path, now_provider=now)

    low = orchestrator.add_signal(source="manual", signal_type="market", title="Low", priority_score=0.2)
    high = orchestrator.add_signal(source="manual", signal_type="capability", title="High", priority_score=0.9)

    top = orchestrator.top_signals(limit=1)
    assert top[0].id == high.id

    task = orchestrator.generate_action()
    assert task.id == "ACT-20260216-001"
    assert task.goal.startswith("Respond to signal")

    lti = orchestrator.apply_writeback()
    assert lti.id == "LTI-1.0"
    assert lti.linked_evidence == [task.id]

    signal_rows = orchestrator.signals.read_all()
    linked = [row for row in signal_rows if row["id"] == high.id][0]
    assert linked["linked_action_id"] == task.id

    writebacks = orchestrator.writebacks.read_all()
    statuses = [row["status"] for row in writebacks]
    assert statuses == ["pending", "applied"]

    assert low.id == "SIG-20260216-001"
    assert high.id == "SIG-20260216-002"


def test_generate_action_fails_without_signals(tmp_path) -> None:
    orchestrator = Orchestrator(tmp_path)

    try:
        orchestrator.generate_action()
    except ValueError as exc:
        assert "No signals found" in str(exc)
    else:
        raise AssertionError("Expected ValueError when no signals exist")
