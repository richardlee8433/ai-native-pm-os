from __future__ import annotations

import json

from graph.ops import GraphStore
from pmos.cli import main


def test_validation_project_flow(tmp_path, capsys) -> None:
    rc = main(["--root", str(tmp_path), "vp", "init", "--title", "VP A"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    vp_id = payload["id"]

    graph_store = GraphStore(tmp_path)
    graph = graph_store.create(node_type="concept", title="Graph Title")

    rc = main(["--root", str(tmp_path), "vp", "link-graph", "--id", vp_id, "--graph-id", graph.id])
    assert rc == 0
    linked = json.loads(capsys.readouterr().out)
    assert graph.id in linked["linked_graph_nodes"]

    rc = main(["--root", str(tmp_path), "vp", "link-evidence", "--id", vp_id, "--evidence-id", "AVL-EP-20260224-001"])
    assert rc == 0
    linked = json.loads(capsys.readouterr().out)
    assert "AVL-EP-20260224-001" in linked["linked_evidence_packs"]

    rc = main(["--root", str(tmp_path), "vp", "status", "--id", vp_id, "--status", "active"])
    assert rc == 0
    updated = json.loads(capsys.readouterr().out)
    assert updated["status"] == "active"
