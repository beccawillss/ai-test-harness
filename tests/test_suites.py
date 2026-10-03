"""Offline suite execution, immutable context, and exact source verification."""

import json
from dataclasses import replace

import pytest
from test_replay import scorer as judge_scorer
from test_replay import settings

from harness.core.dataset import hash_cases, load_dataset
from harness.core.fingerprints import fingerprint
from harness.core.models import (
    CaseResult,
    RunResult,
    Score,
    ScorerKind,
    TargetResponse,
    Verdict,
)
from harness.core.models import TestCase as Case
from harness.core.replay import prepare_replay, reconstruct_source_cases
from harness.core.runner import run
from harness.core.store import SQLiteResultStore
from harness.core.suites import (
    EvaluationProfile,
    Suite,
    execute_suite,
    resolve_suite,
)
from harness.targets.base import CallableTarget


class Metric:
    name = "metric"
    kind = ScorerKind.DETERMINISTIC
    requires = frozenset()

    def score(self, case, response):
        return Score(name=self.name, kind=self.kind, value=1, passed=True)


class RecordingTarget:
    name = "recording-v1"
    capabilities = frozenset()

    def __init__(self):
        self.calls = []
        self.closed = False

    def invoke(self, case):
        self.calls.append(case.model_copy(deep=True))
        return TargetResponse(output="answer")

    def close(self):
        self.closed = True


def profile(**kwargs):
    return EvaluationProfile(id="profile-v1", taxonomy_evidence="excluded", **kwargs)


def author(tmp_path, **suite_changes):
    cases = [
        {
            "id": "a",
            "input": {"message": "INPUT_SENTINEL", "history": []},
            "reference": {"expected": "REFERENCE_SENTINEL"},
            "title": "First",
            "description": "Prose",
            "category": "family",
            "risk": "high",
            "tags": ["quick"],
            "extra": {
                "safe": {"revision": 1},
                "private": {"nested": "SECRET_CASE"},
                "provenance": "SECRET_PROVENANCE",
            },
        },
        {"id": "b", "input": "second", "tags": ["quick"]},
        {"id": "c", "input": "third"},
    ]
    (tmp_path / "cases.jsonl").write_text("\n".join(json.dumps(c) for c in cases))
    descriptor = {
        "schema_version": "dataset-descriptor-v1",
        "id": "dataset",
        "version": "study-v1",
        "cases": "cases.jsonl",
        "extra": {
            "safe": {"origin": "fixture"},
            "private": {"nested": "SECRET_DESCRIPTOR"},
        },
        "fingerprint_scheme": "dataset-cases-v2",
    }
    (tmp_path / "dataset.json").write_text(json.dumps(descriptor))
    directory = tmp_path / "suites"
    directory.mkdir(exist_ok=True)
    path = directory / "quick.json"
    data = {
        "schema_version": "suite-v1",
        "id": "quick",
        "dataset": {
            "id": "dataset",
            "version": "study-v1",
            "descriptor": "../dataset.json",
        },
        "selection": {"tags_any": ["quick"]},
        "attempts": 2,
        "evaluation_profile": "profile-v1",
        **suite_changes,
    }
    path.write_text(json.dumps(data))
    return path


def edit(path, section, key, value):
    data = json.loads(path.read_text())
    (data if section is None else data[section])[key] = value
    path.write_text(json.dumps(data))


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema_version", "unknown"),
        ("id", " quick"),
        ("id", ""),
        ("title", "  "),
        ("attempts", True),
        ("attempts", 0),
        ("attempts", -1),
        ("attempts", 1.5),
        ("attempts", "2"),
        ("evaluation_profile", "p "),
        ("selection", {"tags_any": []}),
        ("cases", []),
    ],
)
def test_strict_suite_models_and_loader(tmp_path, key, value):
    path = author(tmp_path)
    edit(path, None, key, value)
    with pytest.raises(ValueError):
        Suite.model_validate(json.loads(path.read_text()))
    with pytest.raises(ValueError, match="quick.json"):
        resolve_suite(path)


