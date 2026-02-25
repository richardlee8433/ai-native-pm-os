from __future__ import annotations

import json

from orchestrator.cli import main


def test_cli_signal_action_writeback_flow(tmp_path, capsys, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(tmp_path / "vault"))

    rc = main([
        "--data-dir",
        str(data_dir),
        "signal",
        "add",
        "--source",
        "manual",
        "--type",
        "capability",
        "--title",
        "CLI signal",
        "--priority-score",
        "0.8",
    ])
    assert rc == 0
    signal_payload = json.loads(capsys.readouterr().out)
    assert signal_payload["id"].startswith("SIG-")

    rc = main(["--data-dir", str(data_dir), "signal", "top", "--limit", "1"])
    assert rc == 0
    top_payload = json.loads(capsys.readouterr().out)
    assert len(top_payload) == 1

    rc = main(["--data-dir", str(data_dir), "action", "generate"])
    assert rc == 0
    action_payload = json.loads(capsys.readouterr().out)
    assert action_payload["id"].startswith("ACT-")

    rc = main(["--data-dir", str(data_dir), "writeback", "apply"])
    assert rc == 0
    lti_payload = json.loads(capsys.readouterr().out)
    assert lti_payload["id"].startswith("LTI-")
    assert lti_payload["written_path"].endswith(".md")
    assert "96_Weekly_Review/_LTI_Drafts" in lti_payload["written_path"].replace("\\", "/")



def test_cli_ingest_writes_signal_markdown_and_vault_root_precedence(tmp_path, capsys, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    env_vault = tmp_path / "vault-from-env"
    cli_vault = tmp_path / "vault-from-cli"
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(env_vault))

    class _Fetcher:
        def fetch(self, source_cfg, limit):
            return [
                {
                    "title": "Agent policy and tooling update",
                    "url": "https://example.com/signal",
                    "content": "Useful content for vault writeback",
                    "published_at": __import__("datetime").datetime.now(tz=__import__("datetime").timezone.utc),
                }
            ]

    from ingest.registry import SourceConfig

    monkeypatch.setattr("orchestrator.cli.load_sources", lambda path: [SourceConfig(id="demo", type="rss", signal_type="research")])
    monkeypatch.setattr("orchestrator.cli.get_fetcher", lambda source_type: _Fetcher())

    rc = main([
        "--data-dir",
        str(data_dir),
        "ingest",
        "--out",
        str(data_dir / "signals.jsonl"),
        "--vault-root",
        str(cli_vault),
        "--since-days",
        "30",
        "--threshold",
        "0",
        "--writeback-signals",
    ])

    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["vault_written"] == 1
    assert len(report["vault_paths"]) == 1

    env_notes = list((env_vault / "95_Signals").glob("*.md")) if (env_vault / "95_Signals").exists() else []
    cli_notes = list((cli_vault / "95_Signals").glob("*.md"))
    assert env_notes == []
    assert len(cli_notes) == 1


def test_cli_ingest_no_writeback_without_flag(tmp_path, capsys, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    env_vault = tmp_path / "vault-from-env"
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(env_vault))

    class _Fetcher:
        def fetch(self, source_cfg, limit):
            return [
                {
                    "title": "Agent policy and tooling update",
                    "url": "https://example.com/signal",
                    "content": "Useful content for vault writeback",
                    "published_at": __import__("datetime").datetime.now(tz=__import__("datetime").timezone.utc),
                }
            ]

    from ingest.registry import SourceConfig

    monkeypatch.setattr("orchestrator.cli.load_sources", lambda path: [SourceConfig(id="demo", type="rss", signal_type="research")])
    monkeypatch.setattr("orchestrator.cli.get_fetcher", lambda source_type: _Fetcher())

    rc = main([
        "--data-dir",
        str(data_dir),
        "ingest",
        "--out",
        str(data_dir / "signals.jsonl"),
        "--since-days",
        "30",
        "--threshold",
        "0",
    ])

    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["vault_written"] == 0
    assert report["vault_paths"] == []
    assert report["index_path"].endswith("signals_index.json")
    assert not (env_vault / "95_Signals").exists()



