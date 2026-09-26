"""Offline generic fixed-response experiments, without a target even in fixtures."""

import json
import sqlite3
from datetime import UTC, datetime

import pytest

from harness.core.dataset import hash_cases
from harness.core.fingerprints import canonical_json, fingerprint
from harness.core.models import (
    AttemptResult,
    CaseResult,
    RunResult,
    Score,
    ScorerKind,
    TargetResponse,
    ToolCall,
    Verdict,
)
from harness.core.models import TestCase as Case
from harness.core.replay import (
    EvaluatorConfiguration,
    JudgeConfiguration,
    ReplayAttemptResult,
    ReplayResult,
    SourceProvenance,
    prepare_replay,
    replay,
    source_locator,
    variance_summary,
)
from harness.core.store import SQLiteResultStore
from harness.judges.base import JudgeReply
from harness.scorers.rubric_judge import RubricJudgeScorer


def settings(**changes):
    return JudgeConfiguration.model_validate(
        {
            "provider": "fake",
            "model": "fake-v1",
            "adapter_version": "fake-v1",
            "instruction_version": "instructions-v1",
            "response_schema": "score-reason-v1",
            "max_output_tokens": 2048,
            "timeouts": {"connect": 5, "read": 120, "write": 10, "pool": 5},
            **changes,
        }
    )


def scorer(judge=lambda _: '{"score":0.8,"reason":"Clear."}', **changes):
    return RubricJudgeScorer(
        judge,
        "fake-v1",
        **{
            "rubric": "Be useful.",
            "name": "helpfulness",
            "rubric_version": "useful-v1",
            "projection_version": "question-answer-v1",
            "projection_reviewed": True,
            "evidence_builder": lambda case, response: {
                "question": case.input,
                "answer": response.output,
            },
            **changes,
        },
    )


def fixture_run(scoring=None):
    scoring = scoring or scorer()
    cases = [
        Case(
            id="a",
            input="First question",
            reference={"expectation": "clear"},
            extra={"version": 1},
        ),
        Case(id="b", input="Second question", tags=["pair"]),
    ]
    response = TargetResponse(
        output="Saved answer",
        contexts=["chunk1", "chunk2"],
        structured={
            "turns": [{"input": "q", "output": "a"}],
            "null": None,
            "empty": [],
        },
        trajectory=[
            ToolCall(name="search", arguments={"q": "x"}, result={"value": "known"})
        ],
        latency_ms=12,
        cost_usd=0.2,
        metadata={"private": "SECRET_METADATA"},
        raw={"private": "SECRET_RAW"},
    )
    config = scoring.preparation_configuration
    source = RunResult(
        run_id="source",
        config_path="PRIVATE_LOCAL_PATH",
        config_snapshot={
            "scorers": [config],
            "attempts": 1,
            "resolved_cases": [
                c.model_dump(mode="json", exclude={"extra"}) for c in cases
            ],
            "selection": {"case_ids": [c.id for c in cases]},
            "full_dataset_hash": hash_cases(cases),
        },
        target_name="fake-target",
        pack_name="generic",
        dataset_path="PRIVATE_DATASET_PATH",
        dataset_hash=hash_cases(cases),
        cases=[
            CaseResult(
                case_id=c.id,
                tags=c.tags,
                attempts=[
                    AttemptResult(
                        index=4,
                        response=response.model_copy(deep=True),
                        verdict=Verdict.FAIL,
                        scores=[
                            Score(
                                name=scoring.name,
                                kind=ScorerKind.JUDGED,
                                value=0.1,
                                passed=False,
                                reason="SECRET_OLD_REASON",
                                extra={"judge": {"observed_model": "snapshot-v1"}},
                            ),
                            Score(
                                name="deterministic",
                                kind=ScorerKind.DETERMINISTIC,
                                value=0,
                                passed=False,
                                reason="SECRET_VERDICT",
                            ),
                        ],
                    ),
                ],
            )
            for c in cases
        ],
    )
    return source, cases, scoring


