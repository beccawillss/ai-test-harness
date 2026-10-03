"""Pinned pre-change artifacts and explicit case-definition compatibility."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError
from test_replay import _v2_source, prepare, scorer

from harness.core.calibration import (
    CalibrationExample,
    CalibrationManifest,
    FrozenAnnotationSet,
    HumanAnnotation,
    ObservationPolicy,
    RatingContract,
    blind_packet,
    historical_observations,
    make_example,
    replay_observations,
    verify_rebuilt,
)
from harness.core.case_fingerprints import (
    CASE_SCHEME_V1,
    CASE_SCHEME_V2,
    case_payload,
    hash_case_definition,
    resolved_case_payload,
)
from harness.core.dataset import hash_cases, load_cases
from harness.core.fingerprints import fingerprint
from harness.core.models import RunResult
from harness.core.models import TestCase as Case
from harness.core.replay import PreparedReplay, ReplayResult
from harness.core.store import SQLiteResultStore

FIXTURE = Path(__file__).parent / "fixtures/taxonomy/legacy-v1.json"


def never_judge(_):
    raise AssertionError("Compatibility preparation must not invoke a judge")


def test_pinned_legacy_artifacts_and_bindings(tmp_path):
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
        "5818ce99cec46d4ec82095b7a6e9eb11685a8537248cff8eae2419e95dd49e4b"
    )
    fixture = json.loads(FIXTURE.read_text())
    docs = fixture["documents"]
    source = RunResult.model_validate(docs["source"])
    cases = [Case.model_validate(c) for c in fixture["cases"]]
    prepared = PreparedReplay.model_validate(docs["prepared"])
    replayed = ReplayResult.model_validate(docs["replay"])
    manifest = CalibrationManifest.model_validate(docs["manifest"])
    historical = CalibrationExample.model_validate(docs["historical_example"])
    replay_example = CalibrationExample.model_validate(docs["replay_example"])
    human = HumanAnnotation.model_validate(docs["annotation"])
    frozen = FrozenAnnotationSet.model_validate(docs["frozen"])
    frozen.verify_manifest(manifest)
    rebuilt = prepare(source, cases, scorer(never_judge), attempts=1)
    verify_rebuilt(historical, rebuilt)
    verify_rebuilt(replay_example, rebuilt)
    assert rebuilt.model_dump() == prepared.model_dump()
    assert hash_cases(cases) == fixture["dataset_hash"]
    assert historical.identity_hash == fixture["identity_hash"]
    assert historical.binding_hash == fixture["binding_hash"]
    models = {
        "source": source,
        "prepared": prepared,
        "replay": replayed,
        "contract": manifest.contract,
        "historical_example": historical,
        "replay_example": replay_example,
        "manifest": manifest,
        "packet": blind_packet(manifest),
        "annotation": human,
        "frozen": frozen,
        "historical_observations": historical_observations(historical, source, rebuilt),
        "replay_observations": replay_observations(replay_example, replayed, rebuilt),
    }
    for name, model in models.items():
        assert model.model_dump(mode="json") == docs[name], name
        assert model.model_dump_json() == fixture["document_json"][name], name
        assert (
            fingerprint(model.model_dump(mode="json"))
            == (fixture["document_hashes"][name])
        ), name
    for sample in fixture["case_samples"]:
        case = Case.model_validate(sample["payload"])
        assert case.model_dump() == sample["payload"]
        assert case.model_dump_json() == sample["json"]
        assert case.model_dump(mode="json", exclude={"extra"}) == sample["resolved"]
        assert fingerprint(case.model_dump(mode="json")) == sample["case_hash"]
    store = SQLiteResultStore(tmp_path / "legacy.sqlite")
    store.save(source)
    restored, digest = store.load_with_fingerprint(source.run_id)
    assert digest == fixture["document_hashes"]["source"]
    assert restored.model_dump_json() == fixture["document_json"]["source"]
    store.save_replay(replayed)
    assert (
        store.load_replay(replayed.replay_id).model_dump_json()
        == (fixture["document_json"]["replay"])
    )


def test_frozen_dataset_bytes_and_hashes():
    frozen = {
        "baseline": (
            "f24ffe05b08d75848860f71ef726cf96dccb78e457e5757fb7144cd30db4a747",
            "c1a73ef207f2cabe3292d743504f7249f4729825d785adff5b6bf14ad6a7b12b",
        ),
        "semantic": (
            "3200acd541c6db9f3bb3301186f4213746e177c0c3048b4ad99434da590791a9",
            "33654c3f4870efc67edd8e30a6ae0a82c17eb58c8c30cb323add5d0efe414849",
        ),
    }
    for name, (byte_hash, case_hash) in frozen.items():
        path = Path("datasets/salesagent") / f"{name}.jsonl"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == byte_hash
        assert hash_cases(load_cases(path)) == case_hash
        assert hash_cases(load_cases(path), scheme=CASE_SCHEME_V1) == case_hash


def test_legacy_serialization_nested_and_include_exclude():
    class Envelope(BaseModel):
        case: Case

    payload = {"id": "c", "input": "hi", "reference": None, "tags": [], "extra": {}}
    case = Case(
        id="c", input="hi", title=None, description=None, category=None, risk=None
    )
    for mode in ("python", "json"):
        assert case.model_dump(mode=mode) == payload
        assert Envelope(case=case).model_dump(mode=mode) == {"case": payload}
        assert case.model_dump(mode=mode, include={"id", "title", "reference"}) == {
            "id": "c",
            "reference": None,
        }
        assert case.model_dump(mode=mode, exclude={"extra", "reference"}) == {
            "id": "c",
            "input": "hi",
            "tags": [],
        }
        assert case.model_dump(mode=mode, exclude_unset=True) == {
            "id": "c",
            "input": "hi",
        }
        assert case.model_dump(mode=mode, exclude_defaults=True) == {
            "id": "c",
            "input": "hi",
        }
    assert json.loads(Envelope(case=case).model_dump_json()) == {"case": payload}
    assert TypeAdapter(list[Case]).dump_python([case], mode="json") == [payload]
    assert case.model_dump(include={"title"}) == {}
    assert case.model_dump(exclude_none=True) == {
        "id": "c",
        "input": "hi",
        "tags": [],
        "extra": {},
    }


@pytest.mark.parametrize("field", ["title", "description", "category", "risk"])
def test_definition_fields_roundtrip_and_never_disappear_under_v1(field):
    case = Case(id="c", input="hi", **{field: "opaque value"})
    assert Case.model_validate_json(case.model_dump_json()) == case
    assert case.model_dump(include={field}) == {field: "opaque value"}
    assert field not in case.model_dump(exclude={field})
    for operation in (case_payload, resolved_case_payload, hash_case_definition):
        with pytest.raises(ValueError, match="require dataset-cases-v2"):
            operation(case, scheme=CASE_SCHEME_V1)
    with pytest.raises(ValueError, match="require dataset-cases-v2"):
        hash_cases([case])
    assert case_payload(case, scheme=CASE_SCHEME_V2)[field] == "opaque value"


def test_empty_prose_is_populated_for_v1_and_valid_v2():
    case = Case(id="c", input="hi", description="")
    with pytest.raises(ValueError, match="require dataset-cases-v2"):
        hash_cases([case])
    assert case_payload(case, scheme=CASE_SCHEME_V2)["description"] == ""


@pytest.mark.parametrize("field", ["title", "category", "risk"])
@pytest.mark.parametrize("value", ["", " ", "\t\n", "\u00a0", 1, True, b"text"])
def test_new_definition_fields_validate_direct_construction(field, value):
    with pytest.raises(ValidationError):
        Case(id="c", input="hi", **{field: value})


@pytest.mark.parametrize("field", ["category", "risk"])
@pytest.mark.parametrize(
    "value", [" leading", "trailing ", "\tvalue", "value\n", "\u00a0value"]
)
def test_taxonomy_boundary_whitespace_rejected_in_python_and_json(field, value):
    data = {"id": "c", "input": "hi", field: value}
    with pytest.raises(ValidationError, match="boundary whitespace"):
        Case.model_validate(data)
    with pytest.raises(ValidationError, match="boundary whitespace"):
        Case.model_validate_json(json.dumps(data))


def test_opaque_internal_whitespace_and_prose_are_preserved():
    case = Case(
        id="case a",
        input="hi",
        tags=["tag a"],
        category="family a",
        risk="risk a",
        title=" A title ",
        description=" \n prose \t ",
    )
    payload = case_payload(case, scheme=CASE_SCHEME_V2)
    assert payload["id"] == "case a"
    assert payload["tags"] == ["tag a"]
    assert payload["category"] == "family a"
    assert payload["risk"] == "risk a"
    assert payload["title"] == " A title "
    assert payload["description"] == " \n prose \t "


@pytest.mark.parametrize(
    "changes",
    [
        {"id": ""},
        {"id": " a"},
        {"id": "a "},
        {"id": "a\n"},
        {"tags": [""]},
        {"tags": [" x"]},
        {"tags": ["x "]},
        {"tags": ["x", "x"]},
    ],
)
def test_strict_v2_boundary_preserves_permissive_legacy_fields(changes, tmp_path):
    payload = {"id": "a", "input": "hi", **changes, "unknown": "still ignored"}
    path = tmp_path / "legacy.jsonl"
    path.write_text(json.dumps(payload) + "\n")
    case = load_cases(path)[0]
    assert "unknown" not in case.model_dump()
    assert hash_cases([case]) == hash_cases([Case.model_validate(payload)])
    with pytest.raises(ValueError):
        hash_cases([case], scheme=CASE_SCHEME_V2)


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", 3),
        ("tags", [1]),
        ("tags", ("a",)),
        ("tags", ["a", "a"]),
        ("category", " wrong"),
        ("title", ""),
        ("risk", 3),
        ("description", False),
        ("input", []),
        ("reference", []),
        ("extra", []),
    ],
)
def test_v2_revalidates_mutated_and_constructed_cases(field, value):
    for case in (Case(id="c", input="hi"), Case.model_construct(id="c", input="hi")):
        setattr(case, field, value)
        with pytest.raises(ValueError):
            case_payload(case, scheme=CASE_SCHEME_V2)


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        b"bytes",
        {"set"},
        ("tuple",),
        Decimal("1.25"),
        datetime(2026, 1, 1, tzinfo=UTC),
        {1: "nonstring key"},
    ],
)
@pytest.mark.parametrize("field", ["input", "reference", "extra"])
def test_v2_rejects_non_json_and_nonfinite_before_serialization(field, value):
    case = Case(
        id="c", input="hi", **({} if field == "input" else {field: {"nested": [value]}})
    )
    if field == "input":
        case.input = {"nested": [value]}
    with pytest.raises(ValueError, match="V2"):
        hash_cases([case], scheme=CASE_SCHEME_V2)


def test_v2_rejects_cycles_without_recursion_overflow():
    recursive = []
    recursive.append(recursive)
    case = Case(id="c", input="hi", extra={"cycle": recursive})
    with pytest.raises(ValueError, match="cycles"):
        hash_cases([case], scheme=CASE_SCHEME_V2)


def test_v1_unicode_null_and_nonfinite_algorithm_is_unchanged():
    case = Case(id="c", input="é", extra={"number": float("nan")})
    # The pre-change model's JSON-mode dump maps non-finite floats to null.
    original_row = '{"extra":{"number":null},"id":"c","input":"\\u00e9","reference":null,"tags":[]}\n'
    assert hash_cases([case]) == hashlib.sha256(original_row.encode()).hexdigest()


def test_v2_canonical_envelope_and_single_case_are_explicit():
    case = Case(id="c", input="café 雪", extra={"nullable": None})
    payload_json = '{"category":null,"description":null,"extra":{"nullable":null},"id":"c","input":"café 雪","reference":null,"risk":null,"tags":[],"title":null}'
    dataset_json = '{"cases":[' + payload_json + '],"scheme":"dataset-cases-v2"}'
    single_json = '{"case":' + payload_json + ',"scheme":"dataset-cases-v2"}'
    assert (
        hash_cases(iter([case]), scheme=CASE_SCHEME_V2)
        == hashlib.sha256(dataset_json.encode()).hexdigest()
    )
    assert (
        hash_case_definition(case, scheme=CASE_SCHEME_V2)
        == hashlib.sha256(single_json.encode()).hexdigest()
    )
    assert hash_case_definition(case, scheme=CASE_SCHEME_V2) != hash_cases(
        [case], scheme=CASE_SCHEME_V2
    )
    assert hash_case_definition(case, scheme=CASE_SCHEME_V1) == fingerprint(
        case.model_dump(mode="json")
    )
    assert resolved_case_payload(case, scheme=CASE_SCHEME_V2) == {
        key: value for key, value in json.loads(payload_json).items() if key != "extra"
    }
    assert (
        hash_cases([], scheme=CASE_SCHEME_V2)
        == hashlib.sha256(b'{"cases":[],"scheme":"dataset-cases-v2"}').hexdigest()
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "different"),
        ("input", "different"),
        ("reference", {"expected": True}),
        ("tags", ["second", "first"]),
        ("extra", {"revision": 2}),
        ("title", "Title"),
        ("description", ""),
        ("category", "family a"),
        ("risk", "opaque"),
    ],
)
def test_every_definition_field_affects_v2_hash(field, value):
    case = Case(id="c", input="hi", tags=["first", "second"], extra={"revision": 1})
    changed = case.model_copy(update={field: value}, deep=True)
    assert hash_cases([case], scheme=CASE_SCHEME_V2) != hash_cases(
        [changed], scheme=CASE_SCHEME_V2
    )
    assert hash_case_definition(case, scheme=CASE_SCHEME_V2) != hash_case_definition(
        changed, scheme=CASE_SCHEME_V2
    )


def test_v2_format_defaults_and_order_are_stable():
    case = Case(id="c", input={"b": 2, "a": 1})
    equivalent = Case.model_validate_json(
        '{ "input": {"a":1,"b":2}, "id":"c", "risk":null, "title":null, "description":null, "category":null }'
    )
    assert hash_cases([case], scheme=CASE_SCHEME_V2) == hash_cases(
        [equivalent], scheme=CASE_SCHEME_V2
    )
    other = Case(id="d", input="hi")
    assert hash_cases([case, other], scheme=CASE_SCHEME_V2) != hash_cases(
        [other, case], scheme=CASE_SCHEME_V2
    )


@pytest.mark.parametrize("scheme", ["", "dataset-cases-v3", None, [], {}])
def test_unknown_schemes_rejected_even_for_empty_dataset(scheme):
    with pytest.raises(ValueError, match="Unknown case fingerprint scheme"):
        hash_cases([], scheme=scheme)
    with pytest.raises(ValueError, match="Unknown case fingerprint scheme"):
        case_payload(Case(id="c", input="hi"), scheme=scheme)


@pytest.mark.parametrize(
    "field", ["case_hash", "dataset_hash", "dataset_fingerprint_scheme"]
)
def test_pinned_calibration_binding_rejects_provenance_tampering(field):
    fixture = json.loads(FIXTURE.read_text())
    example = fixture["documents"]["historical_example"]
    example["prepared"]["source"][field] = (
        CASE_SCHEME_V2 if field.endswith("scheme") else "a" * 64
    )
    with pytest.raises(ValueError, match="binding differs"):
        CalibrationExample.model_validate(example)


@pytest.mark.parametrize("policy", ["full", "hashes_only"])
def test_v2_calibration_identity_binds_classification_independently_of_prompt(policy):
    source, cases, scoring = _v2_source(policy)
    prepared = prepare(source, cases, scoring)
    fixture = json.loads(FIXTURE.read_text())
    contract = RatingContract.model_validate(fixture["documents"]["contract"])
    example = make_example(
        prepared,
        contract,
        ObservationPolicy(kind="historical", artifact_id=source.run_id),
    )
    restored = CalibrationExample.model_validate_json(example.model_dump_json())
    assert restored.identity_hash == example.identity_hash
    assert restored.binding_hash == example.binding_hash
    verify_rebuilt(restored, prepare(source, cases, scoring))
    cases[0].category = "different family"
    source.dataset_hash = hash_cases(cases, scheme=CASE_SCHEME_V2)
    source.config_snapshot["full_dataset_hash"] = source.dataset_hash
    if policy == "full":
        source.config_snapshot["resolved_cases"] = [
            resolved_case_payload(c, scheme=CASE_SCHEME_V2) for c in cases
        ]
    changed = prepare(source, cases, scoring)
    assert changed.prepared.prompt_hash == prepared.prepared.prompt_hash
    assert changed.source.case_hash != prepared.source.case_hash
    with pytest.raises(ValueError, match="differs"):
        verify_rebuilt(restored, changed)
