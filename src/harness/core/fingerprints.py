"""Versioned fingerprints of normalized evaluation data, not provider objects."""

import hashlib
import json
from typing import Any

CANONICAL_VERSION = "replay-canonical-json-v1"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def fingerprint(value: Any) -> str:
    return text_hash(canonical_json(value))
