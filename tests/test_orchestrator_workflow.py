from __future__ import annotations

import datetime as dt
from pathlib import Path

from orchestrator.workflow import Orchestrator


class FakeNow:
    def __init__(self, start: dt.datetime) -> None:
        self.current = start

    def __call__(self) -> dt.datetime:
        value = self.current
        self.current = value + dt.timedelta(seconds=1)
        return value


def test_manual_workflow_signal_action_writeback(tmp_path, monkeypatch) -> None:
    now = FakeNow(dt.datetime(2026, 2, 16, 10, 0, 0, tzinfo=dt.timezone.utc))
    vault_root = tmp_path / "vault"
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(vault_root))
    orchestrator = Orchestrator(tmp_path, now_provider=now)

    low = orchestrator.add_signal(source="manual", signal_type="market", title="Low", priority_score=0.2)
    high = orchestrator.add_signal(source="manual", signal_type="capability", title="High", priority_score=0.9)

    top = orchestrator.top_signals(limit=1)
    assert top[0].id == high.id

    task = orchestrator.generate_action()
    assert task.id == "ACT-20260216-001"
    assert task.goal.startswith("Respond to signal")

    lti_payload = orchestrator.apply_writeback()
    assert lti_payload["id"] == "LTI-1.0"
    assert lti_payload["linked_evidence"] == [task.id]
    assert lti_payload["written_path"].endswith("96_Weekly_Review/_LTI_Drafts/LTI-1.0.md")

    signal_rows = orchestrator.signals.read_all()
    linked = [row for row in signal_rows if row["id"] == high.id][0]
    assert linked["linked_action_id"] == task.id

    writebacks = orchestrator.writebacks.read_all()
    statuses = [row["status"] for row in writebacks]
    assert statuses == ["pending", "applied"]

    assert low.id == "SIG-20260216-001"
    assert high.id == "SIG-20260216-002"


def test_apply_writeback_writes_and_overwrites_lti_markdown(tmp_path, monkeypatch) -> None:
    now = FakeNow(dt.datetime(2026, 2, 16, 10, 0, 0, tzinfo=dt.timezone.utc))
    vault_root = tmp_path / "vault"
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(vault_root))
    orchestrator = Orchestrator(tmp_path, now_provider=now)

    orchestrator.add_signal(
        source="manual",
        signal_type="capability",
        title="High",
        content="Original summary",
        priority_score=0.9,
    )
    task = orchestrator.generate_action(goal="LTI markdown title")

    first = orchestrator.apply_writeback(action_id=task.id)
    markdown_path = Path(first["written_path"])
    assert markdown_path.exists()
    first_text = markdown_path.read_text(encoding="utf-8")
    assert "id: LTI-1.0" in first_text
    assert "source_task_id: ACT-20260216-001" in first_text
    assert "status: under_review" in first_text
    assert "# LTI markdown title" in first_text
    assert "Original summary" in first_text

    task_rows = orchestrator.tasks.read_all()
    task_rows[0]["context"] = "Updated summary"
    orchestrator.tasks.rewrite_all(task_rows)

    second = orchestrator.apply_writeback(action_id=task.id)
    assert second["id"] == "LTI-1.0"
    second_text = markdown_path.read_text(encoding="utf-8")
    assert "Updated summary" in second_text
    assert "Original summary" not in second_text


def test_generate_action_fails_without_signals(tmp_path) -> None:
    orchestrator = Orchestrator(tmp_path)

    try:
        orchestrator.generate_action()
    except ValueError as exc:
        assert "No signals found" in str(exc)
    else:
        raise AssertionError("Expected ValueError when no signals exist")
