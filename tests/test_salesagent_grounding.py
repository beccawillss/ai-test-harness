"""Frozen conformance plus evidence-boundary tests; no live services or scoring."""

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from harness.core.fingerprints import fingerprint
from harness.core.models import TargetResponse
from harness.packs import salesagent_grounding as pack

CORPUS = Path(__file__).parent / "fixtures/salesagent_grounding/v1"
ROWS = [json.loads(line) for line in (CORPUS / "cases.jsonl").read_text().splitlines()]
GOLD = {
    row["id"]: row
    for row in map(json.loads, (CORPUS / "expected.jsonl").read_text().splitlines())
}


def fixture(case_id="S01"):
    return copy.deepcopy(next(row["input"] for row in ROWS if row["id"] == case_id))


def diagnose(data):
    return pack.diagnose_numeric_waterproof_claims(
        TargetResponse.model_validate(data["response"]),
        context=pack.GroundingDiagnosticContext.model_validate(data["context"]),
        authority=data["authority"],
    )


def rehash(data):
    authority = data["authority"]
    for source in authority["sources"]:
        source["sha256"] = fingerprint(source["content"])
    authority["review"]["reviewed_source_hashes"] = [
        s["sha256"] for s in authority["sources"]
    ]


def set_text(data, text, index=-1):
    data["response"]["structured"]["turns"][index]["output"] = text
    data["response"]["output"] = data["response"]["structured"]["turns"][-1]["output"]


def test_frozen_manifest_and_review_are_unchanged():
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    approved = {
        "cases.jsonl": "1bfb96ec6a381ed313db86957e03843cdf7a020363793e9bb7bd04d75a19f5ce",
        "expected.jsonl": "8682d235f38e90ab5ab78a79ba0d7c97c28a3ddc5d27e592dc52753dbc67e962",
    }
    assert manifest["status"] == "frozen"
    assert (
        manifest["files"]
        == manifest["independent_review"]["approved_files"]
        == approved
    )
    assert manifest["independent_review"]["decision"] == "APPROVED"
    assert (
        manifest["independent_review"]["review_sha256"]
        == "dfbe8ac2c315623800e6c6769359e3044d699cf798e71ab7a807ab1ffd61fa31"
    )
    for name, digest in {
        **approved,
        "independent-review.md": manifest["independent_review"]["review_sha256"],
    }.items():
        assert hashlib.sha256((CORPUS / name).read_bytes()).hexdigest() == digest
    assert len(ROWS) == len(GOLD) == 32


@pytest.mark.parametrize("row", ROWS, ids=lambda row: row["id"])
def test_exact_frozen_semantics_roundtrip_and_immutability(row):
    data = copy.deepcopy(row["input"])
    before = copy.deepcopy(data)
    response = TargetResponse.model_validate(data["response"])
    response_before = response.model_dump(mode="json")
    report = pack.diagnose_numeric_waterproof_claims(
        response,
        context=pack.GroundingDiagnosticContext(**data["context"]),
        authority=data["authority"],
    )
    assert fingerprint(data) == GOLD[row["id"]]["input_sha256"]
    assert report.semantic_projection() == GOLD[row["id"]]["expected"]
    assert data == before
    assert response.model_dump(mode="json") == response_before
    restored = pack.GroundingDiagnosticReport.model_validate_json(
        report.model_dump_json()
    )
    assert restored.canonical_body() == report.canonical_body()
    assert (
        restored.body_sha256()
        == report.body_sha256()
        == fingerprint(report.model_dump(mode="json"))
    )
    assert diagnose(data).body_sha256() == report.body_sha256()
    assert not {"score", "passed", "verdict", "quality"} & report.model_dump().keys()
    for candidate in report.candidates:
        assert candidate["agent_grounding"] == "not_assessed"
        text = data["response"]["structured"]["turns"][candidate["turn_index"]][
            "output"
        ]
        for field in (
            "span",
            "subject_span",
            "property_span",
            "value_span",
            "unit_span",
        ):
            span = candidate[field]
            if span:
                assert text[span["start"] : span["end"]] == span["text"]


