from __future__ import annotations

import json

from pmos.cli import main


def test_graph_create_list_show_update(tmp_path, capsys) -> None:
    rc = main(["--root", str(tmp_path), "graph", "create", "--type", "concept", "--title", "Graph A"])
    assert rc == 0
    created = json.loads(capsys.readouterr().out)
    assert created["id"].startswith("GRAPH-CONCEPT-")

    rc = main(["--root", str(tmp_path), "graph", "list"])
    assert rc == 0
    items = json.loads(capsys.readouterr().out)
    assert len(items) == 1

    rc = main(["--root", str(tmp_path), "graph", "show", "--id", created["id"]])
    assert rc == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["id"] == created["id"]

    rc = main(["--root", str(tmp_path), "graph", "update-status", "--id", created["id"], "--status", "validation_ready"])
    assert rc == 0
    updated = json.loads(capsys.readouterr().out)
    assert updated["status"] == "validation_ready"
