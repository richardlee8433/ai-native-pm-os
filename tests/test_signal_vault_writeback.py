from __future__ import annotations

import datetime as dt
import json

from kb_manager.signals_ops import SignalVaultWriter
from pm_os_contracts.models import SIGNAL


def _signal(
    signal_id: str,
    *,
    source: str = "openai",
    title: str = "Signal title",
    url: str | None,
    timestamp: dt.datetime,
) -> SIGNAL:
    return SIGNAL(
        id=signal_id,
        source=source,
        type="capability",
        title=title,
        content="Body with https://example.com/context",
        url=url,
        timestamp=timestamp,
        priority_score=0.9,
        impact_area=["strategy"],
    )


def test_signal_vault_writeback_dedupe_and_index(tmp_path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "00_Index").mkdir(parents=True)

    ts = dt.datetime(2026, 2, 16, 12, 34, 56, tzinfo=dt.timezone.utc)
    first = _signal("SIG-20260216-001", source="src-a", title="A", url="https://example.com/a", timestamp=ts)
    same_url = _signal("SIG-20260216-002", source="src-b", title="B", url="https://example.com/a", timestamp=ts)
    same_fingerprint = _signal("SIG-20260216-003", source="src-a", title="A", url="https://example.com/c", timestamp=ts)
    unique = _signal("SIG-20260216-004", source="src-z", title="Z", url="https://example.com/z", timestamp=ts)

    writer = SignalVaultWriter(vault_root)
    summary = writer.write_signals([first, same_url, same_fingerprint, unique])

    assert summary == {"written": 2, "skipped_existing": 0, "skipped_dupe": 2}

    month_dir = vault_root / "95_Signals"
    assert (month_dir / "SIG-20260216-001.md").exists()
    assert (month_dir / "SIG-20260216-004.md").exists()
    assert not (month_dir / "SIG-20260216-002.md").exists()
    assert not (month_dir / "SIG-20260216-003.md").exists()

    index_payload = json.loads((vault_root / "00_Index" / "signal_url_index.json").read_text(encoding="utf-8"))
    assert index_payload["seen_urls"]["https://example.com/a"] == "SIG-20260216-001"
    assert index_payload["seen_urls"]["https://example.com/z"] == "SIG-20260216-004"
    assert len(index_payload["seen_fingerprints"]) == 2

    second_summary = writer.write_signals([first])
    assert second_summary == {"written": 0, "skipped_existing": 0, "skipped_dupe": 1}

    temp_files = [path for path in (vault_root / "00_Index").iterdir() if path.name != "signal_url_index.json"]
    assert temp_files == []
