from __future__ import annotations

import json

from pmos.cli import main


def _fill_required_fields(path) -> None:
    text = path.read_text(encoding="utf-8")
    replacements = {
        "hypothesis:": "hypothesis: Test hypothesis",
        "context:": "context: Real constraints",
        "method:": "method: project_cycle",
        "outcome:": "outcome: pass",
        "cost_paid:": "cost_paid: time=2d",
        "failure_modes:": "failure_modes: none",
        "delta:": "delta: Faster iteration",
        "recommendation:": "recommendation: promote",
        "governance_impact:": "governance_impact: none",
    }
    for key, value in replacements.items():
        text = text.replace(key, value, 1)
    path.write_text(text, encoding="utf-8")


def test_avl_pack_create_and_validate(tmp_path, capsys) -> None:
    rc = main(["--root", str(tmp_path), "avl", "pack", "create", "--title", "Pack A"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    pack_path = tmp_path / payload["path"]
    assert pack_path.exists()

    _fill_required_fields(pack_path)

    rc = main(["--root", str(tmp_path), "avl", "pack", "validate", "--path", str(pack_path)])
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
