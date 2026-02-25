from __future__ import annotations

from pathlib import Path


def test_current_architecture_pointer_exists() -> None:
    path = Path("docs/CURRENT_ARCHITECTURE.md")
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "docs/AI-Native-PM-OS-v4.1-Architecture.md" in content


def test_readme_points_to_current_architecture() -> None:
    readme = Path("README.md")
    assert readme.exists()
    content = readme.read_text(encoding="utf-8")
    assert "docs/CURRENT_ARCHITECTURE.md" in content