@pytest.mark.parametrize(
    "case_id", [row["id"] for row in ROWS if row["group"] != "error"]
)
def test_comparator_with_gold_extraction_independent_of_detector(case_id):
    data = fixture(case_id)
    for gold in GOLD[case_id]["expected"]["candidates"]:
        extracted = copy.deepcopy(gold)
        # Erase gold comparison outputs; retain extraction/uncertainty reasons.
        if (
            extracted["disposition"] == "affirmative"
            and extracted["extraction"] == "exact"
        ):
            extracted.update(finding=None, reason="", evidence_refs=[])
        before = copy.deepcopy(extracted)
        assert pack._compare(extracted, data["authority"]) == gold
        assert extracted == before


def eligible(candidate):
    return (
        candidate["disposition"] == "affirmative" and candidate["extraction"] == "exact"
    )


def anchor(candidate):
    span = candidate["value_span"]
    return candidate["turn_index"], candidate["family"], span["start"], span["end"]


def test_evaluator_metrics_by_split(capsys):
    metrics = {}
    for split in ("development", "acceptance"):
        counts = Counter()
        for row in ROWS:
            if row["split"] != split:
                continue
            report = diagnose(row["input"])
            gold = GOLD[row["id"]]["expected"]
            predicted = [c for c in report.candidates if eligible(c)]
            expected = [c for c in gold["candidates"] if eligible(c)]
            gold_anchors = Counter(anchor(c) for c in expected)
            pred_anchors = Counter(anchor(c) for c in predicted)
            matched = sum((gold_anchors & pred_anchors).values())
            counts.update(
                tp=matched,
                fp=len(predicted) - matched,
                fn=len(expected) - matched,
                emitted=len(predicted),
                gold=len(expected),
            )
            for expected_candidate in expected:
                match = next(
                    (c for c in predicted if anchor(c) == anchor(expected_candidate)),
                    None,
                )
                if match is not None:
                    for field in (
                        "subject",
                        "normalized",
                        "span",
                        "property_span",
                        "subject_span",
                        "value_span",
                        "unit_span",
                    ):
                        counts[field + "_correct"] += (
                            match[field] == expected_candidate[field]
                        )
            for expected_candidate in gold["candidates"]:
                extracted = copy.deepcopy(expected_candidate)
                if eligible(extracted):
                    extracted.update(finding=None, reason="", evidence_refs=[])
                counts["comparison_correct"] += (
                    pack._compare(extracted, row["input"]["authority"])
                    == expected_candidate
                )
            counts["indeterminate_exact"] += sum(
                c["finding"] == "indeterminate" for c in predicted
            )
            counts["candidates"] += len(report.candidates)
            counts["abstained"] += sum(
                c["extraction"] != "exact" or c["subject"]["method"] == "unresolved"
                for c in report.candidates
            )
            counts["excluded"] += report.counts["excluded"]
            counts["challenges"] += sum(
                c["extraction"] != "exact" for c in report.candidates
            )
            counts[
                "error_fixtures" if row["group"] == "error" else "text_fixtures"
            ] += 1
            counts["exact_fixtures"] += report.semantic_projection() == gold
        assert counts["fp"] == counts["fn"] == 0
        assert counts["tp"] == counts["gold"] == counts["emitted"]
        for field in (
            "subject",
            "normalized",
            "span",
            "property_span",
            "subject_span",
            "value_span",
            "unit_span",
        ):
            assert counts[field + "_correct"] == counts["tp"]
        assert counts["comparison_correct"] == counts["candidates"]
        metrics[split] = dict(counts)
    assert sum(v["gold"] for v in metrics.values()) == 15
    # Emit raw denominators for the human review log, not a runtime quality score.
    with capsys.disabled():
        print("\nFrozen corpus metrics: " + json.dumps(metrics, sort_keys=True))


