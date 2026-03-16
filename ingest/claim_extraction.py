from __future__ import annotations

import datetime as dt
import hashlib
import re
from typing import Any

from pm_os_contracts.models import ClaimObject

VERSION = "v5.0"

DOMAIN_RULES = {
    "product_development": ["product", "prototype", "workflow", "iteration", "mvp", "build"],
    "governance": ["governance", "policy", "compliance", "decision", "escalation"],
    "evaluation": ["evaluation", "eval", "benchmark", "metric", "quality", "accuracy"],
    "agent_systems": ["agent", "agents", "automation", "tool use", "autonomous"],
}

CONTEXT_RULES = {
    "early product exploration": ["prototype", "mvp", "exploration", "discovery"],
    "operational workflow execution": ["workflow", "process", "execution", "handoff"],
    "governance decision-making": ["governance", "policy", "decision", "escalation"],
}

METRIC_RULES = {
    "iteration speed": ["speed", "faster", "iteration", "ship", "cycle time"],
    "quality": ["quality", "accuracy", "reliability", "correctness"],
    "cost": ["cost", "cheaper", "reduce engineering dependency", "efficiency"],
    "latency": ["latency", "response time"],
}

FAILURE_MODE_RULES = {
    "solution bias": ["solution bias", "premature solution"],
    "governance drift": ["governance drift", "inconsistent policy"],
    "latency overhead": ["latency", "slow"],
    "hallucination risk": ["hallucination", "fabricated", "incorrect"],
}


def extract_claims_from_item(
    *,
    source_id: str,
    source_type: str,
    source_url: str | None,
    item: dict[str, Any],
    extracted_at: dt.datetime,
) -> list[ClaimObject]:
    statements = extract_claim_statements(title=item.get("title"), content=item.get("content"), source_type=source_type)
    claims: list[ClaimObject] = []
    for statement in statements:
        claim = ClaimObject(
            claim_id=build_claim_id(
                source_id=source_id,
                source_type=source_type,
                source_url=source_url,
                claim_statement=statement,
            ),
            claim_statement=statement,
            source_id=source_id,
            source_type=source_type,
            source_url=source_url,
            domain=detect_domain(item),
            context=detect_context(statement, item.get("content")),
            metric=identify_metric(statement, item.get("content")),
            evidence_type=detect_evidence_type(source_type),
            confidence=estimate_confidence(statement, source_type=source_type, item=item),
            assumptions=extract_assumptions(item.get("content")),
            failure_modes=detect_failure_modes(statement, item.get("content")),
            applicability=detect_applicability(statement, item.get("content")),
            rule_candidate=generate_rule_candidate(statement, item.get("content")),
            extracted_at=extracted_at,
            version=VERSION,
        )
        claims.append(claim)
    return claims


def build_claim_id(*, source_id: str, source_type: str, source_url: str | None, claim_statement: str) -> str:
    normalized_statement = _normalize_statement(claim_statement)
    raw = "||".join([source_id.strip().lower(), source_type.strip().lower(), (source_url or "").strip().lower(), normalized_statement])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16].upper()
    return f"CLM-{digest}"


def extract_claim_statements(*, title: str | None, content: str | None, source_type: str) -> list[str]:
    candidates: list[str] = []
    if title:
        candidates.append(title)
    if content:
        candidates.extend(_split_sentences(content))

    output: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        statement = _normalize_statement(candidate)
        if not statement or statement in seen:
            continue
        if len(statement) < 20:
            continue
        if source_type == "rss" and len(output) >= 2:
            break
        if source_type == "newsletter" and len(output) >= 3:
            break
        seen.add(statement)
        output.append(_render_claim_statement(statement))

    if output:
        return output
    fallback = _normalize_statement(content or title or "Untitled claim")
    return [_render_claim_statement(fallback)]


def detect_domain(item: dict[str, Any]) -> str | None:
    categories = item.get("categories") or []
    if categories:
        first = categories[0]
        if isinstance(first, str) and first.strip():
            return first.strip().lower().replace(" ", "_")
    text = f"{item.get('title') or ''} {item.get('content') or ''}".lower()
    for domain, keywords in DOMAIN_RULES.items():
        if any(keyword in text for keyword in keywords):
            return domain
    return None


def detect_context(statement: str, content: str | None) -> str | None:
    text = f"{statement} {content or ''}".lower()
    for context, keywords in CONTEXT_RULES.items():
        if any(keyword in text for keyword in keywords):
            return context
    return None


def identify_metric(statement: str, content: str | None) -> str | None:
    text = f"{statement} {content or ''}".lower()
    for metric, keywords in METRIC_RULES.items():
        if any(keyword in text for keyword in keywords):
            return metric
    return None


def extract_assumptions(content: str | None) -> list[str]:
    if not content:
        return []
    assumptions: list[str] = []
    for sentence in _split_sentences(content):
        lowered = sentence.lower()
        if lowered.startswith("if ") or lowered.startswith("when ") or lowered.startswith("assuming "):
            assumptions.append(_normalize_statement(sentence))
    return assumptions[:3]


def detect_failure_modes(statement: str, content: str | None) -> list[str]:
    text = f"{statement} {content or ''}".lower()
    output: list[str] = []
    for label, keywords in FAILURE_MODE_RULES.items():
        if any(keyword in text for keyword in keywords):
            output.append(label)
    return output


def detect_applicability(statement: str, content: str | None) -> str | None:
    context = detect_context(statement, content)
    if context:
        return context
    text = f"{statement} {content or ''}".lower()
    if "team" in text:
        return "team workflows"
    return None


def generate_rule_candidate(statement: str, content: str | None) -> str | None:
    context = detect_context(statement, content)
    metric = identify_metric(statement, content)
    if context and metric:
        return f"Prefer this practice in {context} when optimizing for {metric}."
    if context:
        return f"Prefer this practice in {context} when the claim matches local evidence."
    return None


def detect_evidence_type(source_type: str) -> str:
    if source_type == "newsletter":
        return "newsletter_article"
    if source_type == "rss":
        return "rss_item"
    return "external_content"


def estimate_confidence(statement: str, *, source_type: str, item: dict[str, Any]) -> float:
    score = 0.55 if source_type == "rss" else 0.65
    if item.get("content"):
        score += 0.1
    if len(statement.split()) >= 8:
        score += 0.05
    return min(score, 0.95)


def _split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    if not normalized:
        return []
    return [part.strip(" -") for part in re.split(r"(?<=[.!?])\s+", normalized) if part.strip(" -")]


def _normalize_statement(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    return normalized.strip(" -")


def _render_claim_statement(statement: str) -> str:
    if not statement.endswith((".", "!", "?")):
        return f"{statement}."
    return statement
