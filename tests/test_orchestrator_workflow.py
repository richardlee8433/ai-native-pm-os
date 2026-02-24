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
    assert lti_payload["written_path"].replace("\\", "/").endswith("96_Weekly_Review/_LTI_Drafts/LTI-1.0.md")

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


def test_gate_approved_creates_deepening_task_and_updates_signal(tmp_path, monkeypatch) -> None:
    now = FakeNow(dt.datetime(2026, 2, 16, 10, 0, 0, tzinfo=dt.timezone.utc))
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(tmp_path / "vault"))
    orchestrator = Orchestrator(tmp_path, now_provider=now)

    signal = orchestrator.add_signal(
        source="manual",
        signal_type="capability",
        title="Deepen me",
        content="Long form evidence preview",
    )

    payload = orchestrator.create_gate_decision(signal_id=signal.id, decision="approved", priority="High")

    assert payload["deepening_task_created"] is True
    assert payload["deepening_task_id"] == f"ACT-DEEPEN-{signal.id}"
    assert payload["signal_updated"] is True

    tasks = orchestrator.tasks.read_all()
    assert len(tasks) == 1
    assert tasks[0]["id"] == f"ACT-DEEPEN-{signal.id}"
    assert tasks[0]["type"] == "deepening"
    assert tasks[0]["signal_id"] == signal.id
    assert tasks[0]["auto_generated"] is True

    signals = orchestrator.signals.read_all()
    assert signals[0]["gate_status"] == "approved"
    assert signals[0]["gate_decision_id"] == payload["decision_id"]
    assert signals[0]["deepening_task_id"] == f"ACT-DEEPEN-{signal.id}"


def test_gate_approved_routes_l5_and_marks_decided(tmp_path, monkeypatch) -> None:
    now = FakeNow(dt.datetime(2026, 2, 16, 10, 0, 0, tzinfo=dt.timezone.utc))
    vault_root = tmp_path / "vault"
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(vault_root))
    orchestrator = Orchestrator(tmp_path, now_provider=now)

    signal = orchestrator.add_signal(
        source="manual",
        signal_type="capability",
        title="Route me",
        content="Evidence preview",
    )

    payload = orchestrator.create_gate_decision(signal_id=signal.id, decision="approved", priority="High")

    l5_created = payload["l5_created"]
    draft_entry = next(item for item in l5_created if item.get("type") == "lti_draft")
    draft_id = draft_entry["id"]
    assert (vault_root / "96_Weekly_Review" / "_LTI_Drafts" / f"{draft_id}.md").exists()

    signal_row = orchestrator.signals.read_all()[0]
    assert signal_row["lifecycle_status"] == "decided"
    assert signal_row["lti_draft_id"] == draft_id


def test_gate_approved_route_error_does_not_mark_decided(tmp_path, monkeypatch) -> None:
    now = FakeNow(dt.datetime(2026, 2, 16, 10, 0, 0, tzinfo=dt.timezone.utc))
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(tmp_path / "vault"))
    orchestrator = Orchestrator(tmp_path, now_provider=now)

    signal = orchestrator.add_signal(
        source="manual",
        signal_type="capability",
        title="Broken routing",
        content="Evidence preview",
    )

    def _raise_route(*_args, **_kwargs):
        raise FileNotFoundError("vault missing")

    import orchestrator.workflow as workflow

    monkeypatch.setattr(workflow, "route_after_gate_decision", _raise_route)

    payload = orchestrator.create_gate_decision(signal_id=signal.id, decision="approved", priority="High")
    assert payload["l5_created"][0]["error"].startswith("path error:")

    signal_row = orchestrator.signals.read_all()[0]
    assert "lifecycle_status" not in signal_row


def test_gate_duplicate_approved_is_idempotent(tmp_path, monkeypatch) -> None:
    now = FakeNow(dt.datetime(2026, 2, 16, 10, 0, 0, tzinfo=dt.timezone.utc))
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(tmp_path / "vault"))
    orchestrator = Orchestrator(tmp_path, now_provider=now)

    signal = orchestrator.add_signal(source="manual", signal_type="capability", title="Deepen me")

    first = orchestrator.create_gate_decision(signal_id=signal.id, decision="approved", priority="High")
    second = orchestrator.create_gate_decision(signal_id=signal.id, decision="approved", priority="High")

    tasks = orchestrator.tasks.read_all()
    assert len(tasks) == 1
    assert first["deepening_task_id"] == second["deepening_task_id"]
    assert second["deepening_task_created"] is False
    assert second["signal_updated"] is False

    signals = orchestrator.signals.read_all()
    assert signals[0]["gate_decision_id"] == first["decision_id"]


def test_gate_non_approved_does_not_create_deepening_task(tmp_path, monkeypatch) -> None:
    now = FakeNow(dt.datetime(2026, 2, 16, 10, 0, 0, tzinfo=dt.timezone.utc))
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(tmp_path / "vault"))
    orchestrator = Orchestrator(tmp_path, now_provider=now)

    signal = orchestrator.add_signal(source="manual", signal_type="market", title="Maybe later")
    payload = orchestrator.create_gate_decision(signal_id=signal.id, decision="deferred", priority="Low")

    assert payload["deepening_task_created"] is False
    assert payload["deepening_task_id"] is None
    assert payload["signal_updated"] is False
    assert orchestrator.tasks.read_all() == []

    signal_row = orchestrator.signals.read_all()[0]
    assert "gate_status" not in signal_row


