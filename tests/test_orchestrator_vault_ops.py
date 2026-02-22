from __future__ import annotations

import datetime as dt

from orchestrator.vault_ops import (
    resolve_vault_root,
    write_gate_decision,
    write_lti_markdown,
    write_signal_markdown,
    write_weekly_review,
)
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

    assert out == tmp_path / "95_Signals" / "SIG-20260216-001.md"
    text = out.read_text(encoding="utf-8")
    assert "impact_area:" in text
    assert '- safety_alignment' in text
    assert "status: raw" in text
    assert "## Preview" in text
    assert "## Full Evidence" in text


def test_write_lti_markdown_routes_to_drafts_without_approval(tmp_path) -> None:
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

    assert out == tmp_path / "96_Weekly_Review" / "_LTI_Drafts" / "LTI-1.0.md"
    text = out.read_text(encoding="utf-8")
    assert "human_approved: False" in text
    assert "f(x)" in text
    assert "textbf" not in text


def test_write_lti_markdown_approved_routes_to_lti(tmp_path) -> None:
    node = LTI_NODE(id="LTI-1.1", title="Approved", series="LTI-1.x", status="active")
    out = write_lti_markdown(
        tmp_path,
        node,
        "ACT-20260216-002",
        updated_at="2026-02-16T10:00:00+00:00",
        human_approved=True,
        publish_intent="publish",
    )
    assert out == tmp_path / "02_LTI" / "LTI-1.1.md"


def test_write_weekly_review_path(tmp_path) -> None:
    from orchestrator.vault_ops import SignalScore

    out = write_weekly_review(
        tmp_path,
        "2026-W08",
        [SignalScore(id="SIG-20260216-001", score=0.9, preview="Top signal", url="https://x", impact_area=["strategy"])],
    )
    assert out == tmp_path / "96_Weekly_Review" / "Weekly-Intel-2026-W08.md"


def test_write_gate_decision_immutable_no_overwrite(tmp_path) -> None:
    first = write_gate_decision(
        tmp_path,
        decision_id="DEC-20260216-001",
        signal_id="SIG-20260216-001",
        decision="approved",
        priority="High",
        decision_date=dt.date(2026, 2, 16),
        reason="Strong strategic fit.",
        next_actions=["Deepen evidence (L3 full fetch)", "Draft LTI insight note"],
        signal_summary="Signal preview text.",
    )
    assert first.parent == tmp_path / "97_Gate_Decisions"

    import pytest

    with pytest.raises(FileExistsError):
        write_gate_decision(
            tmp_path,
            decision_id="DEC-20260216-001",
            signal_id="SIG-20260216-001",
            decision="approved",
            priority="High",
            decision_date=dt.date(2026, 2, 16),
            reason="Strong strategic fit.",
            next_actions=["Deepen evidence (L3 full fetch)", "Draft LTI insight note"],
            signal_summary="Signal preview text.",
        )


def test_resolve_vault_root_precedence(tmp_path, monkeypatch) -> None:
    cli_root = tmp_path / "cli-vault"
    env_root = tmp_path / "env-vault"

    monkeypatch.setenv("PM_OS_VAULT_ROOT", str(env_root))
    assert resolve_vault_root(str(cli_root)) == cli_root
    assert resolve_vault_root(None) == env_root

    monkeypatch.delenv("PM_OS_VAULT_ROOT")
    assert resolve_vault_root(None).as_posix() == ".vault_test"
