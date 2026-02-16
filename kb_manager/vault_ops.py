from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from pm_os_contracts.models import COS_CASE, LPL_POST, LTI_NODE, RTI_NODE


@dataclass(frozen=True)
class SyncResult:
    lti_count: int
    cos_count: int
    lpl_count: int
    rti_count: int


class KnowledgeBaseManager:
    """Manage atomic writeback and index synchronization for vault artifacts."""

    def __init__(self, vault_root: Path | str):
        self.vault_root = Path(vault_root)
        self.rti_dir = self.vault_root / "01_RTI"
        self.lti_dir = self.vault_root / "02_LTI"
        self.cos_dir = self.vault_root / "06_Archive" / "COS"
        self.lpl_dir = self.vault_root / "11_LPL"

        self.lti_index_path = self.lti_dir / "lti_index.json"
        self.cos_index_path = self.cos_dir / "cos_index.json"
        self.rti_index_path = self.rti_dir / "rti_index.json"
        self.lpl_index_path = self.lpl_dir / "lpl_index.jsonl"

    def writeback_lti(self, lti_node: LTI_NODE) -> Path:
        target = self.lti_dir / lti_node.series / f"{lti_node.id}.md"
        self._write_model(target, lti_node)
        self.sync_indices()
        return target

    def writeback_cos(self, cos_case: COS_CASE) -> Path:
        target = self.cos_dir / cos_case.failure_pattern_id / f"{cos_case.id}.md"
        self._write_model(target, cos_case)
        self.sync_indices()
        return target

    def writeback_lpl(self, lpl_post: LPL_POST) -> Path:
        year, month = self._year_month_from_lpl_id(lpl_post.id)
        target = self.lpl_dir / year / month / f"{lpl_post.id}.md"
        self._write_model(target, lpl_post)
        self.sync_indices()
        return target

    def update_rti_status(self, rti_id: str, status: str) -> None:
        target = self.rti_dir / f"{rti_id}.md"
        current = self._read_json_file(target)
        if current is None:
            current = RTI_NODE(id=rti_id, title=rti_id, status="active").model_dump(mode="json", exclude_none=True)

        current["status"] = status
        current["updated_at"] = self._utc_now_iso()
        self._atomic_write_text(target, self._render_json_document(current))
        self.sync_indices()

    def sync_indices(self) -> SyncResult:
        lti_entries = self._scan_json_markdown(self.lti_dir, "LTI-")
        cos_entries = self._scan_json_markdown(self.cos_dir, "COS-")
        lpl_entries = self._scan_json_markdown(self.lpl_dir, "LPL-")
        rti_entries = self._scan_json_markdown(self.rti_dir, "RTI-")

        lti_index = {
            "generated_at": self._utc_now_iso(),
            "items": [
                {
                    "id": item["id"],
                    "path": item["_relpath"],
                    "series": item.get("series"),
                    "status": item.get("status"),
                }
                for item in lti_entries
            ],
        }
        self._atomic_write_text(self.lti_index_path, json.dumps(lti_index, indent=2, sort_keys=True) + "\n")

        cos_index = {
            "generated_at": self._utc_now_iso(),
            "items": [
                {
                    "id": item["id"],
                    "path": item["_relpath"],
                    "failure_pattern_id": item.get("failure_pattern_id"),
                }
                for item in cos_entries
            ],
        }
        self._atomic_write_text(self.cos_index_path, json.dumps(cos_index, indent=2, sort_keys=True) + "\n")

        rti_index = {
            "generated_at": self._utc_now_iso(),
            "items": [
                {
                    "id": item["id"],
                    "path": item["_relpath"],
                    "status": item.get("status"),
                    "confidence_level": item.get("confidence_level"),
                    "revision_trigger_count": item.get("revision_trigger_count"),
                }
                for item in rti_entries
            ],
        }
        self._atomic_write_text(self.rti_index_path, json.dumps(rti_index, indent=2, sort_keys=True) + "\n")

        lines = [
            json.dumps(
                {
                    "id": item["id"],
                    "path": item["_relpath"],
                    "source_lti_id": item.get("source_lti_id"),
                    "published_at": item.get("published_at"),
                },
                sort_keys=True,
            )
            for item in lpl_entries
        ]
        lpl_content = "\n".join(lines)
        if lpl_content:
            lpl_content += "\n"
        self._atomic_write_text(self.lpl_index_path, lpl_content)

        return SyncResult(
            lti_count=len(lti_entries),
            cos_count=len(cos_entries),
            lpl_count=len(lpl_entries),
            rti_count=len(rti_entries),
        )

    def _write_model(self, target: Path, model: LTI_NODE | COS_CASE | LPL_POST) -> None:
        payload = model.model_dump(mode="json", exclude_none=True)
        payload["updated_at"] = self._utc_now_iso()
        self._atomic_write_text(target, self._render_json_document(payload))

    def _scan_json_markdown(self, root: Path, id_prefix: str) -> list[dict[str, Any]]:
        if not root.exists():
            return []

        results: list[dict[str, Any]] = []
        for md_path in sorted(root.rglob("*.md")):
            payload = self._read_json_file(md_path)
            if not payload:
                continue
            item_id = payload.get("id")
            if not isinstance(item_id, str) or not item_id.startswith(id_prefix):
                continue
            payload["_relpath"] = md_path.relative_to(self.vault_root).as_posix()
            results.append(payload)
        return results

    def _read_json_file(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _atomic_write_text(self, target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_name = tmp.name
        os.replace(tmp_name, target)

    @staticmethod
    def _render_json_document(payload: dict[str, Any]) -> str:
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _year_month_from_lpl_id(lpl_id: str) -> tuple[str, str]:
        # LPL-YYYYMMDDTHHMMSSZ-NNN
        timestamp = lpl_id.split("-")[1]
        return timestamp[:4], timestamp[4:6]
