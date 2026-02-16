from __future__ import annotations

from orchestrator.storage import JSONLStorage


def test_jsonl_storage_append_read_and_rewrite(tmp_path) -> None:
    store = JSONLStorage(tmp_path / "events.jsonl")

    store.append({"id": 1, "name": "first"})
    store.append({"id": 2, "name": "second"})

    rows = store.read_all()
    assert rows == [{"id": 1, "name": "first"}, {"id": 2, "name": "second"}]

    store.rewrite_all([{"id": 3, "name": "third"}])
    assert store.read_all() == [{"id": 3, "name": "third"}]