@pytest.mark.parametrize(
    "change,reason",
    [
        ("none", "authority_missing"),
        ("unbound", "authority_unbound"),
        ("unreviewed", "authority_unreviewed"),
        ("open", "authority_incomplete"),
        ("incomplete_set", "authority_incomplete"),
        ("future", "authority_not_applicable"),
    ],
)
def test_insufficient_authority_never_becomes_unsupported(change, reason):
    data = fixture("V04")
    if change == "none":
        data["authority"] = None
    elif change == "unbound":
        data["authority"]["binding"] = None
    elif change == "unreviewed":
        data["authority"]["review"]["status"] = "unreviewed"
    elif change == "open":
        data["authority"]["records"][0]["coverage"] = "open"
    elif change == "incomplete_set":
        data["authority"]["review"]["complete_source_set"] = False
    else:
        for source in data["authority"]["sources"]:
            source["valid_turns"] = {"first": 1, "last": 1}
        for record in data["authority"]["records"]:
            record["valid_turns"] = {"first": 1, "last": 1}
    report = diagnose(data)
    assert report.execution_status == "complete"
    assert report.candidates[0]["finding"] == "indeterminate"
    assert report.candidates[0]["reason"] == reason


def test_omitted_authority_matches_explicit_null():
    data = fixture()
    context = pack.GroundingDiagnosticContext(**data["context"])
    response = TargetResponse(**data["response"])
    omitted = pack.diagnose_numeric_waterproof_claims(response, context=context)
    explicit = pack.diagnose_numeric_waterproof_claims(
        response, context=context, authority=None
    )
    assert omitted == explicit


@pytest.mark.parametrize(
    "case_id,finding", [("S01", "supported"), ("V01", "contradicted")]
)
def test_numeric_reference_does_not_require_complete_source_set(case_id, finding):
    data = fixture(case_id)
    data["authority"]["review"]["complete_source_set"] = False
    data["authority"]["records"][0]["coverage"] = "open"
    assert diagnose(data).candidates[0]["finding"] == finding


def test_value_absence_conflict_and_duplicate_agreement():
    data = fixture("A06")
    fact = data["authority"]["sources"][1]["content"]["facts"][0]
    fact.update(status="not_supplied", value_mm=None)
    rehash(data)
    assert diagnose(data).candidates[0]["reason"] == "conflicting_authority"
    fact.update(status="value", value_mm="20000")
    rehash(data)
    candidate = diagnose(data).candidates[0]
    assert candidate["finding"] == "supported"
    assert candidate["evidence_refs"] == [
        "/authority/records/0",
        "/authority/records/2",
    ]
    assert len(candidate["identity_evidence_refs"]) == 3


def test_duplicate_names_are_unresolved_and_ids_stay_distinct():
    data = fixture("S05")
    data["authority"]["sources"][0]["content"]["subjects"][1]["name"] = "RAIN  SHELL A"
    rehash(data)
    assert diagnose(data).candidates[0]["reason"] == "unresolved_subject"
    set_text(data, fixture("V03")["response"]["output"])
    assert diagnose(data).candidates[0]["subject"]["product_id"] == "SYN-002"


def test_identity_provenance_retains_prior_observations_without_future_leakage():
    data = fixture("S06")
    turns = data["response"]["structured"]["turns"]
    turns[1]["trajectory"] = []
    data["authority"] = None
    report = diagnose(data)
    assert report.candidates[0]["subject"]["product_id"] == "SYN-001"
    assert report.candidates[0]["identity_evidence_refs"] == [
        "/response/structured/turns/0/trajectory/0/result"
    ]
    # Same captured claim at the earlier turn cannot use a future observation.
    turns[1]["trajectory"] = turns[0]["trajectory"]
    turns[0]["trajectory"] = []
    set_text(data, turns[1]["output"], 0)
    report = diagnose(data)
    assert report.candidates[0]["reason"] == "unresolved_subject"
    assert report.candidates[1]["subject"]["product_id"] == "SYN-001"


def test_future_source_subjects_cannot_resolve_earlier_claim():
    data = fixture("V03")
    data["response"]["structured"]["turns"][0]["trajectory"] = []
    for source in data["authority"]["sources"]:
        source["valid_turns"] = {"first": 1, "last": 1}
    for record in data["authority"]["records"]:
        record["valid_turns"] = {"first": 1, "last": 1}
    assert diagnose(data).candidates[0]["reason"] == "unresolved_subject"


