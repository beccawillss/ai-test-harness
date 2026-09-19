"""Load and fingerprint evaluation datasets."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

from harness.core.models import TestCase


def load_cases(path: str | Path) -> list[TestCase]:
    """Load one TestCase per non-blank line from a JSONL file."""
    dataset_path = Path(path)
    try:
        text = dataset_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read dataset '{dataset_path}': {exc}") from exc

    cases: list[TestCase] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(TestCase.model_validate_json(line))
        except ValueError as exc:
            raise ValueError(
                f"{dataset_path}:{line_number}: invalid TestCase: {exc}"
            ) from exc

    if not cases:
        raise ValueError(f"Dataset '{dataset_path}' contains no test cases.")
    return cases


def hash_cases(cases: Iterable[TestCase]) -> str:
    """Fingerprint parsed cases in order, independent of JSON formatting."""
    digest = hashlib.sha256()
    for case in cases:
        payload = json.dumps(
            case.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        digest.update(payload.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


__all__ = ["hash_cases", "load_cases"]
