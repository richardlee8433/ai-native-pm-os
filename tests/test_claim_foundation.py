from __future__ import annotations

import datetime as dt
import json

import pytest

from claims.store import ClaimStore
from pm_os_contracts.models import AVL_EVIDENCE_PACK, LTI_NODE, ClaimObject
from pmos import cli


def _sample_claim(*, claim_id: str = "CLM-1234ABCDEF567890") -> ClaimObject:
    return ClaimObject(
        claim_id=claim_id,
        claim_statement="AI prototyping accelerates product iteration.",
        source_id="openai_news",
        source_type="rss",
        source_url="https://example.com/news/1",
        domain="product_development",
        context="early product exploration",
        metric="iteration speed",
        evidence_type="article",
        confidence=0.72,
        assumptions=["team has clear feedback loop"],
        failure_modes=["solution bias"],
        applicability="early-stage product teams",
        rule_candidate="Use AI prototyping in early exploration when iteration speed matters.",
        extracted_at=dt.datetime(2026, 3, 16, 10, 0, tzinfo=dt.timezone.utc),
        version="v5.0",
    )


def test_claim_object_accepts_valid_payload() -> None:
    claim = _sample_claim()
    assert claim.claim_id == "CLM-1234ABCDEF567890"


def test_claim_object_rejects_missing_required_field() -> None:
    with pytest.raises(Exception):
        ClaimObject(
            claim_id="CLM-1234ABCDEF567890",
            source_id="openai_news",
            source_type="rss",
            extracted_at=dt.datetime(2026, 3, 16, tzinfo=dt.timezone.utc),
            version="v5.0",
        )


def test_avl_and_lti_new_fields_are_backward_compatible() -> None:
    avl = AVL_EVIDENCE_PACK(
        id="AVL-EP-20260316-001",
        hypothesis="Test",
        context="Context",
        method="replay",
        outcome="pass",
        cost_paid="time",
        failure_modes=["none"],
        delta="delta",
        recommendation="promote",
        governance_impact="none",
    )
    lti = LTI_NODE(id="LTI-1.0", title="Title", series="LTI-1.x", status="active")
    assert avl.claim_reference is None
    assert lti.knowledge_type is None


def test_claim_store_write_read_and_list(tmp_path) -> None:
    store = ClaimStore(tmp_path)
    claim = _sample_claim()

    result = store.write(claim)
    assert result["written"] is True
    assert store.get(claim.claim_id)["claim_statement"] == claim.claim_statement

    listed = store.list()
    assert len(listed) == 1
    assert listed[0]["claim_id"] == claim.claim_id


def test_claim_store_skips_duplicate_claim_id(tmp_path) -> None:
    store = ClaimStore(tmp_path)
    claim = _sample_claim()

    first = store.write(claim)
    second = store.write(claim)

    assert first["written"] is True
    assert second["written"] is False
    assert second["reason"] == "duplicate_claim_id"
    assert len(store.list()) == 1


def test_claim_cli_list_and_show(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("PMOS_V5_CLAIMS_ENABLED", "true")
    claim = _sample_claim()
    ClaimStore(tmp_path).write(claim)

    rc = cli.main(["--root", str(tmp_path), "claim", "list"])
    assert rc == 0
    listed = json.loads(capsys.readouterr().out)
    assert len(listed) == 1
    assert listed[0]["claim_id"] == claim.claim_id

    rc = cli.main(["--root", str(tmp_path), "claim", "show", claim.claim_id])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["claim_id"] == claim.claim_id


def test_claim_cli_disabled_by_feature_flag(tmp_path, capsys) -> None:
    rc = cli.main(["--root", str(tmp_path), "claim", "list"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "PMOS_V5_CLAIMS_ENABLED is not enabled"
