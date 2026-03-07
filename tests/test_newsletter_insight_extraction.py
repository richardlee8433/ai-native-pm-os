from __future__ import annotations

import datetime as dt

from ingest.newsletter_governance import process_newsletter_source
from ingest.registry import SourceConfig


def test_insight_extraction_drives_claim_and_idea(tmp_path) -> None:
    cfg = SourceConfig(id="lenny", type="html_list", url="https://example.com", source_type="pm_newsletter")
    now = dt.datetime(2026, 3, 6, tzinfo=dt.timezone.utc)
    items = [
        {
            "title": "How Perplexity builds product",
            "content": "Perplexity shortens product learning cycles by shipping rapidly and collecting direct user feedback through a rapid experiment workflow.",
            "url": "https://example.com/post",
            "published_at": now,
        }
    ]

    payload = process_newsletter_source(source_cfg=cfg, items=items, root=tmp_path, now=now)
    decision = payload["decisions"][0]

    assert decision["core_claim"] != items[0]["title"]
    assert "If we apply" in decision["hypothesis_statement"]
    assert "shipping rapidly" in decision["hypothesis_statement"]
    assert "learning cycles" in decision["hypothesis_statement"]
    assert "shipping rapidly" in decision["seven_day_validation_idea"]