def test_writeback_syncs_lti_index(tmp_path, monkeypatch) -> None:
    now = FakeNow(dt.datetime(2026, 2, 16, 10, 0, 0, tzinfo=dt.timezone.utc))
    vault_root = tmp_path / "vault"
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(vault_root))
    orchestrator = Orchestrator(tmp_path, now_provider=now)

    orchestrator.add_signal(source="manual", signal_type="market", title="Index sync")
    task = orchestrator.generate_action()

    _ = orchestrator.apply_writeback(action_id=task.id, artifact_kind="lti")

    lti_index = vault_root / "02_LTI" / "lti_index.json"
    assert lti_index.exists()


def test_rejection_syncs_cos_index(tmp_path, monkeypatch) -> None:
    now = FakeNow(dt.datetime(2026, 2, 17, 10, 0, 0, tzinfo=dt.timezone.utc))
    vault_root = tmp_path / "vault"
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(vault_root))
    orchestrator = Orchestrator(tmp_path, now_provider=now)

    signal = orchestrator.add_signal(source="manual", signal_type="governance", title="Reject me")
    _ = orchestrator.create_gate_decision(signal_id=signal.id, decision="reject", priority="Low")

    cos_index = vault_root / "06_Archive" / "COS" / "cos_index.json"
    assert cos_index.exists()


def test_run_deepening_appends_evidence_and_updates_state(tmp_path, monkeypatch) -> None:
    now = FakeNow(dt.datetime(2026, 2, 16, 10, 0, 0, tzinfo=dt.timezone.utc))
    vault_root = tmp_path / "vault"
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(vault_root))
    orchestrator = Orchestrator(tmp_path, now_provider=now)

    from orchestrator.vault_ops import write_signal_markdown

    signal = orchestrator.add_signal(
        source="manual",
        signal_type="research",
        title="Deepen this",
        content="Preview content",
        url="https://example.com/post",
    )
    write_signal_markdown(vault_root, orchestrator.signals.read_all()[0])
    orchestrator.tasks.append(
        {
            "id": f"ACT-DEEPEN-{signal.id}",
            "type": "deepening",
            "signal_id": signal.id,
            "status": "pending",
            "auto_generated": True,
        }
    )

    class _Resp:
        status_code = 200
        text = "<html><body><article>Full evidence for signal.</article></body></html>"

    monkeypatch.setattr(Orchestrator, "_http_get", lambda self, url: _Resp.text)

    report = orchestrator.run_deepening(limit=5)
    assert report["completed"] == 1

    sig_text = (vault_root / "95_Signals" / f"{signal.id}.md").read_text(encoding="utf-8")
    assert "## Deepened Evidence (L3)" in sig_text
    assert "fetch_status: ok" in sig_text

    task_row = orchestrator.tasks.read_all()[0]
    assert task_row["status"] == "completed"

    signal_row = orchestrator.signals.read_all()[0]
    assert signal_row["deepened"] is True


def test_run_deepening_is_idempotent_for_same_url(tmp_path, monkeypatch) -> None:
    now = FakeNow(dt.datetime(2026, 2, 16, 10, 0, 0, tzinfo=dt.timezone.utc))
    vault_root = tmp_path / "vault"
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(vault_root))
    orchestrator = Orchestrator(tmp_path, now_provider=now)

    from orchestrator.vault_ops import write_signal_markdown

    signal = orchestrator.add_signal(
        source="manual",
        signal_type="research",
        title="Deepen once",
        content="Preview content",
        url="https://example.com/idempotent",
    )
    write_signal_markdown(vault_root, orchestrator.signals.read_all()[0])
    orchestrator.tasks.append({"id": f"ACT-DEEPEN-{signal.id}", "type": "deepening", "signal_id": signal.id, "status": "pending"})

    class _Resp:
        status_code = 200
        text = "<html><body>Body evidence</body></html>"

    monkeypatch.setattr(Orchestrator, "_http_get", lambda self, url: _Resp.text)

    orchestrator.run_deepening(limit=5)
    task_rows = orchestrator.tasks.read_all()
    task_rows[0]["status"] = "pending"
    orchestrator.tasks.rewrite_all(task_rows)
    orchestrator.run_deepening(limit=5, force=True)

    sig_text = (vault_root / "95_Signals" / f"{signal.id}.md").read_text(encoding="utf-8")
    assert sig_text.count("## Deepened Evidence (L3)") == 1


def test_run_deepening_failed_fetch_marks_failed_and_writes_failed_note(tmp_path, monkeypatch) -> None:
    now = FakeNow(dt.datetime(2026, 2, 16, 10, 0, 0, tzinfo=dt.timezone.utc))
    vault_root = tmp_path / "vault"
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(vault_root))
    orchestrator = Orchestrator(tmp_path, now_provider=now)

    from orchestrator.vault_ops import write_signal_markdown

    signal = orchestrator.add_signal(
        source="manual",
        signal_type="research",
        title="Fetch fails",
        content="Fallback preview",
        url="https://example.com/fail",
    )
    write_signal_markdown(vault_root, orchestrator.signals.read_all()[0])
    orchestrator.tasks.append({"id": f"ACT-DEEPEN-{signal.id}", "type": "deepening", "signal_id": signal.id, "status": "pending"})

    monkeypatch.setattr(Orchestrator, "_http_get", lambda self, url: (_ for _ in ()).throw(RuntimeError("network down")))

    report = orchestrator.run_deepening(limit=5)
    assert report["failed"] == 1

    task_row = orchestrator.tasks.read_all()[0]
    assert task_row["status"] == "failed"
    assert "network down" in task_row["error"]

    sig_text = (vault_root / "95_Signals" / f"{signal.id}.md").read_text(encoding="utf-8")
    assert "fetch_status: failed" in sig_text