@pytest.mark.parametrize("bad_index", [0, 1])
def test_partial_turn_error_retains_unaffected_findings(bad_index):
    data = fixture("S06")
    set_text(data, data["response"]["output"], 0)
    del data["response"]["structured"]["turns"][bad_index]["output"]
    report = diagnose(data)
    assert report.execution_status == "partial"
    assert report.counts["supported"] == 1
    assert report.errors[0].code == "missing_turn_output"
    assert report.errors[0].turn_index == bad_index
    assert report.candidates[0]["turn_index"] == 1 - bad_index


def test_all_turns_unprocessable_and_independent_errors_in_order():
    data = fixture("S06")
    for turn in data["response"]["structured"]["turns"]:
        del turn["output"]
    report = diagnose(data)
    assert report.execution_status == "error"
    assert [e.turn_index for e in report.errors] == [0, 1]
    assert not report.candidates


def test_empty_output_is_complete_and_not_quality_pass():
    data = fixture()
    set_text(data, "")
    report = diagnose(data)
    assert report.execution_status == "complete"
    assert report.turns_without_candidates == [0]
    assert report.counts["candidates"] == 0
    assert not report.errors


@pytest.mark.parametrize(
    "value",
    [True, 0, -1, "0", "-1", "020000", "20000.0", "2e4", "Infinity", "NaN", "20,000"],
)
def test_invalid_authority_numbers_are_errors(value):
    data = fixture()
    data["authority"]["sources"][0]["content"]["facts"][0]["value_mm"] = value
    rehash(data)
    report = diagnose(data)
    assert report.execution_status == "error"
    assert report.errors[0].code == "invalid_authority_value"
    assert not report.candidates


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("binding", "authority_binding_mismatch"),
        ("binding_bool", "authority_binding_mismatch"),
        ("version", "unsupported_authority_version"),
        ("review_hash", "review_hash_mismatch"),
        ("simulated", "simulated_authority_in_real_context"),
        ("extra_content", "invalid_authority_structure"),
        ("duplicate_source", "invalid_source_identity"),
        ("duplicate_record", "invalid_record_identity"),
        ("interval", "invalid_authority_interval"),
        ("coverage", "invalid_completeness"),
        ("pointer", "invalid_evidence_reference"),
    ],
)
def test_malformed_authority_is_safe_error(mutation, code):
    data = fixture()
    authority = data["authority"]
    if mutation == "binding":
        authority["binding"]["source_id"] = "other"
    elif mutation == "binding_bool":
        authority["binding"]["attempt_index"] = False
    elif mutation == "version":
        authority["contract_version"] = "future"
    elif mutation == "review_hash":
        authority["review"]["reviewed_source_hashes"] = []
    elif mutation == "simulated":
        data["context"]["synthetic"] = False
    elif mutation == "extra_content":
        authority["sources"][0]["content"]["authorization"] = "SECRET"
        rehash(data)
    elif mutation == "duplicate_source":
        authority["sources"].append(copy.deepcopy(authority["sources"][0]))
    elif mutation == "duplicate_record":
        authority["records"].append(copy.deepcopy(authority["records"][0]))
    elif mutation == "interval":
        authority["records"][0]["valid_turns"]["last"] = 2
    elif mutation == "coverage":
        authority["review"]["complete_source_set"] = "true"
    elif mutation == "pointer":
        authority["records"][0]["fact_ref"] = "https://example.com/SECRET"
    report = diagnose(data)
    assert report.execution_status == "error"
    assert report.errors[0].code == code
    assert "SECRET" not in report.canonical_body()


def test_response_errors_precede_authority_and_hash_precedes_numeric_semantics():
    data = fixture("E02")
    data["authority"]["sources"][0]["sha256"] = "bad"
    assert diagnose(data).errors[0].code == "invalid_turn_sequence"
    data = fixture("E05")
    data["authority"]["sources"][0]["sha256"] = "bad"
    assert diagnose(data).errors[0].code == "source_hash_mismatch"


@pytest.mark.parametrize("value", [True, -1, 1, "0"])
def test_turn_index_is_strict_and_contiguous(value):
    data = fixture()
    data["response"]["structured"]["turns"][0]["index"] = value
    assert diagnose(data).errors[0].code == "invalid_turn_sequence"


