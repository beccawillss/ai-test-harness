"""Small declarative assertions over normalized JSON evidence.

Paths are lists of keys/indices; '*' projects list members. No code evaluation
or target-specific business rules are supported. See docs/structured-assertions.md.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harness.core.models import Score, ScorerKind, TargetResponse, TestCase
from harness.scorers.base import MissingFieldError

SCHEMA_VERSION = "structured-assertions-v1"
_MISSING = object()
_UNARY = {"is_null", "not_null", "nonempty"}
_OPS = Literal[
    "equals",
    "decimal_equals",
    "decimal_lte",
    "is_null",
    "not_null",
    "exists",
    "nonempty",
    "contains",
    "excludes",
    "matches",
    "matches_any",
    "subset",
]


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Decimal assertion requires finite numeric values")  # noqa: TRY004 - invalid evaluator data
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Decimal assertion requires finite numeric values") from None
    if not number.is_finite():
        raise ValueError("Decimal assertion requires finite numeric values")
    return number


def _valid_path(path: list[str | int]) -> None:
    if not path or any(
        isinstance(p, bool) or (isinstance(p, int) and p < 0) or p == "" for p in path
    ):
        raise ValueError("Paths require nonempty keys or nonnegative indices")
    if path[0] not in {
        "output",
        "structured",
        "metadata",
        "contexts",
        "trajectory",
        "latency_ms",
        "cost_usd",
    }:
        raise ValueError("Path must address normalized response evidence")


class Assertion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1)
    path: list[str | int]
    op: _OPS
    expected: Any = None
    expected_path: list[str | int] | None = None
    quantifier: Literal["any", "all"] | None = None
    gated: bool = True
    critical: bool = False

    @model_validator(mode="after")
    def check(self) -> Assertion:
        _valid_path(self.path)
        if self.expected_path is not None:
            _valid_path(self.expected_path)
        if self.critical and not self.gated:
            raise ValueError("Critical assertions must be gated")
        if "*" in self.path and self.quantifier is None:
            raise ValueError("Projected paths require an explicit quantifier")
        if "*" not in self.path and self.quantifier is not None:
            raise ValueError("Quantifiers require a projected path")
        has_expected = "expected" in self.model_fields_set
        if self.op in _UNARY:
            if has_expected or self.expected_path is not None:
                raise ValueError("Unary assertions have no expected value")
        elif has_expected == (self.expected_path is not None):
            raise ValueError("Specify exactly one of expected and expected_path")
        if self.op == "exists" and (
            not has_expected or type(self.expected) is not bool
        ):
            raise ValueError("exists requires a boolean expected value")
        if self.op.startswith("decimal_") and has_expected:
            _decimal(self.expected)
        if (
            self.op in {"matches_any", "subset"}
            and has_expected
            and not isinstance(self.expected, list)
        ):
            raise ValueError("Collection expectation must be a list")
        return self


def validate_assertions(reference: Any) -> list[Assertion]:
    if (
        not isinstance(reference, dict)
        or not isinstance(reference.get("assertions"), list)
        or not reference["assertions"]
    ):
        raise ValueError("A nonempty assertions list is required")
    try:
        assertions = [Assertion.model_validate(a) for a in reference["assertions"]]
    except ValueError:
        # Pydantic diagnostics include input values; keep persisted errors safe.
        raise ValueError("Malformed structured assertion configuration") from None
    if len({a.id for a in assertions}) != len(assertions):
        raise ValueError("Assertion IDs must be unique")
    return assertions


def _resolve(value: Any, path: list[str | int]) -> Any:
    if not path:
        return value
    key, *rest = path
    if value is _MISSING:
        return _MISSING
    if value is None:
        # A known nullable parent is business evidence, not missing telemetry.
        return None
    if key == "*":
        if not isinstance(value, list):
            raise ValueError("Projection requires a list")
        values = [_resolve(item, rest) for item in value]
        if "*" in rest:
            return [
                v
                for group in values
                for v in (group if isinstance(group, list) else [group])
            ]
        return values
    if isinstance(key, int):
        if not isinstance(value, list):
            raise ValueError("Index requires a list")  # noqa: TRY004 - invalid assertion path
        return _resolve(value[key] if key < len(value) else _MISSING, rest)
    if not isinstance(value, dict):
        raise ValueError("Key requires an object")  # noqa: TRY004 - invalid assertion path
    return _resolve(value.get(key, _MISSING), rest)


def _equal(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(
            _equal(v, expected[k]) for k, v in actual.items()
        )
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(
            _equal(a, b) for a, b in zip(actual, expected)
        )
    return bool(actual == expected)


def _matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            k in actual and _matches(actual[k], v) for k, v in expected.items()
        )
    return _equal(actual, expected)


def _missing(value: Any) -> bool:
    if value is _MISSING:
        return True
    if isinstance(value, list):
        return any(_missing(item) for item in value)
    return False


def _test(op: str, actual: Any, expected: Any) -> bool:
    if op == "exists":
        return (actual is not _MISSING) == expected
    if actual is _MISSING or expected is _MISSING:
        raise MissingFieldError("structured_assertions", "assertion path")
    if op == "is_null":
        return actual is None
    if op == "not_null":
        return actual is not None
    if op == "equals":
        return _equal(actual, expected)
    if op == "matches":
        return _matches(actual, expected)
    if op == "matches_any":
        if not isinstance(expected, list):
            raise ValueError("matches_any expectation must be a list")
        return any(_matches(actual, e) for e in expected)
    if actual is None:
        return False
    if op.startswith("decimal_"):
        a, b = _decimal(actual), _decimal(expected)
        return a == b if op == "decimal_equals" else a <= b
    if not isinstance(actual, list):
        raise ValueError("Collection assertion requires a list")  # noqa: TRY004 - invalid evidence
    if op == "nonempty":
        return bool(actual)
    if op in {"contains", "excludes"}:
        found = any(_matches(a, expected) for a in actual)
        return found if op == "contains" else not found
    if op == "subset":
        if not isinstance(expected, list):
            raise ValueError("subset expectation must be a list")
        return all(any(_matches(a, e) for e in expected) for a in actual)
    raise ValueError("Unknown assertion operator")


class StructuredAssertionsScorer:
    name = "structured_assertions"
    kind = ScorerKind.DETERMINISTIC
    schema_version = SCHEMA_VERSION

    def __init__(self, *, requires: frozenset[str] = frozenset({"structured"})) -> None:
        self.requires = frozenset(requires)

    def score(self, case: TestCase, response: TargetResponse) -> Score:
        assertions = validate_assertions(case.reference)
        for field in self.requires:
            value = getattr(response, field, None)
            if value is None or (field in {"structured", "metadata"} and value == {}):
                raise MissingFieldError(self.name, field)
        evidence = response.model_dump(mode="json")
        outcomes = []
        for assertion in assertions:
            actual = _resolve(evidence, assertion.path)
            expected = (
                _resolve(evidence, assertion.expected_path)
                if assertion.expected_path is not None
                else assertion.expected
            )
            if _missing(expected):
                raise MissingFieldError(self.name, "expected evidence path")
            if assertion.quantifier is not None:
                if actual is _MISSING:
                    raise MissingFieldError(self.name, "assertion projection")
                if actual is None:
                    passed = False
                else:
                    values = [_test(assertion.op, item, expected) for item in actual]
                    # Non-vacuous ALL: an empty projection cannot prove quality.
                    passed = bool(values) and (
                        all(values) if assertion.quantifier == "all" else any(values)
                    )
            else:
                passed = _test(assertion.op, actual, expected)
            outcomes.append(
                {
                    "id": assertion.id,
                    "passed": passed,
                    "gated": assertion.gated,
                    "critical": assertion.critical,
                }
            )
        gates = [o["passed"] for o in outcomes if o["gated"]]
        count = sum(o["passed"] is True for o in outcomes)
        return Score(
            name=self.name,
            kind=self.kind,
            value=count / len(outcomes),
            passed=all(gates) if gates else None,
            reason=f"{count}/{len(outcomes)} assertions passed",
            extra={"schema_version": self.schema_version, "assertions": outcomes},
        )
