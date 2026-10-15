"""Offline numeric reference agreement; deliberately independent of quality scores.

The grammar is bounded by salesagent-waterproof-diagnostic-v1. No target, judge,
dataset, or reference labels are consulted. Authority is evaluator-owned JSON;
malformed evidence is reported, while invalid caller configuration raises.
"""

from __future__ import annotations

import re
from copy import deepcopy
from decimal import Decimal, localcontext
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from harness.core.case_fingerprints import validate_json_data
from harness.core.fingerprints import canonical_json, fingerprint, text_hash
from harness.core.models import TargetResponse

CONTRACT: Literal["salesagent-waterproof-diagnostic-v1"] = (
    "salesagent-waterproof-diagnostic-v1"
)
EVIDENCE_VERSION = "salesagent-evidence-v2"
PROPERTY = "hydrostatic_head_mm"
AUTHORITY_CONTENT_LIMIT = 1_048_576
CONFIGURATION = {
    "contract_version": CONTRACT,
    "authority_content_limit_bytes": AUTHORITY_CONTENT_LIMIT,
    "grammar": "isolated English numeric waterproof/hydrostatic-head clauses",
    "exclusions": "questions, negation, attributed quotes, hypotheticals, other dimensions",
    "agent_grounding": "not_assessed",
}

# A JSON envelope, intentionally not an eagerly validating model: bad authority
# is evaluation evidence and must produce report errors, not configuration errors.
GroundingEvidenceManifest = dict[str, Any]


class GroundingConfigurationError(ValueError):
    """Caller configuration is invalid; no diagnostic execution took place."""


