from __future__ import annotations

import datetime as dt
import json

from claims.store import ClaimStore
from graph.claim_ops import (
    ClaimGraphStore,
    adapt_legacy_hypothesis_to_claim,
    get_claim_graph_node,
    list_claim_neighbors,
    persist_all_claims_to_graph,
    persist_claim_to_graph,
)
from graph.ops import GraphStore
from ingest.registry import SourceConfig
from pm_os_contracts.models import ClaimObject
from pmos import cli


def _sample_claim(*, claim_id: str = "CLM-1234ABCDEF567890") -> ClaimObject:
    return ClaimObject(
        claim_id=claim_id,
        claim_statement="AI prototyping accelerates product iteration.",
        source_id="openai_news",
        source_type="rss",
        source_url="https://example.com/news/1",
        domain="product_development",
        context="early product exploration",
        metric="iteration speed",
        evidence_type="article",
        confidence=0.72,
        assumptions=["team has clear feedback loop"],
        failure_modes=["solution bias"],
        applicability="early-stage product teams",
        rule_candidate="Use AI prototyping in early exploration when iteration speed matters.",
        extracted_at=dt.datetime(2026, 3, 16, 10, 0, tzinfo=dt.timezone.utc),
        version="v5.0",
    )


def test_persist_claim_to_graph_creates_typed_nodes_and_edges(tmp_path) -> None:
    result = persist_claim_to_graph(root=tmp_path, claim=_sample_claim())

    assert result["node_id"] == "CGN-CLAIM-CLM-1234ABCDEF567890"
    node = get_claim_graph_node(root=tmp_path, claim_id="CLM-1234ABCDEF567890")
    assert node is not None
    assert node["node_type"] == "claim"
    assert node["source_url"] == "https://example.com/news/1"

    neighbors = list_claim_neighbors(root=tmp_path, claim_id="CLM-1234ABCDEF567890")
    relation_types = {item["relation_type"] for item in neighbors}
    assert relation_types == {"applies_to", "derived_from", "exposed_to", "measured_by"}


def test_claim_graph_persistence_is_deterministic_and_deduplicated(tmp_path) -> None:
    claim = _sample_claim()
    first = persist_claim_to_graph(root=tmp_path, claim=claim)
    second = persist_claim_to_graph(root=tmp_path, claim=claim)

    store = ClaimGraphStore(tmp_path)
    node = store.get_claim_node(claim.claim_id)
    assert first["node_id"] == second["node_id"] == node["node_id"]
    assert len(store._read_index(store.node_index_path)) == 5
    assert len(store._read_index(store.edge_index_path)) == 4
    assert len(store.node_store.read_all()) == 5
    assert len(store.edge_store.read_all()) == 4


def test_claim_graph_neighbors_can_filter_relation_type(tmp_path) -> None:
    persist_claim_to_graph(root=tmp_path, claim=_sample_claim())

    metric_neighbors = list_claim_neighbors(
        root=tmp_path,
        claim_id="CLM-1234ABCDEF567890",
        relation_type="measured_by",
    )
    assert len(metric_neighbors) == 1
    assert metric_neighbors[0]["node"]["node_type"] == "metric"


def test_claim_graph_sync_from_claim_store(tmp_path) -> None:
    claim = _sample_claim()
    ClaimStore(tmp_path).write(claim)

    result = persist_all_claims_to_graph(root=tmp_path)
    assert result["claims_processed"] == 1
    assert result["claim_ids"] == [claim.claim_id]
    assert get_claim_graph_node(root=tmp_path, claim_id=claim.claim_id) is not None


def test_legacy_hypothesis_adapter_is_deterministic(tmp_path) -> None:
    graph = GraphStore(tmp_path).create(
        node_type="hypothesis",
        title="Legacy graph hypothesis",
        content="AI prototyping accelerates product iteration.",
        extra={"hypothesis_statement": "Validate whether AI prototyping accelerates product iteration."},
    )

    first = adapt_legacy_hypothesis_to_claim(graph.to_dict())
    second = adapt_legacy_hypothesis_to_claim(graph.to_dict())
    assert first == second
    assert first["bridge_relation"] == "derived_from"
    assert first["claim"]["source_type"] == "legacy_graph_hypothesis"


