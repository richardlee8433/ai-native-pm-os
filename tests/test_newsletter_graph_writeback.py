from __future__ import annotations

import datetime as dt

import pytest

from graph.ops import GraphStore
from ingest.newsletter_governance import build_newsletter_graph_payload, process_newsletter_source
from ingest.registry import SourceConfig


def test_newsletter_graph_payload_builder() -> None:
    cfg = SourceConfig(
        id="lenny",
        type="html_list",
        url="https://example.com",
        source_type="pm_newsletter",
        credibility="high",
        name="Lenny's Newsletter",
    )
    item = {"title": "Prototype a new PM workflow", "url": "https://example.com/post"}
    payload = build_newsletter_graph_payload(
        title=item["title"],
        core_claim="Prototype a new PM workflow",
        hypothesis_statement="Validate whether: Prototype a new PM workflow",
        routing_decision="buildable",
        justification="Contains buildable keywords: prototype",
        seven_day_validation_idea="7-Day Validation Idea: Prototype a new PM workflow",
        implementation_options=[
            {"option_id": "opt_a", "label": "Decision file only", "summary": "Decision file only"}
        ],
        validation_plan="system_build",
        source_cfg=cfg,
        item=item,
        content_id="post-123",
    )

    assert payload["node_type"] == "hypothesis"
    assert payload["title"]
    assert payload["source_ref"]["source_name"] == "Lenny's Newsletter"
    assert payload["source_ref"]["source_type"] == "pm_newsletter"
    assert payload["source_ref"]["source_url"] == "https://example.com/post"
    assert payload["core_claim"] == "Prototype a new PM workflow"
    assert payload["hypothesis_statement"].startswith("Validate whether:")
    assert payload["routing_decision"] == "buildable"
    assert payload["justification"]
    assert payload["validation_seed"]["seven_day_validation_idea"].startswith("7-Day Validation Idea")
    assert payload["validation_seed"]["implementation_options"]


def test_newsletter_graph_persistence_roundtrip(tmp_path) -> None:
    cfg = SourceConfig(
        id="lenny",
        type="html_list",
        url="https://example.com",
        source_type="pm_newsletter",
        credibility="high",
        name="Lenny's Newsletter",
    )
    now = dt.datetime(2026, 2, 25, tzinfo=dt.timezone.utc)
    items = [
        {
            "title": "Prototype a new PM workflow",
            "content": "Build an MVP workflow experiment",
            "url": "https://example.com/post",
            "published_at": now,
        }
    ]
    payload = process_newsletter_source(source_cfg=cfg, items=items, root=tmp_path, now=now)
    decision = payload["decisions"][0]

    graph_store = GraphStore(tmp_path)
    graph = graph_store.get(decision["graph_node_id"])
    assert graph is not None
    assert graph["source_ref"]["source_url"] == "https://example.com/post"
    assert graph["source_ref"]["source_type"] == "pm_newsletter"
    assert graph["core_claim"] == "Prototype a new PM workflow"
    assert graph["hypothesis_statement"].startswith("Validate whether:")
    assert graph["routing_decision"] == "buildable"
    assert graph["justification"]
    assert graph["validation_seed"]["seven_day_validation_idea"].startswith("7-Day Validation Idea")
    assert graph["validation_seed"]["implementation_options"]


def test_newsletter_graph_validation_failure(tmp_path) -> None:
    store = GraphStore(tmp_path)
    payload = {
        "node_type": "hypothesis",
        "title": "Missing fields",
        "source_ref": {"source_type": "pm_newsletter"},
    }
    with pytest.raises(ValueError):
        store.create_from_payload(payload)