@pytest.mark.parametrize(
    "text",
    [
        '{"schema_version":"suite-v1","id":"a","id":"b"}',
        '{"attempts":NaN}',
        '{"attempts":1e400}',
        "[]",
    ],
)
def test_suite_json_integrity(tmp_path, text):
    path = author(tmp_path)
    path.write_text(text)
    with pytest.raises(ValueError):
        resolve_suite(path)


@pytest.mark.parametrize(
    "key,value",
    [
        ("id", "wrong"),
        ("version", "wrong"),
        ("id", " dataset"),
        ("version", "study-v1 "),
        ("descriptor", "/tmp/dataset.json"),
        ("descriptor", "https://example.test/dataset.json"),
        ("descriptor", "C:\\x.json"),
        ("expected_fingerprint", "0" * 64),
        ("expected_case_fingerprint", "bad"),
        ("expected_descriptor_fingerprint", "bad"),
        ("expected_case_fingerprint", "0" * 64),
        ("expected_descriptor_fingerprint", "0" * 64),
    ],
)
def test_binding_failures(tmp_path, key, value):
    path = author(tmp_path)
    edit(path, "dataset", key, value)
    with pytest.raises(ValueError):
        resolve_suite(path)


def test_pins_relative_resolution_and_descriptor_only_drift(tmp_path, monkeypatch):
    path = author(tmp_path)
    dataset = load_dataset(tmp_path / "dataset.json")
    edit(path, "dataset", "expected_case_fingerprint", dataset.full_dataset_hash)
    monkeypatch.chdir(tmp_path.parent)
    resolved = resolve_suite(path)
    assert resolved.preview.case_ids == ["a", "b"]
    assert resolved.dataset.full_dataset_hash != resolved.preview.selected_dataset_hash
    edit(path, "dataset", "expected_descriptor_fingerprint", dataset.descriptor_hash)
    resolve_suite(path)
    descriptor_path = tmp_path / "dataset.json"
    edit(descriptor_path, None, "description", "Changed descriptor only")
    with pytest.raises(ValueError, match="descriptor fingerprint"):
        resolve_suite(path)
    edit(path, "dataset", "expected_descriptor_fingerprint", None)
    assert resolve_suite(path).dataset.full_dataset_hash == dataset.full_dataset_hash
    edit(path, "dataset", "expected_case_fingerprint", dataset.descriptor_hash)
    with pytest.raises(ValueError, match="case fingerprint"):
        resolve_suite(path)


@pytest.mark.parametrize("policy", ["hashes_only", "full"])
def test_execution_context_payload_policy_and_store_roundtrip(tmp_path, policy):
    resolved = resolve_suite(author(tmp_path))
    before = resolved.suite.model_dump_json()
    target = RecordingTarget()
    result = execute_suite(
        resolved,
        target,
        [Metric()],
        profile=profile(case_extra_keys=["safe"], dataset_extra_keys=["safe"]),
        case_payload_snapshot=policy,
    )
    assert [c.id for c in target.calls] == ["a", "a", "b", "b"]
    assert target.closed
    config = result.config_snapshot
    assert config["organization_schema_version"] == "run-organization-v1"
    assert config["dataset_fingerprint_scheme"] == "dataset-cases-v2"
    assert result.dataset_hash == resolved.preview.selected_dataset_hash
    assert config["full_dataset_hash"] == resolved.dataset.full_dataset_hash
    assert config["dataset_descriptor_hash"] == resolved.dataset.descriptor_hash
    assert config["suite_hash"] == resolved.suite_hash
    assert config["selection"] == {
        "expression": {"tags_any": ["quick"]},
        "case_ids": ["a", "b"],
    }
    assert config["case_payload_snapshot_source"] == "run_override"
    assert config["overrides"] == {"case_payload_snapshot": policy}
    assert not config["dataset_descriptor_snapshot_complete"]
    assert config["dataset_descriptor"]["extra"] == {"safe": {"origin": "fixture"}}
    assert result.cases[0].definition.extra == {"safe": {"revision": 1}}
    assert result.cases[0].definition.category == "family"
    assert result.cases[0].tags == ["quick"]
    assert "tags" not in result.cases[0].definition.model_dump()
    assert "SECRET" not in result.model_dump_json()
    assert ("resolved_cases" in config) == (policy == "full")
    assert ("INPUT_SENTINEL" in result.model_dump_json()) == (policy == "full")
    assert ("REFERENCE_SENTINEL" in result.model_dump_json()) == (policy == "full")
    if policy == "full":
        assert "extra" not in config["resolved_cases"][0]
        assert config["resolved_cases"][1]["category"] is None
    assert resolved.suite.model_dump_json() == before
    assert RunResult.model_validate_json(result.model_dump_json()) == result
    store = SQLiteResultStore(tmp_path / "new.sqlite")
    store.save(result)
    assert store.load(result.run_id) == result
    assert store.load_with_fingerprint(result.run_id)[1] == fingerprint(
        result.model_dump(mode="json")
    )
    with pytest.raises(ValueError, match="already stored"):
        store.save(result)


