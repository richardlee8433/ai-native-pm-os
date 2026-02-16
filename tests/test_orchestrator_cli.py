from __future__ import annotations

import json

from orchestrator.cli import main


def test_cli_signal_action_writeback_flow(tmp_path, capsys) -> None:
    data_dir = tmp_path / "data"

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
