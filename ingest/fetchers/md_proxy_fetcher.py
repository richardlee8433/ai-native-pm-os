from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

from ingest.fetchers.common import RateLimiter, parse_datetime
from ingest.fetchers.http import http_get

if TYPE_CHECKING:
    from ingest.registry import SourceConfig

USER_AGENT = "ai-native-pm-os/0.1 (+https://example.local)"
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_SKIP_TITLES = {"skip to main content", "main content"}


class MDProxyFetcher:
    def __init__(self, *, rate_limiter: RateLimiter | None = None) -> None:
        self.rate_limiter = rate_limiter or RateLimiter(min_interval=1.5)

    def fetch(self, source: SourceConfig, *, limit: int) -> list[dict[str, Any]]:
        if not source.url:
            raise ValueError(f"Source '{source.id}' requires a url")

        self.rate_limiter.wait(source.url)
        response = http_get(source.url, headers={"User-Agent": USER_AGENT}, timeout=20)

        items: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for line in response.text.splitlines():
            for title, url in _MARKDOWN_LINK_RE.findall(line):
                cleaned_title = " ".join(title.split())
                if not cleaned_title:
                    continue
                if cleaned_title.lower() in _SKIP_TITLES:
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                date_match = _DATE_RE.search(line)
                items.append(
                    {
                        "title": cleaned_title,
                        "url": url,
                        "published_at": parse_datetime(date_match.group(1) if date_match else None),
                        "content": line.strip(),
                        "raw": {"line": line.strip()},
                    }
                )
                if len(items) >= limit:
                    return items

        return items