def test_defaults_profiles_overrides_and_policy_hash_independence(tmp_path):
    resolved = resolve_suite(author(tmp_path))
    default = execute_suite(resolved, RecordingTarget(), [Metric()], profile=profile())
    assert default.config_snapshot["case_payload_snapshot"] == "hashes_only"
    assert default.config_snapshot["case_payload_snapshot_source"] == "default"
    assert default.config_snapshot["overrides"] == {}
    assert default.cases[0].definition.extra == {}
    p = EvaluationProfile(
        id="replacement", taxonomy_evidence="excluded", case_payload_snapshot="full"
    )
    full = execute_suite(
        resolved,
        RecordingTarget(),
        [Metric()],
        profile=p,
        attempts=1,
        evaluation_profile="replacement",
    )
    assert full.dataset_hash == default.dataset_hash
    assert (
        full.cases[0].definition.definition_hash
        == default.cases[0].definition.definition_hash
    )
    assert full.config_snapshot["attempts"] == 1
    assert full.config_snapshot["suite"]["attempts"] == 2
    assert full.config_snapshot["suite"]["evaluation_profile"] == "profile-v1"
    assert full.config_snapshot["evaluation_profile"]["id"] == "replacement"
    assert full.config_snapshot["case_payload_snapshot_source"] == "profile"
    assert len(full.cases[0].attempts) == 1
    with pytest.raises(ValueError, match="differs"):
        execute_suite(resolved, RecordingTarget(), [Metric()], profile=p)
    no_profile = resolve_suite(author(tmp_path, evaluation_profile=None))
    execute_suite(no_profile, RecordingTarget(), [Metric()], profile=p)
    with pytest.raises(TypeError):
        execute_suite(no_profile, RecordingTarget(), [Metric()])


@pytest.mark.parametrize("override", [True, 0, -1, 1.5, "2"])
def test_invalid_attempt_override_before_calls(tmp_path, override):
    target = RecordingTarget()
    with pytest.raises(ValueError):
        execute_suite(
            resolve_suite(author(tmp_path)),
            target,
            [Metric()],
            profile=profile(),
            attempts=override,
        )
    assert target.calls == []


@pytest.mark.parametrize(
    "change",
    [
        "empty",
        "capabilities",
        "duplicate_scorers",
        "references",
        "unsafe",
        "mismatch",
        "policy",
        "required_full",
        "case_drift",
        "suite_drift",
        "preview_drift",
        "descriptor_path",
        "observable",
        "profile_whitespace",
    ],
)
def test_execution_preflight_rejects_before_target_calls(tmp_path, change):
    resolved = resolve_suite(
        author(
            tmp_path,
            **({"selection": {"tags_any": ["absent"]}} if change == "empty" else {}),
        )
    )
    target = RecordingTarget()
    metric = Metric()
    metrics = [metric]
    p = profile()
    options = {}
    if change == "capabilities":
        metric.requires = frozenset({"evidence"})
    elif change == "duplicate_scorers":
        metrics.append(Metric())
    elif change == "references":
        p = profile(reference_contract="reference-v1")

        def validate(case):
            if case.id == "b":
                raise ValueError("Private reference detail")

        options["validate_reference"] = validate
    elif change == "unsafe":
        p.safe_parameters["client"] = object()
    elif change == "mismatch":
        p = EvaluationProfile(id="different", taxonomy_evidence="excluded")
    elif change == "policy":
        options["case_payload_snapshot"] = "invalid"
    elif change == "required_full":
        p = profile(case_payload_snapshot="full", requires_full_payload=True)
        options["case_payload_snapshot"] = "hashes_only"
    elif change == "case_drift":
        resolved.dataset.cases[0].extra["mutated"] = 1
    elif change == "suite_drift":
        resolved.suite.selection.tags_any.append("other")
    elif change == "preview_drift":
        resolved.preview.case_ids.reverse()
    elif change == "descriptor_path":
        resolved = replace(
            resolved, suite_path=tmp_path / "elsewhere" / "nested" / "suite.json"
        )
    elif change == "observable":
        p = profile(scorer_configuration={"metric": {"kind": "judged"}})
    elif change == "profile_whitespace":
        options["evaluation_profile"] = " replacement"
    with pytest.raises(ValueError):
        execute_suite(resolved, target, metrics, profile=p, **options)
    assert not target.calls


