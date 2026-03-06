from __future__ import annotations

import json

from graph.ops import GraphStore
from pmos.cli import main


def _create_graph_with_seed(root) -> str:
    store = GraphStore(root)
    record = store.create(
        node_type="hypothesis",
        title="Newsletter Hypothesis",
        content="Validate whether: Prototype a new PM workflow",
        validation_plan="system_build",
        extra={
            "core_claim": "Prototype a new PM workflow",
            "hypothesis_statement": "Validate whether: Prototype a new PM workflow",
            "validation_seed": {
                "seven_day_validation_idea": "Apply workflow change across 3 task cycles.",
                "implementation_options": [
                    {"option_id": "opt_b", "label": "Decision file + role prompts", "summary": "Decision file + role prompts"}
                ],
            },
        },
    )
    return record.id


def test_vp_init_from_graph_creates_validation_plan(tmp_path, capsys) -> None:
    graph_id = _create_graph_with_seed(tmp_path)
    rc = main(["--root", str(tmp_path), "vp", "init", "--from-graph", "--graph-id", graph_id])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    vp_id = payload["id"]

    project_path = tmp_path / "validation_projects" / vp_id / "project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    plan = project.get("validation_plan")
    assert plan is not None
    assert plan["claim"] == "Validate whether: Prototype a new PM workflow"
    assert plan["experiment_design"].startswith("Apply workflow change")
    assert plan["timebox_days"] == 7


def test_vp_plan_md_generation(tmp_path, capsys) -> None:
    graph_id = _create_graph_with_seed(tmp_path)
    rc = main(["--root", str(tmp_path), "vp", "init", "--from-graph", "--graph-id", graph_id])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    vp_id = payload["id"]

    plan_path = tmp_path / "validation_projects" / vp_id / "vp_plan.md"
    content = plan_path.read_text(encoding="utf-8")
    assert "## Core Claim" in content
    assert "Prototype a new PM workflow" in content
    assert "## Hypothesis" in content
    assert "Validate whether: Prototype a new PM workflow" in content
    assert "## Experiment Design" in content
    assert "Apply workflow change across 3 task cycles." in content


def test_vp_init_legacy_still_works(tmp_path, capsys) -> None:
    rc = main(["--root", str(tmp_path), "vp", "init", "--title", "Legacy VP"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"].startswith("VP-")


def test_vp_init_from_graph_missing_graph_errors(tmp_path, capsys) -> None:
    rc = main(["--root", str(tmp_path), "vp", "init", "--from-graph", "--graph-id", "GRAPH-UNKNOWN-00000000-000"])
    assert rc != 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "Graph node not found" in payload["reason"]


def test_validation_plan_lint_warning_on_status(tmp_path, capsys) -> None:
    graph_id = _create_graph_with_seed(tmp_path)
    rc = main(["--root", str(tmp_path), "vp", "init", "--from-graph", "--graph-id", graph_id])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    vp_id = payload["id"]

    rc = main(["--root", str(tmp_path), "vp", "status", "--id", vp_id, "--status", "active"])
    assert rc == 0
    updated = json.loads(capsys.readouterr().out)
    assert "warnings" in updated
    assert "metrics" in updated["warnings"][0]
