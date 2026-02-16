from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass
class HTTPResponse:
    text: str
    content: bytes


def http_get(url: str, *, headers: dict[str, str] | None = None, params: dict | None = None, timeout: int = 20) -> HTTPResponse:
    final_url = url
    if params:
        query = urlencode({k: v for k, v in params.items() if v is not None})
        final_url = f"{url}?{query}"
    req = Request(final_url, headers=headers or {})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310
        content = resp.read()
    return HTTPResponse(text=content.decode("utf-8", errors="replace"), content=content)
