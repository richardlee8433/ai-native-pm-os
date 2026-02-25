from __future__ import annotations

import json

from pmos.cli import main


def test_validation_project_flow(tmp_path, capsys) -> None:
    rc = main(["--root", str(tmp_path), "vp", "init", "--title", "VP A"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    vp_id = payload["id"]

    rc = main(["--root", str(tmp_path), "vp", "link-graph", "--id", vp_id, "--graph-id", "GRAPH-CONCEPT-20260224-001"])
    assert rc == 0
    linked = json.loads(capsys.readouterr().out)
    assert "GRAPH-CONCEPT-20260224-001" in linked["linked_graph_nodes"]

    rc = main(["--root", str(tmp_path), "vp", "link-evidence", "--id", vp_id, "--evidence-id", "AVL-EP-20260224-001"])
    assert rc == 0
    linked = json.loads(capsys.readouterr().out)
    assert "AVL-EP-20260224-001" in linked["linked_evidence_packs"]

    rc = main(["--root", str(tmp_path), "vp", "status", "--id", vp_id, "--status", "active"])
    assert rc == 0
    updated = json.loads(capsys.readouterr().out)
    assert updated["status"] == "active"
