from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from orchestrator.storage import JSONLStorage

GraphType = Literal["concept", "skill", "playbook", "hypothesis", "evidence"]
GraphStatus = Literal["exploring", "validation_ready", "validated", "archived"]


@dataclass(frozen=True)
class GraphNodeRecord:
    id: str
    type: GraphType
    status: GraphStatus
    title: str
    content: str | None
    created_at: str
    updated_at: str
    validation_plan: str | None
    related_nodes: list[str]
    tags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "validation_plan": self.validation_plan,
            "related_nodes": self.related_nodes,
            "tags": self.tags,
        }


class GraphStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.graph_dir = self.root / "graph"
        self.nodes_path = self.graph_dir / "graph_nodes.jsonl"
        self.index_path = self.graph_dir / "graph_index.json"
        self.store = JSONLStorage(self.nodes_path)

    def create(
        self,
        *,
        node_type: GraphType,
        title: str,
        content: str | None = None,
        validation_plan: str | None = None,
        related_nodes: list[str] | None = None,
        tags: list[str] | None = None,
        now: dt.datetime | None = None,
    ) -> GraphNodeRecord:
        now_dt = now or dt.datetime.now(tz=dt.timezone.utc)
        now_iso = now_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        node_id = self._next_id(node_type, now_dt.date())

        record = GraphNodeRecord(
            id=node_id,
            type=node_type,
            status="exploring",
            title=title,
            content=content,
            created_at=now_iso,
            updated_at=now_iso,
            validation_plan=validation_plan,
            related_nodes=related_nodes or [],
            tags=tags or [],
        )
        self.store.append(record.to_dict())
        self._update_index(record)
        return record

    def list(self) -> list[dict[str, Any]]:
        return list(self._read_index().values())

    def get(self, node_id: str) -> dict[str, Any] | None:
        return self._read_index().get(node_id)

    def update_status(
        self,
        *,
        node_id: str,
        status: GraphStatus,
        now: dt.datetime | None = None,
    ) -> dict[str, Any]:
        current = self.get(node_id)
        if not current:
            raise ValueError(f"Graph node not found: {node_id}")
        now_dt = now or dt.datetime.now(tz=dt.timezone.utc)
        now_iso = now_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        updated = dict(current)
        updated["status"] = status
        updated["updated_at"] = now_iso
        self.store.append(updated)
        self._write_index({**self._read_index(), node_id: updated})
        return updated

    def _next_id(self, node_type: GraphType, day: dt.date) -> str:
        date_key = day.strftime("%Y%m%d")
        prefix = f"GRAPH-{node_type.upper()}-{date_key}-"
        existing = [node_id for node_id in self._read_index().keys() if node_id.startswith(prefix)]
        return f"{prefix}{len(existing) + 1:03d}"

    def _read_index(self) -> dict[str, dict[str, Any]]:
        if not self.index_path.exists():
            return {}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _write_index(self, payload: dict[str, dict[str, Any]]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _update_index(self, record: GraphNodeRecord) -> None:
        index = self._read_index()
        index[record.id] = record.to_dict()
        self._write_index(index)
