from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable

from pm_os_contracts.models import SIGNAL

from ingest.registry import SourceConfig

MIN_PRIORITY_THRESHOLD = 0.6

IMPACT_KEYWORDS: dict[str, list[str]] = {
    "agent_systems": ["agent", "agents", "autonomous", "workflow agent", "tool use"],
    "evaluation": ["eval", "evaluation", "benchmark", "leaderboard", "metric", "red team"],
    "safety_alignment": ["safety", "alignment", "constitutional", "harm", "risk", "guardrail"],
    "policy_governance": ["policy", "regulation", "governance", "compliance", "standards"],
    "multimodal": ["multimodal", "vision", "speech", "audio", "video", "image"],
    "tooling_infra": ["sdk", "api", "tooling", "inference", "serving", "platform", "framework"],
}


def infer_impact_area(title: str | None, content: str | None) -> list[str]:
    text = f"{title or ''} {content or ''}".lower()
    impacts: list[str] = []
    for area, terms in IMPACT_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(term)}\b", text) for term in terms):
            impacts.append(area)
    return impacts or ["tooling_infra"]


def _freshness_score(published_at: dt.datetime | None, now_utc: dt.datetime) -> float:
    if not published_at:
        return 0.4
    age_days = max(0.0, (now_utc - published_at.astimezone(dt.timezone.utc)).total_seconds() / 86400)
    if age_days <= 3:
        return 1.0
    if age_days <= 7:
        return 0.7
    return 0.4


def _impact_signal_score(impact_areas: Iterable[str]) -> float:
    area_count = len(set(impact_areas))
    if area_count >= 3:
        return 1.0
    if area_count == 2:
        return 0.8
    if area_count == 1:
        return 0.6
    return 0.4


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def calculate_priority_score(source_cfg: SourceConfig, item: dict, keywords: list[str]) -> float:
    """
    Priority = (Strength × Confidence) / Effort

    Strength = freshness × impact_signal
    Confidence = source_weight
    Effort = 1.0 (placeholder for MVP)
    """
    now_utc = dt.datetime.now(tz=dt.timezone.utc)
    freshness = _freshness_score(item.get("published_at"), now_utc)
    impact_signal = _impact_signal_score(keywords)
    strength = freshness * impact_signal
    confidence = source_cfg.weight
    effort = 1.0
    return clamp01((strength * confidence) / effort)


def normalize_item_to_signal(source_cfg: SourceConfig, item: dict, seq_num: int, now_utc: dt.datetime) -> SIGNAL:
    signal_id = f"SIG-{now_utc.strftime('%Y%m%d')}-{seq_num:03d}"
    title = item.get("title")
    content = item.get("content")
    impact_area = infer_impact_area(title, content)
    priority_score = calculate_priority_score(source_cfg, item, impact_area)
    timestamp = item.get("published_at") or now_utc

    return SIGNAL(
        id=signal_id,
        source=source_cfg.name or source_cfg.id,
        type=source_cfg.signal_type,
        timestamp=timestamp,
        title=title,
        content=content,
        url=item.get("url"),
        impact_area=impact_area,
        priority_score=priority_score,
    )
