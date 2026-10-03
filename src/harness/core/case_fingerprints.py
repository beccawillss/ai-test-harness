"""Versioned case representations, independent of default model serialization."""

from __future__ import annotations

import math
from typing import Any, Literal, cast

from harness.core.fingerprints import fingerprint
from harness.core.models import TestCase

CaseFingerprintScheme = Literal["dataset-cases-v1", "dataset-cases-v2"]
CASE_SCHEME_V1: CaseFingerprintScheme = "dataset-cases-v1"
CASE_SCHEME_V2: CaseFingerprintScheme = "dataset-cases-v2"
LEGACY_CASE_FIELDS = ("id", "input", "reference", "tags", "extra")
DEFINITION_FIELDS = ("title", "description", "category", "risk")


def validate_case_scheme(scheme: str) -> CaseFingerprintScheme:
    """Never infer a representation from fields or silently downgrade it."""
    if scheme not in (CASE_SCHEME_V1, CASE_SCHEME_V2):
        raise ValueError("Unknown case fingerprint scheme")
    return cast(CaseFingerprintScheme, scheme)


def _finite_json(value: Any, ancestors: set[int]) -> None:
    """Check before model serialization can coerce non-JSON Python values."""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) not in (list, dict):
        raise ValueError("V2 case values must be finite JSON data")
    if id(value) in ancestors:
        raise ValueError("V2 case values must not contain cycles")
    ancestors.add(id(value))
    try:
        if isinstance(value, dict):
            if any(type(key) is not str for key in value):
                raise ValueError("V2 JSON object keys must be strings")
            children = value.values()
        else:
            children = value
        for child in children:
            _finite_json(child, ancestors)
    finally:
        ancestors.remove(id(value))


def validate_v2_case(case: TestCase) -> None:
    """Validate Python-created/mutated cases without tightening legacy models."""
    values = {
        key: getattr(case, key) for key in (*LEGACY_CASE_FIELDS, *DEFINITION_FIELDS)
    }
    validate_json_data(values)
    # Validate a dictionary, not an already constructed model (which Pydantic
    # otherwise need not revalidate). This also rechecks the new-field rules.
    try:
        TestCase.model_validate(values, strict=True)
    except ValueError:
        raise ValueError("Invalid v2 case field types or definition text") from None
    for value in (case.id, *case.tags):
        if not value or value != value.strip():
            raise ValueError(
                "V2 identity values must be nonblank without boundary whitespace"
            )
    if len(set(case.tags)) != len(case.tags):
        raise ValueError("V2 tags must be unique")


def validate_json_data(value: Any) -> None:
    """Validate authored JSON before serialization can normalize Python values."""
    _finite_json(value, set())


def case_payload(case: TestCase, *, scheme: str) -> dict[str, Any]:
    """Return the explicit definition, including all defaults for its scheme."""
    selected_scheme = validate_case_scheme(scheme)
    if selected_scheme == CASE_SCHEME_V1:
        if any(getattr(case, key) is not None for key in DEFINITION_FIELDS):
            raise ValueError("Populated definition fields require dataset-cases-v2")
        return case.model_dump(mode="json", include=set(LEGACY_CASE_FIELDS))
    validate_v2_case(case)
    # The ordinary serializer omits new nulls for legacy compatibility. The v2
    # representation deliberately includes them, including explicit nulls.
    payload = case.model_dump(mode="json", include=set(LEGACY_CASE_FIELDS))
    payload.update({key: getattr(case, key) for key in DEFINITION_FIELDS})
    return payload


def hash_case_definition(case: TestCase, *, scheme: str) -> str:
    """Single-case hash; distinct from the hash of a one-element dataset."""
    payload = case_payload(case, scheme=scheme)
    if scheme == CASE_SCHEME_V1:
        return fingerprint(payload)
    return fingerprint({"scheme": CASE_SCHEME_V2, "case": payload})


def resolved_case_payload(case: TestCase, *, scheme: str) -> dict[str, Any]:
    """Explicit full input/reference snapshot; metadata has a separate policy."""
    payload = case_payload(case, scheme=scheme)
    del payload["extra"]
    return payload
