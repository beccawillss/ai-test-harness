"""Runner tests.

The first two classes are the ones that matter: they pin ADR 0001 in both
directions. Infrastructure failures must never look like quality failures,
and quality failures must never look like infrastructure failures. If
those ever go green-but-wrong, every gate built on this harness is lying.
"""

from __future__ import annotations

import logging

import pytest
from conftest import ClosingTarget, ExplodingTarget, StubScorer

from harness.core.config import RunConfig, RunMode
from harness.core.errors import ConfigError, IncompatibleTargetError
from harness.core.models import ScorerKind, TargetResponse, TestCase, Verdict
from harness.core.runner import WARN_NO_GATED_SCORES, run, validate_run
from harness.packs.base import SimplePack
from harness.scorers.base import MissingFieldError
from harness.targets.base import CAP_CONTEXTS, CAP_TRAJECTORY, StaticTarget


def _pack(*scorers, name: str = "demo") -> SimplePack:
    return SimplePack(name=name, scorers=list(scorers))


# ---------------------------------------------------------------------------
# ADR 0001: infrastructure failures are never quality failures
# ---------------------------------------------------------------------------


class TestErrorsAreNotFailures:
    def test_all_attempts_errored_reports_no_pass_rate(self, cases):
        """The sharpest form of the invariant: a dead target is not a 0% run.

        If pass_rate were 0.0 here, a broken adapter would be indistinguishable
        from a product that failed every single case, and a CI gate would
        block a release over an infrastructure problem.
        """
        target = ExplodingTarget()
        result = run(
            RunConfig(attempts=2),
            target=target,
            pack=_pack(StubScorer()),
            cases=cases,
        )

        assert result.aggregate_pass_rate is None
        assert result.error_rate == 1.0
        for case_result in result.cases:
            assert case_result.pass_rate is None
            assert case_result.had_errors is True
            for attempt in case_result.attempts:
                assert attempt.verdict is Verdict.ERROR
                assert attempt.response is None
                assert "ConnectionError: connection refused" in attempt.error

    def test_target_error_names_the_target(self, cases, responses):
        # StaticTarget raises LookupError for a case it has no response for.
        target = StaticTarget({"c1": responses["c1"]})
        result = run(RunConfig(), target, _pack(StubScorer()), cases)

        ok, missing = result.cases
        assert ok.attempts[0].verdict is Verdict.PASS
        assert missing.attempts[0].verdict is Verdict.ERROR
        assert missing.attempts[0].error.startswith("target 'static': LookupError:")
        # One case still errored, so the run is not clean...
        assert result.error_rate == 0.5
        # ...but the case that *was* judged still reports its real rate.
        assert ok.pass_rate == 1.0
        assert result.aggregate_pass_rate == 1.0

    def test_scorer_error_errors_the_attempt_but_keeps_partial_scores(
        self, cases, responses
    ):
        good = StubScorer(name="good")
        broken = StubScorer(
            name="broken",
            behaviour=_raise(RuntimeError("judge API 503")),
        )
        after = StubScorer(name="after")

        result = run(
            RunConfig(),
            StaticTarget(responses),
            _pack(good, broken, after),
            cases,
        )

        attempt = result.cases[0].attempts[0]
        assert attempt.verdict is Verdict.ERROR
        assert "scorer 'broken': RuntimeError: judge API 503" in attempt.error
        # Partial scores survive for debugging...
        assert [s.name for s in attempt.scores] == ["good", "after"]
        # ...and every scorer ran, so one run surfaces every broken scorer.
        assert after.calls == ["c1", "c2"]
        assert result.aggregate_pass_rate is None
        assert result.error_rate == 1.0

    def test_missing_field_error_is_flagged_as_an_adapter_pack_mismatch(
        self, cases, responses
    ):
        scorer = StubScorer(
            name="faithfulness",
            behaviour=_raise(MissingFieldError("faithfulness", "contexts")),
        )
        result = run(RunConfig(), StaticTarget(responses), _pack(scorer), cases)

        error = result.cases[0].attempts[0].error
        assert "adapter/pack mismatch" in error
        assert "should have been caught at config validation" in error

    def test_keyboard_interrupt_is_not_swallowed(self, cases, responses):
        """Only Exception is caught. An abort must abort, not log 500 errors."""
        scorer = StubScorer(behaviour=_raise(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):
            run(RunConfig(), StaticTarget(responses), _pack(scorer), cases)


class TestQualityFailuresAreNotErrors:
    def test_low_score_is_a_fail_and_counts_toward_the_pass_rate(
        self, cases, responses
    ):
        """The other half of ADR 0001: a bad answer is a FAIL, not an ERROR."""
        scorer = StubScorer(
            name="accuracy",
            behaviour=lambda case, response: 0.1 if case.id == "c1" else 0.9,
        )
        result = run(RunConfig(), StaticTarget(responses), _pack(scorer), cases)

        failed, passed = result.cases
        assert failed.attempts[0].verdict is Verdict.FAIL
        assert failed.attempts[0].error is None
        assert failed.had_errors is False
        assert failed.pass_rate == 0.0  # real evidence, all of it bad
        assert passed.pass_rate == 1.0
        assert result.aggregate_pass_rate == 0.5
        assert result.error_rate == 0.0

    def test_one_failing_gated_score_fails_the_attempt(self, cases, responses):
        result = run(
            RunConfig(),
            StaticTarget(responses),
            _pack(
                StubScorer(name="a", behaviour=lambda c, r: 1.0),
                StubScorer(name="b", behaviour=lambda c, r: 0.0),
                StubScorer(name="c", behaviour=lambda c, r: 1.0),
            ),
            cases,
        )
        assert result.cases[0].attempts[0].verdict is Verdict.FAIL

    def test_informational_scores_never_decide_a_verdict(self, cases, responses):
        result = run(
            RunConfig(),
            StaticTarget(responses),
            _pack(
                StubScorer(name="gated", behaviour=lambda c, r: 1.0),
                # value 0.0 but ungated: must not drag the verdict to FAIL
                StubScorer(name="info", gates=False, behaviour=lambda c, r: 0.0),
            ),
            cases,
        )
        assert result.cases[0].attempts[0].verdict is Verdict.PASS


# ---------------------------------------------------------------------------
# Validation happens before anything executes
# ---------------------------------------------------------------------------


class TestValidation:
    def test_incompatible_target_raises_before_any_case_runs(self, cases, responses):
        target = StaticTarget(responses)  # declares no capabilities
        pack = _pack(
            StubScorer(name="context_recall", requires=frozenset({CAP_CONTEXTS})),
            StubScorer(name="tool_choice", requires=frozenset({CAP_TRAJECTORY})),
            name="rag",
        )

        with pytest.raises(IncompatibleTargetError) as excinfo:
            run(RunConfig(), target, pack, cases)

        # The money assertion: nothing was invoked.
        assert target.calls == []
        message = str(excinfo.value)
        assert "contexts" in message and "trajectory" in message
        assert "context_recall" in message and "tool_choice" in message
        assert excinfo.value.missing == ["contexts", "trajectory"]

    def test_compatible_target_passes_validation(self, cases, responses):
        target = StaticTarget(responses, capabilities=frozenset({CAP_CONTEXTS}))
        pack = _pack(StubScorer(requires=frozenset({CAP_CONTEXTS})))
        assert validate_run(RunConfig(), target, pack, cases) == []

    def test_duplicate_case_ids_are_rejected(self, responses):
        duplicated = [
            TestCase(id="c1", input="a"),
            TestCase(id="c1", input="b"),
        ]
        with pytest.raises(ConfigError, match="Duplicate case ids"):
            run(RunConfig(), StaticTarget(responses), _pack(StubScorer()), duplicated)

    def test_duplicate_scorer_names_are_rejected(self, cases, responses):
        pack = _pack(StubScorer(name="same"), StubScorer(name="same"))
        with pytest.raises(ConfigError, match="duplicate scorer names"):
            run(RunConfig(), StaticTarget(responses), pack, cases)

    def test_empty_case_list_is_rejected(self, responses):
        with pytest.raises(ConfigError, match="No cases to execute"):
            run(RunConfig(), StaticTarget(responses), _pack(StubScorer()), [])

    def test_filters_removing_every_case_is_rejected(self, cases, responses):
        config = RunConfig(include_tags=["nonexistent"])
        with pytest.raises(ConfigError, match="No cases to execute"):
            run(config, StaticTarget(responses), _pack(StubScorer()), cases)

    def test_score_mode_without_a_pack_is_rejected(self, cases, responses):
        with pytest.raises(ConfigError, match="pack is required in score mode"):
            run(RunConfig(), StaticTarget(responses), None, cases)

    def test_kind_filter_leaving_no_scorers_is_rejected(self, cases, responses):
        pack = _pack(StubScorer(kind=ScorerKind.JUDGED))
        config = RunConfig(scorer_kinds=frozenset({ScorerKind.DETERMINISTIC}))
        with pytest.raises(ConfigError, match="contributes no scorers"):
            run(config, StaticTarget(responses), pack, cases)

    def test_concurrency_above_one_is_not_implemented_yet(self, cases, responses):
        with pytest.raises(NotImplementedError, match="Parallel execution"):
            run(
                RunConfig(concurrency=2),
                StaticTarget(responses),
                _pack(StubScorer()),
                cases,
            )


# ---------------------------------------------------------------------------
# Execution mechanics
# ---------------------------------------------------------------------------


class TestExecution:
    def test_every_case_runs_every_attempt(self, cases, responses):
        target = StaticTarget(responses)
        scorer = StubScorer()
        result = run(RunConfig(attempts=3), target, _pack(scorer), cases)

        assert target.calls == ["c1"] * 3 + ["c2"] * 3
        assert scorer.calls == ["c1"] * 3 + ["c2"] * 3
        assert [c.case_id for c in result.cases] == ["c1", "c2"]
        assert [a.index for a in result.cases[0].attempts] == [0, 1, 2]

    def test_pass_rate_reflects_flaky_attempts(self, cases, responses):
        calls: dict[str, int] = {}

        def flaky(case: TestCase, response: TargetResponse) -> float:
            calls[case.id] = calls.get(case.id, 0) + 1
            return 1.0 if calls[case.id] == 1 else 0.0

        result = run(
            RunConfig(attempts=4),
            StaticTarget(responses),
            _pack(StubScorer(behaviour=flaky)),
            cases,
        )
        # One pass in four attempts — the flakiness the attempts exist to measure.
        assert result.cases[0].pass_rate == 0.25
        assert result.aggregate_pass_rate == 0.25

    def test_case_tags_and_timings_are_recorded(self, cases, responses):
        result = run(RunConfig(), StaticTarget(responses), _pack(StubScorer()), cases)
        assert result.cases[0].tags == ["smoke", "math"]
        assert result.cases[0].attempts[0].duration_ms >= 0.0

    def test_closeable_target_is_closed_once(self, cases):
        target = ClosingTarget()
        run(RunConfig(attempts=2), target, _pack(StubScorer()), cases)
        assert target.closed == 1

    def test_target_is_closed_even_when_every_attempt_errors(self, cases):
        target = ClosingTarget()
        target.invoke = _raise_invoke(RuntimeError("down"))
        run(RunConfig(), target, _pack(StubScorer()), cases)
        assert target.closed == 1

    def test_failing_close_is_recorded_not_raised(self, cases):
        target = ClosingTarget(fail_on_close=True)
        result = run(RunConfig(), target, _pack(StubScorer()), cases)
        # The run's results are worth more than a tidy teardown.
        assert result.aggregate_pass_rate == 1.0
        assert any(
            "target_close_failed" in w for w in result.config_snapshot["warnings"]
        )


class TestFiltering:
    def test_include_tags_selects_matching_cases(self, cases, responses):
        result = run(
            RunConfig(include_tags=["geo"]),
            StaticTarget(responses),
            _pack(StubScorer()),
            cases,
        )
        assert [c.case_id for c in result.cases] == ["c2"]

    def test_exclude_tags_wins_over_include_tags(self, cases, responses):
        result = run(
            RunConfig(include_tags=["smoke", "geo"], exclude_tags=["math"]),
            StaticTarget(responses),
            _pack(StubScorer()),
            cases,
        )
        assert [c.case_id for c in result.cases] == ["c2"]

    def test_max_cases_truncates(self, cases, responses):
        result = run(
            RunConfig(max_cases=1),
            StaticTarget(responses),
            _pack(StubScorer()),
            cases,
        )
        assert [c.case_id for c in result.cases] == ["c1"]

    def test_kind_filter_skips_judged_scorers(self, cases, responses):
        deterministic = StubScorer(name="det", kind=ScorerKind.DETERMINISTIC)
        judged = StubScorer(name="judge", kind=ScorerKind.JUDGED)
        result = run(
            RunConfig(scorer_kinds=frozenset({ScorerKind.DETERMINISTIC})),
            StaticTarget(responses),
            _pack(deterministic, judged),
            cases,
        )
        assert judged.calls == []
        assert deterministic.calls == ["c1", "c2"]
        assert [s["name"] for s in result.config_snapshot["scorers"]] == ["det"]


# ---------------------------------------------------------------------------
# Explore mode
# ---------------------------------------------------------------------------


class TestExploreMode:
    def test_explore_captures_traces_without_scoring(self, cases, responses):
        scorer = StubScorer()
        result = run(
            RunConfig(mode=RunMode.EXPLORE),
            StaticTarget(responses),
            _pack(scorer),
            cases,
        )

        assert scorer.calls == []
        for case_result in result.cases:
            for attempt in case_result.attempts:
                assert attempt.verdict is Verdict.SKIP
                assert attempt.scores == []
                assert attempt.response is not None
        # The traces are the point of the mode.
        first = result.cases[0].attempts[0].response
        assert first.contexts == ["arithmetic basics"]
        assert first.trajectory[0].name == "calculator"

    def test_explore_reports_no_pass_rate_rather_than_zero(self, cases, responses):
        result = run(
            RunConfig(mode=RunMode.EXPLORE), StaticTarget(responses), None, cases
        )
        assert result.cases[0].pass_rate is None
        assert result.aggregate_pass_rate is None
        assert result.error_rate == 0.0

    def test_explore_runs_against_an_incompatible_target(
        self, cases, responses, caplog
    ):
        """Checking whether an adapter populates a field is a reason to explore."""
        target = StaticTarget(responses)  # declares no capabilities
        pack = _pack(StubScorer(requires=frozenset({CAP_CONTEXTS})), name="rag")

        with caplog.at_level(logging.WARNING):
            result = run(RunConfig(mode=RunMode.EXPLORE), target, pack, cases)

        assert target.calls == ["c1", "c2"]
        assert "missing_capabilities" in result.config_snapshot["warnings"]
        assert "does not declare contexts" in caplog.text

    def test_explore_without_a_pack_records_no_pack(self, cases, responses):
        result = run(
            RunConfig(mode=RunMode.EXPLORE), StaticTarget(responses), None, cases
        )
        assert result.pack_name == "none"
        assert result.config_snapshot["pack"] is None

    def test_target_errors_still_error_in_explore_mode(self, cases):
        result = run(RunConfig(mode=RunMode.EXPLORE), ExplodingTarget(), None, cases)
        assert result.cases[0].attempts[0].verdict is Verdict.ERROR
        assert result.error_rate == 1.0

    # Snapshotting an unvalidated config warns; that is the point of the test.
    @pytest.mark.filterwarnings("ignore:Pydantic serializer warnings:UserWarning")
    def test_a_raw_string_mode_still_explores(self, cases, responses):
        """model_copy(update=...) skips validation and leaves mode a plain str.

        RunMode is a StrEnum, so an identity check would miss it and
        silently *score* a run somebody asked only to explore — paying for
        judges they never requested.
        """
        config = RunConfig().model_copy(update={"mode": "explore"})
        scorer = StubScorer()

        result = run(config, StaticTarget(responses), _pack(scorer), cases)

        assert scorer.calls == []
        assert result.cases[0].attempts[0].verdict is Verdict.SKIP


# ---------------------------------------------------------------------------
# A pack that gates on nothing is a run with no signal
# ---------------------------------------------------------------------------


class TestGatingWarning:
    def test_informational_only_pack_warns_on_the_first_attempt(
        self, cases, responses, caplog
    ):
        pack = _pack(
            StubScorer(name="a", gates=False),
            StubScorer(name="b", gates=False),
            name="informational",
        )
        with caplog.at_level(logging.WARNING):
            result = run(RunConfig(attempts=2), StaticTarget(responses), pack, cases)

        assert WARN_NO_GATED_SCORES in result.config_snapshot["warnings"]
        assert "no gating signal" in caplog.text
        # Warned once, not once per attempt.
        assert result.config_snapshot["warnings"].count(WARN_NO_GATED_SCORES) == 1
        # The scores are still recorded; they just can't decide anything.
        assert result.cases[0].attempts[0].verdict is Verdict.SKIP
        assert result.cases[0].pass_rate is None

    def test_gated_pack_produces_no_warning(self, cases, responses):
        result = run(RunConfig(), StaticTarget(responses), _pack(StubScorer()), cases)
        assert WARN_NO_GATED_SCORES not in result.config_snapshot["warnings"]

    def test_all_scorers_erroring_does_not_trigger_the_gating_warning(
        self, cases, responses
    ):
        """No scores at all is an error problem, not a gating problem."""
        pack = _pack(StubScorer(behaviour=_raise(RuntimeError("boom"))))
        result = run(RunConfig(), StaticTarget(responses), pack, cases)
        assert WARN_NO_GATED_SCORES not in result.config_snapshot["warnings"]


# ---------------------------------------------------------------------------
# The result must explain itself months later
# ---------------------------------------------------------------------------


class TestResultAssembly:
    def test_snapshot_records_the_resolved_run(self, cases, responses):
        target = StaticTarget(
            responses, name="cap-rag@v3", capabilities=frozenset({CAP_CONTEXTS})
        )
        scorer = StubScorer(name="faithfulness", requires=frozenset({CAP_CONTEXTS}))
        config = RunConfig(
            config_path="evals/rag.yaml",
            dataset_path="data/rag.jsonl",
            attempts=2,
            model_versions={"target": "claude-opus-5"},
        )

        result = run(config, target, _pack(scorer, name="rag"), cases)

        assert result.target_name == "cap-rag@v3"
        assert result.pack_name == "rag"
        assert result.config_path == "evals/rag.yaml"
        assert result.dataset_path == "data/rag.jsonl"
        snapshot = result.config_snapshot
        assert snapshot["target"] == "cap-rag@v3"
        assert snapshot["target_capabilities"] == ["contexts"]
        assert snapshot["attempts"] == 2
        assert snapshot["mode"] == "score"
        assert snapshot["scorers"] == [
            {
                "name": "faithfulness",
                "kind": "deterministic",
                "pass_threshold": 0.5,
                "requires": ["contexts"],
            }
        ]

    def test_judge_models_are_recorded_alongside_target_models(self, cases, responses):
        judged = StubScorer(name="faithfulness", kind=ScorerKind.JUDGED)
        judged.judge_model = "claude-opus-5"  # what JudgedScorer exposes

        result = run(
            RunConfig(model_versions={"target": "cap-rag@v3"}),
            StaticTarget(responses),
            _pack(judged),
            cases,
        )
        assert result.model_versions == {
            "target": "cap-rag@v3",
            "judge:faithfulness": "claude-opus-5",
        }

    def test_dataset_hash_covers_the_cases_actually_executed(self, cases, responses):
        full = run(RunConfig(), StaticTarget(responses), _pack(StubScorer()), cases)
        filtered = run(
            RunConfig(max_cases=1), StaticTarget(responses), _pack(StubScorer()), cases
        )
        assert full.dataset_hash != filtered.dataset_hash

    def test_timestamps_and_cost_are_populated(self, cases, responses):
        result = run(RunConfig(), StaticTarget(responses), _pack(StubScorer()), cases)
        assert result.finished_at is not None
        assert result.finished_at >= result.started_at
        assert result.total_cost_usd == pytest.approx(0.03)

    def test_result_round_trips_through_json(self, cases, responses):
        from harness.core.models import RunResult

        result = run(
            RunConfig(attempts=2), StaticTarget(responses), _pack(StubScorer()), cases
        )
        restored = RunResult.model_validate_json(result.model_dump_json())
        assert restored.model_dump() == result.model_dump()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _raise(exc: BaseException):
    def behaviour(case: TestCase, response: TargetResponse) -> float:
        raise exc

    return behaviour


def _raise_invoke(exc: BaseException):
    def invoke(case: TestCase) -> TargetResponse:
        raise exc

    return invoke