def prepare(source, cases, scoring, **changes):
    options = {
        "judge_configuration": settings(),
        "database_locator": "runs/source.sqlite",
        "case_id": "a",
        "source_attempt": 4,
        "attempts": 5,
        "source_evaluator": EvaluatorConfiguration(
            scorer_json=canonical_json(source.config_snapshot["scorers"][0]),
            judge=settings(),
        ),
    }
    options.update(changes)
    return prepare_replay(source, cases, scoring, **options)


def test_replay_has_no_target_construction_or_runner_and_preserves_exact_source(
    monkeypatch, tmp_path
):
    import harness.targets.base as targets
    from harness.core import runner
    from harness.targets import salesagent

    def bomb(*args, **kwargs):
        pytest.fail("Target/runner must not be used for replay")

    monkeypatch.setattr(runner, "run", bomb)
    monkeypatch.setattr(targets.StaticTarget, "__init__", bomb)
    monkeypatch.setattr(salesagent.SalesAgentTarget, "__init__", bomb)
    monkeypatch.setattr(salesagent.SalesAgentTarget, "invoke", bomb)
    seen_responses, prompts = [], []
    values = iter([0.8, 0.6, 0.8, 0.8, 0.6])

    def build(case, response):
        seen_responses.append(response.model_dump(mode="json"))
        return {"question": case.input, "answer": response.output}

    def judge(prompt):
        prompts.append(prompt)
        return JudgeReply(
            text=json.dumps({"score": next(values), "reason": "Observable omission."}),
            observed_model="snapshot-v1",
            input_tokens=20,
            latency_ms=3,
        )

    original, cases, scoring = fixture_run(scorer(judge, evidence_builder=build))
    path = tmp_path / "source.sqlite"
    store = SQLiteResultStore(path)
    store.save(original)
    before = path.read_bytes()
    loaded, document_hash = SQLiteResultStore(
        path, read_only=True
    ).load_with_fingerprint(original.run_id)
    saved = loaded.model_dump_json()
    prepared = prepare(loaded, cases, scoring, source_document_hash=document_hash)
    result = replay(prepared, scoring, judge_configuration=settings)
    assert seen_responses == [
        loaded.cases[0].attempts[0].response.model_dump(mode="json")
    ]
    assert len(prompts) == 5 and len(set(prompts)) == 1
    assert loaded.model_dump_json() == saved and path.read_bytes() == before
    assert result.input.source.attempt_index == 4  # Stored index, not list position.
    assert result.input.source.response_hash == fingerprint(seen_responses[0])
    assert result.input.source.document_hash == document_hash
    assert {a.prompt_hash for a in result.attempts} == {prepared.prepared.prompt_hash}
    assert {a.input_hash for a in result.attempts} == {prepared.input_hash}
    assert result.summary["scores_by_attempt"] == [0.8, 0.6, 0.8, 0.8, 0.6]
    assert result.summary["mean"] == pytest.approx(0.72)
    assert result.summary["population_stddev"] == pytest.approx(0.0979795897)
    assert result.summary["range"] == pytest.approx(0.2)
    assert result.summary["pass_count"] == 3 and result.summary["fail_count"] == 2
    assert result.summary["threshold_crossing"] is True
    assert result.summary["known_cost_usd"] is None
    assert result.summary["source_observed_model_changed"] is False
    assert (
        "SECRET" not in result.model_dump_json()
        and "PRIVATE" not in result.model_dump_json()
    )
    assert ReplayResult.model_validate_json(result.model_dump_json()) == result