def test_definition_and_context_copies_precede_calls_and_isolate_attempts(tmp_path):
    resolved = resolve_suite(author(tmp_path))
    p = profile(
        case_extra_keys=["safe"],
        dataset_extra_keys=["safe"],
        safe_parameters={"nested": {"value": 1}},
    )
    calls = []

    def invoke(case):
        calls.append(case.model_copy(deep=True))
        case.category = "mutated by target"
        case.tags.append("injected")
        if isinstance(case.input, dict):
            case.input["history"].append("state")
        resolved.dataset.cases[0].category = "external mutation"
        resolved.suite.selection.tags_any.append("changed")
        p.safe_parameters["nested"]["value"] = 9
        return TargetResponse(output="ok")

    class AssertingMetric(Metric):
        def score(self, case, response):
            assert case.category != "mutated by target"
            assert "injected" not in case.tags
            if isinstance(case.input, dict):
                assert case.input["history"] == []
            return super().score(case, response)

    result = execute_suite(
        resolved,
        CallableTarget(name="mutating", invoke=invoke),
        [AssertingMetric()],
        profile=p,
        case_payload_snapshot="full",
    )
    assert all(a.verdict == Verdict.PASS for c in result.cases for a in c.attempts)
    assert calls[0].input["history"] == calls[1].input["history"] == []
    assert result.cases[0].definition.category == "family"
    assert result.config_snapshot["evaluation_profile"]["safe_parameters"] == {
        "nested": {"value": 1}
    }
    assert result.config_snapshot["selection"]["expression"] == {"tags_any": ["quick"]}
    before = result.model_dump_json()
    resolved.dataset.cases[0].extra["safe"]["revision"] = 99
    p.case_extra_keys.append("private")
    assert result.model_dump_json() == before


def test_runtime_verdicts_and_independent_scorers(tmp_path):
    resolved = resolve_suite(author(tmp_path, selection={}))

    class Primary(Metric):
        def score(self, case, response):
            if case.id == "b":
                raise RuntimeError("scorer error")
            return Score(
                name=self.name,
                kind=self.kind,
                value=0.25,
                passed=False if case.id == "a" else None,
            )

    class Independent(Metric):
        name = "independent"

        def score(self, case, response):
            return Score(name=self.name, kind=self.kind, value=0.75)

    result = execute_suite(
        resolved, RecordingTarget(), [Primary(), Independent()], profile=profile()
    )
    assert [c.attempts[0].verdict for c in result.cases] == [
        Verdict.FAIL,
        Verdict.ERROR,
        Verdict.SKIP,
    ]
    assert result.cases[1].attempts[0].scores[0].name == "independent"

    def timeout(_):
        raise TimeoutError("offline timeout")

    result = execute_suite(
        resolved,
        CallableTarget(name="timeout", invoke=timeout),
        [Metric()],
        profile=profile(),
    )
    assert all(
        a.verdict == Verdict.ERROR and a.response is None
        for c in result.cases
        for a in c.attempts
    )


