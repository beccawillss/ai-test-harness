"""Local validation/projection of the public Sales Agent V1 HTTP contract.

No target package is imported. Unknown fields are discarded at every level;
only declared commerce facts cross the normalized evidence boundary.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer


def decimal_value(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Expected a finite decimal")  # noqa: TRY004 - Pydantic validator
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Expected a finite decimal") from None
    if not result.is_finite():
        raise ValueError("Expected a finite decimal")
    return result


def decimal_text(value: Decimal) -> str:
    # Never round an incorrect price into a passing value.
    whole, _, fraction = format(value, "f").partition(".")
    return whole + "." + fraction.rstrip("0").ljust(2, "0")


Money = Annotated[
    Decimal,
    BeforeValidator(decimal_value),
    Field(ge=0),
    PlainSerializer(decimal_text, return_type=str),
]
Percentage = Annotated[Money, Field(le=100)]
Nonempty = Annotated[str, Field(min_length=1, pattern=r"\S")]
Count = Annotated[int, Field(ge=0)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)


class Variant(Contract):
    colour: str
    size: str
    stock: Count


class Recommendation(Contract):
    product_id: Nonempty
    name: str
    price: Money
    currency: Literal["GBP"]
    product_url: str
    availability: Literal["in_stock", "out_of_stock", "partial", "unknown"]
    matched_variant: Variant | None = None


class Promotion(Contract):
    code: str
    valid: bool
    discount_percent: Percentage | None = None
    reason: str | None = None


class Pricing(Contract):
    product_id: str
    original_price: Money = Field(validation_alias="base_price")
    final_price: Money
    currency: Literal["GBP"]
    discount_code: str | None = None
    discount_percent: Percentage | None = None


class Chat(Contract):
    session_id: Nonempty
    trace_id: Nonempty
    message: str
    recommendations: list[Recommendation] = Field(max_length=3)
    promotion: Promotion | None = None
    pricing: Pricing | None = None


class Constraints(Contract):
    category: str | None = None
    activity: str | None = None
    weather: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    maximum_price: Money | None = None
    colour: str | None = None
    size: str | None = None
    season: str | None = None
    priority: str | None = None


class Change(Contract):
    field: str
    previous: Any
    current: Any


class Validation(Contract):
    all_products_exist: bool
    prices_match_catalogue: bool
    urls_match_catalogue: bool
    stock_claims_validated: bool
    validation_errors: list[str] = Field(default_factory=list)


class Usage(Contract):
    input_tokens: Count
    output_tokens: Count
    total_tokens: Count


class Error(Contract):
    code: str
    # Deliberately exclude arbitrary diagnostic text from persisted evidence.
    message: str = Field(exclude=True)
    tool_call_id: str | None = None


class Tool(Contract):
    sequence: Annotated[int, Field(ge=1)]
    tool_call_id: Nonempty
    tool_name: Literal[
        "search_products", "get_product", "check_inventory", "validate_discount"
    ]
    arguments: dict[str, Any]
    result: dict[str, Any]
    status: Literal["success", "error"]
    duration_ms: Count


class Trace(Contract):
    trace_id: Nonempty
    session_id: Nonempty
    timestamp: Nonempty
    turn_index: Annotated[int, Field(ge=1)]
    user_message: str
    model: Nonempty
    prompt_version: Nonempty
    resolved_constraints: Constraints
    constraint_changes: list[Change]
    tool_calls: list[Tool]
    recommendation_validation: Validation
    recommended_product_ids: list[str]
    promotion: Promotion | None = None
    pricing: Pricing | None = None
    latency_ms: Count
    token_usage: Usage
    errors: list[Error]


class SearchArguments(Contract):
    category: str | None = None
    activity: str | None = None
    weather: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    maximum_price: Money | None = None
    colour: str | None = None
    size: str | None = None
    in_stock_only: bool = False


class ProductArguments(Contract):
    product_id: str


class InventoryArguments(ProductArguments):
    colour: str
    size: str


class DiscountArguments(Contract):
    code: str


class Product(Contract):
    product_id: str
    name: str
    price: Money
    currency: Literal["GBP"]
    product_url: str
    category: str
    activities: list[str]
    weather: list[str]
    features: list[str]
    variants: list[Variant]
    total_stock: Count


class SearchResult(Contract):
    products: list[Product]
    count: Count


class Inventory(InventoryArguments):
    stock: Count | None = None
    available: bool
    status: Literal[
        "in_stock", "out_of_stock", "variant_not_found", "product_not_found"
    ]


class ToolResult(Contract):
    tool_name: str
    success: bool
    data: dict[str, Any] | None
    error: Error | None


ARGUMENTS: dict[str, type[Contract]] = {
    "search_products": SearchArguments,
    "get_product": ProductArguments,
    "check_inventory": InventoryArguments,
    "validate_discount": DiscountArguments,
}
RESULTS: dict[str, type[Contract]] = {
    "search_products": SearchResult,
    "get_product": Product,
    "check_inventory": Inventory,
    "validate_discount": Promotion,
}
# These indicate rejected proposals or ordinary tool business outcomes, not
# unavailable infrastructure. Unknown failure categories must fail closed.
BUSINESS_ERRORS = frozenset(
    {
        "unknown_tool",
        "invalid_arguments",
        "product_not_found",
        "ungrounded_promotion_code",
        "promotion_nomination_missing",
    }
)
