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
    ])

    assert rc == 0
    stdout = capsys.readouterr().out
    assert "vault_writeback: written=1" in stdout

    env_notes = list((env_vault / "98_Signals").glob("*.md")) if (env_vault / "98_Signals").exists() else []
    cli_notes = list((cli_vault / "98_Signals").glob("*.md"))
    assert env_notes == []
    assert len(cli_notes) == 1
