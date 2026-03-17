from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from claims.store import ClaimStore
from orchestrator.storage import JSONLStorage
from pm_os_contracts.models import ClaimObject

ClaimGraphNodeType = Literal["claim", "context", "metric", "failure_mode", "evidence"]
ClaimGraphRelationType = Literal[
    "applies_to",
    "supports",
    "contradicts",
    "derived_from",
    "measured_by",
    "exposed_to",
]

CLAIM_GRAPH_VERSION = "v5.0"


@dataclass(frozen=True)
class ClaimGraphNodeRecord:
    node_id: str
    node_type: ClaimGraphNodeType
    title: str
    slug: str
    created_at: str
    updated_at: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "title": self.title,
            "slug": self.slug,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": CLAIM_GRAPH_VERSION,
        }
        payload.update(self.extra)
        return payload


@dataclass(frozen=True)
class ClaimGraphEdgeRecord:
    edge_id: str
    from_node_id: str
    to_node_id: str
    relation_type: ClaimGraphRelationType
    created_at: str
    updated_at: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "edge_id": self.edge_id,
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "relation_type": self.relation_type,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": CLAIM_GRAPH_VERSION,
        }
        payload.update(self.extra)
        return payload


class ClaimGraphStore:
    """Append-only typed graph store for v5.0 claim graph persistence."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.graph_dir = self.root / "graph"
        self.nodes_path = self.graph_dir / "claim_graph_nodes.jsonl"
        self.edges_path = self.graph_dir / "claim_graph_edges.jsonl"
        self.node_index_path = self.graph_dir / "claim_graph_node_index.json"
        self.edge_index_path = self.graph_dir / "claim_graph_edge_index.json"
        self.claim_index_path = self.graph_dir / "claim_graph_claim_index.json"
        self.node_store = JSONLStorage(self.nodes_path)
        self.edge_store = JSONLStorage(self.edges_path)

    def upsert_node(
        self,
        *,
        node_id: str,
        node_type: ClaimGraphNodeType,
        title: str,
        slug: str,
        extra: dict[str, Any] | None = None,
        now: dt.datetime | None = None,
    ) -> dict[str, Any]:
        now_iso = _as_iso(now)
        current = self.get_node(node_id)
        payload = ClaimGraphNodeRecord(
            node_id=node_id,
            node_type=node_type,
            title=title,
            slug=slug,
            created_at=current["created_at"] if current else now_iso,
            updated_at=now_iso,
            extra=dict(extra or {}),
        ).to_dict()
        if current and _node_semantics_match(current, payload):
            return current
        if current:
            payload["created_at"] = current["created_at"]
        self.node_store.append(payload)
        index = self._read_index(self.node_index_path)
        index[node_id] = payload
        self._write_index(self.node_index_path, index)
        claim_id = payload.get("claim_id")
        if isinstance(claim_id, str) and claim_id:
            claim_index = self._read_index(self.claim_index_path)
            claim_index[claim_id] = node_id
            self._write_index(self.claim_index_path, claim_index)
        return payload

    def upsert_edge(
        self,
        *,
        edge_id: str,
        from_node_id: str,
        to_node_id: str,
        relation_type: ClaimGraphRelationType,
        extra: dict[str, Any] | None = None,
        now: dt.datetime | None = None,
    ) -> dict[str, Any]:
        now_iso = _as_iso(now)
        current = self.get_edge(edge_id)
        payload = ClaimGraphEdgeRecord(
            edge_id=edge_id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            relation_type=relation_type,
            created_at=current["created_at"] if current else now_iso,
            updated_at=now_iso,
            extra=dict(extra or {}),
        ).to_dict()
        if current and _edge_semantics_match(current, payload):
            return current
        if current:
            payload["created_at"] = current["created_at"]
        self.edge_store.append(payload)
        index = self._read_index(self.edge_index_path)
        index[edge_id] = payload
        self._write_index(self.edge_index_path, index)
        return payload

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self._read_index(self.node_index_path).get(node_id)

    def get_claim_node(self, claim_id: str) -> dict[str, Any] | None:
        node_id = self._read_index(self.claim_index_path).get(claim_id)
        if not node_id:
            return None
        return self.get_node(node_id)

    def get_edge(self, edge_id: str) -> dict[str, Any] | None:
        return self._read_index(self.edge_index_path).get(edge_id)

    def list_edges_for_node(self, node_id: str, relation_type: str | None = None) -> list[dict[str, Any]]:
        edges = []
        for edge in self._read_index(self.edge_index_path).values():
            if edge["from_node_id"] != node_id and edge["to_node_id"] != node_id:
                continue
            if relation_type and edge["relation_type"] != relation_type:
                continue
            edges.append(edge)
        edges.sort(key=lambda item: (item["relation_type"], item["edge_id"]))
        return edges

    def _read_index(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_index(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def persist_claim_to_graph(
    *,
    root: Path,
    claim: ClaimObject | dict[str, Any],
    supports_claim_ids: list[str] | None = None,
    contradicts_claim_ids: list[str] | None = None,
    legacy_hypothesis_id: str | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    claim_obj = claim if isinstance(claim, ClaimObject) else ClaimObject.from_dict(claim)
    store = ClaimGraphStore(root)
    node = store.upsert_node(
        node_id=claim_node_id(claim_obj.claim_id),
        node_type="claim",
        title=claim_obj.claim_statement,
        slug=_slugify(claim_obj.claim_statement),
        extra={
            "claim_id": claim_obj.claim_id,
            "claim_statement": claim_obj.claim_statement,
            "source_id": claim_obj.source_id,
            "source_type": claim_obj.source_type,
            "source_url": claim_obj.source_url,
            "version": claim_obj.version,
            "extracted_at": claim_obj.extracted_at.isoformat().replace("+00:00", "Z"),
            "domain": claim_obj.domain,
            "applicability": claim_obj.applicability,
            "confidence": claim_obj.confidence,
            "evidence_type": claim_obj.evidence_type,
            "assumptions": claim_obj.assumptions or [],
            "failure_modes": claim_obj.failure_modes or [],
            "rule_candidate": claim_obj.rule_candidate,
        },
        now=now,
    )

    node_ids = {node["node_id"]}
    edge_ids: set[str] = set()

    if claim_obj.context:
        context_node = store.upsert_node(
            node_id=typed_node_id("context", claim_obj.context),
            node_type="context",
            title=claim_obj.context,
            slug=_slugify(claim_obj.context),
            extra={"value": claim_obj.context},
            now=now,
        )
        node_ids.add(context_node["node_id"])
        edge_ids.add(
            _upsert_relation(
                store=store,
                from_node_id=node["node_id"],
                to_node_id=context_node["node_id"],
                relation_type="applies_to",
                extra={"claim_id": claim_obj.claim_id},
                now=now,
            )["edge_id"]
        )

    if claim_obj.metric:
        metric_node = store.upsert_node(
            node_id=typed_node_id("metric", claim_obj.metric),
            node_type="metric",
            title=claim_obj.metric,
            slug=_slugify(claim_obj.metric),
            extra={"value": claim_obj.metric},
            now=now,
        )
        node_ids.add(metric_node["node_id"])
        edge_ids.add(
            _upsert_relation(
                store=store,
                from_node_id=node["node_id"],
                to_node_id=metric_node["node_id"],
                relation_type="measured_by",
                extra={"claim_id": claim_obj.claim_id},
                now=now,
            )["edge_id"]
        )

    for failure_mode in claim_obj.failure_modes or []:
        failure_node = store.upsert_node(
            node_id=typed_node_id("failure_mode", failure_mode),
            node_type="failure_mode",
            title=failure_mode,
            slug=_slugify(failure_mode),
            extra={"value": failure_mode},
            now=now,
        )
        node_ids.add(failure_node["node_id"])
        edge_ids.add(
            _upsert_relation(
                store=store,
                from_node_id=node["node_id"],
                to_node_id=failure_node["node_id"],
                relation_type="exposed_to",
                extra={"claim_id": claim_obj.claim_id},
                now=now,
            )["edge_id"]
        )

    evidence_node = store.upsert_node(
        node_id=evidence_node_id(
            source_id=claim_obj.source_id,
            source_type=claim_obj.source_type,
            source_url=claim_obj.source_url,
        ),
        node_type="evidence",
        title=claim_obj.source_url or claim_obj.source_id,
        slug=_slugify(claim_obj.source_url or claim_obj.source_id),
        extra={
            "source_id": claim_obj.source_id,
            "source_type": claim_obj.source_type,
            "source_url": claim_obj.source_url,
            "evidence_type": claim_obj.evidence_type,
        },
        now=now,
    )
    node_ids.add(evidence_node["node_id"])
    edge_ids.add(
        _upsert_relation(
            store=store,
            from_node_id=node["node_id"],
            to_node_id=evidence_node["node_id"],
            relation_type="derived_from",
            extra={"claim_id": claim_obj.claim_id, "origin": "source"},
            now=now,
        )["edge_id"]
    )

    for relation_type, target_ids in (
        ("supports", supports_claim_ids or []),
        ("contradicts", contradicts_claim_ids or []),
    ):
        for target_claim_id in target_ids:
            target_node = ensure_claim_placeholder(store=store, claim_id=target_claim_id, now=now)
            node_ids.add(target_node["node_id"])
            edge_ids.add(
                _upsert_relation(
                    store=store,
                    from_node_id=node["node_id"],
                    to_node_id=target_node["node_id"],
                    relation_type=relation_type,
                    extra={"from_claim_id": claim_obj.claim_id, "to_claim_id": target_claim_id},
                    now=now,
                )["edge_id"]
            )

    if legacy_hypothesis_id:
        legacy_node = store.upsert_node(
            node_id=typed_node_id("evidence", f"legacy:{legacy_hypothesis_id}"),
            node_type="evidence",
            title=legacy_hypothesis_id,
            slug=_slugify(legacy_hypothesis_id),
            extra={"origin": "legacy_hypothesis", "legacy_hypothesis_id": legacy_hypothesis_id},
            now=now,
        )
        node_ids.add(legacy_node["node_id"])
        edge_ids.add(
            _upsert_relation(
                store=store,
                from_node_id=node["node_id"],
                to_node_id=legacy_node["node_id"],
                relation_type="derived_from",
                extra={"claim_id": claim_obj.claim_id, "origin": "legacy_hypothesis"},
                now=now,
            )["edge_id"]
        )

    return {
        "claim_id": claim_obj.claim_id,
        "node_id": node["node_id"],
        "node": node,
        "node_count": len(node_ids),
        "edge_count": len(edge_ids),
    }


def persist_all_claims_to_graph(*, root: Path, claim_ids: list[str] | None = None) -> dict[str, Any]:
    claim_store = ClaimStore(root)
    claims = claim_store.list()
    if claim_ids is not None:
        wanted = set(claim_ids)
        claims = [claim for claim in claims if claim["claim_id"] in wanted]
    persisted = [persist_claim_to_graph(root=root, claim=claim) for claim in claims]
    return {
        "claims_processed": len(claims),
        "claim_ids": [item["claim_id"] for item in persisted],
        "node_ids": [item["node_id"] for item in persisted],
    }


def get_claim_graph_node(*, root: Path, claim_id: str) -> dict[str, Any] | None:
    return ClaimGraphStore(root).get_claim_node(claim_id)


def list_claim_neighbors(*, root: Path, claim_id: str, relation_type: str | None = None) -> list[dict[str, Any]]:
    store = ClaimGraphStore(root)
    claim_node = store.get_claim_node(claim_id)
    if claim_node is None:
        return []
    neighbors = []
    for edge in store.list_edges_for_node(claim_node["node_id"], relation_type=relation_type):
        neighbor_id = edge["to_node_id"] if edge["from_node_id"] == claim_node["node_id"] else edge["from_node_id"]
        neighbors.append(
            {
                "relation_type": edge["relation_type"],
                "direction": "outgoing" if edge["from_node_id"] == claim_node["node_id"] else "incoming",
                "edge_id": edge["edge_id"],
                "node": store.get_node(neighbor_id),
            }
        )
    return neighbors


def adapt_legacy_hypothesis_to_claim(graph_record: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic forward adapter without mutating the legacy graph store."""

    statement = graph_record.get("hypothesis_statement") or graph_record.get("core_claim") or graph_record.get("title")
    legacy_seed = "||".join(
        [
            graph_record.get("id", ""),
            graph_record.get("title", ""),
            graph_record.get("content") or "",
            statement or "",
        ]
    )
    claim_id = f"CLM-{hashlib.sha1(legacy_seed.encode('utf-8')).hexdigest()[:16].upper()}"
    source_ref = graph_record.get("source_ref") or {}
    return {
        "claim": {
            "claim_id": claim_id,
            "claim_statement": statement,
            "source_id": graph_record.get("id"),
            "source_type": "legacy_graph_hypothesis",
            "source_url": source_ref.get("source_url"),
            "domain": None,
            "context": None,
            "metric": None,
            "evidence_type": "legacy_graph_node",
            "confidence": None,
            "assumptions": [],
            "failure_modes": [],
            "applicability": None,
            "rule_candidate": None,
            "extracted_at": graph_record.get("updated_at") or graph_record.get("created_at"),
            "version": CLAIM_GRAPH_VERSION,
        },
        "legacy_graph_node_id": graph_record.get("id"),
        "bridge_relation": "derived_from",
    }