@pytest.mark.parametrize("policy", ["hashes_only", "full"])
def test_suite_replay_verified_sources_and_tampering(tmp_path, policy):
    scoring = judge_scorer()
    p = profile(
        judge_configurations={scoring.name: settings()},
        scorer_configuration={scoring.name: scoring.preparation_configuration},
    )
    resolved = resolve_suite(author(tmp_path))
    result = execute_suite(
        resolved, RecordingTarget(), [scoring], profile=p, case_payload_snapshot=policy
    )

    def prepare(source=result, cases=None):
        return prepare_replay(
            source,
            resolved.dataset.cases if cases is None else cases,
            scoring,
            judge_configuration=settings(),
            database_locator="runs/synthetic.sqlite",
            case_id="a",
            source_attempt=0,
            attempts=1,
        )

    prepared = prepare()
    assert prepared.source.case_hash == result.cases[0].definition.definition_hash
    with pytest.raises(ValueError):
        prepare(cases=[])
    with pytest.raises(ValueError):
        reconstruct_source_cases(
            result
        )  # subset and/or unexported extra are insufficient
    for field in (
        "title",
        "description",
        "category",
        "risk",
        "extra",
        "definition_hash",
    ):
        tampered = result.model_copy(deep=True)
        definition = tampered.cases[0].definition
        tampered.cases[0].definition = definition.model_copy(
            update={
                field: {"wrong": 1}
                if field == "extra"
                else "0" * 64
                if field == "definition_hash"
                else "changed"
            }
        )
        with pytest.raises(ValueError, match="snapshot"):
            prepare(tampered)
    for key in ("suite_hash", "dataset_descriptor_hash"):
        tampered = result.model_copy(deep=True)
        tampered.config_snapshot[key] = "bad"
        with pytest.raises(ValueError):
            prepare(tampered)
    tampered = result.model_copy(deep=True)
    tampered.config_snapshot["evaluation_profile"]["scorers"][0]["observed"][
        "rubric"
    ] = "changed"
    with pytest.raises(ValueError):
        prepare(tampered)


def test_full_reconstruction_only_with_complete_verified_material(tmp_path):
    resolved = resolve_suite(author(tmp_path, selection={}))
    # Safe synthetic fixture data is explicitly supplied here; no private subtree is exported.
    for case in resolved.dataset.cases:
        case.extra.clear()
    rows = "\n".join(c.model_dump_json() for c in resolved.dataset.cases)
    (tmp_path / "cases.jsonl").write_text(rows)
    resolved = resolve_suite(tmp_path / "suites/quick.json")
    result = execute_suite(
        resolved,
        RecordingTarget(),
        [Metric()],
        profile=profile(case_payload_snapshot="full"),
    )
    assert reconstruct_source_cases(result) == resolved.dataset.cases
    assert (
        hash_cases(reconstruct_source_cases(result), scheme="dataset-cases-v2")
        == result.dataset_hash
    )


def test_legacy_case_result_serialization_omits_only_new_field():
    result = CaseResult(case_id="a")
    assert result.model_dump() == {"case_id": "a", "tags": [], "attempts": []}
    assert result.model_dump_json() == '{"case_id":"a","tags":[],"attempts":[]}'
    assert result.model_dump(include={"case_id", "definition"}) == {"case_id": "a"}


@pytest.mark.parametrize(
    "options",
    [
        {"fingerprint_scheme": "unknown"},
        {"case_payload_snapshot": "full"},
        {"case_extra_keys": ["safe"]},
        {"fingerprint_scheme": "dataset-cases-v2", "attempts": True},
        {"fingerprint_scheme": "dataset-cases-v2", "case_payload_snapshot": "invalid"},
        {"fingerprint_scheme": "dataset-cases-v2", "case_extra_keys": ["safe", "safe"]},
    ],
)
def test_direct_runner_explicit_v2_preflight(options):
    target = RecordingTarget()
    with pytest.raises(ValueError):
        run(target, [Metric()], [Case(id="a", input="x")], **options)
    assert not target.calls


