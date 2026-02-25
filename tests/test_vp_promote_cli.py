from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from graph.ops import GraphStore
from pmos import cli
from validation_projects.ops import ValidationProjectStore


def _write_evidence_pack(root: Path, *, pack_id: str) -> Path:
    base_dir = root / "avl" / "evidence_packs"
    base_dir.mkdir(parents=True, exist_ok=True)
    pack_path = base_dir / f"{pack_id}.md"
    content = "\n".join(
        [
            "---",
            f"id: {pack_id}",
            "title: CX Replay Pack",
            "created_at: 2026-02-25T00:00:00Z",
            "updated_at: 2026-02-25T00:00:00Z",
            "hypothesis: H",
            "context: C",
            "method: replay",
            "outcome: pass",
            "cost_paid: time",
            "failure_modes: edge",
            "delta: D",
            "recommendation: promote",
            "governance_impact: none",
            "---",
            "",
            "# AVL Evidence Pack",
            "",
        ]
    )
    pack_path.write_text(content, encoding="utf-8")

    index_path = base_dir / "index.json"
    payload = {"items": [{"id": pack_id, "path": pack_path.relative_to(root).as_posix()}]}
    index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return pack_path


def test_vp_promote_cli_output_and_frontmatter(tmp_path: Path, monkeypatch, capsys) -> None:
    root = tmp_path
    vault_root = root / ".vault_test"
    vault_root.mkdir(parents=True, exist_ok=True)

    graph_store = GraphStore(root)
    graph = graph_store.create(node_type="concept", title="Graph Title")

    pack_id = "AVL-EP-20260225-001"
    _write_evidence_pack(root, pack_id=pack_id)

    vp_store = ValidationProjectStore(root)
    vp = vp_store.init(title="VP")
    vp_store.link_graph(project_id=vp.id, graph_ids=[graph.id])
    vp_store.link_evidence(project_id=vp.id, evidence_ids=[pack_id])

    monkeypatch.setenv("PMOS_USE_V41_PROMOTION", "true")

    exit_code = cli.main(["--root", str(root), "vp", "promote", "--id", vp.id])
    assert exit_code == 0

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)
    assert payload["ok"] is True
    assert payload["action"] == "lti_created"

    lti_path = Path(payload["lti_path"])
    assert lti_path.exists()
    content = lti_path.read_text(encoding="utf-8")
    assert "validation_status: provisional" in content
    assert f"- {graph.id}" in content
    assert f"- {pack_id}" in content
    assert "revalidate_status: pending" in content

    today = dt.datetime.now(tz=dt.timezone.utc).date()
    expected = (today + dt.timedelta(days=28)).isoformat()
    assert f"revalidate_by: {expected}" in content