def claim_node_id(claim_id: str) -> str:
    return f"CGN-CLAIM-{claim_id}"


def typed_node_id(node_type: ClaimGraphNodeType, value: str) -> str:
    digest = hashlib.sha1(value.strip().lower().encode("utf-8")).hexdigest()[:16].upper()
    return f"CGN-{node_type.upper()}-{digest}"


def evidence_node_id(*, source_id: str, source_type: str, source_url: str | None) -> str:
    raw = "||".join([source_id, source_type, source_url or ""])
    return typed_node_id("evidence", raw)


def ensure_claim_placeholder(*, store: ClaimGraphStore, claim_id: str, now: dt.datetime | None = None) -> dict[str, Any]:
    current = store.get_claim_node(claim_id)
    if current is not None:
        return current
    return store.upsert_node(
        node_id=claim_node_id(claim_id),
        node_type="claim",
        title=claim_id,
        slug=_slugify(claim_id),
        extra={
            "claim_id": claim_id,
            "claim_statement": None,
            "placeholder": True,
            "version": CLAIM_GRAPH_VERSION,
        },
        now=now,
    )


def _upsert_relation(
    *,
    store: ClaimGraphStore,
    from_node_id: str,
    to_node_id: str,
    relation_type: ClaimGraphRelationType,
    extra: dict[str, Any] | None,
    now: dt.datetime | None,
) -> dict[str, Any]:
    edge_id = deterministic_edge_id(from_node_id=from_node_id, to_node_id=to_node_id, relation_type=relation_type)
    return store.upsert_edge(
        edge_id=edge_id,
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        relation_type=relation_type,
        extra=extra,
        now=now,
    )


def deterministic_edge_id(*, from_node_id: str, to_node_id: str, relation_type: str) -> str:
    digest = hashlib.sha1(f"{from_node_id}||{relation_type}||{to_node_id}".encode("utf-8")).hexdigest()[:16].upper()
    return f"CEDGE-{digest}"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return slug.strip("-") or "unknown"


def _as_iso(now: dt.datetime | None) -> str:
    current = now or dt.datetime.now(tz=dt.timezone.utc)
    return current.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _node_semantics_match(current: dict[str, Any], candidate: dict[str, Any]) -> bool:
    return _without_timestamps(current) == _without_timestamps(candidate)


def _edge_semantics_match(current: dict[str, Any], candidate: dict[str, Any]) -> bool:
    return _without_timestamps(current) == _without_timestamps(candidate)


def _without_timestamps(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in {"created_at", "updated_at"}}
