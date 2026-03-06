from __future__ import annotations

import datetime as dt
import json
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from graph.ops import GraphStore
from ingest.registry import SourceConfig

BUILDABLE_KEYWORDS = ["mvp", "prototype", "experiment", "workflow", "build", "ship", "implement", "replay", "system build"]
STRUCTURAL_KEYWORDS = ["governance", "policy", "architecture", "operating system", "escalation", "constitution", "kernel"]


@dataclass(frozen=True)
class NewsletterDecision:
    source_id: str
    source_name: str | None
    source_url: str | None
    source_type: str
    credibility: str | None
    content_id: str | None
    content_title: str | None
    core_claim: str | None
    hypothesis_statement: str | None
    routing_decision: str
    justification: str
    seven_day_validation_idea: str | None
    implementation_options: list[dict[str, Any]]
    timestamp: str
    title: str | None
    week_key: str
    validation_potential: float
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "credibility": self.credibility,
            "content_id": self.content_id,
            "content_title": self.content_title,
            "core_claim": self.core_claim,
            "hypothesis_statement": self.hypothesis_statement,
            "routing_decision": self.routing_decision,
            "justification": self.justification,
            "seven_day_validation_idea": self.seven_day_validation_idea,
            "implementation_options": self.implementation_options,
            "timestamp": self.timestamp,
            "title": self.title,
            "week_key": self.week_key,
            "validation_potential": self.validation_potential,
            **self.evidence,
        }


