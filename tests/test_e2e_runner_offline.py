from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_e2e_runner_offline_smoke() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    cmd = [sys.executable, "scripts/e2e_three_branch_flow.py", "--offline", "--now-iso", "2025-01-15T12:00:00Z"]
    result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr + "\n" + result.stdout
    assert "E2E PASS" in result.stdout
