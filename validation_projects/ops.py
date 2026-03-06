from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from validation_projects.plan_initializer import build_validation_plan_from_graph

@dataclass(frozen=True)
class ValidationProjectRecord:
    id: str
    status: str
    created_at: str
    updated_at: str
    title: str
    description: str | None
    linked_graph_nodes: list[str]
    linked_evidence_packs: list[str]
    path: str
    validation_plan: dict[str, Any] | None = None

    def to_index(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "status": self.status,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "path": self.path,
            "linked_graph_nodes": self.linked_graph_nodes,
            "linked_evidence_packs": self.linked_evidence_packs,
        }
        if self.description is not None:
            payload["description"] = self.description
        if self.validation_plan is not None:
            payload["validation_plan"] = self.validation_plan
        return payload


class ValidationProjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.base_dir = self.root / "validation_projects"
        self.index_path = self.base_dir / "index.json"

    def init(
        self,
        *,
        title: str,
        description: str | None = None,
        validation_plan: dict[str, Any] | None = None,
        now: dt.datetime | None = None,
    ) -> ValidationProjectRecord:
        now_dt = now or dt.datetime.now(tz=dt.timezone.utc)
        now_iso = now_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        project_id = self._next_id(now_dt.date())
        project_dir = self.base_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)

        project = ValidationProjectRecord(
            id=project_id,
            status="planned",
            created_at=now_iso,
            updated_at=now_iso,
            title=title,
            description=description,
            linked_graph_nodes=[],
            linked_evidence_packs=[],
            path=str(project_dir.relative_to(self.root).as_posix()),
            validation_plan=validation_plan,
        )
        project_payload = project.to_index()
        (project_dir / "project.json").write_text(json.dumps(project_payload, indent=2), encoding="utf-8")
        (project_dir / "notes.md").write_text(f"# {title}\n\n", encoding="utf-8")
        self._update_index(project)
        self._write_plan_doc(project_payload)
        return project

    def init_from_graph(
        self,
        *,
        graph_id: str,
        title: str | None = None,
        now: dt.datetime | None = None,
    ) -> dict[str, Any]:
        graph = self._load_graph(graph_id)
        resolved_title = title or graph.get("title") or f"Validation Project {graph_id}"
        validation_plan = build_validation_plan_from_graph(graph)
        record = self.init(title=resolved_title, description=graph.get("content"), validation_plan=validation_plan, now=now)
        project = self.link_graph(project_id=record.id, graph_ids=[graph_id])
        return project

    def link_graph(self, *, project_id: str, graph_ids: list[str]) -> dict[str, Any]:
        for graph_id in graph_ids:
            self._load_graph(graph_id, required=True)
        project = self._load_project(project_id)
        project["linked_graph_nodes"] = sorted(set(project.get("linked_graph_nodes", []) + graph_ids))
        project["updated_at"] = self._now_iso()
        self._write_project(project_id, project)
        self._update_index_from_payload(project)
        self._write_plan_doc(project)
        return project

    def link_evidence(self, *, project_id: str, evidence_ids: list[str]) -> dict[str, Any]:
        project = self._load_project(project_id)
        project["linked_evidence_packs"] = sorted(set(project.get("linked_evidence_packs", []) + evidence_ids))
        project["updated_at"] = self._now_iso()
        self._write_project(project_id, project)
        self._update_index_from_payload(project)
        self._write_plan_doc(project)
        return project

    def update_status(self, *, project_id: str, status: str) -> dict[str, Any]:
        project = self._load_project(project_id)
        project["status"] = status
        project["updated_at"] = self._now_iso()
        self._write_project(project_id, project)
        self._update_index_from_payload(project)
        self._write_plan_doc(project)
        return project

    def get(self, project_id: str) -> dict[str, Any]:
        return self._load_project(project_id)

    def _next_id(self, day: dt.date) -> str:
        date_key = day.strftime("%Y")
        existing = []
        if self.index_path.exists():
            index = json.loads(self.index_path.read_text(encoding="utf-8"))
            existing = [item["id"] for item in index.get("items", []) if item["id"].startswith(f"VP-{date_key}-")]
        return f"VP-{date_key}-{len(existing) + 1:03d}"

    def _update_index(self, record: ValidationProjectRecord) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        if self.index_path.exists():
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        else:
            payload = {"items": []}
        payload["items"].append(record.to_index())
        self.index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _update_index_from_payload(self, payload: dict[str, Any]) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        index = {"items": []}
        if self.index_path.exists():
            index = json.loads(self.index_path.read_text(encoding="utf-8"))
        items = index.get("items", [])
        for idx, item in enumerate(items):
            if item["id"] == payload["id"]:
                items[idx] = payload
                break
        else:
            items.append(payload)
        index["items"] = items
        self.index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    def _load_project(self, project_id: str) -> dict[str, Any]:
        path = self.base_dir / project_id / "project.json"
        if not path.exists():
            raise ValueError(f"Validation project not found: {project_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_project(self, project_id: str, payload: dict[str, Any]) -> None:
        path = self.base_dir / project_id / "project.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load_graph(self, graph_id: str, *, required: bool = True) -> dict[str, Any] | None:
        from graph.ops import GraphStore

        store = GraphStore(self.root)
        graph = store.get(graph_id)
        if not graph and required:
            raise ValueError(f"Graph node not found: {graph_id}")
        return graph

    def _write_plan_doc(self, project: dict[str, Any]) -> None:
        from vp.plan_writer import write_vp_plan

        graph = None
        graph_ids = project.get("linked_graph_nodes") or []
        if graph_ids:
            graph = self._load_graph(graph_ids[0], required=False)
        write_vp_plan(self.root, project, graph)

    @staticmethod
    def _now_iso() -> str:
        return dt.datetime.now(tz=dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
