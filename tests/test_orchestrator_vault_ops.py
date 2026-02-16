from __future__ import annotations

import datetime as dt

from orchestrator.vault_ops import resolve_vault_root, write_lti_markdown, write_signal_markdown
from pm_os_contracts.models import LTI_NODE, SIGNAL


def test_write_signal_markdown_creates_obsidian_note(tmp_path) -> None:
    signal = SIGNAL(
        id="SIG-20260216-001",
        source="arXiv AI",
        type="research",
        timestamp=dt.datetime(2026, 2, 13, 8, 0, 0, tzinfo=dt.timezone.utc),
        title="A Safety Paper",
        content="This paper introduces methods for safety alignment and policy governance.",
        url="https://arxiv.org/abs/1234.5678",
        priority_score=0.7,
        impact_area=["safety_alignment", "policy_governance", "tooling_infra"],
    )

    out = write_signal_markdown(tmp_path, signal)

    assert out == tmp_path / "98_Signals" / "SIG-20260216-001.md"
    text = out.read_text(encoding="utf-8")
    assert "impact_area:" in text
    assert '- safety_alignment' in text
    assert "## Excerpt" in text
    assert "## Source" in text


def test_write_lti_markdown_formats_yaml_lists_and_sanitizes_summary(tmp_path) -> None:
    node = LTI_NODE(
        id="LTI-1.0",
        title="Trustworthy Agent Loops",
        series="LTI-1.x",
        status="under_review",
        summary="Use $f(x)$ with \\textbf{robust} constraints and \\(g(y)\\) checks.",
        linked_evidence=["ACT-20260216-001"],
        linked_rti=["RTI-1.1"],
        tags=["agents", "safety"],
        published_at=dt.date(2026, 2, 16),
    )

    out = write_lti_markdown(
        tmp_path,
        node,
        "ACT-20260216-001",
        updated_at="2026-02-16T10:00:00+00:00",
    )

    text = out.read_text(encoding="utf-8")
    assert "linked_evidence:" in text
    assert '- ACT-20260216-001' in text
    assert "linked_rti:" in text
    assert '- RTI-1.1' in text
    assert "tags:" in text
    assert "summary_sanitized: true" in text
    assert "- ACT-20260216-001" in text
    assert "- agents" in text
    assert "f(x)" in text
    assert "textbf" not in text
    assert "$" not in text


def test_resolve_vault_root_precedence(tmp_path, monkeypatch) -> None:
    cli_root = tmp_path / "cli-vault"
    env_root = tmp_path / "env-vault"

    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(env_root))
    assert resolve_vault_root(str(cli_root)) == cli_root
    assert resolve_vault_root(None) == env_root

    monkeypatch.delenv("PM_OS_VAULT_ROOT")
    assert resolve_vault_root(None).as_posix() == ".vault_test"
