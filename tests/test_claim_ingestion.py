from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from claims.store import ClaimStore
from ingest.claim_pipeline import ingest_claims_for_source, ingest_claims_from_items
from ingest.registry import SourceConfig
from pmos import cli


def test_newsletter_claim_ingestion_from_items_is_deterministic(tmp_path: Path) -> None:
    cfg = SourceConfig(
        id="lennys_newsletter",
        name="Lenny's Newsletter",
        type="html_list",
        url="https://example.com",
        source_type="pm_newsletter",
    )
    now = dt.datetime(2026, 3, 16, 12, 0, tzinfo=dt.timezone.utc)
    items = [
        {
            "title": "Prototype a new PM workflow",
            "content": "AI prototyping accelerates product iteration. Teams can validate ideas faster.",
            "url": "https://example.com/post-1",
            "published_at": now,
        }
    ]

    first = ingest_claims_from_items(root=tmp_path, source_cfg=cfg, items=items, extracted_at=now)
    second = ingest_claims_from_items(root=tmp_path, source_cfg=cfg, items=items, extracted_at=now)

    assert first["ok"] is True
    assert first["claims_extracted"] >= 1
    assert first["claims_written"] >= 1
    assert second["claims_written"] == 0
    assert second["claims_skipped"] == first["claims_extracted"]

    stored = ClaimStore(tmp_path).list()
    assert stored
    assert all(item["source_type"] == "newsletter" for item in stored)
    assert all(item["version"] == "v5.0" for item in stored)


def test_rss_claim_ingestion_from_items_is_deterministic(tmp_path: Path) -> None:
    cfg = SourceConfig(id="openai_news", name="OpenAI News", type="rss", url="https://example.com/rss.xml")
    now = dt.datetime(2026, 3, 16, 12, 0, tzinfo=dt.timezone.utc)
    items = [
        {
            "title": "Agent eval toolkit released",
            "content": "Includes safety evaluation and multimodal support. Teams can measure quality faster.",
            "url": "https://example.com/news/toolkit",
            "published_at": now,
            "categories": ["Research"],
        }
    ]

    first = ingest_claims_from_items(root=tmp_path, source_cfg=cfg, items=items, extracted_at=now)
    second = ingest_claims_from_items(root=tmp_path, source_cfg=cfg, items=items, extracted_at=now)

    assert first["ok"] is True
    assert first["claims_extracted"] >= 1
    assert second["claims_written"] == 0

    stored = ClaimStore(tmp_path).list()
    assert stored[0]["source_type"] == "rss"
    assert stored[0]["claim_id"].startswith("CLM-")


def test_claim_ingest_cli_for_newsletter(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("PMOS_V5_CLAIMS_ENABLED", "true")
    monkeypatch.setenv("PMOS_V5_CLAIM_INGEST_ENABLED", "true")

    cfg = SourceConfig(
        id="lennys_newsletter",
        name="Lenny's Newsletter",
        type="html_list",
        url="https://example.com",
        source_type="pm_newsletter",
    )

    class _Fetcher:
        def fetch(self, source_cfg, *, limit):
            return [
                {
                    "title": "Prototype a new PM workflow",
                    "content": "Build an MVP workflow experiment. AI prototyping accelerates product iteration.",
                    "url": "https://example.com/post-1",
                    "published_at": dt.datetime(2026, 3, 16, 12, 0, tzinfo=dt.timezone.utc),
                }
            ]

    monkeypatch.setattr("ingest.claim_pipeline.load_sources", lambda path: [cfg])
    monkeypatch.setattr("ingest.claim_pipeline.get_fetcher", lambda source_type: _Fetcher())

    rc = cli.main(["--root", str(tmp_path), "claim", "ingest", "lennys_newsletter"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["source_type"] == "newsletter"
    assert payload["claims_written"] >= 1


def test_claim_ingest_cli_for_rss(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("PMOS_V5_CLAIMS_ENABLED", "true")
    monkeypatch.setenv("PMOS_V5_CLAIM_INGEST_ENABLED", "true")

    cfg = SourceConfig(id="openai_news", name="OpenAI News", type="rss", url="https://example.com/rss.xml")

    class _Fetcher:
        def fetch(self, source_cfg, *, limit):
            return [
                {
                    "title": "Agent eval toolkit released",
                    "content": "Includes safety evaluation and multimodal support.",
                    "url": "https://example.com/news/toolkit",
                    "published_at": dt.datetime(2026, 3, 16, 12, 0, tzinfo=dt.timezone.utc),
                }
            ]

    monkeypatch.setattr("ingest.claim_pipeline.load_sources", lambda path: [cfg])
    monkeypatch.setattr("ingest.claim_pipeline.get_fetcher", lambda source_type: _Fetcher())

    rc = cli.main(["--root", str(tmp_path), "claim", "ingest", "openai_news"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["source_type"] == "rss"
    assert payload["claims_written"] >= 1


def test_ingest_claims_for_source_rejects_unsupported_type(tmp_path: Path) -> None:
    cfg = SourceConfig(id="arxiv_ai", name="arXiv", type="arxiv_api", url="https://example.com")
    result = ingest_claims_from_items(root=tmp_path, source_cfg=cfg, items=[], extracted_at=dt.datetime(2026, 3, 16, tzinfo=dt.timezone.utc))
    assert result["ok"] is False


def test_claim_ingest_cli_disabled_by_feature_flag(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("PMOS_V5_CLAIM_INGEST_ENABLED", raising=False)
    rc = cli.main(["--root", str(tmp_path), "claim", "ingest", "openai_news"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "PMOS_V5_CLAIM_INGEST_ENABLED is not enabled"
