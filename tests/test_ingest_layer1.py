from __future__ import annotations

import datetime as dt
from pathlib import Path

from ingest.fetchers.arxiv_fetcher import ArxivFetcher
from ingest.fetchers.html_list_fetcher import HTMLListFetcher
from ingest.fetchers.rss_fetcher import RSSFetcher
from ingest.normalize import normalize_item_to_signal
from ingest.registry import SourceConfig
from ingest.store import append_signals
from ingest.validation import validate_signal_contract


def test_rss_fetcher_parses_entries(monkeypatch) -> None:
    fixture = Path("tests/fixtures/feeds/openai_news.xml")

    def fake_get(*args, **kwargs):
        from ingest.fetchers.http import HTTPResponse

        data = fixture.read_bytes()
        return HTTPResponse(text=data.decode("utf-8"), content=data)

    monkeypatch.setattr("ingest.fetchers.rss_fetcher.http_get", fake_get)
    fetcher = RSSFetcher()
    source = SourceConfig(id="openai", type="rss", url="https://example.com/rss.xml")
    items = fetcher.fetch(source, limit=5)
    assert len(items) == 2
    assert items[0]["url"] == "https://openai.com/news/agent-sdk"


def test_arxiv_fetcher_parses_entries(monkeypatch) -> None:
    fixture = Path("tests/fixtures/feeds/arxiv_sample.xml")

    def fake_get(*args, **kwargs):
        from ingest.fetchers.http import HTTPResponse

        data = fixture.read_bytes()
        return HTTPResponse(text=data.decode("utf-8"), content=data)

    monkeypatch.setattr("ingest.fetchers.arxiv_fetcher.http_get", fake_get)
    fetcher = ArxivFetcher()
    source = SourceConfig(id="arxiv", type="arxiv", base_url="http://example.test/api", search_query="cat:cs.AI")
    items = fetcher.fetch(source, limit=3)
    assert len(items) == 1
    assert items[0]["authors"] == ["Jane Doe"]


def test_html_list_fetcher_extracts_links(monkeypatch) -> None:
    fixture = Path("tests/fixtures/html/anthropic_news.html")

    def fake_get(*args, **kwargs):
        from ingest.fetchers.http import HTTPResponse

        text = fixture.read_text(encoding="utf-8")
        return HTTPResponse(text=text, content=text.encode("utf-8"))

    monkeypatch.setattr("ingest.fetchers.html_list_fetcher.http_get", fake_get)
    fetcher = HTMLListFetcher()
    source = SourceConfig(
        id="anthropic",
        type="html_list",
        url="https://www.anthropic.com/news",
        link_selector="a[href^='/news/']",
        date_hint=True,
    )
    items = fetcher.fetch(source, limit=5)
    assert len(items) == 1
    assert items[0]["url"] == "https://www.anthropic.com/news/claude-agents"


def test_normalize_outputs_contract_valid_signal() -> None:
    now = dt.datetime(2026, 2, 13, tzinfo=dt.timezone.utc)
    source = SourceConfig(id="openai", name="OpenAI News", type="rss", signal_type="capability", weight=0.9)
    item = {
        "title": "Agent eval toolkit released",
        "url": "https://openai.com/news/toolkit",
        "published_at": now - dt.timedelta(days=1),
        "content": "Includes safety evaluation and multimodal support",
    }
    signal = normalize_item_to_signal(source, item, seq_num=1, now_utc=now)
    validate_signal_contract(signal)
    assert signal.id == "SIG-20260213-001"
    assert signal.priority_score is not None and signal.priority_score > 0


def test_store_dedupe_by_url(tmp_path) -> None:
    out = tmp_path / "signals.jsonl"
    idx = tmp_path / "signals_index.json"
    now = dt.datetime(2026, 2, 13, tzinfo=dt.timezone.utc)
    source = SourceConfig(id="openai", name="OpenAI News", type="rss", signal_type="capability", weight=0.9)
    item = {
        "title": "Agent eval toolkit released",
        "url": "https://openai.com/news/toolkit",
        "published_at": now,
        "content": "summary",
    }
    first = normalize_item_to_signal(source, item, seq_num=1, now_utc=now)
    second = normalize_item_to_signal(source, item, seq_num=2, now_utc=now)

    written1, skipped1 = append_signals(out, [first], index_path=idx)
    written2, skipped2 = append_signals(out, [second], index_path=idx)

    assert (written1, skipped1) == (1, 0)
    assert (written2, skipped2) == (0, 1)
