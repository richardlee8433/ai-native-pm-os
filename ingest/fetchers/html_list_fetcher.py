from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin


from ingest.fetchers.common import RateLimiter, parse_datetime
from ingest.fetchers.http import http_get
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ingest.registry import SourceConfig

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # pragma: no cover - fallback parser
    BeautifulSoup = None

USER_AGENT = "ai-native-pm-os/0.1 (+https://example.local)"
DATE_RE = re.compile(r"(?:20\d{2}[-/]\d{1,2}[-/]\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d{2})", re.IGNORECASE)


class HTMLListFetcher:
    def __init__(self, *, rate_limiter: RateLimiter | None = None) -> None:
        self.rate_limiter = rate_limiter or RateLimiter(min_interval=1.5)

    def fetch(self, source: SourceConfig, *, limit: int) -> list[dict[str, Any]]:
        if not source.url:
            raise ValueError(f"Source '{source.id}' requires a url")

        self.rate_limiter.wait(source.url)
        response = http_get(source.url, headers={"User-Agent": USER_AGENT}, timeout=20)

        if BeautifulSoup is None:
            links = _fallback_extract_links(response.text)
            return _normalize_link_rows(links, source, limit)

        soup = BeautifulSoup(response.text, "html.parser")
        anchors = soup.select(source.link_selector or "a[href]")
        pattern = re.compile(source.include_pattern) if source.include_pattern else None
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for anchor in anchors:
            href = anchor.get("href")
            if not href:
                continue
            full_url = urljoin(source.url, href)
            if pattern and not pattern.search(full_url):
                continue
            if full_url in seen:
                continue
            seen.add(full_url)

            title = (anchor.get_text(" ", strip=True) or None)
            container = anchor.find_parent() or anchor
            container_text = container.get_text(" ", strip=True)
            date_text = None
            time_tag = container.find("time")
            if time_tag:
                date_text = time_tag.get("datetime") or time_tag.get_text(" ", strip=True)
            if not date_text and source.date_hint:
                match = DATE_RE.search(container_text)
                if match:
                    date_text = match.group(0)

            items.append(
                {
                    "title": title,
                    "url": full_url,
                    "published_at": parse_datetime(date_text),
                    "content": container_text[:500] if container_text else None,
                    "raw": {"date_text": date_text},
                }
            )
            if len(items) >= limit:
                break

        return items


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._current_href = dict(attrs).get("href")
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_href:
            self.links.append((self._current_href, " ".join(self._current_text).strip()))
            self._current_href = None
            self._current_text = []


def _fallback_extract_links(html: str) -> list[dict[str, str]]:
    parser = _AnchorParser()
    parser.feed(html)
    return [{"href": href, "title": title} for href, title in parser.links]


def _normalize_link_rows(rows: list[dict[str, str]], source: SourceConfig, limit: int) -> list[dict[str, Any]]:
    pattern = re.compile(source.include_pattern) if source.include_pattern else None
    items: list[dict[str, Any]] = []
    for row in rows:
        href = row.get("href")
        if not href:
            continue
        full_url = urljoin(source.url or "", href)
        if pattern and not pattern.search(full_url):
            continue
        items.append(
            {
                "title": row.get("title"),
                "url": full_url,
                "published_at": None,
                "content": row.get("title"),
                "raw": {},
            }
        )
        if len(items) >= limit:
            break
    return items
