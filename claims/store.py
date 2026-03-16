from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.storage import JSONLStorage
from pm_os_contracts.models import ClaimObject


class ClaimStore:
    """Append-only store for v5.0 claim objects."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.claim_dir = self.root / "claims"
        self.claims_path = self.claim_dir / "claims.jsonl"
        self.index_path = self.claim_dir / "claim_index.json"
        self.store = JSONLStorage(self.claims_path)

    def write(self, claim: ClaimObject) -> dict[str, Any]:
        current = self.get(claim.claim_id)
        if current is not None:
            return {"written": False, "reason": "duplicate_claim_id", "claim_id": claim.claim_id, "claim": current}

        payload = claim.to_dict()
        self.store.append(payload)
        index = self._read_index()
        index[claim.claim_id] = payload
        self._write_index(index)
        return {"written": True, "claim_id": claim.claim_id, "claim": payload}

    def write_many(self, claims: list[ClaimObject]) -> dict[str, Any]:
        written: list[str] = []
        skipped: list[str] = []
        for claim in claims:
            result = self.write(claim)
            if result["written"]:
                written.append(claim.claim_id)
            else:
                skipped.append(claim.claim_id)
        return {"written": written, "skipped": skipped}

    def get(self, claim_id: str) -> dict[str, Any] | None:
        return self._read_index().get(claim_id)

    def list(self) -> list[dict[str, Any]]:
        claims = list(self._read_index().values())
        claims.sort(key=lambda item: (item.get("extracted_at", ""), item.get("claim_id", "")))
        return claims

    def _read_index(self) -> dict[str, dict[str, Any]]:
        if not self.index_path.exists():
            return {}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _write_index(self, payload: dict[str, dict[str, Any]]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
