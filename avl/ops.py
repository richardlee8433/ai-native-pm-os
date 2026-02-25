from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = [
    "hypothesis",
    "context",
    "method",
    "outcome",
    "cost_paid",
    "failure_modes",
    "delta",
    "recommendation",
    "governance_impact",
]


@dataclass(frozen=True)
class EvidencePackRecord:
    id: str
    title: str
    created_at: str
    updated_at: str
    fields: dict[str, Any]
    path: str

    def to_index(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "path": self.path,
            "outcome": self.fields.get("outcome"),
            "recommendation": self.fields.get("recommendation"),
            "governance_impact": self.fields.get("governance_impact"),
        }


class EvidencePackStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.base_dir = self.root / "avl" / "evidence_packs"
        self.index_path = self.base_dir / "index.json"
        self.template_path = self.base_dir / "template.md"

    def create(self, *, title: str, now: dt.datetime | None = None) -> EvidencePackRecord:
        now_dt = now or dt.datetime.now(tz=dt.timezone.utc)
        now_iso = now_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        pack_id = self._next_id(now_dt.date())
        pack_path = self.base_dir / f"{pack_id}.md"

        content = self._render_template(
            {
                "id": pack_id,
                "title": title,
                "created_at": now_iso,
                "updated_at": now_iso,
                "hypothesis": "",
                "context": "",
                "method": "",
                "outcome": "",
                "cost_paid": "",
                "failure_modes": "",
                "delta": "",
                "recommendation": "",
                "governance_impact": "",
            }
        )
        pack_path.parent.mkdir(parents=True, exist_ok=True)
        pack_path.write_text(content, encoding="utf-8")

        record = EvidencePackRecord(
            id=pack_id,
            title=title,
            created_at=now_iso,
            updated_at=now_iso,
            fields={field: "" for field in REQUIRED_FIELDS},
            path=str(pack_path.relative_to(self.root).as_posix()),
        )
        self._update_index(record)
        return record

    def validate(self, path: Path) -> dict[str, Any]:
        payload = self._read_frontmatter(path)
        missing = [field for field in REQUIRED_FIELDS if not payload.get(field)]
        return {"ok": not missing, "missing": missing, "id": payload.get("id"), "path": str(path)}

    def _next_id(self, day: dt.date) -> str:
        date_key = day.strftime("%Y%m%d")
        prefix = f"AVL-EP-{date_key}-"
        existing = []
        if self.index_path.exists():
            index = json.loads(self.index_path.read_text(encoding="utf-8"))
            existing = [item["id"] for item in index.get("items", []) if item["id"].startswith(prefix)]
        return f"{prefix}{len(existing) + 1:03d}"

    def _update_index(self, record: EvidencePackRecord) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        if self.index_path.exists():
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        else:
            payload = {"items": []}
        payload["items"].append(record.to_index())
        self.index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _render_template(self, fields: dict[str, Any]) -> str:
        frontmatter = [
            "---",
            f"id: {fields['id']}",
            f"title: {fields['title']}",
            f"created_at: {fields['created_at']}",
            f"updated_at: {fields['updated_at']}",
            f"hypothesis: {fields['hypothesis']}",
            f"context: {fields['context']}",
            f"method: {fields['method']}",
            f"outcome: {fields['outcome']}",
            f"cost_paid: {fields['cost_paid']}",
            f"failure_modes: {fields['failure_modes']}",
            f"delta: {fields['delta']}",
            f"recommendation: {fields['recommendation']}",
            f"governance_impact: {fields['governance_impact']}",
            "---",
            "",
            "# AVL Evidence Pack",
            "",
            "## Hypothesis",
            "",
            "## Context",
            "",
            "## Method",
            "",
            "## Outcome",
            "",
            "## Cost Paid",
            "",
            "## Failure Modes",
            "",
            "## Delta",
            "",
            "## Recommendation",
            "",
            "## Governance Impact",
            "",
        ]
        return "\n".join(frontmatter)

    def _read_frontmatter(self, path: Path) -> dict[str, str]:
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0].strip() != "---":
            return {}
        data: dict[str, str] = {}
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
        return data