def test_claim_graph_cli_show_neighbors_persist_and_sync(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("PMOS_V5_CLAIMS_ENABLED", "true")
    monkeypatch.setenv("PMOS_V5_CLAIM_GRAPH_ENABLED", "true")
    claim = _sample_claim()
    ClaimStore(tmp_path).write(claim)

    rc = cli.main(["--root", str(tmp_path), "claim", "graph", "persist", claim.claim_id])
    assert rc == 0
    persisted = json.loads(capsys.readouterr().out)
    assert persisted["node_id"] == "CGN-CLAIM-CLM-1234ABCDEF567890"

    rc = cli.main(["--root", str(tmp_path), "claim", "graph", "show", claim.claim_id])
    assert rc == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["exists"] is True
    assert shown["node"]["claim_id"] == claim.claim_id

    rc = cli.main(["--root", str(tmp_path), "claim", "graph", "neighbors", claim.claim_id])
    assert rc == 0
    neighbors = json.loads(capsys.readouterr().out)
    assert len(neighbors["neighbors"]) == 4

    rc = cli.main(["--root", str(tmp_path), "claim", "graph", "sync"])
    assert rc == 0
    synced = json.loads(capsys.readouterr().out)
    assert synced["claims_processed"] == 1


def test_claim_ingest_can_optionally_persist_graph(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("PMOS_V5_CLAIMS_ENABLED", "true")
    monkeypatch.setenv("PMOS_V5_CLAIM_INGEST_ENABLED", "true")
    monkeypatch.setenv("PMOS_V5_CLAIM_GRAPH_ENABLED", "true")

    cfg = SourceConfig(id="openai_news", name="OpenAI News", type="rss", url="https://example.com/rss.xml")

    class _Fetcher:
        def fetch(self, source_cfg, *, limit):
            return [
                {
                    "title": "Agent eval toolkit released",
                    "content": "Includes safety evaluation and multimodal support. Teams can measure quality faster.",
                    "url": "https://example.com/news/toolkit",
                    "published_at": dt.datetime(2026, 3, 16, 12, 0, tzinfo=dt.timezone.utc),
                }
            ]

    monkeypatch.setattr("ingest.claim_pipeline.load_sources", lambda path: [cfg])
    monkeypatch.setattr("ingest.claim_pipeline.get_fetcher", lambda source_type: _Fetcher())

    rc = cli.main(["--root", str(tmp_path), "claim", "ingest", "openai_news", "--persist-graph"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["graph_sync"]["claims_processed"] >= 1


def test_claim_ingest_default_path_stays_phase1_compatible(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("PMOS_V5_CLAIMS_ENABLED", "true")
    monkeypatch.setenv("PMOS_V5_CLAIM_INGEST_ENABLED", "true")
    monkeypatch.delenv("PMOS_V5_CLAIM_GRAPH_ENABLED", raising=False)

    cfg = SourceConfig(id="openai_news", name="OpenAI News", type="rss", url="https://example.com/rss.xml")

    class _Fetcher:
        def fetch(self, source_cfg, *, limit):
            return [
                {
                    "title": "Agent eval toolkit released",
                    "content": "Includes safety evaluation and multimodal support.",
                    "url": "https://example.com/news/toolkit",
                    "published_at": dt.datetime(2026, 3, 16, 12, 0, tzinfo=dt.timezone.utc),
                }
            ]

    monkeypatch.setattr("ingest.claim_pipeline.load_sources", lambda path: [cfg])
    monkeypatch.setattr("ingest.claim_pipeline.get_fetcher", lambda source_type: _Fetcher())

    rc = cli.main(["--root", str(tmp_path), "claim", "ingest", "openai_news"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert "graph_sync" not in payload
    assert get_claim_graph_node(root=tmp_path, claim_id=payload["claim_ids"][0]) is None


def test_claim_ingest_persist_graph_requires_graph_flag(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("PMOS_V5_CLAIMS_ENABLED", "true")
    monkeypatch.setenv("PMOS_V5_CLAIM_INGEST_ENABLED", "true")
    monkeypatch.delenv("PMOS_V5_CLAIM_GRAPH_ENABLED", raising=False)

    rc = cli.main(["--root", str(tmp_path), "claim", "ingest", "openai_news", "--persist-graph"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "PMOS_V5_CLAIM_GRAPH_ENABLED is not enabled"


def test_claim_graph_cli_respects_feature_flag(tmp_path, capsys) -> None:
    rc = cli.main(["--root", str(tmp_path), "claim", "graph", "sync"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "PMOS_V5_CLAIM_GRAPH_ENABLED is not enabled"
