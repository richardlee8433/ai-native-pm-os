from __future__ import annotations

import json

import pytest

from pm_os_contracts.models import (
    ACTION_TASK,
    COS_CASE,
    ECHO_METRICS,
    EVAL_REPORT,
    GATE_DECISION,
    LPL_POST,
    LTI_NODE,
    RTI_NODE,
    SIGNAL,
    deserialize_contract,
    serialize_contract,
)


def test_signal_roundtrip_serialization() -> None:
    signal = SIGNAL(
        id="SIG-20260216-001",
        source="anthropic_blog",
        type="capability",
        timestamp="2026-02-16T12:00:00Z",
        priority_score=0.85,
    )

    payload = serialize_contract(signal)
    restored = deserialize_contract("SIGNAL", payload)

    assert isinstance(restored, SIGNAL)
    assert restored.id == signal.id
    assert json.loads(payload)["source"] == "anthropic_blog"


@pytest.mark.parametrize(
    "model_cls, valid_payload",
    [
        (ACTION_TASK, {"id": "ACT-20260216-001", "type": "tech_prototype", "goal": "Build MVP", "deliverables": ["scorer.py"]}),
        (EVAL_REPORT, {"task_id": "ACT-20260216-001", "average_score": 0.72, "decision": "approve"}),
        (GATE_DECISION, {"task_id": "ACT-20260216-001", "decision": "approve", "destination": "lti"}),
        (LTI_NODE, {"id": "LTI-6.5", "title": "Signal scoring", "series": "LTI-6.x", "status": "active"}),
        (COS_CASE, {"id": "COS-20260216-001", "task_id": "ACT-20260216-001", "failure_pattern_id": "FP-001"}),
        (RTI_NODE, {"id": "RTI-1.2", "title": "Feedback loops", "status": "active"}),
        (LPL_POST, {"id": "LPL-20260216T120000Z-001", "source_lti_id": "LTI-6.5", "content": "Post body"}),
        (ECHO_METRICS, {"lpl_id": "LPL-20260216T120000Z-001", "captured_at": "2026-02-17T12:00:00Z"}),
    ],
)
def test_models_accept_valid_payloads(model_cls, valid_payload) -> None:
    model = model_cls.model_validate(valid_payload)
    assert model is not None


def test_model_rejects_invalid_pattern() -> None:
    with pytest.raises(Exception):
        SIGNAL(
            id="SIG-INVALID",
            source="x",
            type="market",
            timestamp="2026-02-16T12:00:00Z",
        )
