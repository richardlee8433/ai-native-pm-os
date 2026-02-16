from __future__ import annotations

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from pm_os_contracts.models import LTI_NODE


def write_lti_markdown(vault_root: Path, node: LTI_NODE, source_task_id: str, *, updated_at: str) -> Path:
    """Write an LTI node as Obsidian-friendly markdown and return the file path."""
    target = vault_root / "02_LTI" / f"{node.id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)

    frontmatter = {
        "id": node.id,
        "series": node.series,
        "status": node.status,
        "published_at": node.published_at.isoformat() if node.published_at else None,
        "linked_evidence": node.linked_evidence or [],
        "tags": node.tags or [],
        "source_task_id": source_task_id,
        "updated_at": updated_at,
    }

    linked_evidence_lines = node.linked_evidence or []
    linked_evidence_body = "\n".join(f"- {evidence}" for evidence in linked_evidence_lines) or "- None"

    content = (
        "---\n"
        f"id: {frontmatter['id']}\n"
        f"series: {frontmatter['series']}\n"
        f"status: {frontmatter['status']}\n"
        f"published_at: {frontmatter['published_at']}\n"
        f"linked_evidence: {frontmatter['linked_evidence']}\n"
        f"tags: {frontmatter['tags']}\n"
        f"source_task_id: {frontmatter['source_task_id']}\n"
        f"updated_at: {frontmatter['updated_at']}\n"
        "---\n\n"
        f"# {node.title}\n\n"
        "## Summary\n"
        f"{node.summary or ''}\n\n"
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
