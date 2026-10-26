"""Opt-in, catalogue-bound no-match proof; historical Study scorers stay intact."""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from harness.core.models import Score, TargetResponse, TestCase
from harness.packs.salesagent_rules import StudyLabelAssertionsScorer, validate_rules
from harness.scorers.base import MissingFieldError
from harness.targets._salesagent_contract import (
    Money,
    Product,
    SearchArguments,
    SearchResult,
    WaterproofRating,
)
from harness.targets.salesagent import validate_input


def _label(value: str) -> str:
    # The public search contract applies strip/casefold, without aliases.
    return value.strip().casefold()


class SearchFact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    product_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    price: Money
    features: list[str]
    waterproof_rating: WaterproofRating


class NoMatchRule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1)
    rule: Literal["no-match-search-v1"]
    turn: int = Field(ge=0)
    gated: Literal[True]
    critical: Literal[False]
    category: Literal["jacket"]
    maximum_price: Money
    catalogue_revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    catalogue_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    catalogue: list[SearchFact] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_catalogue(self) -> NoMatchRule:
        ids = [p.product_id for p in self.catalogue]
        if len(ids) != len(set(ids)):
            raise ValueError("No-match catalogue IDs must be unique")
        if any(
            _label(p.category) == self.category
            and p.price <= self.maximum_price
            and "waterproof" in map(_label, p.features)
            for p in self.catalogue
        ):
            raise ValueError(
                "Reviewed catalogue contains an eligible waterproof jacket"
            )
        return self


class _SearchArguments(SearchArguments):
    # A new unrecognized filter must never disappear into an accepted proof.
    model_config = ConfigDict(extra="forbid", strict=True)


def validate_search_rules(case: TestCase) -> list[NoMatchRule]:
    """Validate v4 opt-ins while retaining unchanged v2/v3 rule validation."""
    legacy = case.model_copy(deep=True)
    raw = (
        legacy.reference.get("salesagent_rules", [])
        if isinstance(legacy.reference, dict)
        else []
    )
    if not isinstance(raw, list):
        raise ValueError("salesagent_rules must be a list")  # noqa: TRY004 - invalid evaluator configuration
    rules = []
    other = []
    for item in raw:
        if isinstance(item, dict) and item.get("rule") == "no-match-search-v1":
            rules.append(NoMatchRule.model_validate(item))
        else:
            other.append(item)
    if isinstance(legacy.reference, dict) and "salesagent_rules" in legacy.reference:
        legacy.reference["salesagent_rules"] = other
    existing = validate_rules(legacy)
    assert isinstance(legacy.reference, dict)  # validated by validate_rules
    ids = (
        [a["id"] for a in legacy.reference["assertions"]]
        + [r.id for r in existing]
        + [r.id for r in rules]
    )
    if len(ids) != len(set(ids)):
        raise ValueError("Assertion and Sales Agent rule IDs must be unique")
    if any(r.turn >= len(validate_input(case.input)) for r in rules):
        raise ValueError("Sales Agent rule turn is outside the conversation")
    return rules


def _covers_request(args: _SearchArguments, rule: NoMatchRule) -> bool:
    return (
        (args.category is None or _label(args.category) == rule.category)
        and (args.maximum_price is None or args.maximum_price >= rule.maximum_price)
        and all(_label(f) == "waterproof" for f in args.features)
        and args.activity is None
        and not args.weather
        and args.colour is None
        and args.size is None
        and not args.in_stock_only
    )


def _same_facts(observed: Product, expected: SearchFact) -> bool:
    return (
        observed.product_id == expected.product_id
        and _label(observed.category) == _label(expected.category)
        and observed.price == expected.price
        and Counter(map(_label, observed.features))
        == Counter(map(_label, expected.features))
        and observed.waterproof_rating == expected.waterproof_rating
    )


def _supports_no_match(turn: dict, rule: NoMatchRule) -> bool:
    calls = turn["trajectory"]
    if not isinstance(calls, list):
        raise TypeError("Missing turn trajectory")
    catalogue = {p.product_id: p for p in rule.catalogue}
    proof = False
    consistent = True
    for call in calls:
        if not isinstance(call, dict) or not isinstance(call.get("name"), str):
            raise TypeError("Malformed tool observation")
        if call["name"] != "search_products":
            continue
        error = call["error"]
        if error is not None:
            if not isinstance(error, str):
                raise TypeError("Malformed tool error")
            continue
        args = _SearchArguments.model_validate(call["arguments"])
        result = SearchResult.model_validate(call["result"])
        ids = [p.product_id for p in result.products]
        if result.count != len(ids) or len(ids) != len(set(ids)):
            raise ValueError("Malformed search count or duplicate product IDs")
        consistent &= all(
            p.product_id in catalogue and _same_facts(p, catalogue[p.product_id])
            for p in result.products
        )
        if not _covers_request(args, rule):
            continue
        expected = {
            p.product_id
            for p in rule.catalogue
            if (args.category is None or _label(p.category) == _label(args.category))
            and (args.maximum_price is None or p.price <= args.maximum_price)
            and set(map(_label, args.features)) <= set(map(_label, p.features))
        }
        consistent &= set(ids) == expected
        # The reviewed catalogue is already checked for absence at the case cap;
        # completeness plus unchanged source facts establishes the same absence.
        proof = True
    return proof and consistent


class StudySearchAssertionsScorer(StudyLabelAssertionsScorer):
    """V4 adds explicit no-match proof rules; no case-ID-based dispatch."""

    schema_version = "salesagent-study-assertions-v4"

    def score(self, case: TestCase, response: TargetResponse) -> Score:
        rules = validate_search_rules(case)
        legacy = case.model_copy(deep=True)
        assert isinstance(legacy.reference, dict)  # validated above
        if rules:
            legacy.reference["salesagent_rules"] = [
                r
                for r in legacy.reference["salesagent_rules"]
                if r["rule"] != "no-match-search-v1"
            ]
        base = super().score(legacy, response)
        outcomes = list(base.extra["assertions"])
        shoppers = validate_input(case.input)
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
                passed = _supports_no_match(turn, rule)
            except (
                ValidationError,
                KeyError,
                IndexError,
                TypeError,
                ValueError,
                ArithmeticError,
            ):
                raise MissingFieldError(
                    self.name, "valid current-turn no-match search evidence"
                ) from None
            outcomes.append(
                {"id": rule.id, "passed": passed, "gated": True, "critical": False}
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