def test_errors_retain_successes_and_per_call_observations():
    replies = iter(
        [
            JudgeReply(
                text='{"score":0.7,"reason":"Adequate."}',
                input_tokens=3,
                observed_model="snapshot-v1",
                cost_usd=0.01,
            ),
            RuntimeError("SECRET_PROVIDER"),
            JudgeReply(
                text="SECRET_MALFORMED", input_tokens=7, observed_model="snapshot-v2"
            ),
            '{"score":0.6,"reason":"Missing detail."}',
            '{"score":0.8,"reason":"Clear."}',
        ]
    )

    def judge(_):
        item = next(replies)
        if isinstance(item, Exception):
            raise item
        return item

    source, cases, scoring = fixture_run(scorer(judge))
    result = replay(
        prepare(source, cases, scoring), scoring, judge_configuration=settings
    )
    assert result.summary["scores_by_attempt"] == [0.7, None, None, 0.6, 0.8]
    assert (
        result.summary["error_count"] == 2
        and result.summary["completed_score_count"] == 3
    )
    assert result.summary["mean"] == pytest.approx(0.7)
    assert result.summary["pass_rate"] == pytest.approx(2 / 3)
    assert result.attempts[2].observation.input_tokens == 7
    assert result.attempts[1].observation.input_tokens is None
    assert result.attempts[3].observation.input_tokens is None
    assert all(a.duration_ms >= 0 for a in result.attempts)
    assert result.summary["observed_model_varied"]
    assert result.summary["source_observed_model_changed"]
    assert (
        result.summary["known_cost_usd"] == 0.01 and not result.summary["cost_complete"]
    )
    assert "SECRET" not in result.model_dump_json()


@pytest.mark.parametrize(
    "values,threshold,crossing,stddev",
    [
        ([], 0.7, None, None),
        ([0.8], 0.7, False, 0.0),
        ([0.8, 1.0], 0.7, False, 0.1),
        ([0.2, 0.2], 0.7, False, 0.0),
        ([0.6, 0.7], 0.7, True, 0.05),
        ([0.2, 0.8], None, None, 0.3),
    ],
)
def test_summary_edges(values, threshold, crossing, stddev):
    attempts = []
    for index, value in enumerate(values):
        passed = value >= threshold if threshold is not None else None
        attempts.append(
            ReplayAttemptResult(
                index=index,
                score=Score(
                    name="s", kind=ScorerKind.JUDGED, value=value, passed=passed
                ),
                verdict=Verdict.SKIP
                if passed is None
                else Verdict.PASS
                if passed
                else Verdict.FAIL,
                started_at=datetime.now(UTC),
                duration_ms=1,
                input_hash="input",
            )
        )
    summary = variance_summary(attempts)
    assert summary["threshold_crossing"] is crossing
    assert summary["population_stddev"] == (
        pytest.approx(stddev) if stddev is not None else None
    )
    assert summary["insufficient_repeats"] == (len(values) < 2)
    if not values:
        assert summary["error_rate"] == 0 and summary["pass_rate"] is None
        assert (
            summary["mean"]
            is summary["range"]
            is summary["min"]
            is summary["max"]
            is None
        )


@pytest.mark.parametrize(
    "reply",
    [
        "garbage",
        '{"score":true,"reason":"x"}',
        '{"score":1,"reason":"x","raw":"SECRET"}',
        '{"score":NaN,"reason":"x"}',
        '{"score":0.8}',
        '{"score":2,"reason":"x"}',
    ],
)
def test_all_malformed_scores_are_errors_not_zero(reply):
    source, cases, scoring = fixture_run(scorer(lambda _: reply))
    result = replay(
        prepare(source, cases, scoring), scoring, judge_configuration=settings
    )
    assert result.summary["scores_by_attempt"] == [None] * 5
    assert result.summary["error_count"] == 5 and result.summary["pass_rate"] is None
    assert result.summary["mean"] is result.summary["threshold_crossing"] is None
    assert "SECRET" not in result.model_dump_json()


@pytest.mark.parametrize(
    "change",
    [
        "input",
        "reference",
        "extra",
        "tags",
        "full_hash",
        "resolved",
        "selection",
        "source_tags",
        "missing_case",
        "duplicate_case",
        "duplicate_dataset",
        "duplicate_attempt",
        "missing_response",
    ],
)
def test_source_dataset_and_structure_fail_preflight(change):
    source, cases, scoring = fixture_run(scorer(lambda _: pytest.fail("judge called")))
    if change in {"input", "reference", "extra", "tags"}:
        setattr(
            cases[0],
            change,
            {"changed": True}
            if change in {"reference", "extra"}
            else ["changed"]
            if change == "tags"
            else "changed",
        )
    elif change == "full_hash":
        source.config_snapshot["full_dataset_hash"] = "changed"
    elif change == "resolved":
        source.config_snapshot["resolved_cases"][0]["input"] = "changed"
    elif change == "selection":
        source.config_snapshot["selection"]["case_ids"].reverse()
    elif change == "source_tags":
        source.cases[0].tags = ["changed"]
    elif change == "missing_case":
        source.cases[0].case_id = "missing"
    elif change == "duplicate_case":
        source.cases.append(source.cases[0])
    elif change == "duplicate_dataset":
        cases.append(cases[0])
    elif change == "duplicate_attempt":
        source.cases[0].attempts.append(source.cases[0].attempts[0])
    elif change == "missing_response":
        source.cases[0].attempts[0].response = None
    with pytest.raises(ValueError):
        prepare(source, cases, scoring, allow_reconfigured=True)


