from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from pm_os_contracts.models import SIGNAL


def _hash_key(source: str, title: str | None, published: str) -> str:
    raw = f"{source}|{title or ''}|{published}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_index(index_path: Path) -> dict[str, set[str]]:
    if not index_path.exists():
        return {"urls": set(), "fallback_hashes": set()}
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    return {
        "urls": set(payload.get("urls", [])),
        "fallback_hashes": set(payload.get("fallback_hashes", [])),
    }


def _write_index_atomic(index_path: Path, index_data: dict[str, set[str]]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        {
            "urls": sorted(index_data["urls"]),
            "fallback_hashes": sorted(index_data["fallback_hashes"]),
        },
        indent=2,
    )
    with NamedTemporaryFile("w", encoding="utf-8", dir=index_path.parent, delete=False) as tmp:
        tmp.write(serialized)
        tmp_path = Path(tmp.name)
    tmp_path.replace(index_path)


def append_signals(path: str | Path, signals: list[SIGNAL], *, index_path: str | Path | None = None) -> tuple[int, int]:
    written_signals, skipped = append_signals_with_results(path, signals, index_path=index_path)
    return len(written_signals), skipped


def append_signals_with_results(
    path: str | Path,
    signals: list[SIGNAL],
    *,
    index_path: str | Path | None = None,
) -> tuple[list[SIGNAL], int]:
    data_path = Path(path)
    idx_path = Path(index_path) if index_path else data_path.parent / "signals_index.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)

    index_data = _load_index(idx_path)

    written_signals: list[SIGNAL] = []
    skipped = 0
    with data_path.open("a", encoding="utf-8") as handle:
        for signal in signals:
            signal_payload = signal.to_dict()
            url = signal_payload.get("url")
            published = str(signal_payload.get("timestamp", ""))
            fallback = _hash_key(signal.source, signal.title, published)

            if url and url in index_data["urls"]:
                skipped += 1
                continue
            if fallback in index_data["fallback_hashes"]:
                skipped += 1
                continue

            handle.write(json.dumps(signal_payload) + "\n")
            written_signals.append(signal)

            if url:
                index_data["urls"].add(url)
            index_data["fallback_hashes"].add(fallback)

    _write_index_atomic(idx_path, index_data)
    return written_signals, skipped
