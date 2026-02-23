from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft7Validator

CONTRACTS_DIR = Path("contracts/v1.0")
EXPECTED_SCHEMAS = {
    "SIGNAL.schema.json",
    "ACTION_TASK.schema.json",
    "EVAL_REPORT.schema.json",
    "GATE_DECISION.schema.json",
    "LTI_NODE.schema.json",
    "COS_CASE.schema.json",
    "RTI_NODE.schema.json",
    "LTI_DRAFT.schema.json",
    "RTI_PROPOSAL.schema.json",
    "LPL_POST.schema.json",
    "ECHO_METRICS.schema.json",
}


def test_all_expected_schema_files_exist() -> None:
    found = {path.name for path in CONTRACTS_DIR.glob("*.schema.json")}
    assert found == EXPECTED_SCHEMAS


def test_all_schemas_are_valid_draft7() -> None:
    for file_name in EXPECTED_SCHEMAS:
        path = CONTRACTS_DIR / file_name
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft7Validator.check_schema(schema)