@pytest.mark.parametrize(
    "options",
    [
        {"attempts": 0},
        {"attempts": -1},
        {"attempts": True},
        {"attempts": 1.5},
        {"source_attempt": -1},
        {"source_attempt": True},
        {"source_attempt": 0},
        {"case_id": "missing"},
    ],
)
def test_invalid_selection(options):
    with pytest.raises(ValueError):
        prepare(*fixture_run(), **options)


@pytest.mark.parametrize(
    "field,value",
    [
        ("pass_threshold", 0.9),
        ("rubric", "Changed"),
        ("projection_version", "v2"),
        ("prompt_version", "v2"),
        ("judgment_version", "v2"),
    ],
)
def test_configuration_changes_are_explicit(field, value):
    source, cases, scoring = fixture_run()
    setattr(scoring, field, value)
    with pytest.raises(ValueError, match="incompatible"):
        prepare(source, cases, scoring)
    prepared = prepare(source, cases, scoring, allow_reconfigured=True)
    assert prepared.compatibility == "different"
    assert f"scorer.{field}" in prepared.differences


def test_unknown_configuration_and_required_evidence():
    source, cases, scoring = fixture_run()
    with pytest.raises(ValueError, match="incompatible"):
        prepare(source, cases, scoring, source_evaluator=None)
    assert (
        prepare(
            source, cases, scoring, source_evaluator=None, allow_reconfigured=True
        ).compatibility
        == "unknown"
    )
    scoring.requires = frozenset({"missing"})
    with pytest.raises(ValueError, match="cannot be prepared"):
        prepare(source, cases, scoring, allow_reconfigured=True)
    scoring.requires = frozenset()
    scoring.projection_reviewed = False
    with pytest.raises(ValueError, match="reviewed"):
        prepare(source, cases, scoring)


def test_builder_mutation_is_rejected_without_mutating_source():
    def mutate(case, response):
        response.output = "changed"
        return {"answer": response.output}

    source, cases, scoring = fixture_run(scorer(evidence_builder=mutate))
    before = source.model_dump_json()
    with pytest.raises(ValueError, match="mutated"):
        prepare(source, cases, scoring)
    assert source.model_dump_json() == before


def test_configuration_drift_between_attempts_blocks_changed_calls():
    calls = []

    def judge(prompt):
        calls.append(prompt)
        scoring.rubric = "Changed after first call"
        return '{"score":0.8,"reason":"Clear."}'

    source, cases, scoring = fixture_run(scorer(judge))
    result = replay(
        prepare(source, cases, scoring), scoring, judge_configuration=settings
    )
    assert len(calls) == 1 and result.summary["error_count"] == 4
    assert all(a.error == "input_integrity_error" for a in result.attempts[1:])
    assert all(a.prompt_hash is None for a in result.attempts[1:])


def test_actual_adapter_settings_are_checked_before_calls():
    source, cases, scoring = fixture_run(scorer(lambda _: pytest.fail("judge called")))
    with pytest.raises(ValueError, match="Execution configuration"):
        replay(
            prepare(source, cases, scoring),
            scoring,
            judge_configuration=lambda: settings(max_output_tokens=1),
        )


