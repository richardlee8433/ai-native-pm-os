from __future__ import annotations

import os


def _flag_enabled(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def claims_enabled() -> bool:
    return _flag_enabled("PMOS_V5_CLAIMS_ENABLED", default=False)


def claim_ingest_enabled() -> bool:
    return _flag_enabled("PMOS_V5_CLAIM_INGEST_ENABLED", default=False)
