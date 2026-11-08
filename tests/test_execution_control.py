"""Observable opt-in lifecycle behavior; default execution stays exhaustive."""

import pytest
from test_runner import CloseableStaticTarget, RecordingStaticTarget, StubScorer, _case

from harness.core.execution_control import ExecutionControlError
from harness.core.models import TargetResponse, Verdict
from harness.core.runner import run


class Control:
    def __init__(self, fault=None):
        self.events = []
        self.fault = fault

    def event(self, name, *values):
        self.events.append((name, *values))
        if self.fault == name:
            raise ExecutionControlError(f"journal {name}")

    def prepared(self, result, cases):
        assert result.finished_at is None and not result.cases
        self.event("prepared", result.dataset_hash)

    def reserve(self, case_id, index):
        self.event("reserve", case_id, index)

    def response_received(self, case_id, index, response):
        self.event("response", response.output)

    def scorer_recorded(self, case_id, index, name, score, error):
        self.event("score", name, score, error)

    def attempt_completed(self, case_id, attempt):
        self.event("attempt", case_id, attempt)
        return attempt.verdict is not Verdict.ERROR

    def run_assembled(self, result):
        self.event("assembled", result)


def target():
    return RecordingStaticTarget({c: TargetResponse(output="4") for c in ("a", "b")})


def test_response_precedes_scorers_fail_continues_and_error_stops_dispatch():
    first, second = StubScorer("good", passed=False), StubScorer("broken")
    t = target()
    control = Control()
    original = second.score

    def score(case, response):
        assert control.events[-1][0] == "score"
        if case.id == "b":
            raise ValueError("scoring unavailable")
        return original(case, response)

    second.score = score
    result = run(
        t,
        [first, second],
        [_case("a"), _case("b")],
        attempts=2,
        execution_control=control,
    )
    assert t.calls == ["a", "a", "b"]
    assert [a.verdict for c in result.cases for a in c.attempts] == [
        Verdict.FAIL,
        Verdict.FAIL,
        Verdict.ERROR,
    ]
    assert [s.name for s in result.cases[-1].attempts[0].scores] == ["good"]
    assert [e[0] for e in control.events] == ["prepared"] + [
        "reserve",
        "response",
        "score",
        "score",
        "attempt",
    ] * 3 + ["assembled"]
    assert control.events[-3][2] is None
    assert "scoring unavailable" in control.events[-3][3]


def test_target_error_stops_without_fabricating_response_or_scorer_events():
    t = target()
    control = Control()
    result = run(
        t,
        [StubScorer("good")],
        [_case("missing"), _case("a")],
        attempts=2,
        execution_control=control,
    )
    assert t.calls == ["missing"]
    assert result.cases[0].attempts[0].verdict is Verdict.ERROR
    assert [e[0] for e in control.events] == [
        "prepared",
        "reserve",
        "attempt",
        "assembled",
    ]


@pytest.mark.parametrize(
    "boundary", ["prepared", "reserve", "response", "score", "attempt", "assembled"]
)
def test_callback_failure_propagates_and_prevents_later_dispatch(boundary):
    t = target()
    control = Control(boundary)
    scorer = StubScorer("good")
    with pytest.raises(ExecutionControlError, match=boundary):
        run(t, [scorer], [_case("a"), _case("b")], execution_control=control)
    assert len(t.calls) == (
        0
        if boundary in {"prepared", "reserve"}
        else 2
        if boundary == "assembled"
        else 1
    )
    if boundary == "response":
        assert scorer.calls == []


def test_validation_precedes_control_and_dispatch():
    control = Control()
    with pytest.raises(ValueError, match="Duplicate"):
        run(
            target(),
            [StubScorer("good")],
            [_case("a"), _case("a")],
            execution_control=control,
        )
    assert control.events == []


def test_control_failure_escapes_target_and_scorer_catches():
    for source in ("target", "scorer"):
        t = target()
        scorer = StubScorer("broken", error=ExecutionControlError("durable failure"))
        if source == "target":

            def invoke(case):
                raise ExecutionControlError("durable failure")

            t.invoke = invoke
        with pytest.raises(ExecutionControlError, match="durable failure"):
            run(t, [scorer], [_case("a"), _case("b")], execution_control=Control())


def test_cleanup_failure_preserves_primary_control_failure():
    t = CloseableStaticTarget({"a": TargetResponse(output="4")})

    def close():
        raise RuntimeError("cleanup")

    t.close = close
    with pytest.raises(ExecutionControlError, match="journal response") as caught:
        run(
            t, [StubScorer("good")], [_case("a")], execution_control=Control("response")
        )
    assert caught.value.__notes__ == ["Target cleanup also failed: RuntimeError"]


def test_cleanup_failure_without_primary_failure_prevents_assembled_callback():
    t = CloseableStaticTarget({"a": TargetResponse(output="4")})
    control = Control()

    def close():
        raise RuntimeError("cleanup")

    t.close = close
    with pytest.raises(RuntimeError, match="cleanup"):
        run(t, [StubScorer("good")], [_case("a")], execution_control=control)
    assert control.events[-1][0] == "attempt"


def test_default_still_dispatches_after_error():
    t = target()
    result = run(
        t,
        [StubScorer("broken", error=ValueError("offline"))],
        [_case("a"), _case("b")],
        attempts=2,
    )
    assert t.calls == ["a", "a", "b", "b"]
    assert all(a.verdict is Verdict.ERROR for c in result.cases for a in c.attempts)
    assert "capture_identity" not in result.config_snapshot


