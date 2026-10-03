"""Small shared v2 definition projection rules for execution and verification."""

from collections.abc import Sequence
from copy import deepcopy
from typing import Any, Literal

from harness.core.case_fingerprints import (
    CASE_SCHEME_V2,
    hash_case_definition,
    validate_json_data,
)
from harness.core.models import CaseDefinitionSnapshot, TestCase

PayloadPolicy = Literal["hashes_only", "full"]


def metadata_keys(keys: Sequence[str]) -> list[str]:
    """A trusted integration reviews each allowed subtree; names imply no safety."""
    if not isinstance(keys, (list, tuple)) or len(keys) > 128:
        raise ValueError("Metadata allowlist must contain at most 128 keys")
    if any(type(key) is not str or not key for key in keys):
        raise ValueError("Metadata allowlist keys must be nonempty strings")
    if len(set(keys)) != len(keys):
        raise ValueError("Metadata allowlist keys must be unique")
    return list(keys)


def project_metadata(extra: dict[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    projected = {key: extra[key] for key in metadata_keys(keys) if key in extra}
    validate_json_data(projected)
    return deepcopy(projected)


def definition_snapshot(
    case: TestCase, keys: Sequence[str] = ()
) -> CaseDefinitionSnapshot:
    return CaseDefinitionSnapshot(
        definition_hash=hash_case_definition(case, scheme=CASE_SCHEME_V2),
        title=case.title,
        description=case.description,
        category=case.category,
        risk=case.risk,
        extra=project_metadata(case.extra, keys),
    )
