from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_validate_contracts_script_schema_only() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/validate_contracts.py", "--validate-schemas-only"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "OK:" in result.stdout


def test_validate_contracts_script_payload(tmp_path: Path) -> None:
    payload = {
        "id": "ACT-20260216-001",
        "type": "task_tracking",
        "goal": "Track task",
        "deliverables": ["board update"],
    }
    payload_file = tmp_path / "action_task.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/validate_contracts.py",
            "--contract",
            "ACTION_TASK",
            "--input",
            str(payload_file),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "ACTION_TASK" in result.stdout
