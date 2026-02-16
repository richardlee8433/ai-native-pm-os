from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - fallback path
    yaml = None

from ingest.fetchers.arxiv_fetcher import ArxivFetcher
from ingest.fetchers.html_list_fetcher import HTMLListFetcher
from ingest.fetchers.md_proxy_fetcher import MDProxyFetcher
from ingest.fetchers.rss_fetcher import RSSFetcher


@dataclass(slots=True)
class SourceConfig:
    id: str
    type: str
    url: str | None = None
    base_url: str | None = None
    signal_type: str = "research"
    weight: float = 0.5
    name: str | None = None
    include_pattern: str | None = None
    link_selector: str | None = None
    title_selector: str | None = None
    date_hint: bool = False
    fetch_article_body: bool = False
    search_query: str | None = None
    sortBy: str | None = None
    sortOrder: str | None = None
    max_results: int | None = None
    query: str | None = None
    priority_weight: float | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SourceConfig":
        normalized = dict(payload)

        if normalized.get("priority_weight") is not None and normalized.get("weight") is None:
            normalized["weight"] = normalized["priority_weight"]

        if normalized.get("query") is not None and normalized.get("search_query") is None:
            normalized["search_query"] = normalized["query"]

        return cls(**normalized)


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _minimal_yaml_load(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            if current:
                items.append(current)
            current = {}
            line = line[2:]
            if line:
                key, value = line.split(":", 1)
                current[key.strip()] = _parse_scalar(value)
            continue
        if current is None:
            continue
        key, value = line.split(":", 1)
        current[key.strip()] = _parse_scalar(value)

    if current:
        items.append(current)
    return items


def load_sources(path: str | Path) -> list[SourceConfig]:
    config_path = Path(path)
    raw_text = config_path.read_text(encoding="utf-8")
    if yaml is not None:
        source_list = yaml.safe_load(raw_text) or []
    else:
        source_list = _minimal_yaml_load(raw_text)
    return [SourceConfig.from_dict(row) for row in source_list]


def get_fetcher(source_type: str):
    if source_type == "rss":
        return RSSFetcher()
    if source_type in {"arxiv", "arxiv_api"}:
        return ArxivFetcher()
    if source_type == "html_list":
        return HTMLListFetcher()
    if source_type == "md_proxy":
        return MDProxyFetcher()
    raise ValueError(f"Unsupported source type: {source_type}")
