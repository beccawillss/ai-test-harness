"""Loading and fingerprinting datasets.

The hash is the point of this module. A golden set that drifts silently —
a case edited, a line deleted — makes every historical comparison a lie,
and the drift is invisible precisely when it matters most: when a run
disagrees with its baseline. Every RunResult therefore carries a hash of
the cases it actually executed.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from pathlib import Path

from harness.core.errors import ConfigError
from harness.core.models import TestCase


def load_cases(path: str | Path) -> list[TestCase]:
    """Load a JSONL dataset: one TestCase object per line.

    Blank lines are skipped. Malformed lines raise ConfigError naming the
    line number — a dataset typo should be a two-second fix, not a hunt.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read dataset '{path}': {exc}") from exc

    cases: list[TestCase] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(TestCase.model_validate_json(line))
        except ValueError as exc:
            raise ConfigError(f"{path}:{lineno}: invalid TestCase: {exc}") from exc

    if not cases:
        raise ConfigError(f"Dataset '{path}' contains no cases.")
    return cases


def hash_cases(cases: Iterable[TestCase]) -> str:
    """Fingerprint the cases themselves, in order.

    Computed from the parsed models rather than the file bytes, so
    programmatically built sets are covered too and reformatting the JSONL
    doesn't read as drift. Order is part of the identity: the same cases in
    a different order is a different dataset for pairing runs case-by-case.
    """
    digest = hashlib.sha256()
    for case in cases:
        payload = json.dumps(case.model_dump(mode="json"), sort_keys=True)
        digest.update(payload.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def duplicate_case_ids(cases: Sequence[TestCase]) -> list[str]:
    """Return case ids appearing more than once, sorted.

    Case ids are the join key for regression comparison, so duplicates
    silently corrupt any diff against a baseline.
    """
    seen: set[str] = set()
    duplicates: set[str] = set()
    for case in cases:
        if case.id in seen:
            duplicates.add(case.id)
        seen.add(case.id)
    return sorted(duplicates)


__all__ = ["duplicate_case_ids", "hash_cases", "load_cases"]
