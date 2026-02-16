from __future__ import annotations

import datetime as dt
import email.utils
import re
import time
from urllib.parse import urlparse


class RateLimiter:
    def __init__(self, min_interval: float = 1.5) -> None:
        self.min_interval = min_interval
        self._last_request_by_host: dict[str, float] = {}

    def wait(self, url: str) -> None:
        host = urlparse(url).netloc or "default"
        now = time.monotonic()
        last = self._last_request_by_host.get(host)
        if last is not None:
            delay = self.min_interval - (now - last)
            if delay > 0:
                time.sleep(delay)
        self._last_request_by_host[host] = time.monotonic()


def parse_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None

    # RSS-style dates
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        parsed = None
    if parsed:
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)

    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ):
        try:
            parsed_dt = dt.datetime.strptime(value, fmt)
            if parsed_dt.tzinfo is None:
                parsed_dt = parsed_dt.replace(tzinfo=dt.timezone.utc)
            return parsed_dt
        except ValueError:
            continue

    # partial year/month hints in html pages
    if re.search(r"\b20\d{2}\b", value):
        year = int(re.search(r"\b(20\d{2})\b", value).group(1))
        return dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)

    return None