def test_direct_v2_and_legacy_new_fields_fail_before_calls():
    case = Case(id="a", input="x", category="family")
    target = RecordingTarget()
    with pytest.raises(ValueError):
        run(target, [Metric()], [case])
    assert not target.calls
    result = run(target, [Metric()], [case], fingerprint_scheme="dataset-cases-v2")
    assert result.cases[0].definition.category == "family"
    assert result.config_snapshot["case_payload_snapshot"] == "hashes_only"
    assert result.dataset_hash == hash_cases([case], scheme="dataset-cases-v2")


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "different"),
        ("description", "different"),
        ("category", "different"),
        ("tags", ["different"]),
        ("risk", "different"),
        ("extra", {"x": "different"}),
    ],
)
def test_taxonomy_excluded_judge_projection_bytes(field, value):
    scoring = judge_scorer()
    case = Case(id="a", input="question", reference="expected")
    response = TargetResponse(output="answer")
    original = scoring.prepare(case, response)
    setattr(case, field, value)
    revised = scoring.prepare(case, response)
    assert revised.prompt == original.prompt
    assert revised.evidence_json == original.evidence_json
    assert revised.configuration_json == original.configuration_json


def test_default_judge_cannot_claim_taxonomy_exclusion(tmp_path):
    scoring = judge_scorer(evidence_builder=None)
    resolved = resolve_suite(author(tmp_path))
    target = RecordingTarget()
    with pytest.raises(ValueError, match="includes tags"):
        execute_suite(resolved, target, [scoring], profile=profile())
    assert not target.calls
    execute_suite(
        resolved,
        target,
        [scoring],
        profile=EvaluationProfile(
            id="profile-v1", taxonomy_evidence="explicitly_included"
        ),
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("id", " profile-v1"),
        ("id", ""),
        ("taxonomy_evidence", "guess"),
        ("case_extra_keys", ["safe", "safe"]),
        ("dataset_extra_keys", [1]),
        ("case_extra_keys", [str(i) for i in range(129)]),
        ("safe_parameters", {"invalid": float("nan")}),
        ("scorer_configuration", {"metric": {"invalid": object()}}),
    ],
)
def test_strict_profile_configuration(key, value):
    with pytest.raises(ValueError):
        EvaluationProfile.model_validate(
            {"id": "profile-v1", "taxonomy_evidence": "excluded", key: value}
        )


def test_complete_descriptor_snapshot_and_unrecorded_scorer_configuration(tmp_path):
    resolved = resolve_suite(author(tmp_path))
    # Replace private fixture data rather than deeming a private subtree safe.
    (tmp_path / "dataset.json").write_text(
        json.dumps(
            {
                **resolved.dataset.descriptor.model_dump(),
                "extra": {"safe": {"revision": 1}},
            }
        )
    )
    resolved = resolve_suite(tmp_path / "suites/quick.json")
    result = execute_suite(
        resolved,
        RecordingTarget(),
        [Metric()],
        profile=profile(dataset_extra_keys=["safe"]),
    )
    context = result.config_snapshot
    assert context["dataset_descriptor_snapshot_complete"]
    assert (
        fingerprint(context["dataset_descriptor"]) == context["dataset_descriptor_hash"]
    )
    assert (
        context["evaluation_profile"]["scorers"][0]["configuration_status"] == "unknown"
    )
    assert context["artifact_capabilities"]["external_source_cases_required"]


def test_content_pin_detects_case_changes_and_both_pins_are_independent(tmp_path):
    path = author(tmp_path)
    dataset = load_dataset(tmp_path / "dataset.json")
    edit(path, "dataset", "expected_case_fingerprint", dataset.full_dataset_hash)
    edit(path, "dataset", "expected_descriptor_fingerprint", dataset.descriptor_hash)
    rows = (tmp_path / "cases.jsonl").read_text().replace("second", "revised")
    (tmp_path / "cases.jsonl").write_text(rows)
    with pytest.raises(ValueError, match="case fingerprint"):
        resolve_suite(path)
    revised = load_dataset(tmp_path / "dataset.json")
    edit(path, "dataset", "expected_case_fingerprint", revised.full_dataset_hash)
    resolve_suite(path)
    edit(path, "dataset", "expected_descriptor_fingerprint", dataset.full_dataset_hash)
    with pytest.raises(ValueError, match="descriptor fingerprint"):
        resolve_suite(path)