def test_cli_writeback_human_approved_routes_to_final_lti(tmp_path, capsys, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(tmp_path / "vault"))

    main(["--data-dir", str(data_dir), "signal", "add", "--source", "manual", "--type", "capability", "--title", "S"])
    _ = capsys.readouterr()
    main(["--data-dir", str(data_dir), "action", "generate"])
    _ = capsys.readouterr()

    rc = main(["--data-dir", str(data_dir), "writeback", "apply", "--human-approved", "--publish-intent", "publish"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "/02_LTI/" in payload["written_path"].replace("\\", "/")

def test_ingest_help_includes_writeback_flag(capsys) -> None:
    try:
        main(["ingest", "-h"])
    except SystemExit as exc:
        assert exc.code == 0

    help_text = capsys.readouterr().out
    assert "--writeback-signals" in help_text
    assert "--vault-root" in help_text
    assert "--index-path" in help_text


def test_cli_gate_decide_generates_default_actions(tmp_path, capsys, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(tmp_path / "vault"))

    main([
        "--data-dir",
        str(data_dir),
        "signal",
        "add",
        "--source",
        "manual",
        "--type",
        "capability",
        "--title",
        "Signal for decision",
        "--content",
        "Preview content",
    ])
    signal_payload = json.loads(capsys.readouterr().out)

    rc = main([
        "--data-dir",
        str(data_dir),
        "gate",
        "decide",
        "--signal-id",
        signal_payload["id"],
        "--decision",
        "approved",
        "--priority",
        "High",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision_id"].startswith("DEC-")
    assert payload["next_actions"] == ["Deepen evidence (L3 full fetch)", "Draft LTI insight note"]
    assert payload["deepening_task_created"] is True
    assert payload["deepening_task_id"] == f"ACT-DEEPEN-{signal_payload['id']}"
    assert payload["signal_updated"] is True


def test_cli_gate_decide_rejects_overwrite(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(tmp_path / "vault"))

    signal_rc = main([
        "--data-dir",
        str(data_dir),
        "signal",
        "add",
        "--source",
        "manual",
        "--type",
        "capability",
        "--title",
        "Signal for decision",
    ])
    assert signal_rc == 0

    import datetime as dt
    import pytest

    from orchestrator.workflow import Orchestrator

    orchestrator = Orchestrator(data_dir=data_dir, now_provider=lambda: dt.datetime(2026, 2, 16, tzinfo=dt.timezone.utc))
    signals = orchestrator.signals.read_all()
    signal_id = signals[0]["id"]

    orchestrator.create_gate_decision(signal_id=signal_id, decision="reject", priority="Low")
    orchestrator.decision_index_path.unlink()

    with pytest.raises(FileExistsError):
        orchestrator.create_gate_decision(signal_id=signal_id, decision="reject", priority="Low")


def test_cli_deepen_run_returns_report(tmp_path, capsys, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    vault_root = tmp_path / "vault"
    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(vault_root))

    rc = main([
        "--data-dir",
        str(data_dir),
        "signal",
        "add",
        "--source",
        "manual",
        "--type",
        "research",
        "--title",
        "CLI deepen",
        "--url",
        "https://example.com/news",
        "--content",
        "Preview",
    ])
    assert rc == 0
    signal_payload = json.loads(capsys.readouterr().out)

    from orchestrator.vault_ops import write_signal_markdown
    from orchestrator.workflow import Orchestrator

    orchestrator = Orchestrator(data_dir=data_dir)
    write_signal_markdown(vault_root, orchestrator.signals.read_all()[0])
    orchestrator.tasks.append({"id": f"ACT-DEEPEN-{signal_payload['id']}", "type": "deepening", "signal_id": signal_payload["id"], "status": "pending"})

    class _Resp:
        status_code = 200
        text = "<html><body>CLI deepened evidence.</body></html>"

    monkeypatch.setattr(Orchestrator, "_http_get", lambda self, url: _Resp.text)

    rc = main(["--data-dir", str(data_dir), "deepen", "run", "--limit", "1"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["processed"] == 1
    assert payload["completed"] == 1
    assert payload["results"][0]["status"] == "completed"
