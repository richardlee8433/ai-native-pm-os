from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from kb_manager import KnowledgeBaseManager
from pm_os_contracts.models import COS_CASE, LPL_POST, LTI_NODE, RTI_NODE


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_writeback_lti_creates_file_and_updates_lti_index(tmp_path: Path) -> None:
    manager = KnowledgeBaseManager(tmp_path)

    node = LTI_NODE(id="LTI-6.5", title="Signal scoring", series="LTI-6.x", status="active")
    out_path = manager.writeback_lti(node)

    assert out_path == tmp_path / "02_LTI" / "LTI-6.x" / "LTI-6.5.md"
    assert out_path.exists()

    content = _read_json(out_path)
    assert content["id"] == "LTI-6.5"
    assert "updated_at" in content

    lti_index = _read_json(tmp_path / "02_LTI" / "lti_index.json")
    assert [item["id"] for item in lti_index["items"]] == ["LTI-6.5"]


def test_writeback_cos_and_lpl_sync_corresponding_indices(tmp_path: Path) -> None:
    manager = KnowledgeBaseManager(tmp_path)

    cos = COS_CASE(id="COS-20260216-001", task_id="ACT-20260216-001", failure_pattern_id="FP-001")
    lpl = LPL_POST(id="LPL-20260216T120000Z-001", source_lti_id="LTI-6.5", content="post")

    cos_path = manager.writeback_cos(cos)
    lpl_path = manager.writeback_lpl(lpl)

    assert cos_path == tmp_path / "06_Archive" / "COS" / "FP-001" / "COS-20260216-001.md"
    assert lpl_path == tmp_path / "11_LPL" / "2026" / "02" / "LPL-20260216T120000Z-001.md"

    cos_index = _read_json(tmp_path / "06_Archive" / "COS" / "cos_index.json")
    assert cos_index["items"][0]["failure_pattern_id"] == "FP-001"

    lines = (tmp_path / "11_LPL" / "lpl_index.jsonl").read_text(encoding="utf-8").strip().splitlines()
    payloads = [json.loads(line) for line in lines]
    assert payloads[0]["id"] == "LPL-20260216T120000Z-001"
    assert payloads[0]["source_lti_id"] == "LTI-6.5"


def test_update_rti_status_updates_existing_rti_file_and_syncs_index(tmp_path: Path) -> None:
    manager = KnowledgeBaseManager(tmp_path)

    rti = RTI_NODE(id="RTI-1.2", title="Feedback loops", status="active")
    rti_path = tmp_path / "01_RTI" / "RTI-1.2.md"
    rti_path.parent.mkdir(parents=True, exist_ok=True)
    rti_path.write_text(json.dumps(rti.model_dump(mode="json"), indent=2), encoding="utf-8")

    manager.update_rti_status("RTI-1.2", "under_review")

    updated = _read_json(rti_path)
    assert updated["status"] == "under_review"
    assert "updated_at" in updated

    rti_index = _read_json(tmp_path / "01_RTI" / "rti_index.json")
    assert rti_index["items"][0]["id"] == "RTI-1.2"
    assert rti_index["items"][0]["status"] == "under_review"


def test_sync_indices_reconciles_drift_from_stale_index_files(tmp_path: Path) -> None:
    manager = KnowledgeBaseManager(tmp_path)

    stale_index = tmp_path / "02_LTI" / "lti_index.json"
    stale_index.parent.mkdir(parents=True, exist_ok=True)
    stale_index.write_text(json.dumps({"items": [{"id": "LTI-9.9"}]}), encoding="utf-8")

    manager.writeback_lti(LTI_NODE(id="LTI-6.5", title="Signal scoring", series="LTI-6.x", status="active"))
    result = manager.sync_indices()

    lti_index = _read_json(stale_index)
    assert [item["id"] for item in lti_index["items"]] == ["LTI-6.5"]
    assert result.lti_count == 1


def test_atomic_writeback_uses_os_replace(tmp_path: Path) -> None:
    manager = KnowledgeBaseManager(tmp_path)

    with patch("kb_manager.vault_ops.os.replace") as replace_mock:
        manager.writeback_lti(LTI_NODE(id="LTI-6.5", title="Signal scoring", series="LTI-6.x", status="active"))

    assert replace_mock.called
