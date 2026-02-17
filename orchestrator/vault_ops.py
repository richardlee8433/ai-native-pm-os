from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from pm_os_contracts.models import GATE_DECISION, LTI_NODE, RTI_NODE, SIGNAL

SIGNALS_DIR = "95_Signals"
WEEKLY_DIR = "96_Weekly_Review"
DECISIONS_DIR = "97_Decisions"
LTI_DIR = "02_LTI"
RTI_DIR = "RTI"
LTI_DRAFTS_DIR = "96_Weekly_Review/_LTI_Drafts"
RTI_PROPOSALS_DIR = "97_Decisions/_RTI_Proposals"

_LATEX_INLINE_PATTERN = re.compile(r"\$(.*?)\$|\\\((.*?)\\\)|\\\[(.*?)\\\]", re.DOTALL)
_LATEX_COMMAND_PATTERN = re.compile(r"\\[a-zA-Z]+\*?(?:\{[^{}]*\})?")
_LATEX_TEXTBF_PATTERN = re.compile(r"\\textbf\{([^{}]*)\}")


@dataclass(slots=True)
class SignalScore:
    id: str
    score: float
    preview: str
    url: str | None
    impact_area: list[str]


def resolve_vault_root(cli_override: str | None) -> Path:
    if cli_override:
        return Path(cli_override)
    env_root = os.getenv("PM_OS_VAULT_ROOT")
    if env_root:
        return Path(env_root)
    return Path(".vault_test")


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        if re.match(r"^[A-Za-z0-9_./:.-]+$", value):
            return value
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return str(value)


def _yaml_list(values: list[str] | None, *, indent: int = 2) -> str:
    if not values:
        return "[]"
    prefix = " " * indent
    return "\n".join(f"{prefix}- {_yaml_scalar(value)}" for value in values)