def test_failed_tools_cannot_supply_identity_and_search_products_can():
    data = fixture()
    data["authority"] = None
    call = data["response"]["structured"]["turns"][0]["trajectory"][0]
    call["error"] = "SECRET failed tool"
    assert diagnose(data).candidates[0]["subject"]["method"] == "unresolved"
    call["error"] = None
    call["name"] = "search_products"
    call["result"] = {"products": [call["result"]]}
    report = diagnose(data)
    assert report.candidates[0]["identity_evidence_refs"] == [
        "/response/structured/turns/0/trajectory/0/result/products/0"
    ]
    call["result"] = {"products": "SECRET"}
    report = diagnose(data)
    assert report.errors[0].code == "invalid_tool_evidence"
    assert "SECRET" not in report.canonical_body()


def test_unrelated_response_fields_and_raw_payload_are_not_reported_or_consumed():
    data = fixture()
    data["response"]["raw"] = {"authorization": "SECRET", "reasoning": "HIDDEN"}
    data["response"]["structured"]["recommendations"] = "IGNORED"
    data["response"]["structured"]["turns"][0]["structured"] = None
    report = diagnose(data)
    assert report.candidates[0]["finding"] == "supported"
    assert all(
        secret not in report.canonical_body()
        for secret in ("SECRET", "HIDDEN", "IGNORED")
    )


def test_repeated_attempts_and_calls_are_isolated():
    original = fixture()
    first = diagnose(original)
    other = fixture()
    other["context"].update(source_id="opaque-other", attempt_index=1)
    other["authority"] = None
    other["response"]["structured"]["turns"][0]["trajectory"] = []
    assert diagnose(other).candidates[0]["reason"] == "unresolved_subject"
    assert diagnose(original).body_sha256() == first.body_sha256()
    original["authority"]["sources"][0]["content"]["subjects"][0]["name"] = (
        "changed after return"
    )
    assert "changed after return" not in first.canonical_body()


def test_ids_are_opaque_and_do_not_influence_findings():
    data = fixture()
    expected = diagnose(data).candidates
    data["context"]["source_id"] = "V04-this-is-not-a-hint"
    data["authority"]["binding"]["source_id"] = data["context"]["source_id"]
    assert diagnose(data).candidates == expected


@pytest.mark.parametrize(
    "fields",
    [
        {"source_id": ""},
        {"attempt_index": True},
        {"attempt_index": -1},
        {"synthetic": 1},
        {"unexpected": "SECRET"},
    ],
)
def test_invalid_caller_configuration_raises_typed_error(fields):
    data = fixture()
    context = pack.GroundingDiagnosticContext.model_construct(
        **{**data["context"], **fields}
    )
    if "unexpected" in fields:
        # Strict construction, unlike model_construct, must reject extra fields.
        with pytest.raises(ValidationError):
            pack.GroundingDiagnosticContext(**data["context"], **fields)
        return
    with pytest.raises(
        pack.GroundingConfigurationError, match="Invalid diagnostic context"
    ):
        pack.diagnose_numeric_waterproof_claims(
            TargetResponse(**data["response"]), context=context
        )


def test_report_version_drift_and_artifact_binding():
    data = fixture()
    report = diagnose(data)
    payload = report.model_dump(mode="json")
    payload["contract_version"] = "future"
    with pytest.raises(ValidationError):
        pack.GroundingDiagnosticReport.model_validate(payload)
    data["context"]["harness_revision"] = "revision-under-test"
    data["context"]["expected_response_sha256"] = fingerprint(data["response"])
    assert diagnose(data).harness_revision == "revision-under-test"
    data["context"]["expected_response_sha256"] = "0" * 64
    assert diagnose(data).errors[0].code == "response_hash_mismatch"


@pytest.mark.parametrize(
    "number,unit,expected",
    [
        ("2,000.0", "cm", "20000"),
        ("20", "METRES", "20000"),
        ("0.01", "m", "10"),
        ("00020.000", "mm", "20"),
        (
            "123456789012345678901234567890.001",
            "cm",
            "1234567890123456789012345678900.01",
        ),
    ],
)
def test_exact_decimal_normalization_without_rounding(number, unit, expected):
    assert pack._numeric(number, unit) == expected