def test_fingerprints_preserve_order_and_exact_values():
    assert fingerprint({"b": 1, "a": "é"}) == fingerprint({"a": "é", "b": 1})
    variants = [None, [], {}, "", "é", "e\u0301", "é ", "1.00", 1.0, [1, 2], [2, 1]]
    assert len({fingerprint(v) for v in variants}) == len(variants)
    for invalid in (float("nan"), float("inf"), object()):
        with pytest.raises((ValueError, TypeError)):
            fingerprint(invalid)
    source, cases, scoring = fixture_run()
    initial = prepare(source, cases, scoring)
    source.cases[0].attempts[0].response.output += "!"
    changed = prepare(source, cases, scoring)
    assert initial.input_hash != changed.input_hash
    assert initial.source.response_hash != changed.source.response_hash


def test_read_only_source_and_separate_replay_persistence(tmp_path):
    source, cases, scoring = fixture_run()
    src = tmp_path / "source.sqlite"
    writable = SQLiteResultStore(src)
    writable.save(source)
    before = src.read_bytes()
    readonly = SQLiteResultStore(src, read_only=True)
    result = replay(
        prepare(readonly.load("source"), cases, scoring),
        scoring,
        judge_configuration=settings,
    )
    assert readonly.list_replays() == []
    with pytest.raises(KeyError):
        readonly.load_replay("missing")
    with pytest.raises(KeyError):
        readonly.load("missing")
    with pytest.raises(ValueError, match="read-only"):
        readonly.save(source)
    with pytest.raises(ValueError, match="read-only"):
        readonly.save_replay(result)
    with pytest.raises(sqlite3.OperationalError), readonly._connect() as connection:
        connection.execute("DELETE FROM runs")
    assert src.read_bytes() == before
    missing = tmp_path / "new_directory" / "missing.sqlite"
    with pytest.raises(sqlite3.OperationalError):
        SQLiteResultStore(missing, read_only=True)
    assert not missing.parent.exists()
    destination = SQLiteResultStore(tmp_path / "replay.sqlite")
    destination.save_replay(result)
    loaded = destination.load_replay(result.replay_id)
    assert loaded == result and loaded.summary == result.summary
    with pytest.raises(ValueError, match="already stored"):
        destination.save_replay(result)
    assert destination.load_replay(result.replay_id) == result
    assert destination.list_runs() == []
    listing = destination.list_replays()
    assert listing[0]["source_attempt_index"] == 4 and "prompt" not in json.dumps(
        listing
    )
    assert src.read_bytes() == before


@pytest.mark.parametrize(
    "change",
    ["input_hash", "prompt", "attempt_count", "score", "verdict", "observation"],
)
def test_reload_rejects_inconsistent_artifacts(change):
    source, cases, scoring = fixture_run()
    result = replay(
        prepare(source, cases, scoring), scoring, judge_configuration=settings
    )
    data = result.model_dump(mode="json")
    if change == "input_hash":
        data["input"]["input_hash"] = "changed"
    elif change == "prompt":
        data["input"]["prepared"]["prompt"] = "changed"
    elif change == "attempt_count":
        data["attempts"].pop()
    elif change == "score":
        data["attempts"][0]["score"]["value"] = 0.1
    elif change == "verdict":
        data["attempts"][0]["verdict"] = "error"
    elif change == "observation":
        data["attempts"][0]["observation"]["input_tokens"] = 5
    with pytest.raises(ValueError):
        ReplayResult.model_validate(data)


@pytest.mark.parametrize(
    "locator",
    [
        "/Users/private/source.sqlite",
        "../source.sqlite",
        "C:\\private\\source.sqlite",
        "file:///tmp/source",
        "https://host/source",
    ],
)
def test_provenance_rejects_absolute_or_unsafe_locators(locator):
    with pytest.raises(ValueError):
        SourceProvenance.safe_locator(locator)


def test_locator_uses_relative_or_logical_name(tmp_path):
    assert (
        source_locator(tmp_path / "runs" / "source.sqlite", tmp_path)
        == "runs/source.sqlite"
    )
    assert (
        source_locator(tmp_path.parent / "private-name.sqlite", tmp_path)
        == "external-source"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"api_key": "SECRET"},
        {"previous_response_id": "SECRET"},
        {"tools": ["search"]},
        {"endpoint": "https://user:SECRET@host"},
        {"endpoint": "https://host/?token=SECRET"},
        {"retries": 2},
        {"store": True},
        {"max_output_tokens": True},
    ],
)
def test_judge_settings_reject_unsafe_or_stateful_configuration(changes):
    with pytest.raises(ValueError):
        settings(**changes)


