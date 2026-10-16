"""Opt-in Sales Agent rules; generic assertions and runner semantics stay unchanged."""

from __future__ import annotations

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