@pytest.mark.parametrize(
    "mode",
    [
        "missing_validator",
        "unnamed_validator",
        "mutating_validator",
        "unknown_scorer",
        "judge_model",
        "unknown_projection",
    ],
)
def test_profile_contract_failures_precede_calls(tmp_path, mode):
    resolved = resolve_suite(author(tmp_path))
    target = RecordingTarget()
    p = profile()
    options = {}
    metrics = [Metric()]
    if mode == "missing_validator":
        p = profile(reference_contract="expected-v1")
    elif mode == "unnamed_validator":
        options["validate_reference"] = lambda _: None
    elif mode == "mutating_validator":
        p = profile(reference_contract="expected-v1")

        def mutate(case):
            case.extra["safe"]["revision"] = True  # 1 == True must not hide mutation

        options["validate_reference"] = mutate
    elif mode == "unknown_scorer":
        p = profile(scorer_configuration={"absent": {}})
    elif mode == "judge_model":
        metrics = [judge_scorer()]
        p = profile(judge_configurations={metrics[0].name: settings(model="other")})
    else:
        metrics = [judge_scorer(projection_version=None)]
    with pytest.raises(ValueError):
        execute_suite(resolved, target, metrics, profile=p, **options)
    assert not target.calls


@pytest.mark.parametrize("policy", ["hashes_only", "full"])
def test_suite_calibration_identity_roundtrip_and_historical_join(tmp_path, policy):
    from harness.core.calibration import (
        CalibrationExample,
        ObservationPolicy,
        RatingContract,
        historical_observations,
        make_example,
        verify_rebuilt,
    )

    resolved = resolve_suite(author(tmp_path))
    scoring = judge_scorer()
    result = execute_suite(
        resolved,
        RecordingTarget(),
        [scoring],
        profile=profile(judge_configurations={scoring.name: settings()}),
        case_payload_snapshot=policy,
    )

    def prepare():
        return prepare_replay(
            result,
            resolved.dataset.cases,
            scoring,
            judge_configuration=settings(),
            database_locator="runs/synthetic.sqlite",
            case_id="a",
            source_attempt=0,
            attempts=1,
        )

    prepared = prepare()
    config = scoring.preparation_configuration
    contract = RatingContract(
        rubric=config["rubric"],
        rubric_version=config["rubric_version"],
        scale="anchors",
        anchors=(0.0, 0.3, 0.6, 0.8, 1.0),
        threshold=config["pass_threshold"],
        projection_version=config["projection_version"],
        prompt_version=config["prompt_version"],
        judgment_version=config["judgment_version"],
        evidence_settings_json=json.dumps(config["evidence_settings"]),
        instructions="Independent synthetic rating",
        instruction_version="test-v1",
        dimensions=("clarity",),
    )
    example = make_example(
        prepared,
        contract,
        ObservationPolicy(kind="historical", artifact_id=result.run_id),
    )
    loaded = CalibrationExample.model_validate_json(example.model_dump_json())
    assert loaded.identity_hash == example.identity_hash
    assert loaded.binding_hash == example.binding_hash
    verify_rebuilt(loaded, prepare())
    observation = historical_observations(loaded, result, prepared)
    assert observation.verification == "historical_input_reconstructed"


def test_full_payload_reconstruction_can_prepare_verified_replay(tmp_path):
    path = author(tmp_path, selection={})
    rows = [
        json.loads(row) for row in (tmp_path / "cases.jsonl").read_text().splitlines()
    ]
    for row in rows:
        row.pop("extra", None)
    (tmp_path / "cases.jsonl").write_text("\n".join(json.dumps(row) for row in rows))
    resolved = resolve_suite(path)
    scoring = judge_scorer()
    result = execute_suite(
        resolved,
        RecordingTarget(),
        [scoring],
        profile=profile(
            judge_configurations={scoring.name: settings()},
            case_payload_snapshot="full",
        ),
    )
    assert not result.config_snapshot["artifact_capabilities"][
        "external_source_cases_required"
    ]
    cases = reconstruct_source_cases(result)
    prepared = prepare_replay(
        result,
        cases,
        scoring,
        judge_configuration=settings(),
        database_locator="runs/synthetic.sqlite",
        case_id="a",
        source_attempt=0,
        attempts=1,
    )
    assert prepared.source.case_hash == result.cases[0].definition.definition_hash
    before = result.model_dump_json()
    cases[0].input["history"].append("caller mutation")
    assert result.model_dump_json() == before
    result.cases[0].tags.append("tampered")
    with pytest.raises(ValueError):
        reconstruct_source_cases(result)