@pytest.mark.parametrize(
    "number", ["0", "-1", "+20", "20k", "20,00", "NaN", "Infinity", "2e4", "20.000,5"]
)
def test_unsupported_scalars_never_normalize(number):
    assert pack._numeric(number) is None


def test_multiple_frozen_clauses_preserve_offsets_and_candidate_order():
    data = fixture()
    first = fixture("S05")["response"]["output"]
    second = fixture("N01")["response"]["output"]
    set_text(data, first + " " + second)
    report = diagnose(data)
    assert [c["id"] for c in report.candidates] == ["c0", "c1"]
    assert [c["finding"] for c in report.candidates] == ["supported", None]
    assert report.candidates[1]["span"]["start"] == len(first) + 1


@pytest.mark.parametrize("case_id", ["S01", "V04"])
def test_unbound_source_fact_prevents_reference_certainty(case_id):
    data = fixture(case_id)
    extra = copy.deepcopy(data["authority"]["sources"][0])
    extra["id"] = "unbound-source"
    extra["content"]["facts"][0].update(status="value", value_mm="25000")
    data["authority"]["sources"].append(extra)
    rehash(data)
    report = diagnose(data)
    assert report.candidates[0]["finding"] == "indeterminate"
    assert report.candidates[0]["reason"] == "authority_incomplete"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), {1: "bad key"}, object()])
def test_non_json_evidence_is_reported_without_raw_values(bad):
    data = fixture()
    data["authority"]["sources"][0]["content"]["facts"][0]["value_mm"] = bad
    report = diagnose(data)
    assert report.execution_status == "error"
    assert report.errors[0].code == "invalid_json_evidence"
    assert report.errors[0].scope == "authority"
    # Response-level errors take precedence even over non-JSON authority.
    data["response"]["structured"]["turns"][0]["index"] = 1
    assert diagnose(data).errors[0].code == "invalid_turn_sequence"


@pytest.mark.parametrize(
    "path",
    [
        ("sources",),
        ("records",),
        ("review",),
        ("binding",),
        ("sources", 0, "id"),
        ("sources", 0, "revision"),
        ("sources", 0, "valid_turns"),
        ("sources", 0, "valid_turns", "first"),
        ("review", "status"),
        ("review", "kind"),
        ("review", "reviewed_source_hashes"),
        ("review", "reviewer_id"),
        ("records", 0, "id"),
        ("records", 0, "fact_ref"),
        ("records", 0, "coverage"),
    ],
)
def test_malformed_consumed_authority_fields_are_errors(path):
    data = fixture()
    cursor = data["authority"]
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = {"invalid": "SECRET"}
    report = diagnose(data)
    assert report.execution_status == "error"
    assert not report.candidates
    assert "SECRET" not in report.canonical_body()


@pytest.mark.parametrize(
    "change,code",
    [
        ("output_type", "invalid_turn_output"),
        ("trajectory", "invalid_turn_trajectory"),
        ("tool", "invalid_tool_evidence"),
        ("identity", "invalid_product_identity"),
    ],
)
def test_malformed_consumed_turn_fields_remain_local(change, code):
    data = fixture("S06")
    turn = data["response"]["structured"]["turns"][0]
    if change == "output_type":
        turn["output"] = 5
    elif change == "trajectory":
        turn["trajectory"] = None
    elif change == "tool":
        turn["trajectory"][0]["error"] = 5
    else:
        turn["trajectory"][0]["result"]["name"] = None
    report = diagnose(data)
    assert report.execution_status == "partial"
    assert report.errors[0].code == code
    assert report.counts["supported"] == 1


def test_programming_errors_are_not_hidden(monkeypatch):
    def broken(*args):
        raise RuntimeError("internal defect")

    monkeypatch.setattr(pack, "_detect", broken)
    with pytest.raises(RuntimeError, match="internal defect"):
        diagnose(fixture())


