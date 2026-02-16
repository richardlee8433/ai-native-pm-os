from __future__ import annotations

from jsonschema import Draft7Validator, FormatChecker

from pm_os_contracts.models import SIGNAL, load_schema


def validate_signal_contract(signal: SIGNAL) -> None:
    payload = signal.to_dict()
    validator = Draft7Validator(schema=load_schema("SIGNAL"), format_checker=FormatChecker())
    validator.validate(payload)
    SIGNAL.model_validate(payload)
