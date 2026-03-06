from __future__ import annotations

from typing import Any


def build_validation_plan_from_graph(graph: dict[str, Any]) -> dict[str, Any]:
    core_claim = graph.get("core_claim") or ""
    hypothesis = graph.get("hypothesis_statement") or ""
    seed = graph.get("validation_seed") or {}
    idea = seed.get("seven_day_validation_idea") or seed.get("idea") or ""
    options = seed.get("implementation_options") or []
    chosen = _normalize_option(options[0]) if options else None

    claim = hypothesis or core_claim or graph.get("title") or "Validation claim"
    return {
        "claim": claim,
        "chosen_implementation_option": chosen,
        "experiment_design": idea,
        "timebox_days": 7,
        "metrics": [],
        "success_criteria": [],
        "risks": [],
    }


def _normalize_option(option: Any) -> dict[str, Any]:
    if isinstance(option, dict):
        payload = {
            "option_id": option.get("option_id"),
            "label": option.get("label"),
            "summary": option.get("summary"),
        }
        return {k: v for k, v in payload.items() if v is not None}
    if isinstance(option, str):
        return {"label": option}
    return {}