def test_generic_non_rubric_informational_replay():
    from harness.scorers.base import JudgedScorer

    class Informational(JudgedScorer):
        name = "generic-observation"
        pass_threshold = None
        projection_reviewed = True
        projection_version = "answer-only-v1"
        prompt_version = "plain-v1"
        judgment_version = "float-v1"
        rubric_version = "not-applicable-v1"

        def build_prompt(self, case, response):
            return response.output

        def parse_judgement(self, raw):
            return float(raw), "Observed quality."

    prompts = []
    scoring = Informational(lambda prompt: prompts.append(prompt) or "0.8", "fake-v1")
    source, cases, _ = fixture_run(scoring)
    result = replay(
        prepare(source, cases, scoring, attempts=2),
        scoring,
        judge_configuration=settings,
    )
    assert prompts == ["Saved answer", "Saved answer"]
    assert (
        result.summary["skip_count"] == 2
        and result.summary["completed_score_count"] == 2
    )
    assert result.summary["pass_rate"] is result.summary["threshold_crossing"] is None
    assert result.input.prepared.evidence_hash is None


@pytest.mark.parametrize(
    "key",
    [
        "raw",
        "metadata",
        "hidden_prompt",
        "system_prompt",
        "authorization",
        "api_key",
        "assertions",
        "verdict",
        "passed",
        "provider_response",
    ],
)
def test_unsafe_projected_fields_rejected_before_calls(key):
    source, cases, scoring = fixture_run(
        scorer(
            lambda _: pytest.fail("judge called"),
            evidence_builder=lambda case, response: {"nested": [{key: "SECRET"}]},
        )
    )
    with pytest.raises(ValueError, match="cannot be prepared") as caught:
        prepare(source, cases, scoring)
    assert "SECRET" not in str(caught.value)


def test_actual_adapter_configuration_drift_stops_further_requests():
    calls, configs = [], [settings()]

    def judge(prompt):
        calls.append(prompt)
        configs[0] = settings(max_output_tokens=1)
        return '{"score":0.8,"reason":"Clear."}'

    source, cases, scoring = fixture_run(scorer(judge))
    result = replay(
        prepare(source, cases, scoring), scoring, judge_configuration=lambda: configs[0]
    )
    assert len(calls) == 1
    assert result.summary["error_count"] == 4
    assert all(a.error == "input_integrity_error" for a in result.attempts[1:])


def test_compatibility_metadata_is_checked_on_reload():
    source, cases, scoring = fixture_run()
    result = replay(
        prepare(source, cases, scoring), scoring, judge_configuration=settings
    )
    data = result.model_dump(mode="json")
    data["input"]["compatibility"] = "different"
    with pytest.raises(ValueError, match="compatibility"):
        ReplayResult.model_validate(data)


@pytest.mark.parametrize(
    "change", ["requirements", "blank_reason", "name", "kind", "raw_extra"]
)
def test_bad_scorer_results_are_errors(change):
    source, cases, scoring = fixture_run()
    prepared = prepare(source, cases, scoring, attempts=1)
    original = scoring.score_prepared

    def bad(prepared, *, on_call):
        score = original(prepared, on_call=on_call)
        if change == "requirements":
            score.passed = False
        elif change == "blank_reason":
            score.reason = " "
        elif change == "name":
            score.name = "other"
        elif change == "kind":
            score.kind = ScorerKind.DETERMINISTIC
        else:
            score.extra["raw"] = "SECRET"
        return score

    scoring.score_prepared = bad
    result = replay(prepared, scoring, judge_configuration=settings)
    assert (
        result.attempts[0].verdict == Verdict.ERROR and result.attempts[0].score is None
    )
    assert "SECRET" not in result.model_dump_json()
