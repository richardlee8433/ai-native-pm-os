from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REVALIDATION_DAYS = 28


@dataclass(frozen=True)
class QueueItem:
    id: str
    title: str
    path: str
    validation_status: str
    revalidate_by: str
    revalidate_status: str
    base_date: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "path": self.path,
            "validation_status": self.validation_status,
            "revalidate_by": self.revalidate_by,
            "revalidate_status": self.revalidate_status,
            "base_date": self.base_date,
        }


def build_revalidation_queue(vault_root: Path, *, today: dt.date | None = None) -> dict[str, Any]:
    today_date = today or dt.datetime.now(tz=dt.timezone.utc).date()
    items: list[QueueItem] = []

    for md_path in _scan_lti_notes(vault_root):
        frontmatter = _read_frontmatter(md_path)
        validation_status = (frontmatter.get("validation_status") or "").strip().lower()
        if validation_status != "provisional":
            continue

        revalidate_by_raw = frontmatter.get("revalidate_by")
        revalidate_status_raw = (frontmatter.get("revalidate_status") or "").strip().lower()
        base_date = _resolve_base_date(frontmatter)

        revalidate_by = _resolve_revalidate_by(revalidate_by_raw, base_date)
        revalidate_status = _resolve_revalidate_status(revalidate_status_raw, revalidate_by, today_date)

        item = QueueItem(
            id=frontmatter.get("id", md_path.stem),
            title=_read_title(md_path),
            path=str(md_path.relative_to(vault_root).as_posix()),
            validation_status=validation_status,
            revalidate_by=revalidate_by,
            revalidate_status=revalidate_status,
            base_date=base_date.isoformat() if base_date else None,
        )
        items.append(item)

    items_sorted = sorted(items, key=lambda item: _sort_key(item, today_date))
    generated_at = dt.datetime.now(tz=dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    return {
        "generated_at": generated_at,
        "items": [item.to_dict() for item in items_sorted],
    }


def write_queue_report(vault_root: Path, output_dir: Path, *, today: dt.date | None = None) -> Path:
    payload = build_revalidation_queue(vault_root, today=today)
    report = _render_markdown(payload)
    output_path = _next_report_path(output_dir, "revalidation_queue.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    return output_path


def _scan_lti_notes(vault_root: Path) -> list[Path]:
    roots = [vault_root / "02_LTI", vault_root / "96_Weekly_Review" / "_LTI_Drafts"]
    results: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        results.extend(sorted(root.rglob("LTI-*.md")))
    return results


def _read_frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    return data


def _read_title(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def _parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        if len(value) == 10 and value[4] == "-":
            return dt.date.fromisoformat(value)
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.date()
    except ValueError:
        return None


def _resolve_base_date(frontmatter: dict[str, str]) -> dt.date | None:
    for key in ("last_validated", "updated_at", "created_at", "published_at"):
        parsed = _parse_date(frontmatter.get(key))
        if parsed:
            return parsed
    return None


def _resolve_revalidate_by(raw: str | None, base_date: dt.date | None) -> str:
    parsed = _parse_date(raw)
    if parsed:
        return parsed.isoformat()
    if base_date is None:
        return "unknown"
    return (base_date + dt.timedelta(days=REVALIDATION_DAYS)).isoformat()


def _resolve_revalidate_status(raw: str, revalidate_by: str, today: dt.date) -> str:
    if raw in {"pending", "complete", "overdue", "n/a"}:
        return raw
    if revalidate_by == "unknown":
        return "pending"
    parsed = _parse_date(revalidate_by)
    if parsed and parsed < today:
        return "overdue"
    return "pending"


def _sort_key(item: QueueItem, today: dt.date) -> tuple[int, dt.date]:
    if item.revalidate_by == "unknown":
        return (1, today)
    parsed = _parse_date(item.revalidate_by)
    if parsed is None:
        return (1, today)
    return (0, parsed)


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Provisional LTI Revalidation Queue",
        "",
        f"Generated at: {payload['generated_at']}",
        "",
        "| id | title | revalidate_by | status | path |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in payload["items"]:
        lines.append(
            f"| {item['id']} | {item['title']} | {item['revalidate_by']} | {item['revalidate_status']} | {item['path']} |"
        )
    lines.append("")
    return "\n".join(lines)


def _next_report_path(output_dir: Path, base_name: str) -> Path:
    base_path = output_dir / base_name
    if not base_path.exists():
        return base_path
    stamp = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y%m%d")
    counter = 1
    while True:
        candidate = output_dir / f"revalidation_queue-{stamp}-{counter:03d}.md"
        if not candidate.exists():
            return candidate
        counter += 1