def test_default_retains_ordinary_error_handling_for_control_exception_type():
    t = target()
    result = run(
        t,
        [StubScorer("broken", error=ExecutionControlError("no control"))],
        [_case("a"), _case("b")],
    )
    assert len(result.cases) == 2
    assert all(c.attempts[0].verdict is Verdict.ERROR for c in result.cases)


def test_cleanup_failure_does_not_mask_already_recorded_target_error():
    t = CloseableStaticTarget({})

    def close():
        raise RuntimeError("cleanup")

    t.close = close
    control = Control()
    result = run(t, [StubScorer("good")], [_case("missing")], execution_control=control)
    assert result.cases[0].attempts[0].verdict is Verdict.ERROR
    assert "target" in result.cases[0].attempts[0].error
    assert result.config_snapshot["execution_cleanup_error"] == "RuntimeError"
    assert control.events[-1][0] == "assembled"


@pytest.mark.parametrize("value", [None, {}, "malformed response"])
def test_malformed_target_response_is_error_before_response_checkpoint(value):
    t = target()
    t.invoke = lambda _: value
    control = Control()
    result = run(
        t, [StubScorer("good")], [_case("a"), _case("b")], execution_control=control
    )
    attempt = result.cases[0].attempts[0]
    assert attempt.verdict is Verdict.ERROR and attempt.response is None
    assert [e[0] for e in control.events] == [
        "prepared",
        "reserve",
        "attempt",
        "assembled",
    ]


@pytest.mark.parametrize("malformed", [None, {}, "bad score", "wrong-name"])
def test_malformed_scorer_result_preserves_other_scorers_and_stops_dispatch(malformed):
    from harness.core.models import Score, ScorerKind

    bad = StubScorer("bad")
    bad.score = lambda *args: (
        Score(name="foreign", kind=ScorerKind.DETERMINISTIC, value=1, passed=True)
        if malformed == "wrong-name"
        else malformed
    )
    control = Control()
    t = target()
    result = run(
        t,
        [bad, StubScorer("good")],
        [_case("a"), _case("b")],
        execution_control=control,
    )
    assert t.calls == ["a"]
    assert result.cases[0].attempts[0].verdict is Verdict.ERROR
    assert [s.name for s in result.cases[0].attempts[0].scores] == ["good"]
    recorded = next(e for e in control.events if e[0] == "score")
    assert recorded[2] is None and recorded[3]


@pytest.mark.parametrize("controlled", [False, True])
@pytest.mark.parametrize("scheme", ["dataset-cases-v1", "dataset-cases-v2"])
@pytest.mark.parametrize("mutator", ["target", "scorer"])
def test_original_metadata_and_bindings_survive_input_mutation(
    controlled, scheme, mutator
):
    from harness.core.dataset import hash_cases
    from harness.core.models import Score, ScorerKind

    cases = [_case("a", tags=["original-a"]), _case("b", tags=["original-b"])]
    original_hash = hash_cases(cases, scheme=scheme)
    received = []

    def mutate(case):
        case.id = "changed"
        case.tags.append("added")
        case.input = "changed input"

    class MutatingTarget:
        name = "synthetic-mutating"
        capabilities = frozenset()

        def invoke(self, case):
            received.append(case.id)
            if mutator == "target":
                mutate(case)
            return TargetResponse(output="4")

    class MutatingScorer:
        name = "synthetic-score"
        kind = ScorerKind.DETERMINISTIC
        requires = frozenset()

        def score(self, case, response):
            if mutator == "scorer":
                mutate(case)
            return Score(name=self.name, kind=self.kind, value=1, passed=True)

    control = Control() if controlled else None
    callbacks = []
    if control is not None:
        control.response_received = lambda cid, index, _: callbacks.append(
            ("response", cid, index)
        )
        control.scorer_recorded = lambda cid, index, *args: callbacks.append(
            ("scorer", cid, index)
        )
    result = run(
        MutatingTarget(),
        [MutatingScorer()],
        cases,
        attempts=2,
        fingerprint_scheme=scheme,
        execution_control=control,
    )
    assert [(c.case_id, c.tags) for c in result.cases] == [
        ("a", ["original-a"]),
        ("b", ["original-b"]),
    ]
    assert result.dataset_hash == original_hash
    assert received == (
        ["a", "changed", "b", "changed"]
        if scheme == "dataset-cases-v1"
        else ["a", "a", "b", "b"]
    )
    if scheme == "dataset-cases-v2":
        assert result.config_snapshot["selection"]["case_ids"] == ["a", "b"]
        assert [case.id for case in cases] == ["a", "b"]
        assert all(case.definition is not None for case in result.cases)
    if control is not None:
        expected = [(cid, i) for cid in ("a", "b") for i in range(2)]
        assert [(e[1], e[2]) for e in control.events if e[0] == "reserve"] == expected
        assert [
            (cid, i) for phase, cid, i in callbacks if phase == "response"
        ] == expected
        assert [
            (cid, i) for phase, cid, i in callbacks if phase == "scorer"
        ] == expected
        assert [e[1] for e in control.events if e[0] == "attempt"] == [
            "a",
            "a",
            "b",
            "b",
        ]
