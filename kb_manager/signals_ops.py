from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from pm_os_contracts.models import SIGNAL

_URL_PATTERN = re.compile(r"https?://[^\s)\]>\"']+")


class SignalVaultWriter:
    def __init__(self, vault_root: Path):
        self.vault_root = Path(vault_root)
        self.signals_root = self.vault_root / "98_Signals"
        self.index_path = self.vault_root / "00_Index" / "signal_url_index.json"

    def write_signals(self, signals: list[SIGNAL]) -> dict[str, int]:
        summary = {"written": 0, "skipped_existing": 0, "skipped_dupe": 0}
        index_data = self._load_index()

        for signal in signals:
            payload = signal.to_dict()
            url = payload.get("url")
            fingerprint = self._fingerprint(signal.source, signal.title, self._iso_timestamp(payload.get("timestamp")))

            if url and url in index_data["seen_urls"]:
                summary["skipped_dupe"] += 1
                continue
            if fingerprint in index_data["seen_fingerprints"]:
                summary["skipped_dupe"] += 1
                continue

            target = self._note_path(signal)
            if target.exists():
                summary["skipped_existing"] += 1
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self._render_note(signal), encoding="utf-8")
            summary["written"] += 1

            if url:
                index_data["seen_urls"][url] = signal.id
            index_data["seen_fingerprints"][fingerprint] = signal.id
            self._write_index_atomic(index_data)

        return summary

    def _note_path(self, signal: SIGNAL) -> Path:
        ts = self._timestamp_to_utc(signal.timestamp)
        return self.signals_root / f"{ts:%Y}" / f"{ts:%m}" / f"{signal.id}.md"

    @staticmethod
    def _timestamp_to_utc(value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)

        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _render_note(self, signal: SIGNAL) -> str:
        payload = signal.to_dict()
        lines = [
            "---",
            f"id: {signal.id}",
            f"source: {signal.source}",
            f"type: {signal.type}",
            f"timestamp: {self._iso_timestamp(payload.get('timestamp'))}",
            f"url: {self._yaml_scalar(signal.url)}",
            f"priority_score: {self._yaml_scalar(signal.priority_score)}",
            f"impact_area: {self._yaml_list(signal.impact_area)}",
            "judgment_status: pending",
            "linked_rti: []",
            f"linked_action_id: {self._yaml_scalar(signal.linked_action_id)}",
            "---",
            "",
            f"# {signal.title or signal.id}",
            "",
            signal.content or "",
        ]

        links = self._extract_links(signal)
        if links:
            lines.extend(["", "## Links", ""])
            lines.extend(f"- {link}" for link in links)

        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _extract_links(signal: SIGNAL) -> list[str]:
        links: list[str] = []
        if signal.url:
            links.append(signal.url)
        if signal.content:
            for found in _URL_PATTERN.findall(signal.content):
                if found not in links:
                    links.append(found)
        return links

    def _load_index(self) -> dict[str, dict[str, str]]:
        if not self.index_path.exists():
            return {"seen_urls": {}, "seen_fingerprints": {}}
        payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        return {
            "seen_urls": dict(payload.get("seen_urls", {})),
            "seen_fingerprints": dict(payload.get("seen_fingerprints", {})),
        }

    def _write_index_atomic(self, index_data: dict[str, dict[str, str]]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(index_data, indent=2, sort_keys=True) + "\n"

        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.index_path.parent, delete=False) as tmp:
            tmp.write(serialized)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_name = tmp.name

        os.replace(tmp_name, self.index_path)

    @staticmethod
    def _fingerprint(source: str, title: str | None, timestamp: str) -> str:
        raw = f"{source}|{title or ''}|{timestamp}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _iso_timestamp(value: Any) -> str:
        if isinstance(value, datetime):
            normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
            return normalized.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if isinstance(value, str):
            return SignalVaultWriter._timestamp_to_utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return ""

    @staticmethod
    def _yaml_scalar(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, str):
            escaped = value.replace('"', '\\"')
            return f'"{escaped}"'
        return str(value)

    @staticmethod
    def _yaml_list(values: list[str] | None) -> str:
        if not values:
            return "[]"
        escaped = ['"' + v.replace('"', '\\"') + '"' for v in values]
        return "[" + ", ".join(escaped) + "]"