def test_saved_real_adapter_response_is_compatible():
    from test_salesagent_semantic import target_response

    response = target_response()
    before = response.model_dump(mode="json")
    report = pack.diagnose_numeric_waterproof_claims(
        response,
        context=pack.GroundingDiagnosticContext(
            source_id="saved-adapter-response", attempt_index=0
        ),
    )
    assert report.execution_status == "complete"
    assert response.model_dump(mode="json") == before
    assert report.provenance["response_sha256"] == fingerprint(before)


@pytest.mark.parametrize("unit", ["feet", "psi", "mm/hour", "cmx", ""])
def test_unrecognized_units_do_not_normalize(unit):
    assert pack._numeric("20", unit) is None


def test_bounded_authority_content_and_human_review_kind():
    data = fixture()
    data["context"]["synthetic"] = False
    data["authority"]["review"]["kind"] = "human"
    assert diagnose(data).candidates[0]["finding"] == "supported"
    data["authority"]["sources"][0]["content"]["subjects"][0]["name"] = (
        "x" * pack.AUTHORITY_CONTENT_LIMIT
    )
    rehash(data)
    report = diagnose(data)
    assert report.errors[0].code == "authority_content_too_large"


def test_hashes_capture_source_revision_and_configuration_without_persistence():
    data = fixture()
    first = diagnose(data)
    data["authority"]["sources"][0]["revision"] = "another-immutable-revision"
    second = diagnose(data)
    assert first.candidates == second.candidates
    assert first.provenance["authority_sha256"] != second.provenance["authority_sha256"]
    assert first.body_sha256() != second.body_sha256()
    assert first.configuration_sha256 == fingerprint(first.configuration)
    assert first.projection_sha256 == fingerprint(first.turns)


def test_failed_turn_does_not_partially_publish_identity_observations():
    data = fixture("S06")
    data["authority"] = None
    turns = data["response"]["structured"]["turns"]
    turns[0]["trajectory"].append(
        {"name": "get_product", "error": None, "result": "malformed"}
    )
    turns[1]["trajectory"] = []
    report = diagnose(data)
    assert report.execution_status == "partial"
    assert report.candidates[0]["reason"] == "unresolved_subject"


@pytest.mark.parametrize("number", ["0", "-1", "+20", "20,00"])
def test_nonpositive_or_unsupported_prose_is_indeterminate_not_execution_error(number):
    data = fixture()
    set_text(data, data["response"]["output"].replace("20000", number))
    report = diagnose(data)
    assert report.execution_status == "complete"
    assert report.candidates[0]["finding"] == "indeterminate"
    assert report.candidates[0]["reason"] == "numeric_syntax_not_supported"
    assert report.candidates[0]["normalized"] is None


def test_name_whitespace_and_case_are_normalized_without_changing_source_spans():
    data = fixture("S05")
    set_text(
        data, data["response"]["output"].replace("rain   shell a", "RAIN\n\tSHELL A")
    )
    report = diagnose(data)
    assert report.candidates[0]["finding"] == "supported"
    assert report.candidates[0]["subject_span"]["text"] == "RAIN\n\tSHELL A"


def test_mutated_non_json_response_reports_evidence_error():
    data = fixture()
    response = TargetResponse(**data["response"])
    response.raw["provider_object"] = object()
    report = pack.diagnose_numeric_waterproof_claims(
        response, context=pack.GroundingDiagnosticContext(**data["context"])
    )
    assert report.errors[0].code == "invalid_json_evidence"
    assert report.errors[0].scope == "response"


@pytest.mark.parametrize(
    "source_index,fact_index", [("9" * 5000, "0"), ("0", "9" * 5000)]
)
def test_oversized_pointer_indices_are_evidence_errors(source_index, fact_index):
    data = fixture()
    data["authority"]["records"][0]["fact_ref"] = (
        f"/sources/{source_index}/content/facts/{fact_index}"
    )
    assert diagnose(data).errors[0].code == "invalid_evidence_reference"


def test_unreviewed_evidence_still_requires_valid_field_types():
    data = fixture()
    data["authority"]["review"].update(status="unreviewed", reviewer_id=42)
    assert diagnose(data).errors[0].code == "invalid_authority_review"