class GroundingDiagnosticContext(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    source_id: str = Field(min_length=1)
    attempt_index: int = Field(ge=0)
    synthetic: bool = False
    expected_response_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    harness_revision: str | None = None

    @field_validator("source_id", "harness_revision")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Identity must be nonblank")
        return value


class GroundingEvidenceError(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    code: str
    path: str
    scope: Literal["response", "authority", "turn"]
    turn_index: int | None = None


class GroundingDiagnosticReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    contract_version: Literal["salesagent-waterproof-diagnostic-v1"] = CONTRACT
    configuration: dict[str, Any]
    configuration_sha256: str
    harness_revision: str | None
    context: GroundingDiagnosticContext
    provenance: dict[str, Any]
    projection_sha256: str
    execution_status: Literal["complete", "partial", "error"]
    candidates: list[dict[str, Any]]
    errors: list[GroundingEvidenceError]
    counts: dict[str, int]
    turns_without_candidates: list[int]
    turns: list[dict[str, Any]]

    def semantic_projection(self) -> dict[str, Any]:
        """Frozen oracle fields; full identity provenance stays in the report.

        The oracle records the primary identity reference, preferring reviewed
        authority. Runtime candidates additionally retain every eligible identity
        reference in identity_evidence_refs, including prior tool observations.
        """
        result = self.model_dump(
            mode="json",
            include={
                "provenance",
                "execution_status",
                "candidates",
                "errors",
                "counts",
                "turns_without_candidates",
            },
        )
        for candidate in result["candidates"]:
            candidate.pop("identity_evidence_refs")
        return result

    def canonical_body(self) -> str:
        return canonical_json(self.model_dump(mode="json"))

    def body_sha256(self) -> str:
        return text_hash(self.canonical_body())


class _EvidenceIssue(Exception):
    def __init__(
        self,
        code: str,
        path: str,
        scope: Literal["response", "authority", "turn"],
        turn: int | None = None,
    ):
        self.error = GroundingEvidenceError(
            code=code, path=path, scope=scope, turn_index=turn
        )


def _require(
    condition: bool,
    code: str,
    path: str,
    scope: Literal["response", "authority", "turn"] = "authority",
    turn: int | None = None,
) -> None:
    if not condition:
        raise _EvidenceIssue(code, path, scope, turn)


def _object(value: Any, keys: set[str], path: str) -> None:
    _require(
        isinstance(value, dict) and set(value) == keys,
        "invalid_authority_structure",
        path,
    )


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _interval(value: Any, path: str) -> None:
    _object(value, {"first", "last"}, path)
    _require(
        type(value["first"]) is int
        and type(value["last"]) is int
        and 0 <= value["first"] <= value["last"],
        "invalid_authority_interval",
        path,
    )


def _at(interval: dict[str, int], turn: int) -> bool:
    return interval["first"] <= turn <= interval["last"]


def _numeric(value: str, unit: str = "mm") -> str | None:
    if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?", value):
        return None
    units = {
        **dict.fromkeys(
            ("mm", "millimetre", "millimetres", "millimeter", "millimeters"), 1
        ),
        **dict.fromkeys(
            ("cm", "centimetre", "centimetres", "centimeter", "centimeters"), 10
        ),
        **dict.fromkeys(("m", "metre", "metres", "meter", "meters"), 1000),
    }
    multiplier = units.get(unit.casefold())
    if multiplier is None:
        return None
    with localcontext() as ctx:
        ctx.prec = len(value) + 5
        number = Decimal(value.replace(",", "")) * multiplier
    if number <= 0:
        return None
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _validate_authority(authority: Any, context: GroundingDiagnosticContext) -> None:
    if authority is None:
        return
    _object(
        authority,
        {
            "contract_version",
            "source_set_id",
            "binding",
            "sources",
            "records",
            "review",
        },
        "/authority",
    )
    _require(
        authority["contract_version"] == CONTRACT,
        "unsupported_authority_version",
        "/authority/contract_version",
    )
    _require(
        _nonblank(authority["source_set_id"]),
        "invalid_authority_structure",
        "/authority/source_set_id",
    )
    binding = authority["binding"]
    if binding is not None:
        _object(binding, {"source_id", "attempt_index"}, "/authority/binding")
        _require(
            type(binding["attempt_index"]) is int
            and binding
            == {"source_id": context.source_id, "attempt_index": context.attempt_index},
            "authority_binding_mismatch",
            "/authority/binding",
        )
    sources, records, review = (
        authority["sources"],
        authority["records"],
        authority["review"],
    )
    _require(
        isinstance(sources, list) and isinstance(records, list),
        "invalid_authority_structure",
        "/authority",
    )
    # Integrity precedes semantic validation (including invalid numeric facts).
    seen: set[str] = set()
    for index, source in enumerate(sources):
        path = f"/authority/sources/{index}"
        _object(source, {"id", "revision", "sha256", "valid_turns", "content"}, path)
        _require(
            _nonblank(source["id"]) and source["id"] not in seen,
            "invalid_source_identity",
            path + "/id",
        )
        seen.add(source["id"])
        _require(
            _nonblank(source["revision"]), "invalid_source_identity", path + "/revision"
        )
        _interval(source["valid_turns"], path + "/valid_turns")
        _require(
            len(canonical_json(source["content"]).encode()) <= AUTHORITY_CONTENT_LIMIT,
            "authority_content_too_large",
            path + "/content",
        )
        _require(
            fingerprint(source["content"]) == source["sha256"],
            "source_hash_mismatch",
            path + "/sha256",
        )
    _object(
        review,
        {
            "status",
            "kind",
            "reviewer_id",
            "reviewed_source_hashes",
            "complete_source_set",
        },
        "/authority/review",
    )
    _require(
        review["status"] in ("reviewed", "unreviewed", "pending"),
        "invalid_authority_review",
        "/authority/review/status",
    )
    _require(
        review["kind"] in ("human", "synthetic_simulation"),
        "invalid_authority_review",
        "/authority/review/kind",
    )
    _require(
        type(review["complete_source_set"]) is bool,
        "invalid_completeness",
        "/authority/review/complete_source_set",
    )
    _require(
        isinstance(review["reviewed_source_hashes"], list)
        and all(isinstance(h, str) for h in review["reviewed_source_hashes"]),
        "invalid_authority_review",
        "/authority/review/reviewed_source_hashes",
    )
    _require(
        review["reviewer_id"] is None or isinstance(review["reviewer_id"], str),
        "invalid_authority_review",
        "/authority/review/reviewer_id",
    )
    if review["status"] == "reviewed":
        _require(
            _nonblank(review["reviewer_id"]),
            "invalid_authority_review",
            "/authority/review/reviewer_id",
        )
        _require(
            review["reviewed_source_hashes"] == [s["sha256"] for s in sources],
            "review_hash_mismatch",
            "/authority/review/reviewed_source_hashes",
        )
    _require(
        context.synthetic or review["kind"] != "synthetic_simulation",
        "simulated_authority_in_real_context",
        "/authority/review/kind",
    )
    for index, source in enumerate(sources):
        path = f"/authority/sources/{index}/content"
        content = source["content"]
        _object(content, {"subjects", "facts"}, path)
        _require(
            isinstance(content["subjects"], list)
            and isinstance(content["facts"], list),
            "invalid_authority_structure",
            path,
        )
        subject_ids: set[str] = set()
        for j, subject in enumerate(content["subjects"]):
            sp = f"{path}/subjects/{j}"
            _object(subject, {"product_id", "name"}, sp)
            _require(
                _nonblank(subject["product_id"])
                and _nonblank(subject["name"])
                and subject["product_id"] not in subject_ids,
                "invalid_source_identity",
                sp,
            )
            subject_ids.add(subject["product_id"])
        for j, fact in enumerate(content["facts"]):
            fp = f"{path}/facts/{j}"
            _object(fact, {"product_id", "property", "status", "value_mm"}, fp)
            _require(
                isinstance(fact["product_id"], str)
                and fact["product_id"] in subject_ids
                and fact["property"] == PROPERTY,
                "invalid_authority_fact",
                fp,
            )
            _require(
                fact["status"] in ("value", "not_supplied"),
                "invalid_authority_fact",
                fp + "/status",
            )
            value = fact["value_mm"]
            valid = (
                value is None
                if fact["status"] == "not_supplied"
                else isinstance(value, str) and _numeric(value) == value
            )
            _require(valid, "invalid_authority_value", fp + "/value_mm")
    seen = set()
    for index, record in enumerate(records):
        path = f"/authority/records/{index}"
        _object(record, {"id", "coverage", "fact_ref", "valid_turns"}, path)
        _require(
            _nonblank(record["id"]) and record["id"] not in seen,
            "invalid_record_identity",
            path + "/id",
        )
        seen.add(record["id"])
        pointer = record["fact_ref"]
        match = (
            re.fullmatch(
                r"/sources/(0|[1-9][0-9]*)/content/facts/(0|[1-9][0-9]*)", pointer
            )
            if isinstance(pointer, str)
            else None
        )
        _require(match is not None, "invalid_evidence_reference", path + "/fact_ref")
        assert match is not None
        si_text, fi_text = match.groups()
        source_count = str(len(sources))
        # Compare canonical digit strings before int conversion: even enormous
        # malformed pointer indices remain evidence errors, not Python failures.
        _require(
            (len(si_text), si_text) < (len(source_count), source_count),
            "invalid_evidence_reference",
            path + "/fact_ref",
        )
        si = int(si_text)
        fact_count = str(len(sources[si]["content"]["facts"]))
        _require(
            (len(fi_text), fi_text) < (len(fact_count), fact_count),
            "invalid_evidence_reference",
            path + "/fact_ref",
        )
        _require(
            record["coverage"] in ("complete", "open"),
            "invalid_completeness",
            path + "/coverage",
        )
        _interval(record["valid_turns"], path + "/valid_turns")
        interval = sources[si]["valid_turns"]
        _require(
            interval["first"]
            <= record["valid_turns"]["first"]
            <= record["valid_turns"]["last"]
            <= interval["last"],
            "invalid_authority_interval",
            path + "/valid_turns",
        )


def _fact(
    authority: GroundingEvidenceManifest, record: dict[str, Any]
) -> dict[str, Any]:
    parts = record["fact_ref"].split("/")
    return authority["sources"][int(parts[2])]["content"]["facts"][int(parts[5])]


def _response_turns(response: TargetResponse) -> list[dict[str, Any]]:
    _require(
        isinstance(response.structured, dict),
        "invalid_turn_sequence",
        "/response/structured/turns",
        "response",
    )
    turns = response.structured.get("turns")
    _require(
        isinstance(turns, list) and bool(turns),
        "invalid_turn_sequence",
        "/response/structured/turns",
        "response",
    )
    assert isinstance(turns, list)
    for index, turn in enumerate(turns):
        _require(
            isinstance(turn, dict)
            and type(turn.get("index")) is int
            and turn["index"] == index,
            "invalid_turn_sequence",
            f"/response/structured/turns/{index}/index",
            "response",
        )
    _require(
        isinstance(response.metadata, dict)
        and response.metadata.get("evidence_schema_version") == EVIDENCE_VERSION,
        "unsupported_evidence_version",
        "/response/metadata/evidence_schema_version",
        "response",
    )
    # Missing/malformed turn text is a turn error; do not cascade final mismatch.
    if all(isinstance(turn.get("output"), str) for turn in turns):
        _require(
            response.output == turns[-1]["output"],
            "final_output_mismatch",
            "/response/output",
            "response",
        )
    return turns


def _turn_identities(turn: dict[str, Any], index: int) -> list[dict[str, Any]]:
    path = f"/response/structured/turns/{index}"
    _require(
        isinstance(turn.get("output"), str),
        "missing_turn_output" if "output" not in turn else "invalid_turn_output",
        path + "/output",
        "turn",
        index,
    )
    trajectory = turn.get("trajectory")
    _require(
        isinstance(trajectory, list),
        "invalid_turn_trajectory",
        path + "/trajectory",
        "turn",
        index,
    )
    assert isinstance(trajectory, list)
    identities = []
    for call_index, call in enumerate(trajectory):
        cp = f"{path}/trajectory/{call_index}"
        _require(
            isinstance(call, dict) and isinstance(call.get("name"), str),
            "invalid_tool_evidence",
            cp,
            "turn",
            index,
        )
        if call["name"] not in ("get_product", "search_products"):
            continue
        _require(
            "error" in call
            and (call["error"] is None or isinstance(call["error"], str)),
            "invalid_tool_evidence",
            cp + "/error",
            "turn",
            index,
        )
        if call["error"] is not None:
            continue
        _require(
            "result" in call, "invalid_tool_evidence", cp + "/result", "turn", index
        )
        result = call["result"]
        if call["name"] == "get_product":
            if result is None:
                continue
            products = [(result, cp + "/result")]
        else:
            _require(
                isinstance(result, dict) and isinstance(result.get("products"), list),
                "invalid_tool_evidence",
                cp + "/result",
                "turn",
                index,
            )
            products = [
                (p, f"{cp}/result/products/{j}")
                for j, p in enumerate(result["products"])
            ]
        for product, pp in products:
            _require(
                isinstance(product, dict)
                and _nonblank(product.get("product_id"))
                and _nonblank(product.get("name")),
                "invalid_product_identity",
                pp,
                "turn",
                index,
            )
            identities.append(
                {
                    "product_id": product["product_id"],
                    "name": product["name"],
                    "ref": pp,
                }
            )
    return identities


def _identities(
    authority: GroundingEvidenceManifest | None,
    turn: int,
    observed: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if (
        authority is not None
        and authority["binding"] is not None
        and authority["review"]["status"] == "reviewed"
    ):
        for i, source in enumerate(authority["sources"]):
            if _at(source["valid_turns"], turn):
                result.extend(
                    {**s, "ref": f"/authority/sources/{i}/content/subjects/{j}"}
                    for j, s in enumerate(source["content"]["subjects"])
                )
    return result + observed


def _resolve(
    text: str, identities: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    normalized = " ".join(text.casefold().split())
    matches = [s for s in identities if s["product_id"].casefold() == normalized]
    method = "explicit_id"
    if not matches:
        matches = [
            s
            for s in identities
            if " ".join(s["name"].casefold().split()) == normalized
        ]
        method = "unique_exact_name"
    if (
        normalized in {"it", "they", "this", "that", "the first one"}
        or len({s["product_id"] for s in matches}) != 1
    ):
        return {
            "method": "unresolved",
            "product_id": None,
            "reason": "unresolved_subject",
            "evidence_refs": [],
        }, []
    refs = list(dict.fromkeys(s["ref"] for s in matches))
    return {
        "method": method,
        "product_id": matches[0]["product_id"],
        "reason": None,
        "evidence_refs": refs[:1],
    }, refs


def _compare(
    candidate: dict[str, Any], authority: GroundingEvidenceManifest | None
) -> dict[str, Any]:
    """Pure comparator; also testable with frozen gold extraction, without detection."""
    result = deepcopy(candidate)
    if result["disposition"] == "excluded":
        return result
    result["finding"] = "indeterminate"
    result["evidence_refs"] = []
    if result["extraction"] != "exact":
        return result
    if result["subject"]["product_id"] is None:
        result["reason"] = "unresolved_subject"
        return result
    if authority is None:
        result["reason"] = "authority_missing"
        return result
    if authority["binding"] is None:
        result["reason"] = "authority_unbound"
        return result
    if authority["review"]["status"] != "reviewed":
        result["reason"] = "authority_unreviewed"
        return result
    records = [
        (i, r, _fact(authority, r))
        for i, r in enumerate(authority["records"])
        if _fact(authority, r)["product_id"] == result["subject"]["product_id"]
    ]
    eligible = [
        (i, r, f) for i, r, f in records if _at(r["valid_turns"], result["turn_index"])
    ]
    result["reason"] = (
        "authority_not_applicable"
        if records and not eligible
        else "authority_incomplete"
    )
    if not eligible:
        return result
    result["evidence_refs"] = [f"/authority/records/{i}" for i, _, _ in eligible]
    # A source fact without a record has no reviewed fact-level applicability.
    # Do not silently drop that gap while claiming reference agreement/absence.
    bound_facts = {r["fact_ref"] for r in authority["records"]}
    for source_index, source in enumerate(authority["sources"]):
        if not _at(source["valid_turns"], result["turn_index"]):
            continue
        for fact_index, fact in enumerate(source["content"]["facts"]):
            if (
                fact["product_id"] == result["subject"]["product_id"]
                and f"/sources/{source_index}/content/facts/{fact_index}"
                not in bound_facts
            ):
                result["reason"] = "authority_incomplete"
                return result
    values = {f["value_mm"] for _, _, f in eligible}
    if len(values) > 1:
        result["reason"] = "conflicting_authority"
    elif values == {None}:
        if authority["review"]["complete_source_set"] and all(
            r["coverage"] == "complete" for _, r, _ in eligible
        ):
            result.update(finding="unsupported", reason="reviewed_complete_absence")
    else:
        equal = values == {result["normalized"]["value_mm"]}
        result.update(
            finding="supported" if equal else "contradicted",
            reason="equal_authoritative_value"
            if equal
            else "unequal_authoritative_value",
        )
    return result


_PROPERTY = r"(?P<property>hydrostatic-head\s+rating|waterproof\s+rating)"
_SUBJECT = r"(?P<subject>\w[\w\s'’-]*?)"
_UNIT = r"(?P<unit>millimetres?|millimeters?|centimetres?|centimeters?|metres?|meters?|mm|cm|m)"
_VALUE = r"(?P<value>[^;\n]+?)\s+" + _UNIT
_RATING = _PROPERTY + r"\s+of\s+" + _VALUE
_FORMS = [
    ("question", r"Does\s+" + _SUBJECT + r"\s+have\s+a\s+" + _RATING + r"\?"),
    (
        "negation",
        r"I\s+cannot\s+confirm\s+a\s+" + _RATING + r"\s+for\s+" + _SUBJECT + r"[.!]?",
    ),
    (
        "unendorsed_quotation",
        r'The\s+shopper\s+said,\s*[“"]'
        + _SUBJECT
        + r"\s+has\s+a\s+"
        + _RATING
        + r'[.!]?[”"]',
    ),
    (
        "hypothetical",
        r"If\s+"
        + _SUBJECT
        + r"\s+had\s+a\s+"
        + _RATING
        + r",\s+it\s+would\b[^.!?]*[.!]?",
    ),
    ("hedged_assertion", _SUBJECT + r"\s+might\s+have\s+a\s+" + _RATING + r"[.!]?"),
    ("different_property", r"The\s+expected\s+rainfall\s+is\s+" + _VALUE + r"[.!]?"),
    (
        "different_property",
        _SUBJECT + r"\s+has\s+a\s+hem\s+length\s+of\s+" + _VALUE + r"[.!]?",
    ),
    ("", _SUBJECT + r"\s+has\s+a\s+" + _RATING + r"[.!]?"),
]
_PATTERNS = [(reason, re.compile(pattern, re.IGNORECASE)) for reason, pattern in _FORMS]
_SENTENCE = re.compile(r'.+?(?:[.!?](?![0-9])[”"]?(?=\s|$)|$)', re.DOTALL)


def _span(text: str, first: int, last: int) -> dict[str, Any]:
    return {"start": first, "end": last, "text": text[first:last]}


def _detect(
    text: str, turn: int, identities: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    candidates = []
    for sentence in _SENTENCE.finditer(text):
        start, end = sentence.span()
        while start < end and not text[start].isalnum():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        clause = text[start:end]
        for reason, pattern in _PATTERNS:
            match = pattern.fullmatch(clause)
            if match is None:
                continue
            slots = {
                name: _span(text, start + match.start(name), start + match.end(name))
                if name in match.groupdict()
                else None
                for name in ("subject", "property", "value", "unit")
            }
            prop = slots["property"]
            family = (
                None
                if prop is None
                else "hydrostatic_head"
                if prop["text"].casefold().startswith("hydrostatic")
                else "numeric_waterproof_rating"
            )
            excluded = bool(reason) and reason != "hedged_assertion"
            value = match.group("value")
            scalar = _numeric(value, match.group("unit"))
            extraction = "uncertain" if reason == "hedged_assertion" else "exact"
            if not excluded and scalar is None:
                extraction = "unsupported_syntax"
                if re.fullmatch(r"[0-9,.]+\s*[–-]\s*[0-9,.]+", value):
                    reason = "range_not_supported"
                elif re.fullmatch(r"[0-9,.]+[kK]", value):
                    reason = "shorthand_not_supported"
                else:
                    reason = "numeric_syntax_not_supported"
            subject, identity_refs = (
                (
                    {
                        "method": "not_attempted",
                        "product_id": None,
                        "reason": "excluded_candidate",
                        "evidence_refs": [],
                    },
                    [],
                )
                if excluded
                else _resolve(match.group("subject"), identities)
            )
            candidates.append(
                {
                    "id": "",
                    "turn_index": turn,
                    "turn_text_sha256": text_hash(text),
                    "span": _span(text, start, end),
                    **{name + "_span": value for name, value in slots.items()},
                    "family": family,
                    "disposition": "excluded"
                    if excluded
                    else "uncertain"
                    if reason == "hedged_assertion"
                    else "affirmative",
                    "extraction": extraction,
                    "subject": subject,
                    "identity_evidence_refs": identity_refs,
                    "normalized": {"property": PROPERTY, "value_mm": scalar}
                    if scalar is not None and not excluded
                    else None,
                    "finding": None if excluded else "indeterminate",
                    "reason": reason,
                    "evidence_refs": [],
                    "agent_grounding": "not_assessed",
                }
            )
            break
    return candidates


def diagnose_numeric_waterproof_claims(
    response: TargetResponse,
    *,
    context: GroundingDiagnosticContext,
    authority: GroundingEvidenceManifest | None = None,
) -> GroundingDiagnosticReport:
    """Diagnose reference agreement without invoking or changing any evaluation run."""
    if not isinstance(context, GroundingDiagnosticContext) or not isinstance(
        response, TargetResponse
    ):
        raise GroundingConfigurationError(
            "Expected TargetResponse and GroundingDiagnosticContext"
        )
    try:
        context = GroundingDiagnosticContext.model_validate(
            context.model_dump(mode="python", warnings=False)
        )
    except ValidationError:
        raise GroundingConfigurationError("Invalid diagnostic context") from None
    context_data = context.model_dump(mode="json", exclude_none=True)
    data = response.model_dump(mode="python")
    hashes: dict[str, Any] = {
        "contract_version": CONTRACT,
        "context_sha256": fingerprint(context_data),
        "response_sha256": None,
        "authority_sha256": None,
    }
    candidates: list[dict[str, Any]] = []
    errors: list[GroundingEvidenceError] = []
    projected: list[dict[str, Any]] = []
    without: list[int] = []
    fatal = False
    try:
        invalid_json: set[str] = set()
        for value, name in ((data, "response"), (authority, "authority")):
            try:
                validate_json_data(value)
                hashes[name + "_sha256"] = fingerprint(value)
            except (ValueError, UnicodeError):
                invalid_json.add(name)
        turns = _response_turns(response)
        for name, scope in (("response", "response"), ("authority", "authority")):
            if name in invalid_json:
                raise _EvidenceIssue(
                    "invalid_json_evidence",
                    "/" + name,
                    "response" if scope == "response" else "authority",
                )
        if context.expected_response_sha256 is not None:
            _require(
                hashes["response_sha256"] == context.expected_response_sha256,
                "response_hash_mismatch",
                "/response",
                "response",
            )
        _validate_authority(authority, context)
        observed: list[dict[str, Any]] = []
        for index, turn in enumerate(turns):
            try:
                new_identities = _turn_identities(turn, index)
            except _EvidenceIssue as issue:
                errors.append(issue.error)
                continue
            observed.extend(new_identities)
            identities = _identities(authority, index, observed)
            projected.append(
                {
                    "index": index,
                    "output": turn["output"],
                    "turn_text_sha256": text_hash(turn["output"]),
                    "identities": deepcopy(identities),
                }
            )
            detected = _detect(turn["output"], index, identities)
            if not detected:
                without.append(index)
            for candidate in detected:
                candidate["id"] = f"c{len(candidates)}"
                candidates.append(_compare(candidate, authority))
    except _EvidenceIssue as issue:
        errors.append(issue.error)
        fatal = True
    counts = {
        "candidates": len(candidates),
        "affirmative_claims": sum(
            c["disposition"] == "affirmative" for c in candidates
        ),
        **{
            finding: sum(c["finding"] == finding for c in candidates)
            for finding in ("supported", "contradicted", "unsupported", "indeterminate")
        },
        "excluded": sum(c["disposition"] == "excluded" for c in candidates),
        "errors": len(errors),
    }
    status: Literal["complete", "partial", "error"] = (
        "error"
        if fatal or errors and not projected
        else "partial"
        if errors
        else "complete"
    )
    return GroundingDiagnosticReport(
        configuration=deepcopy(CONFIGURATION),
        configuration_sha256=fingerprint(CONFIGURATION),
        harness_revision=context.harness_revision,
        context=context,
        provenance=hashes,
        projection_sha256=fingerprint(projected),
        execution_status=status,
        candidates=candidates,
        errors=errors,
        counts=counts,
        turns_without_candidates=without,
        turns=projected,
    )
