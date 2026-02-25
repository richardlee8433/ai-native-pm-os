from __future__ import annotations

import datetime as dt
from pathlib import Path

from revalidation.queue import build_revalidation_queue, write_queue_report


def _write_lti(path: Path, *, lti_id: str, title: str, updated_at: str, revalidate_by: str | None = None) -> None:
    frontmatter = [
        "---",
        f"id: {lti_id}",
        "series: LTI-1.x",
        "status: under_review",
        "validation_status: provisional",
        f"updated_at: {updated_at}",
    ]
    if revalidate_by:
        frontmatter.append(f"revalidate_by: {revalidate_by}")
    frontmatter.extend(["---", "", f"# {title}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(frontmatter), encoding="utf-8")


def test_build_revalidation_queue_orders_and_defaults(tmp_path: Path) -> None:
    vault_root = tmp_path
    _write_lti(
        vault_root / "02_LTI" / "LTI-1.0.md",
        lti_id="LTI-1.0",
        title="Alpha",
        updated_at="2026-02-01T00:00:00Z",
    )
    _write_lti(
        vault_root / "02_LTI" / "LTI-1.1.md",
        lti_id="LTI-1.1",
        title="Beta",
        updated_at="2026-01-01T00:00:00Z",
    )

    payload = build_revalidation_queue(vault_root, today=dt.date(2026, 2, 10))
    items = payload["items"]

    assert [item["id"] for item in items] == ["LTI-1.1", "LTI-1.0"]
    assert items[0]["revalidate_by"] == "2026-01-29"
    assert items[0]["revalidate_status"] == "overdue"
    assert items[1]["revalidate_by"] == "2026-03-01"
    assert items[1]["revalidate_status"] == "pending"


def test_write_queue_report_creates_markdown(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    _write_lti(
        vault_root / "02_LTI" / "LTI-2.0.md",
        lti_id="LTI-2.0",
        title="Gamma",
        updated_at="2026-02-10T00:00:00Z",
    )

    output_dir = tmp_path / "docs"
    report_path = write_queue_report(vault_root, output_dir, today=dt.date(2026, 2, 15))

    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "Provisional LTI Revalidation Queue" in content
    assert "LTI-2.0" in content
