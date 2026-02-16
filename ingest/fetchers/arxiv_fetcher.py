from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any


from ingest.fetchers.common import RateLimiter, parse_datetime
from ingest.fetchers.http import http_get
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ingest.registry import SourceConfig

USER_AGENT = "ai-native-pm-os/0.1 (+https://example.local)"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


class ArxivFetcher:
    def __init__(self, *, rate_limiter: RateLimiter | None = None) -> None:
        self.rate_limiter = rate_limiter or RateLimiter(min_interval=1.5)

    def fetch(self, source: SourceConfig, *, limit: int) -> list[dict[str, Any]]:
        base_url = source.base_url or source.url
        if not base_url:
            raise ValueError(f"Source '{source.id}' requires base_url or url")

        params = {
            "search_query": source.search_query,
            "sortBy": source.sortBy or "submittedDate",
            "sortOrder": source.sortOrder or "descending",
            "max_results": min(limit, source.max_results or limit),
        }

        self.rate_limiter.wait(base_url)
        response = http_get(base_url, params=params, headers={"User-Agent": USER_AGENT}, timeout=25)

        root = ET.fromstring(response.content)
        items: list[dict[str, Any]] = []
        for entry in root.findall("atom:entry", ATOM_NS)[:limit]:
            title = _text(entry.find("atom:title", ATOM_NS))
            url = _text(entry.find("atom:id", ATOM_NS))
            published = _text(entry.find("atom:published", ATOM_NS)) or _text(entry.find("atom:updated", ATOM_NS))
            authors = [_text(node.find("atom:name", ATOM_NS)) for node in entry.findall("atom:author", ATOM_NS)]
            categories = [node.get("term") for node in entry.findall("atom:category", ATOM_NS)]
            items.append(
                {
                    "title": title,
                    "url": url,
                    "published_at": parse_datetime(published),
                    "content": _text(entry.find("atom:summary", ATOM_NS)),
                    "authors": [a for a in authors if a],
                    "categories": [c for c in categories if c],
                    "raw": {},
                }
            )
        return items


def _text(node: ET.Element | None) -> str | None:
    if node is None or node.text is None:
        return None
    return node.text.strip()
