"""Opt-in Sales Agent rules; generic assertions and runner semantics stay unchanged."""

from __future__ import annotations

from copy import deepcopy
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from harness.core.models import Score, TargetResponse, TestCase
from harness.packs.salesagent_semantic import _Commerce, _Product, _Promotion
from harness.scorers.base import MissingFieldError
from harness.scorers.structured_assertions import (
    StructuredAssertionsScorer,
    validate_assertions,
)
from harness.targets.salesagent import validate_input


class DiscountRule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1)
    rule: Literal["validated-discount-v1"]
    turn: int = Field(ge=0)
    gated: Literal[True]
    critical: Literal[True]


def validate_rules(case: TestCase) -> list[DiscountRule]:
    """Validate evaluator configuration before target execution, without ID dispatch."""
    assertions = validate_assertions(case.reference)
    assert isinstance(case.reference, dict)  # validated by validate_assertions
    raw = case.reference.get("salesagent_rules", [])
    if not isinstance(raw, list):
        raise ValueError("salesagent_rules must be a list")  # noqa: TRY004 - invalid configuration
    rules = [DiscountRule.model_validate(item) for item in raw]
    ids = [a.id for a in assertions] + [r.id for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("Assertion and Sales Agent rule IDs must be unique")
    turns = validate_input(case.input)
    if any(r.turn >= len(turns) for r in rules):
        raise ValueError("Sales Agent rule turn is outside the conversation")
    return rules


def _discount_supported(turn: dict[str, Any]) -> bool:
    commerce = _Commerce.model_validate(turn["structured"])
    calls = turn["trajectory"]
    if not isinstance(calls, list):
        raise TypeError("Missing turn trajectory")
    promotions: list[_Promotion] = []
    products: list[_Product] = []
    argument_codes: list[str] = []
    for call in calls:
        if not isinstance(call, dict) or not isinstance(call["name"], str):
            raise TypeError("Malformed tool observation")
        result, error = call["result"], call["error"]
        if error is not None:
            if not isinstance(error, str):
                raise TypeError("Malformed tool error")
            continue
        if call["name"] == "validate_discount":
            code = call["arguments"]["code"]
            if not isinstance(code, str):
                raise TypeError("Malformed discount argument")
            promotions.append(_Promotion.model_validate(result))
            argument_codes.append(code.strip().casefold())
        elif call["name"] in {"get_product", "search_products"}:
            records = (
                result["products"] if call["name"] == "search_products" else [result]
            )
            if not isinstance(records, list):
                raise TypeError("Malformed product observations")
            products.extend(_Product.model_validate(p) for p in records)

    promotion, quote = commerce.promotion, commerce.pricing
    if promotion is None:
        return quote is None
    if not promotion.valid or promotion.discount_percent is None:
        return False
    matching = [
        (p, code)
        for p, code in zip(promotions, argument_codes)
        if p.code == promotion.code or code == promotion.code.casefold()
    ]
    if not matching or any(
        p != promotion or code != promotion.code.casefold() for p, code in matching
    ):
        return False
    if quote is None:
        return True  # A validated offer need not yet be a priced quote.
    if (
        quote.discount_code != promotion.code
        or quote.discount_percent != promotion.discount_percent
    ):
        return False
    observed = [p for p in products if p.product_id == quote.product_id]
    if not observed or any(
        p.price != quote.original_price or p.currency != quote.currency
        for p in observed
    ):
        return False
    discount = (quote.original_price * promotion.discount_percent / 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return quote.final_price == quote.original_price - discount


class StudyAssertionsScorer(StructuredAssertionsScorer):
    """One uniform Study scorer with explicit, fingerprinted per-case rule opt-ins."""

    schema_version = "salesagent-study-assertions-v2"

    def score(self, case: TestCase, response: TargetResponse) -> Score:
        rules = validate_rules(case)
        shoppers = validate_input(case.input)
        base = super().score(case, response)
        outcomes = list(base.extra["assertions"])
        for rule in rules:
            try:
                turns = response.structured["turns"]
                if not isinstance(turns, list) or len(turns) != len(shoppers):
                    raise ValueError("Misaligned turns")
                turn = turns[rule.turn]
                if (
                    type(turn["index"]) is not int
                    or turn["index"] != rule.turn
                    or turn["input"] != shoppers[rule.turn]
                ):
                    raise ValueError("Misaligned turn")
                passed = _discount_supported(turn)
            except (
                ValidationError,
                KeyError,
                IndexError,
                TypeError,
                ValueError,
                ArithmeticError,
            ):
                raise MissingFieldError(
                    self.name, "valid current-turn discount evidence"
                ) from None
            outcomes.append(
                {"id": rule.id, "passed": passed, "gated": True, "critical": True}
            )
        count = sum(o["passed"] is True for o in outcomes)
        gates = [o["passed"] for o in outcomes if o["gated"]]
        return base.model_copy(
            update={
                "value": count / len(outcomes),
                "passed": all(gates) if gates else None,
                "reason": f"{count}/{len(outcomes)} assertions passed",
                "extra": {**base.extra, "assertions": outcomes},
            }
        )


def _turn_prefix(path: tuple[str | int, ...]) -> tuple[str | int, ...]:
    if (
        len(path) >= 3
        and path[:2] == ("structured", "turns")
        and (type(path[2]) is int or path[2] == "*")
    ):
        return path[:3]
    return ()


def _tool_path(path: tuple[str | int, ...]) -> tuple[str | int, ...] | None:
    """Recognize normalized tool entries, never arbitrary nested `name` keys."""
    if _turn_prefix(path):
        path = path[3:]
    if (
        len(path) >= 2
        and path[0] == "trajectory"
        and (type(path[1]) is int or path[1] == "*")
    ):
        return path[:2]
    return None


def _comparison_value(
    value: Any,
    path: tuple[str | int, ...],
    tool_names: dict[tuple[str | int, ...], str],
    tool_name: str | None = None,
    *,
    member: bool = False,
) -> Any:
    """Copy only approved labels into a comparison view; no coercion or aliases."""
    entry = _tool_path(path)
    prefix = _turn_prefix(path)
    if entry is not None:
        if tool_name is None:
            tool_name = tool_names.get(prefix + entry)
        if path == prefix + entry and isinstance(value, dict):
            tool_name = value.get("name", tool_name)
    if isinstance(value, dict):
        return {
            key: _comparison_value(item, (*path, key), tool_names, tool_name)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _comparison_value(item, (*path, i), tool_names, tool_name, member=True)
            for i, item in enumerate(value)
        ]
    if not isinstance(value, str):
        return value
    tail = path[3:] if prefix else path
    constraint = tail[:2] == ("evidence", "resolved_constraints") and bool(prefix)
    label = constraint and (
        (len(tail) == 3 and tail[2] in {"colour", "size"})
        or (len(tail) == 4 and tail[2] == "features" and member)
    )
    if entry is not None:
        field = tail[2:]
        label |= tool_name == "search_products" and field == ("arguments", "category")
        label |= (
            tool_name == "check_inventory"
            and len(field) == 2
            and field[0] == "result"
            and field[1] in {"colour", "size"}
        )
    return value.casefold() if label else value


class StudyLabelAssertionsScorer(StudyAssertionsScorer):
    """V3 label comparisons; the v2 scorer above remains explicitly available."""

    schema_version = "salesagent-study-assertions-v3"

    def score(self, case: TestCase, response: TargetResponse) -> Score:
        assertions = validate_assertions(case.reference)
        raw = response.model_dump(mode="json")
        tool_names: dict[tuple[str | int, ...], str] = {}
        for j, call in enumerate(response.trajectory or []):
            tool_names[("trajectory", j)] = call.name
        # Concrete indexed assertion paths can inherit the observed tool type.
        turns = response.structured.get("turns", [])
        if isinstance(turns, list):
            for i, turn in enumerate(turns):
                calls = turn.get("trajectory", []) if isinstance(turn, dict) else []
                if isinstance(calls, list):
                    for j, call in enumerate(calls):
                        if isinstance(call, dict) and isinstance(call.get("name"), str):
                            tool_names[("structured", "turns", i, "trajectory", j)] = (
                                call["name"]
                            )
        comparison = case.model_copy(deep=True)
        assert isinstance(comparison.reference, dict)  # validated above
        for assertion, item in zip(assertions, comparison.reference["assertions"]):
            if "expected" not in item:
                continue  # expected_path resolves against the same comparison view.
            path = tuple(assertion.path)
            if assertion.op in {"contains", "excludes"}:
                path += ("*",)  # The expected value describes a collection member.
            member = type(path[-1]) is int or path[-1] == "*"
            if assertion.op == "matches_any":
                item["expected"] = [
                    _comparison_value(v, path, tool_names, member=member)
                    for v in assertion.expected
                ]
            else:
                item["expected"] = _comparison_value(
                    assertion.expected, path, tool_names, member=member
                )
        view = deepcopy(response)
        view.structured = _comparison_value(
            raw["structured"], ("structured",), tool_names
        )
        # Top-level trajectory is another normalized view, never persisted mutated.
        if response.trajectory is not None:
            view.trajectory = [
                type(call).model_validate(
                    _comparison_value(record, ("trajectory", i), tool_names)
                )
                for i, (call, record) in enumerate(
                    zip(response.trajectory, raw["trajectory"])
                )
            ]
        return super().score(comparison, view)