def _normalize_datetime(value: datetime | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_markdown_text(raw: str | None) -> str:
    if not raw:
        return ""
    without_textbf = _LATEX_TEXTBF_PATTERN.sub(r"\1", raw)

    def _inline_repl(match: re.Match[str]) -> str:
        return next((group for group in match.groups() if group is not None), "")

    without_math = _LATEX_INLINE_PATTERN.sub(_inline_repl, without_textbf)
    without_commands = _LATEX_COMMAND_PATTERN.sub(" ", without_math)
    return " ".join(without_commands.split())


def _excerpt(content: str | None, *, limit: int = 500) -> str:
    cleaned = _clean_markdown_text(content)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "…"


def _write_atomic(target: Path, content: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as tmp:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_name = tmp.name

    os.replace(tmp_name, target)
    return target


def write_signal_markdown(vault_root: Path, signal: dict[str, Any] | SIGNAL) -> Path:
    """Write a SIGNAL contract as an Obsidian note under 95_Signals."""
    signal_model = _coerce_signal(signal)
    target = vault_root / SIGNALS_DIR / f"{signal_model.id}.md"

    ingested_at = _normalize_datetime(datetime.now(tz=timezone.utc))
    timestamp = _normalize_datetime(signal_model.timestamp)
    impact_areas = signal_model.impact_area or []

    content = (
        "---\n"
        f"id: {_yaml_scalar(signal_model.id)}\n"
        f"source: {_yaml_scalar(signal_model.source)}\n"
        f"type: {_yaml_scalar(signal_model.type)}\n"
        f"timestamp: {_yaml_scalar(timestamp)}\n"
        f"url: {_yaml_scalar(signal_model.url)}\n"
        f"priority_score: {_yaml_scalar(signal_model.priority_score)}\n"
        "impact_area:\n"
        f"{_yaml_list(impact_areas)}\n"
        f"ingested_at: {_yaml_scalar(ingested_at)}\n"
        "status: raw\n"
        "---\n\n"
        f"# {signal_model.title or signal_model.id}\n\n"
        "## Source\n"
        f"{signal_model.source}\n\n"
        "## Preview\n"
        f"{_excerpt(signal_model.content)}\n"
    )

    if signal_model.url:
        content += f"\nSource URL: {signal_model.url}\n"

    content += "\n## Full Evidence (optional; appended later)\n"

    return _write_atomic(target, content)


def _coerce_signal(signal: dict[str, Any] | SIGNAL) -> SIGNAL:
    if isinstance(signal, SIGNAL):
        return signal
    return SIGNAL.model_validate(signal)


def write_weekly_review(vault_root: Path, week_id: str, shortlist: list[SignalScore]) -> Path:
    target = vault_root / WEEKLY_DIR / f"Weekly-Intel-{week_id}.md"
    rows = sorted(shortlist, key=lambda item: item.score, reverse=True)

    lines = [
        f"# Weekly Intel {week_id}",
        "",
        "## Top-K Shortlist",
        "",
    ]

    if not rows:
        lines.extend(["_No shortlisted signals for this week._", ""])
    else:
        for idx, signal in enumerate(rows, start=1):
            impact = ", ".join(signal.impact_area) if signal.impact_area else "none"
            lines.extend(
                [
                    f"### {idx}. {signal.id} (score: {signal.score:.3f})",
                    f"- preview: {signal.preview}",
                    f"- url: {signal.url or 'n/a'}",
                    f"- impact_area: {impact}",
                    "",
                ]
            )

    return _write_atomic(target, "\n".join(lines))


def write_weekly_review_from_signals(vault_root: Path, week_id: str, signals: list[SIGNAL], *, limit: int = 10) -> Path:
    shortlist = [
        SignalScore(
            id=signal.id,
            score=signal.priority_score or 0.0,
            preview=_excerpt(signal.content, limit=180),
            url=signal.url,
            impact_area=signal.impact_area or [],
        )
        for signal in signals
    ]
    return write_weekly_review(vault_root, week_id, shortlist[:limit])


def write_gate_decision(vault_root: Path, decision: GATE_DECISION) -> Path:
    decided_at = decision.decided_at or datetime.now(tz=timezone.utc)
    week_id = f"{decided_at:%Y}-W{decided_at:%V}"
    base_name = f"DEC-{week_id}-001"
    target = vault_root / DECISIONS_DIR / f"{base_name}.md"

    if target.exists():
        rev = 2
        while True:
            candidate = vault_root / DECISIONS_DIR / f"{base_name}-r{rev}.md"
            if not candidate.exists():
                target = candidate
                break
            rev += 1

    lines = [
        "---",
        f"task_id: {_yaml_scalar(decision.task_id)}",
        f"eval_report_id: {_yaml_scalar(decision.eval_report_id)}",
        f"decision: {_yaml_scalar(decision.decision)}",
        f"destination: {_yaml_scalar(decision.destination)}",
        f"post_action: {_yaml_scalar(decision.post_action)}",
        f"canonical_decision: {_yaml_scalar(decision.canonical_decision)}",
        f"decided_at: {_yaml_scalar(_normalize_datetime(decided_at))}",
        "immutable: true",
        "---",
        "",
        f"# {target.stem}",
        "",
        "## Decision Reason",
        decision.decision_reason or "(none provided)",
        "",
    ]
    return _write_atomic(target, "\n".join(lines))


def _writeback_target_dir(*, artifact_kind: str, human_approved: bool) -> str:
    if artifact_kind == "lti":
        return LTI_DIR if human_approved else LTI_DRAFTS_DIR
    if artifact_kind == "rti":
        return RTI_DIR if human_approved else RTI_PROPOSALS_DIR
    raise ValueError(f"Unsupported artifact kind: {artifact_kind}")


def write_lti_markdown(
    vault_root: Path,
    node: LTI_NODE,
    source_task_id: str,
    *,
    updated_at: str,
    source_signal_id: str | None = None,
    source_url: str | None = None,
    impact_area: list[str] | None = None,
    human_approved: bool = False,
    publish_intent: str | None = None,
) -> Path:
    """Write an LTI markdown note; unapproved writes are routed to draft staging."""
    dir_name = _writeback_target_dir(artifact_kind="lti", human_approved=human_approved)
    target = vault_root / dir_name / f"{node.id}.md"

    linked_evidence_lines = node.linked_evidence or []
    linked_evidence_body = "\n".join(f"- {evidence}" for evidence in linked_evidence_lines) or "- None"
    cleaned_summary = _clean_markdown_text(node.summary)

    content = (
        "---\n"
        f"id: {_yaml_scalar(node.id)}\n"
        f"series: {_yaml_scalar(node.series)}\n"
        f"status: {_yaml_scalar(node.status)}\n"
        f"published_at: {_yaml_scalar(node.published_at.isoformat() if node.published_at else None)}\n"
        f"confidence_level: {_yaml_scalar(node.confidence_level)}\n"
        "linked_evidence:\n"
        f"{_yaml_list(node.linked_evidence or [])}\n"
        "linked_rti:\n"
        f"{_yaml_list(node.linked_rti or [])}\n"
        "tags:\n"
        f"{_yaml_list(node.tags or [])}\n"
        f"source_task_id: {_yaml_scalar(source_task_id)}\n"
        f"source_signal_id: {_yaml_scalar(source_signal_id)}\n"
        f"source_url: {_yaml_scalar(source_url)}\n"
        "impact_area:\n"
        f"{_yaml_list(impact_area or [])}\n"
        f"updated_at: {_yaml_scalar(_normalize_datetime(updated_at))}\n"
        f"human_approved: {_yaml_scalar(human_approved)}\n"
        f"publish_intent: {_yaml_scalar(publish_intent)}\n"
        "summary_sanitized: true\n"
        "---\n\n"
        f"# {node.title}\n\n"
        "## Summary\n"
        f"{cleaned_summary}\n\n"
        "## Linked Evidence\n"
        f"{linked_evidence_body}\n"
    )

    return _write_atomic(target, content)


def write_rti_markdown(
    vault_root: Path,
    node: RTI_NODE,
    *,
    updated_at: str,
    human_approved: bool = False,
    rti_intent: str | None = None,
) -> Path:
    dir_name = _writeback_target_dir(artifact_kind="rti", human_approved=human_approved)
    target = vault_root / dir_name / f"{node.id}.md"

    content = (
        "---\n"
        f"id: {_yaml_scalar(node.id)}\n"
        f"title: {_yaml_scalar(node.title)}\n"
        f"status: {_yaml_scalar(node.status)}\n"
        f"category: {_yaml_scalar(node.category)}\n"
        f"confidence_level: {_yaml_scalar(node.confidence_level)}\n"
        f"last_validated: {_yaml_scalar(node.last_validated.isoformat() if node.last_validated else None)}\n"
        "linked_evidence:\n"
        f"{_yaml_list(node.linked_evidence or [])}\n"
        "linked_lti:\n"
        f"{_yaml_list(node.linked_lti or [])}\n"
        "linked_cos_patterns:\n"
        f"{_yaml_list(node.linked_cos_patterns or [])}\n"
        f"revision_trigger_count: {_yaml_scalar(node.revision_trigger_count)}\n"
        f"updated_at: {_yaml_scalar(_normalize_datetime(updated_at))}\n"
        f"human_approved: {_yaml_scalar(human_approved)}\n"
        f"rti_intent: {_yaml_scalar(rti_intent)}\n"
        "---\n\n"
        f"# {node.title}\n"
    )
    return _write_atomic(target, content)


def current_week_id(today: date | None = None) -> str:
    base = today or datetime.now(tz=timezone.utc).date()
    return f"{base:%Y}-W{base:%V}"
