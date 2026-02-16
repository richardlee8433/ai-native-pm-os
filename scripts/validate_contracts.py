#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pm_os_contracts.models import CONTRACT_MODEL_MAP, load_schema


def validate_schema_definitions() -> None:
    for contract_name in CONTRACT_MODEL_MAP:
        schema = load_schema(contract_name)
        Draft7Validator.check_schema(schema)


def validate_payload(contract_name: str, payload: dict[str, Any]) -> None:
    schema = load_schema(contract_name)
    validator = Draft7Validator(schema=schema, format_checker=FormatChecker())
    validator.validate(payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate AI-Native PM OS contracts")
    parser.add_argument("--contract", choices=sorted(CONTRACT_MODEL_MAP.keys()))
    parser.add_argument("--input", type=Path, help="Path to JSON payload for contract validation")
    parser.add_argument(
        "--validate-schemas-only",
        action="store_true",
        help="Validate all JSON Schema files only",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        validate_schema_definitions()

        if args.validate_schemas_only:
            print("OK: all contract schemas are valid draft-07 schemas")
            return 0

        if not args.contract or not args.input:
            print("ERROR: --contract and --input are required unless --validate-schemas-only is used")
            return 2

        payload = json.loads(args.input.read_text(encoding="utf-8"))
        validate_payload(args.contract, payload)
        CONTRACT_MODEL_MAP[args.contract].model_validate(payload)

        print(f"OK: {args.contract} payload is valid against JSON Schema and Pydantic model")
        return 0
    except (ValidationError, ValueError) as exc:
        print(f"VALIDATION ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
