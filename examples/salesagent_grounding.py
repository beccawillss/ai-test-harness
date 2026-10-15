"""Diagnose saved normalized responses against explicit authority, entirely offline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from harness.core.case_fingerprints import validate_json_data
from harness.core.fingerprints import canonical_json
from harness.core.models import TargetResponse
from harness.packs.salesagent_grounding import (
    GroundingConfigurationError,
    GroundingDiagnosticContext,
    diagnose_numeric_waterproof_claims,
)


class _InputError(ValueError):
    """Safe CLI input error; never includes saved evidence or exception text."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _read_json(path: Path, role: str) -> Any:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
        validate_json_data(value)
        canonical_json(value).encode("utf-8")
        return value
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise _InputError(
            f"{role}: expected a readable, finite UTF-8 JSON document with unique keys"
        ) from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--response", type=Path, required=True, help="Saved TargetResponse JSON"
    )
    parser.add_argument(
        "--context", type=Path, required=True, help="GroundingDiagnosticContext JSON"
    )
    parser.add_argument(
        "--authority",
        type=Path,
        required=True,
        help="Explicit authority manifest JSON (or JSON null for absent authority)",
    )
    options = parser.parse_args(argv)
    try:
        response_data = _read_json(options.response, "response")
        context_data = _read_json(options.context, "context")
        authority = _read_json(options.authority, "authority")
        try:
            response = TargetResponse.model_validate(
                response_data, strict=True, extra="forbid"
            )
        except ValidationError:
            raise _InputError(
                "response: invalid normalized TargetResponse envelope"
            ) from None
        try:
            context = GroundingDiagnosticContext.model_validate(context_data)
        except ValidationError:
            raise _InputError("context: invalid GroundingDiagnosticContext") from None
        report = diagnose_numeric_waterproof_claims(
            response, context=context, authority=authority
        )
    except (_InputError, GroundingConfigurationError) as error:
        message = (
            str(error)
            if isinstance(error, _InputError)
            else "context: invalid diagnostic configuration"
        )
        print(message, file=sys.stderr)
        return 2
    print(report.canonical_body())
    return 0 if report.execution_status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
