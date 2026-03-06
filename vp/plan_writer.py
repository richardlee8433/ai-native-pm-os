from __future__ import annotations

from pathlib import Path
from typing import Any


def write_vp_plan(root: Path, project: dict[str, Any], graph: dict[str, Any] | None = None) -> Path:
    project_id = project.get("id", "VP-UNKNOWN")
    project_path = project.get("path")
    if project_path:
        base_dir = root / project_path
    else:
        base_dir = root / "validation_projects" / project_id
    base_dir.mkdir(parents=True, exist_ok=True)

    plan = project.get("validation_plan") or {}
    graph_id = _first_graph_id(project)
    core_claim = _first_value(graph, "core_claim") or plan.get("claim") or "n/a"
    hypothesis = _first_value(graph, "hypothesis_statement") or "n/a"
    chosen = plan.get("chosen_implementation_option") or {}
    chosen_text = _format_option(chosen)
    experiment_design = plan.get("experiment_design") or "n/a"
    timebox_days = plan.get("timebox_days")
    metrics = plan.get("metrics") or []
    success_criteria = plan.get("success_criteria") or []
    risks = plan.get("risks") or []

    lines = [
        "# Validation Plan",
        "",
        "## Source Graph",
        graph_id or "n/a",
        "",
        "## Core Claim",
        core_claim or "n/a",
        "",
        "## Hypothesis",
        hypothesis or "n/a",
        "",
        "## Chosen Implementation",
        chosen_text or "n/a",
        "",
        "## Experiment Design",
        experiment_design or "n/a",
    ]
    if timebox_days:
        lines.extend(["", f"Timebox Days: {timebox_days}"])
    lines.extend(["", "## Metrics"])
    if metrics:
        for metric in metrics:
            lines.append(f"- {_format_metric(metric)}")
    else:
        lines.append("n/a")
    lines.extend(["", "## Success Criteria"])
    if success_criteria:
        for item in success_criteria:
            lines.append(f"- {item}")
    else:
        lines.append("n/a")
    lines.extend(["", "## Risks"])
    if risks:
        for item in risks:
            lines.append(f"- {item}")
    else:
        lines.append("n/a")
    lines.append("")

    path = base_dir / "vp_plan.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _first_graph_id(project: dict[str, Any]) -> str | None:
    graph_ids = project.get("linked_graph_nodes") or []
    if graph_ids:
        return graph_ids[0]
    return None


def _first_value(graph: dict[str, Any] | None, key: str) -> str | None:
    if not graph:
        return None
    value = graph.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _format_option(option: dict[str, Any]) -> str:
    if not option:
        return ""
    option_id = option.get("option_id")
    label = option.get("label")
    summary = option.get("summary")
    parts = [part for part in [label, summary] if part]
    text = " — ".join(parts) if parts else ""
    if option_id and text:
        return f"{option_id}: {text}"
    if option_id:
        return option_id
    return text


def _format_metric(metric: Any) -> str:
    if isinstance(metric, dict):
        name = metric.get("name") or "metric"
        metric_type = metric.get("type")
        if metric_type:
            return f"{name} ({metric_type})"
        return name
    if isinstance(metric, str):
        return metric
    return "metric"
