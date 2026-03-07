from __future__ import annotations

import datetime as dt

from ingest.newsletter_governance import process_newsletter_source, select_weekly_items
from ingest.registry import SourceConfig
from graph.ops import GraphStore


def test_newsletter_governance_only_applies_to_pm_newsletter(tmp_path) -> None:
    cfg = SourceConfig(id="demo", type="rss", url="https://example.com", source_type="rss")
    payload = process_newsletter_source(source_cfg=cfg, items=[], root=tmp_path)
    assert payload["ok"] is False
    assert payload["reason"] == "unsupported source_type"


def test_weekly_scarcity_selects_highest_validation_potential() -> None:
    now = dt.datetime(2026, 2, 25, tzinfo=dt.timezone.utc)
    items = [
        {"title": "Basic update", "content": "notes", "published_at": now},
        {"title": "MVP experiment", "content": "run an experiment", "published_at": now},
    ]
    selected = select_weekly_items(items, now)
    assert len(selected) == 1
    assert selected[0]["title"] == "MVP experiment"


def test_buildable_creates_graph_and_options(tmp_path) -> None:
    cfg = SourceConfig(id="lenny", type="html_list", url="https://example.com", source_type="pm_newsletter")
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
    assert payload["ok"] is True
    assert payload["processed"] == 1
    decision = payload["decisions"][0]
    assert decision["routing_decision"] == "buildable"
    assert decision["idea"].startswith("Run a 7-day experiment")
    assert 2 <= len(decision["options"]) <= 3
    assert decision["source_url"] == "https://example.com/post"
    assert decision["source_type"] == "pm_newsletter"
    assert decision["justification"]
    assert decision["timestamp"]
    assert decision["core_claim"] == "Build an MVP workflow experiment"
    assert decision["hypothesis_statement"].startswith("If we apply")
    assert decision["seven_day_validation_idea"].startswith("Run a 7-day experiment")
    assert decision["implementation_options"]
    assert decision["content_id"]

    graph_store = GraphStore(tmp_path)
    graph = graph_store.get(decision["graph_node_id"])
    assert graph is not None
    assert graph["validation_plan"] in {"system_build", "decision_engine"}
