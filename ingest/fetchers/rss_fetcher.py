from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any


from ingest.fetchers.common import RateLimiter, parse_datetime
from ingest.fetchers.http import http_get
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ingest.registry import SourceConfig

USER_AGENT = "ai-native-pm-os/0.1 (+https://example.local)"


class RSSFetcher:
    def __init__(self, *, rate_limiter: RateLimiter | None = None) -> None:
        self.rate_limiter = rate_limiter or RateLimiter(min_interval=1.5)

    def fetch(self, source: SourceConfig, *, limit: int) -> list[dict[str, Any]]:
        if not source.url:
            raise ValueError(f"Source '{source.id}' requires a url")

        self.rate_limiter.wait(source.url)
        response = http_get(source.url, headers={"User-Agent": USER_AGENT}, timeout=20)

        root = ET.fromstring(response.content)
        items: list[dict[str, Any]] = []
        for item in root.findall("./channel/item")[:limit]:
            items.append(
                {
                    "title": _text(item.find("title")),
                    "url": _text(item.find("link")),
                    "published_at": parse_datetime(_text(item.find("pubDate")) or _text(item.find("published"))),
                    "content": _text(item.find("description")) or _text(item.find("summary")),
                    "authors": [],
                    "categories": [_text(c) for c in item.findall("category") if _text(c)],
                    "raw": {},
                }
            )
        return items


def _text(node: ET.Element | None) -> str | None:
    if node is None or node.text is None:
        return None
    return node.text.strip()
