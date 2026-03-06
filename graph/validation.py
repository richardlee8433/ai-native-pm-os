from __future__ import annotations

from typing import Any


def validate_newsletter_hypothesis_payload(payload: dict[str, Any]) -> None:
    source_ref = payload.get("source_ref")
    if not isinstance(source_ref, dict):
        return
    if source_ref.get("source_type") != "pm_newsletter":
        return

    missing = []
    _require_str(source_ref.get("source_name"), "source_ref.source_name", missing)
    _require_str(source_ref.get("source_type"), "source_ref.source_type", missing)
    _require_str(source_ref.get("source_url"), "source_ref.source_url", missing)
    _require_str(source_ref.get("credibility"), "source_ref.credibility", missing)
    _require_str(payload.get("core_claim"), "core_claim", missing)
    _require_str(payload.get("hypothesis_statement"), "hypothesis_statement", missing)
    _require_str(payload.get("routing_decision"), "routing_decision", missing)
    _require_str(payload.get("justification"), "justification", missing)

    validation_seed = payload.get("validation_seed")
    if not isinstance(validation_seed, dict):
        missing.append("validation_seed")
    else:
        _require_str(
            validation_seed.get("seven_day_validation_idea"),
            "validation_seed.seven_day_validation_idea",
            missing,
        )
        implementation_options = validation_seed.get("implementation_options")
        if not isinstance(implementation_options, list) or not implementation_options:
            missing.append("validation_seed.implementation_options")

    if missing:
        raise ValueError(f"Newsletter hypothesis payload missing required fields: {', '.join(missing)}")


def _require_str(value: Any, label: str, missing: list[str]) -> None:
    if value is None:
        missing.append(label)
        return
    if not isinstance(value, str) or not value.strip():
        missing.append(label)
