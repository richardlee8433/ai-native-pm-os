from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from claims.store import ClaimStore
from graph.claim_ops import persist_all_claims_to_graph
from ingest.claim_extraction import extract_claims_from_item
from ingest.registry import SourceConfig, get_fetcher, load_sources


def ingest_claims_for_source(
    *,
    root: Path,
    source_id: str,
    source_type: str | None = None,
    sources_path: Path,
    limit: int,
    persist_graph: bool = False,
) -> dict[str, Any]:
    source_cfg = _resolve_source(load_sources(sources_path), source_id=source_id, source_type=source_type)
    if source_cfg is None:
        return {"ok": False, "reason": f"Source not found: {source_id}"}

    mapped_type = map_claim_source_type(source_cfg, override=source_type)
    if mapped_type is None:
        return {
            "ok": False,
            "reason": f"Unsupported claim ingestion source type for {source_cfg.id}",
            "source_id": source_cfg.id,
        }

    items = get_fetcher(source_cfg.type).fetch(source_cfg, limit=limit)
    result = ingest_claims_from_items(
        root=root,
        source_cfg=source_cfg,
        items=items,
        mapped_source_type=mapped_type,
        persist_graph=persist_graph,
    )
    return {
        "ok": True,
        "source_id": source_cfg.id,
        "source_type": mapped_type,
        "fetched_items": len(items),
        **result,
    }


def ingest_claims_from_items(
    *,
    root: Path,
    source_cfg: SourceConfig,
    items: list[dict[str, Any]],
    mapped_source_type: str | None = None,
    extracted_at: dt.datetime | None = None,
    persist_graph: bool = False,
) -> dict[str, Any]:
    claim_source_type = mapped_source_type or map_claim_source_type(source_cfg)
    if claim_source_type is None:
        return {"ok": False, "reason": f"Unsupported claim ingestion source type for {source_cfg.id}"}

    now = extracted_at or dt.datetime.now(tz=dt.timezone.utc)
    store = ClaimStore(root)
    claims = []
    for item in items:
        claims.extend(
            extract_claims_from_item(
                source_id=source_cfg.id,
                source_type=claim_source_type,
                source_url=item.get("url") or source_cfg.url,
                item=item,
                extracted_at=now,
            )
        )

    write_result = store.write_many(claims)
    payload = {
        "ok": True,
        "claims_extracted": len(claims),
        "claims_written": len(write_result["written"]),
        "claims_skipped": len(write_result["skipped"]),
        "claim_ids": write_result["written"],
        "skipped_ids": write_result["skipped"],
    }
    if persist_graph:
        payload["graph_sync"] = persist_all_claims_to_graph(root=root, claim_ids=write_result["written"])
    return payload


def map_claim_source_type(source_cfg: SourceConfig, *, override: str | None = None) -> str | None:
    if override in {"newsletter", "rss"}:
        return override
    if source_cfg.source_type == "pm_newsletter":
        return "newsletter"
    if source_cfg.type == "rss":
        return "rss"
    return None


def _resolve_source(sources: list[SourceConfig], *, source_id: str, source_type: str | None) -> SourceConfig | None:
    for source in sources:
        if source.id == source_id:
            return source
    if source_type is not None:
        for source in sources:
            mapped = map_claim_source_type(source)
            if mapped == source_type and source.id == source_id:
                return source
    return None