def process_newsletter_source(
    *,
    source_cfg: SourceConfig,
    items: list[dict[str, Any]],
    root: Path,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    if source_cfg.source_type != "pm_newsletter":
        return {"ok": False, "reason": "unsupported source_type", "source_id": source_cfg.id}

    now_dt = now or dt.datetime.now(tz=dt.timezone.utc)
    selected = select_weekly_items(items, now_dt)
    decisions: list[NewsletterDecision] = []

    for item in selected:
        decision = _route_item(source_cfg, item, root, now_dt)
        decisions.append(decision)

    _write_decisions(root, decisions)

    return {"ok": True, "processed": len(decisions), "decisions": [d.to_dict() for d in decisions]}


def select_weekly_items(items: list[dict[str, Any]], now_dt: dt.datetime) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        week_key = _week_key(item.get("published_at"), now_dt)
        grouped.setdefault(week_key, []).append(item)

    selected: list[dict[str, Any]] = []
    for week_key, week_items in grouped.items():
        best = max(week_items, key=lambda row: (_validation_potential(row), _published_ts(row, now_dt)))
        best = dict(best)
        best["_week_key"] = week_key
        best["_validation_potential"] = _validation_potential(best)
        selected.append(best)

    return selected


def _route_item(source_cfg: SourceConfig, item: dict[str, Any], root: Path, now_dt: dt.datetime) -> NewsletterDecision:
    title = item.get("title")
    content = item.get("content")
    core_claim = _derive_core_claim(title, content)
    hypothesis_statement = _derive_hypothesis_statement(core_claim)
    content_id = _extract_content_id(item)
    decision, justification = classify_newsletter_item(title, content)
    timestamp = now_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    week_key = item.get("_week_key") or _week_key(item.get("published_at"), now_dt)
    validation_score = item.get("_validation_potential") or _validation_potential(item)

    evidence: dict[str, Any] = {}
    seven_day_validation_idea: str | None = None
    implementation_options: list[dict[str, Any]] = []
    if decision == "buildable":
        idea, options, validation_plan = build_validation_idea(title, content)
        seven_day_validation_idea = idea
        implementation_options = _build_implementation_options(options)
        graph_id = _create_graph_hypothesis(
            root,
            title=title or "Newsletter Hypothesis",
            core_claim=core_claim,
            hypothesis_statement=hypothesis_statement,
            routing_decision=decision,
            justification=justification,
            seven_day_validation_idea=seven_day_validation_idea,
            implementation_options=implementation_options,
            validation_plan=validation_plan,
            source_cfg=source_cfg,
            item=item,
            content_id=content_id,
        )
        evidence = {
            "idea": idea,
            "options": options,
            "graph_node_id": graph_id,
            "validation_plan": validation_plan,
            "vp_recommended": True,
        }
    elif decision == "structural":
        watch_path = _append_watchlist(root, title, item.get("url"), justification, timestamp)
        evidence = {"watchlist_path": watch_path}
    else:
        queue_path = _append_research_queue(root, title, item.get("url"), justification, timestamp)
        evidence = {"research_queue_path": queue_path}

    return NewsletterDecision(
        source_id=source_cfg.id,
        source_name=source_cfg.name,
        source_url=item.get("url"),
        source_type=source_cfg.source_type or "pm_newsletter",
        credibility=source_cfg.credibility,
        content_id=content_id,
        content_title=title,
        core_claim=core_claim,
        hypothesis_statement=hypothesis_statement,
        routing_decision=decision,
        justification=justification,
        seven_day_validation_idea=seven_day_validation_idea,
        implementation_options=implementation_options,
        timestamp=timestamp,
        title=title,
        week_key=week_key,
        validation_potential=validation_score,
        evidence=evidence,
    )


def classify_newsletter_item(title: str | None, content: str | None) -> tuple[str, str]:
    text = f"{title or ''} {content or ''}".lower()
    buildable_hits = _keyword_hits(text, BUILDABLE_KEYWORDS)
    structural_hits = _keyword_hits(text, STRUCTURAL_KEYWORDS)

    if buildable_hits:
        return "buildable", "Contains buildable keywords: " + ", ".join(buildable_hits[:3])
    if structural_hits:
        return "structural", "Contains structural keywords: " + ", ".join(structural_hits[:3])
    return "research", "No 7-day buildable or structural governance signals detected"


def build_validation_idea(title: str | None, content: str | None) -> tuple[str, list[str], str]:
    base = title or "Newsletter insight"
    idea = f"7-Day Validation Idea: {base}"
    options = [
        "Build an MVP workflow experiment and measure outcome within 7 days",
        "Run a decision replay with canonical cases and compare outcomes",
        "Implement a small system build iteration and collect evidence",
    ]
    validation_plan = "system_build"
    text = f"{title or ''} {content or ''}".lower()
    if re.search(r"decision|escalation|policy", text):
        validation_plan = "decision_engine"
    return idea, options, validation_plan


def _create_graph_hypothesis(
    root: Path,
    *,
    title: str,
    core_claim: str | None,
    hypothesis_statement: str | None,
    routing_decision: str,
    justification: str,
    seven_day_validation_idea: str | None,
    implementation_options: list[dict[str, Any]],
    validation_plan: str,
    source_cfg: SourceConfig,
    item: dict[str, Any],
    content_id: str | None,
) -> str:
    payload = build_newsletter_graph_payload(
        title=title,
        core_claim=core_claim,
        hypothesis_statement=hypothesis_statement,
        routing_decision=routing_decision,
        justification=justification,
        seven_day_validation_idea=seven_day_validation_idea,
        implementation_options=implementation_options,
        validation_plan=validation_plan,
        source_cfg=source_cfg,
        item=item,
        content_id=content_id,
    )
    store = GraphStore(root)
    record = store.create_from_payload(payload)
    return record.id


def build_newsletter_graph_payload(
    *,
    title: str | None,
    core_claim: str | None,
    hypothesis_statement: str | None,
    routing_decision: str,
    justification: str,
    seven_day_validation_idea: str | None,
    implementation_options: list[dict[str, Any]],
    validation_plan: str | None,
    source_cfg: SourceConfig,
    item: dict[str, Any],
    content_id: str | None,
) -> dict[str, Any]:
    core_claim = (core_claim or "").strip() or None
    hypothesis_statement = (hypothesis_statement or "").strip() or None
    resolved_title = hypothesis_statement or _concise_text(core_claim) or title or "Newsletter hypothesis"
    source_url = item.get("url") or source_cfg.url
    source_ref = {
        "source_name": source_cfg.name or source_cfg.id,
        "source_type": source_cfg.source_type or "pm_newsletter",
        "source_url": source_url,
        "credibility": source_cfg.credibility or "unknown",
    }
    if content_id:
        source_ref["content_id"] = content_id

    payload = {
        "node_type": "hypothesis",
        "title": resolved_title,
        "content": hypothesis_statement or core_claim,
        "validation_plan": validation_plan,
        "source_ref": source_ref,
        "core_claim": core_claim,
        "hypothesis_statement": hypothesis_statement,
        "routing_decision": routing_decision,
        "justification": justification,
        "validation_seed": {
            "seven_day_validation_idea": seven_day_validation_idea,
            "implementation_options": implementation_options,
        },
    }
    return payload


def _derive_core_claim(title: str | None, content: str | None) -> str:
    if title and title.strip():
        return title.strip()
    if content and content.strip():
        snippet = content.strip().splitlines()[0]
        return snippet.strip()
    return "Newsletter insight"


def _derive_hypothesis_statement(core_claim: str | None) -> str:
    claim = (core_claim or "").strip()
    if not claim:
        return "Validate whether the newsletter insight is testable"
    return f"Validate whether: {claim}"


def _extract_content_id(item: dict[str, Any]) -> str | None:
    for key in ("content_id", "id", "guid"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    url = item.get("url")
    if isinstance(url, str) and url.strip():
        return hashlib.sha1(url.strip().encode("utf-8")).hexdigest()
    return None


def _build_implementation_options(options: list[str]) -> list[dict[str, Any]]:
    built: list[dict[str, Any]] = []
    for idx, option in enumerate(options):
        label = _concise_text(option) or f"Option {idx + 1}"
        built.append(
            {
                "option_id": f"opt_{chr(97 + idx)}",
                "label": label,
                "summary": option,
            }
        )
    return built


def _concise_text(text: str | None, *, max_words: int = 8) -> str | None:
    if not text:
        return None
    words = text.strip().split()
    if not words:
        return None
    return " ".join(words[:max_words])


def _append_watchlist(root: Path, title: str | None, url: str | None, justification: str, timestamp: str) -> str:
    path = root / "newsletter_governance" / "watchlist.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = f"- [{timestamp}] {title or 'Untitled'} | {url or 'n/a'} | {justification}\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(entry)
    return str(path)


def _append_research_queue(root: Path, title: str | None, url: str | None, justification: str, timestamp: str) -> str:
    path = root / "newsletter_governance" / "research_queue.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": timestamp,
        "title": title,
        "url": url,
        "justification": justification,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
    return str(path)


def _write_decisions(root: Path, decisions: list[NewsletterDecision]) -> None:
    if not decisions:
        return
    path = root / "newsletter_governance" / "decisions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for decision in decisions:
            handle.write(json.dumps(decision.to_dict()) + "\n")


def _validation_potential(item: dict[str, Any]) -> float:
    title = (item.get("title") or "").lower()
    content = (item.get("content") or "").lower()
    text = f"{title} {content}"
    score = 0.0
    score += 0.5 * len(_keyword_hits(text, BUILDABLE_KEYWORDS))
    score += 0.2 * len(_keyword_hits(text, STRUCTURAL_KEYWORDS))
    return score


def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    hits: list[str] = []
    for term in keywords:
        if re.search(rf"\b{re.escape(term)}\b", text):
            hits.append(term)
    return hits


def _week_key(published_at: dt.datetime | None, now_dt: dt.datetime) -> str:
    base = published_at or now_dt
    if base.tzinfo is None:
        base = base.replace(tzinfo=dt.timezone.utc)
    iso = base.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _published_ts(item: dict[str, Any], now_dt: dt.datetime) -> float:
    published = item.get("published_at")
    if not published:
        return now_dt.timestamp()
    if published.tzinfo is None:
        published = published.replace(tzinfo=dt.timezone.utc)
    return published.timestamp()
