from __future__ import annotations

import json
import datetime as dt
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "v1.0"
CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "contracts" / CONTRACT_VERSION


class ContractBaseModel(BaseModel):
    """Base class with common serialization helpers for PM OS contracts."""

    model_config = ConfigDict(extra="allow")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)

    def to_json(self, *, indent: int | None = None) -> str:
        return self.model_dump_json(indent=indent, exclude_none=True)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ContractBaseModel":
        return cls.model_validate(payload)

    @classmethod
    def from_json(cls, payload: str) -> "ContractBaseModel":
        return cls.model_validate_json(payload)


class SIGNAL(ContractBaseModel):
    id: str = Field(pattern=r"^SIG-[0-9]{8}-[0-9]{3}$")
    source: str
    type: Literal["capability", "research", "governance", "market", "ecosystem"]
    timestamp: dt.datetime
    title: str | None = None
    content: str | None = None
    url: str | None = None
    priority_score: float | None = Field(default=None, ge=0, le=1)
    impact_area: list[str] | None = None
    linked_action_id: str | None = None


class ACTION_TASK(ContractBaseModel):
    id: str = Field(pattern=r"^ACT-[0-9]{8}-[0-9]{3}$")
    type: Literal["tech_prototype", "strategic_design", "content_creation", "task_tracking"]
    goal: str
    context: str | None = None
    deliverables: list[str]
    reflection_prompts: list[str] | None = None
    engine: Literal["aispm_agent", "ai_pmo", "mentorflow"] | None = None
    status: Literal["pending", "in_progress", "completed", "blocked"] | None = None
    created_at: dt.datetime | None = None
    due_date: dt.date | None = None


class BlockingCase(ContractBaseModel):
    dimension: str | None = None
    reason: str | None = None
    severity: Literal["critical", "major", "minor"] | None = None


class EVAL_REPORT(ContractBaseModel):
    task_id: str
    run_id: str | None = None
    average_score: float = Field(ge=0, le=1)
    dimension_scores: dict[str, float] | None = None
    decision: Literal["approve", "reject", "hold"]
    blocking_cases: list[BlockingCase] | None = None
    risk_level: Literal["low", "medium", "high"] | None = None
    evaluated_at: dt.datetime | None = None


class GATE_DECISION(ContractBaseModel):
    task_id: str
    eval_report_id: str | None = None
    decision: Literal["approve", "reject", "hold"]
    destination: Literal["lti", "cos", "none"]
    post_action: Literal["publish_now", "schedule", "do_not_publish", "hold"] | None = None
    canonical_decision: Literal["merge_now", "create_now", "update_later", "no_change"] | None = None
    decision_reason: str | None = None
    decided_at: dt.datetime | None = None


class RevisionHistoryEntry(ContractBaseModel):
    date: dt.date | None = None
    change: str | None = None
    reason: str | None = None


class LTI_NODE(ContractBaseModel):
    id: str = Field(pattern=r"^LTI-[0-9]\.[0-9]+$")
    title: str
    series: str
    status: Literal["active", "archived", "under_review"]
    confidence_level: float | None = Field(default=None, ge=0, le=1)
    published_at: dt.date | None = None
    tags: list[str] | None = None
    summary: str | None = None
    linked_evidence: list[str] | None = None
    linked_rti: list[str] | None = None
    revision_history: list[RevisionHistoryEntry] | None = None


class COS_CASE(ContractBaseModel):
    id: str = Field(pattern=r"^COS-[0-9]{8}-[0-9]{3}$")
    task_id: str
    failure_pattern_id: str
    blocked_by_gate_reason: str | None = None
    blocking_dimension: str | None = None
    linked_rti: list[str] | None = None
    archived_at: dt.datetime | None = None
    content: str | None = None
    analysis: str | None = None


class RTI_NODE(ContractBaseModel):
    id: str = Field(pattern=r"^RTI-[0-9]\.[0-9]+$")
    title: str
    category: str | None = None
    status: Literal["active", "under_review", "deprecated"]
    confidence_level: float = Field(default=0.5, ge=0, le=1)
    linked_evidence: list[str] | None = None
    linked_lti: list[str] | None = None
    linked_cos_patterns: list[str] | None = None
    revision_trigger_count: int = Field(default=0, ge=0)
    last_validated: dt.date | None = None


class EngagementStats(ContractBaseModel):
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    views: int | None = None


class LPL_POST(ContractBaseModel):
    id: str = Field(pattern=r"^LPL-[0-9]{8}T[0-9]{6}Z-[0-9]{3}$")
    source_lti_id: str
    content: str
    post_url: str | None = None
    published_at: dt.datetime | None = None
    engagement_stats: EngagementStats | None = None
    echo_score: float | None = Field(default=None, ge=0, le=1)


class CommentQuality(ContractBaseModel):
    avg_sentiment: float | None = Field(default=None, ge=-1, le=1)
    avg_depth_score: float | None = Field(default=None, ge=0, le=1)
    professional_ratio: float | None = Field(default=None, ge=0, le=1)


class AudienceBreakdown(ContractBaseModel):
    by_role: dict[str, Any] | None = None
    by_industry: dict[str, Any] | None = None


class ECHO_METRICS(ContractBaseModel):
    lpl_id: str
    captured_at: dt.datetime
    engagement_rate: float | None = None
    comment_quality: CommentQuality | None = None
    share_velocity: float | None = None
    audience_breakdown: AudienceBreakdown | None = None
    composite_echo_score: float | None = Field(default=None, ge=0, le=1)


CONTRACT_MODEL_MAP: dict[str, type[ContractBaseModel]] = {
    "SIGNAL": SIGNAL,
    "ACTION_TASK": ACTION_TASK,
    "EVAL_REPORT": EVAL_REPORT,
    "GATE_DECISION": GATE_DECISION,
    "LTI_NODE": LTI_NODE,
    "COS_CASE": COS_CASE,
    "RTI_NODE": RTI_NODE,
    "LPL_POST": LPL_POST,
    "ECHO_METRICS": ECHO_METRICS,
}


def schema_path(contract_name: str) -> Path:
    return CONTRACTS_DIR / f"{contract_name}.schema.json"


def load_schema(contract_name: str) -> dict[str, Any]:
    path = schema_path(contract_name)
    return json.loads(path.read_text(encoding="utf-8"))


def serialize_contract(contract: ContractBaseModel) -> str:
    return contract.to_json()


def deserialize_contract(contract_name: str, payload: str | dict[str, Any]) -> ContractBaseModel:
    model_cls = CONTRACT_MODEL_MAP[contract_name]
    if isinstance(payload, str):
        return model_cls.from_json(payload)
    return model_cls.from_dict(payload)
