from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from pm_os_contracts.models import LTI_NODE, SIGNAL

_LATEX_INLINE_PATTERN = re.compile(r"\$(.*?)\$|\\\((.*?)\\\)|\\\[(.*?)\\\]", re.DOTALL)
_LATEX_COMMAND_PATTERN = re.compile(r"\\[a-zA-Z]+\*?(?:\{[^{}]*\})?")


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        if re.match(r"^[A-Za-z0-9_./:.-]+$", value):
            return value
        escaped = value.replace('"', '\"')
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
    without_math = _LATEX_INLINE_PATTERN.sub(" ", raw)
    without_commands = _LATEX_COMMAND_PATTERN.sub(" ", without_math)
    return " ".join(without_commands.split())


def _excerpt(content: str | None, *, limit: int = 500) -> str:
    cleaned = _clean_markdown_text(content)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "…"


def write_signal_markdown(vault_root: Path, signal: SIGNAL) -> Path:
    """Write a SIGNAL contract as an Obsidian note under 98_Signals."""
    target = vault_root / "98_Signals" / f"{signal.id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)

    ingested_at = _normalize_datetime(datetime.now(tz=timezone.utc))
    timestamp = _normalize_datetime(signal.timestamp)
    impact_areas = signal.impact_area or []
    impact_body = "\n".join(f"- {area}" for area in impact_areas) if impact_areas else "- none"

    content = (
        "---\n"
        f"id: {_yaml_scalar(signal.id)}\n"
        f"source: {_yaml_scalar(signal.source)}\n"
        f"type: {_yaml_scalar(signal.type)}\n"
        f"timestamp: {_yaml_scalar(timestamp)}\n"
        f"url: {_yaml_scalar(signal.url)}\n"
        f"priority_score: {_yaml_scalar(signal.priority_score)}\n"
        "impact_area:\n"
        f"{_yaml_list(impact_areas)}\n"
        f"ingested_at: {_yaml_scalar(ingested_at)}\n"
        "---\n\n"
        f"# {signal.title or signal.id}\n\n"
        "## Source\n"
        f"{signal.url or ''}\n\n"
        "## Impact Areas\n"
        f"{impact_body}\n\n"
        "## Excerpt\n"
        f"{_excerpt(signal.content)}\n"
    )

    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as tmp:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_name = tmp.name

    os.replace(tmp_name, target)
    return target


def write_lti_markdown(vault_root: Path, node: LTI_NODE, source_task_id: str, *, updated_at: str) -> Path:
    """Write an LTI node as Obsidian-friendly markdown and return the file path."""
    target = vault_root / "02_LTI" / f"{node.id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)

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
        f"updated_at: {_yaml_scalar(_normalize_datetime(updated_at))}\n"
        "summary_sanitized: true\n"
        "---\n\n"
        f"# {node.title}\n\n"
        "## Summary\n"
        f"{cleaned_summary}\n\n"
        "## Linked Evidence\n"
        f"{linked_evidence_body}\n"
    )

    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as tmp:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_name = tmp.name

    os.replace(tmp_name, target)
    return target
