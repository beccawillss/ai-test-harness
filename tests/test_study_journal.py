"""Synthetic C2 captures and injected filesystem faults; no actual Study runs."""

import json
import shutil
from pathlib import Path

import httpx
import pytest
from test_salesagent_study import contract, definition
from test_salesagent_target import FakeHTTP

from harness.core.fingerprints import canonical_json, fingerprint
from harness.core.models import RunResult, Verdict
from harness.core.prospective_io import ProspectiveStore
from harness.core.store import SQLiteResultStore
from harness.packs import salesagent_study as study
from harness.study import journal
from harness.targets.salesagent import SalesAgentTarget


def setup(tmp_path):
    d = definition(tmp_path / "synthetic")
    registry = journal.initialize_registry(tmp_path / "registry")
    doc = contract(d).model_dump(mode="json")
    doc.update(
        schema_version="salesagent-study-execution-v2",
        registry=registry.model_dump(mode="json"),
    )
    c = study.load_execution_contract(canonical_json(doc))
    return d, c


def factory(fake):
    return lambda: SalesAgentTarget(
        "http://fake", target_revision="1" * 40, transport=httpx.MockTransport(fake)
    )


def path_for(c, suite="smoke"):
    return (
        Path(c.registry.path) / "captures" / journal.capture_identity(c.digest, suite)
    )


def capture(tmp_path, *, suite="smoke", mutate=None):
    d, c = setup(tmp_path)
    fake = FakeHTTP(mutate)
    result = study.capture(d, c, suite, factory(fake))
    return d, c, result, fake


def test_complete_quality_fail_continues_and_receipt_round_trips(tmp_path):
    def fail_quality(request, payload):
        if request.method == "POST":
            payload["recommendations"] = []

    d, c, result, fake = capture(tmp_path, mutate=fail_quality)
    assert len(result.cases) == 8
    assert all(
        a.verdict is Verdict.FAIL for case in result.cases for a in case.attempts
    )
    assert len(fake.sessions) == 8
    assert (
        result.config_snapshot["capture_completion"]["schema_version"]
        == journal.COMPLETION_VERSION
    )
    document = fingerprint(result.model_dump(mode="json"))
    assert study.verify_capture(d, c, result, document) == "smoke"
    restored = RunResult.model_validate_json(result.model_dump_json())
    assert (
        journal.verify_completion(c.registry, c.digest, "smoke", restored) == restored
    )
    store = SQLiteResultStore(tmp_path / "result.sqlite")
    store.save(result)
    assert store.load(result.run_id) == result


def test_error_stops_later_attempts_and_keeps_earlier_multiturn_evidence(tmp_path):
    posts = 0

    def late_failure(request, payload):
        nonlocal posts
        if request.method == "POST":
            posts += 1
            if posts == 2:
                return httpx.Response(503, text="SECRET")

    d, c, result, fake = capture(tmp_path, suite="multi-turn", mutate=late_failure)
    assert posts == 2 and len(fake.requests) == 3
    attempt = result.cases[0].attempts[0]
    assert attempt.verdict is Verdict.ERROR and attempt.response is None
    records = journal.inspect_capture(c.registry, c.digest, "multi-turn")["records"]
    assert any(name.endswith("http-0000-chat.json") for name in records)
    assert any(name.endswith("http-0000-turn.json") for name in records)
    assert any(name.endswith("outcome.json") for name in records)
    assert "completion.json" not in records
    assert "SECRET" not in canonical_json(records)
    with pytest.raises((ValueError, journal.JournalError)):
        study.verify_capture(d, c, result, fingerprint(result.model_dump(mode="json")))
    with pytest.raises(journal.JournalError):
        journal.recover_save_only(
            c.registry, c.digest, "multi-turn", lambda _: pytest.fail("save incomplete")
        )


def test_chat_is_durable_before_trace_io_and_turn_before_next_chat(tmp_path):
    d, c = setup(tmp_path)
    base = path_for(c, "multi-turn")
    posts = 0

    def check(request, payload):
        nonlocal posts
        records = journal.inspect_capture(c.registry, c.digest, "multi-turn")["records"]
        if request.method == "POST":
            posts += 1
            if posts == 2:
                assert any(n.endswith("http-0000-turn.json") for n in records)
                raise httpx.ReadTimeout("SECRET")
        else:
            assert any(n.endswith("http-0000-chat.json") for n in records)

    result = study.capture(d, c, "multi-turn", factory(FakeHTTP(check)))
    assert result.error_rate == 1 and base.is_dir()


@pytest.mark.parametrize("phase", ["chat", "turn", "response", "scorer", "outcome"])
def test_journal_failures_escape_adapter_and_runner_and_stop_dispatch(
    tmp_path, monkeypatch, phase
):
    d, c = setup(tmp_path)
    fake = FakeHTTP()
    original = journal._publish

    def publish(path, payload):
        if phase in path.name:
            raise journal.JournalError("injected durable failure")
        original(path, payload)

    monkeypatch.setattr(journal, "_publish", publish)
    with pytest.raises(journal.JournalError, match="injected"):
        study.capture(d, c, "smoke", factory(fake))
    assert len(fake.sessions) == 1
    assert len(fake.requests) == (1 if phase == "chat" else 2)
    records = journal.inspect_capture(c.registry, c.digest, "smoke")["records"]
    assert "completion.json" not in records
    if phase in {"scorer", "outcome"}:
        assert any(n.endswith("response.json") for n in records)


def test_scorer_error_keeps_response_and_successful_independent_scores(
    tmp_path, monkeypatch
):
    from test_runner import StubScorer

    from harness.core.runner import run
    from harness.targets.salesagent_recording import SalesAgentRecorder

    d, c = setup(tmp_path)
    context = {"synthetic": True}
    control = journal.StudyJournal(
        c.registry, c.digest, "synthetic-scoring", context, study.CAPTURE_PROFILE
    )
    fake = FakeHTTP()
    t = factory(fake)()
    t.recorder = SalesAgentRecorder(control.record_http)
    result = run(
        t,
        [
            StubScorer("broken", error=ValueError("offline scorer error")),
            StubScorer("good"),
        ],
        d.dataset.cases[:2],
        execution_control=control,
        fingerprint_scheme="dataset-cases-v2",
    )
    attempt = result.cases[0].attempts[0]
    assert attempt.verdict is Verdict.ERROR
    assert [s.name for s in attempt.scores] == ["good"]
    records = journal.inspect_capture(c.registry, c.digest, "synthetic-scoring")[
        "records"
    ]
    assert any(n.endswith("response.json") for n in records)
    outcomes = [r for n, r in records.items() if "scorer-" in n]
    assert {r["name"] for r in outcomes} == {"broken", "good"}
    assert len(fake.sessions) == 1
    assert "completion.json" not in records
    control.close()


@pytest.mark.parametrize("record", ["claim", "preparation", "reservation"])
def test_failure_before_dispatch_leaves_permanent_claim(tmp_path, monkeypatch, record):
    d, c = setup(tmp_path)
    fake = FakeHTTP()
    original = journal._publish

    def publish(path, payload):
        if path.name == record + ".json":
            raise journal.JournalError("before dispatch")
        original(path, payload)

    monkeypatch.setattr(journal, "_publish", publish)
    with pytest.raises(journal.JournalError):
        study.capture(d, c, "smoke", factory(fake))
    assert fake.requests == []
    monkeypatch.setattr(journal, "_publish", original)
    with pytest.raises(journal.JournalError, match="reserved"):
        study.capture(d, c, "smoke", lambda: pytest.fail("duplicate factory"))


def test_duplicate_dispatch_prevention_independent_of_export_directories(tmp_path):
    d, c, result, fake = capture(tmp_path)
    for directory in (tmp_path / "first", tmp_path / "second"):
        directory.mkdir()
        (directory / "capture.json").write_text(result.model_dump_json())
        with pytest.raises(journal.JournalError, match="reserved"):
            study.capture(d, c, "smoke", lambda: pytest.fail("second target"))
    assert len(fake.sessions) == 8


def test_copied_and_relocated_registry_cannot_be_authority(tmp_path):
    _d, c, _, _ = capture(tmp_path)
    copied = tmp_path / "backup"
    shutil.copytree(c.registry.path, copied)
    with pytest.raises(journal.JournalError, match="locator"):
        journal.load_registry(copied)
    changed = c.registry.model_copy(update={"path": str(copied)})
    with pytest.raises(journal.JournalError, match="identity"):
        journal.verify_registry(changed)
    assert Path(c.registry.path).is_dir()


@pytest.mark.parametrize(
    "name",
    [
        "registry.json",
        "claim.json",
        "preparation.json",
        "response.json",
        "outcome.json",
        "completion.json",
        "run.json",
    ],
)
def test_corruption_blocks_recovery_and_never_authorizes_reissue(tmp_path, name):
    _d, c, _, _ = capture(tmp_path)
    file = (
        Path(c.registry.path) / name
        if name == "registry.json"
        else next(path_for(c).rglob(name))
    )
    file.write_text('{"payload":{},"sha256":"bad"}')
    with pytest.raises(journal.JournalError):
        journal.recover_save_only(
            c.registry, c.digest, "smoke", lambda _: pytest.fail("corrupt save")
        )
    with pytest.raises(journal.JournalError):
        study.capture(_d, c, "smoke", lambda: pytest.fail("corrupt dispatch"))


@pytest.mark.parametrize("fault", ["fsync_file", "link", "fsync_directory"])
def test_atomic_publication_reaches_injected_fault(tmp_path, monkeypatch, fault):
    existing = tmp_path / "existing.json"
    journal._publish(existing, {"already": "committed"})
    original = existing.read_bytes()
    path = tmp_path / "new.json"
    calls = []

    def fail(*args, **kwargs):
        calls.append(fault)
        raise OSError("injected " + fault)

    if fault == "link":
        monkeypatch.setattr(journal.os, "link", fail)
    elif fault == "fsync_file":
        monkeypatch.setattr(journal.os, "fsync", fail)
    else:
        monkeypatch.setattr(journal, "_sync", fail)
    with pytest.raises(journal.JournalError) as caught:
        journal._publish(path, {"new": "evidence"})
    assert calls == [fault]
    assert str(caught.value.__cause__) == "injected " + fault
    assert existing.read_bytes() == original
    assert path.exists() is (fault == "fsync_directory")
    if path.exists():
        assert journal._read(path) == {"new": "evidence"}


def test_exclusive_publication_collision_is_distinct_from_sync_failure(
    tmp_path, monkeypatch
):
    path = tmp_path / "record.json"
    journal._publish(path, {"committed": True})
    original = path.read_bytes()
    sync_calls = []
    monkeypatch.setattr(
        journal, "_sync", lambda directory: sync_calls.append(directory)
    )
    with pytest.raises(journal.JournalError) as caught:
        journal._publish(path, {"replacement": True})
    assert isinstance(caught.value.__cause__, FileExistsError)
    assert sync_calls == []
    assert path.read_bytes() == original


def test_post_link_directory_fsync_failure_is_ambiguous_and_not_overwritten(
    tmp_path, monkeypatch
):
    path = tmp_path / "record.json"

    def fail(_):
        raise OSError("fsync unavailable")

    original = journal._sync
    monkeypatch.setattr(journal, "_sync", fail)
    with pytest.raises(journal.JournalError):
        journal._publish(path, {"evidence": "visible"})
    assert journal._read(path) == {"evidence": "visible"}
    monkeypatch.setattr(journal, "_sync", original)
    with pytest.raises(journal.JournalError):
        journal._publish(path, {"evidence": "replacement"})


def test_save_failure_then_save_only_recovery_uses_no_external_calls(tmp_path):
    _d, c, result, _ = capture(tmp_path)

    def failure(_):
        raise OSError("SQLite full")

    with pytest.raises(OSError, match="SQLite"):
        journal.recover_save_only(c.registry, c.digest, "smoke", failure)
    store = SQLiteResultStore(tmp_path / "recovered.sqlite")
    assert (
        journal.recover_save_only(c.registry, c.digest, "smoke", store.save) == result
    )
    assert store.load(result.run_id) == result


def test_crash_after_run_publication_can_finalize_receipt_without_execution(
    tmp_path, monkeypatch
):
    d, c = setup(tmp_path)
    fake = FakeHTTP()
    original = journal._publish

    def publish(path, payload):
        if path.name == "completion.json":
            raise journal.JournalError("crash before final receipt")
        original(path, payload)

    monkeypatch.setattr(journal, "_publish", publish)
    with pytest.raises(journal.JournalError):
        study.capture(d, c, "smoke", factory(fake))
    assert (path_for(c) / "run.json").exists()
    monkeypatch.setattr(journal, "_publish", original)
    restored = []
    result = journal.recover_save_only(c.registry, c.digest, "smoke", restored.append)
    assert restored == [result]
    assert len(fake.sessions) == 8
    assert (
        study.verify_capture(d, c, result, fingerprint(result.model_dump(mode="json")))
        == "smoke"
    )


def test_crash_before_run_assembly_reassembles_only_committed_outcomes(
    tmp_path, monkeypatch
):
    d, c = setup(tmp_path)
    original = journal._publish

    def publish(path, payload):
        if path.name == "run.json":
            raise journal.JournalError("crash before assembly")
        original(path, payload)

    monkeypatch.setattr(journal, "_publish", publish)
    with pytest.raises(journal.JournalError):
        study.capture(d, c, "smoke", factory(FakeHTTP()))
    assert not journal.inspect_capture(c.registry, c.digest, "smoke")[
        "dispatch_authorized"
    ]
    monkeypatch.setattr(journal, "_publish", original)
    restored = journal.recover_save_only(c.registry, c.digest, "smoke", lambda _: None)
    assert len(restored.cases) == 8
    assert (
        study.verify_capture(
            d, c, restored, fingerprint(restored.model_dump(mode="json"))
        )
        == "smoke"
    )


def test_v1_serialization_fixture_is_not_migrated_and_v2_is_strict(tmp_path):
    fixture = (
        Path(__file__).parent / "fixtures/salesagent_study/pre-warmth-execution.json"
    )
    old = study.load_execution_contract(fixture.read_bytes())
    assert type(old) is study.StudyExecutionContract
    assert old.model_dump(mode="json") == json.loads(fixture.read_bytes())
    d, c = setup(tmp_path)
    assert type(study.verify_contract(d, c)) is study.StudyExecutionContractV2
    for field in ("capture_policy", "journal_version", "completion_requirement"):
        doc = c.model_dump(mode="json")
        doc[field] = "unsupported"
        with pytest.raises(ValueError):
            study.load_execution_contract(canonical_json(doc))


def test_full_v2_capture_preparation_and_protected_review_enforce_receipt(tmp_path):
    d, c, source, fake = capture(tmp_path, suite="full")
    digest = fingerprint(source.model_dump(mode="json"))
    preparation = study.prepare_primary(
        d,
        c,
        source,
        database_locator="synthetic.sqlite",
        document_hash=digest,
        plan_id="synthetic-c2-plan",
        review_set_id="synthetic-c2-review",
    )
    loader = lambda _: (source, d.dataset.cases, digest)
    manifest = study.human_manifest(d, c, preparation, loader)
    assert len(manifest.examples) == 12
    assert len(preparation.bundle.requests) == 50
    assert len(fake.sessions) == 50
    from test_calibration_io import authored_draft

    from harness.core.calibration_io import export_bundle, freeze_bundle
    from harness.core.prospective import ProspectiveJudge
    from harness.reporting.study import analyze, load_analysis, save_analysis

    export = tmp_path / "synthetic-human-export"
    frozen = tmp_path / "synthetic-human-freeze"
    export_bundle(manifest, export, annotator_id="synthetic-c2-only")
    freeze_bundle(export, authored_draft(export), frozen)
    protected = next(
        r for r in preparation.bundle.requests if r.selection.requires_human
    )
    observations = ProspectiveStore(tmp_path / "synthetic-observations")
    observations.save_prepared(preparation.bundle)
    judged = study.judge_request(
        d,
        c,
        preparation,
        protected.request_id,
        source_loader=loader,
        scorer_factory=lambda: ProspectiveJudge(
            study.semantic_profile(
                c.evaluator.judge,
                lambda _: '{"score":0.8,"reason":"SYNTHETIC C2 plumbing only"}',
            )[0],
            lambda: c.evaluator.judge,
        ),
        store=observations,
        frozen_bundle=frozen,
    )
    analysis = analyze(
        d,
        c,
        source,
        document_hash=digest,
        preparation=preparation,
        results=[judged],
        source_loader=loader,
        frozen_bundle=frozen,
    )
    assert sum(row.combined == "pass" for row in analysis.rows) == 1
    report_path = tmp_path / "synthetic-analysis"
    save_analysis(analysis, report_path)
    restored_analysis = load_analysis(report_path)
    assert restored_analysis == analysis
    assert type(restored_analysis.contract) is study.StudyExecutionContractV2
    from harness.reporting.study import compare_studies

    assert compare_studies(analysis, analysis)["context"]["execution_policy"] == "equal"
    historical = c.model_dump(
        mode="json",
        exclude={
            "registry",
            "capture_policy",
            "journal_version",
            "completion_requirement",
        },
    )
    historical["schema_version"] = "salesagent-study-execution-v1"
    v1_analysis = analysis.model_copy(
        update={"contract": study.load_execution_contract(canonical_json(historical))}
    )
    comparison = compare_studies(v1_analysis, analysis)
    assert comparison["context"]["execution_policy"] == "changed"
    assert comparison["compatible"] is False
    receipt = path_for(c, "full") / "completion.json"
    receipt.write_text("{}")
    with pytest.raises(journal.JournalError):
        study.human_manifest(d, c, preparation, loader)
    with pytest.raises(journal.JournalError):
        study.judge_request(
            d,
            c,
            preparation,
            preparation.bundle.requests[0].request_id,
            source_loader=loader,
            scorer_factory=lambda: pytest.fail("judge before receipt"),
            store=ProspectiveStore(tmp_path / "judge"),
        )


def test_wrong_completion_identity_or_source_is_rejected(tmp_path):
    d, c, result, _ = capture(tmp_path)
    changed = result.model_copy(deep=True)
    changed.config_snapshot["capture_completion"]["suite_id"] = "full"
    with pytest.raises(journal.JournalError):
        study.verify_capture(
            d, c, changed, fingerprint(changed.model_dump(mode="json"))
        )
    with pytest.raises(journal.JournalError):
        journal.verify_completion(c.registry, c.digest, "full")


def test_public_http_recording_preserves_bytes_timeouts_and_session_isolation(tmp_path):
    from test_salesagent_target import case

    from harness.targets.salesagent_recording import SalesAgentRecorder

    recorded = []
    fakes = [FakeHTTP(), FakeHTTP()]
    outputs = []
    for fake, recorder in zip(
        fakes,
        [None, SalesAgentRecorder(lambda i, p, e: recorded.append((i, p, e)))],
        strict=True,
    ):
        t = SalesAgentTarget(
            "http://fake",
            transport=httpx.MockTransport(fake),
            recorder=recorder,
            connect_timeout=2,
            read_timeout=31,
            write_timeout=3,
            pool_timeout=4,
        )
        outputs.append(t.invoke(case(turns=["hello", "follow up"])))
        t.close()
    for first, second in zip(fakes[0].requests, fakes[1].requests, strict=True):
        assert (
            first.method,
            first.url,
            first.content,
            first.headers,
            first.extensions,
        ) == (
            second.method,
            second.url,
            second.content,
            second.headers,
            second.extensions,
        )
    for response in outputs:
        response.latency_ms = None
    assert outputs[0] == outputs[1]
    assert [(i, p) for i, p, _ in recorded] == [
        (0, "chat"),
        (0, "turn"),
        (1, "chat"),
        (1, "turn"),
    ]


def test_recording_drops_secrets_but_preserves_business_errors_and_quality_fail(
    tmp_path,
):
    def mutate(request, payload):
        payload["hidden_prompt"] = "SECRET_hidden"
        payload["reasoning"] = "SECRET_reasoning"
        payload["provider_envelope"] = {"authorization": "SECRET_auth"}
        if request.method == "POST":
            payload["recommendations"] = []
        else:
            call = payload["tool_calls"][0]
            call["arguments"]["authorization"] = "SECRET_auth"
            call["result"]["data"]["reasoning"] = "SECRET_reasoning"
            payload["recommendation_validation"]["validation_errors"] = [
                "SECRET_diagnostic"
            ]
            payload["errors"] = [
                {"code": "ungrounded_promotion_code", "message": "SECRET_error"}
            ]

    _d, c, source, _fake = capture(tmp_path, mutate=mutate)
    records = journal.inspect_capture(c.registry, c.digest, "smoke")["records"]
    assert "SECRET_" not in canonical_json(records)
    turn = next(
        value for name, value in records.items() if name.endswith("http-0000-turn.json")
    )
    assert turn["evidence"]["evidence"]["errors"] == [
        {"code": "ungrounded_promotion_code"}
    ]
    assert all(
        a.verdict is Verdict.FAIL for case in source.cases for a in case.attempts
    )
    assert "completion.json" in records


@pytest.mark.parametrize("fault", ["timeout", "json", "chat", "trace", "correlation"])
def test_malformed_or_unavailable_http_evidence_stops_without_receipt(tmp_path, fault):
    def mutate(request, payload):
        if request.method == "POST":
            if fault == "timeout":
                raise httpx.ReadTimeout("SECRET")
            if fault == "json":
                return httpx.Response(200, text="SECRET")
            if fault == "chat":
                payload["recommendations"] = "SECRET"
        elif fault == "trace":
            payload["tool_calls"][0]["result"] = "SECRET"
        elif fault == "correlation":
            payload["session_id"] = "wrong-session"

    _d, c, result, fake = capture(tmp_path, mutate=mutate)
    assert len(fake.sessions) == 1 and result.error_rate == 1
    records = journal.inspect_capture(c.registry, c.digest, "smoke")["records"]
    assert "completion.json" not in records
    assert "SECRET" not in canonical_json(records)
    if fault in {"trace", "correlation"}:
        assert any(n.endswith("http-0000-chat.json") for n in records)


def test_concurrent_writers_cannot_claim_one_capture_identity(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    _d, c = setup(tmp_path)

    def claim(_):
        try:
            return journal.StudyJournal(
                c.registry, c.digest, "smoke", {}, study.CAPTURE_PROFILE
            )
        except journal.JournalError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, range(2)))
    assert sum(r is not None for r in results) == 1
    for writer in results:
        if writer is not None:
            writer.close()


@pytest.mark.parametrize(
    "boundary",
    [
        "claim.json",
        "preparation.json",
        "reservation.json",
        "http-0000-chat.json",
        "http-0000-turn.json",
        "response.json",
        "outcome.json",
        "run.json",
        "completion.json",
    ],
)
def test_abrupt_interruption_after_publication_never_reissues(
    tmp_path, monkeypatch, boundary
):
    class Crash(BaseException):
        pass

    d, c = setup(tmp_path)
    fake = FakeHTTP()
    original = journal._publish

    def publish(path, payload):
        original(path, payload)
        if path.name == boundary:
            raise Crash()

    monkeypatch.setattr(journal, "_publish", publish)
    with pytest.raises(Crash):
        study.capture(d, c, "smoke", factory(fake))
    monkeypatch.setattr(journal, "_publish", original)
    with pytest.raises(journal.JournalError):
        study.capture(d, c, "smoke", lambda: pytest.fail("reissued request"))
    if boundary in {"claim.json", "preparation.json", "reservation.json"}:
        assert fake.requests == []
    elif boundary == "http-0000-chat.json":
        assert len(fake.requests) == 1
    elif boundary not in {"run.json", "completion.json"}:
        assert len(fake.requests) == 2
    if boundary in {"run.json", "completion.json"}:
        restored = journal.recover_save_only(
            c.registry, c.digest, "smoke", lambda _: None
        )
        assert len(restored.cases) == 8
    else:
        with pytest.raises(journal.JournalError):
            journal.recover_save_only(
                c.registry,
                c.digest,
                "smoke",
                lambda _: pytest.fail("incomplete recovery"),
            )


def test_temporary_cleanup_failure_cannot_erase_atomic_publication(
    tmp_path, monkeypatch
):
    original = Path.unlink

    def unlink(path, *args, **kwargs):
        if path.name.startswith(".pending-"):
            raise OSError("cleanup unavailable")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    journal._publish(tmp_path / "record.json", {"durable": True})
    assert journal._read(tmp_path / "record.json") == {"durable": True}
    assert len(list(tmp_path.glob(".pending-*"))) == 1


def test_corrupted_previous_reservation_blocks_next_dispatch(tmp_path, monkeypatch):
    d, c = setup(tmp_path)
    original = journal.StudyJournal.attempt_completed

    def complete(control, case_id, attempt):
        dispatch = original(control, case_id, attempt)
        (control._attempt_path(case_id, attempt.index) / "reservation.json").write_text(
            "{}"
        )
        return dispatch

    monkeypatch.setattr(journal.StudyJournal, "attempt_completed", complete)
    fake = FakeHTTP()
    with pytest.raises(journal.JournalError):
        study.capture(d, c, "smoke", factory(fake))
    assert len(fake.sessions) == 1


def test_variance_v2_preserves_attempt_session_isolation_and_diagnostic_preparation(
    tmp_path,
):
    d, c, source, fake = capture(tmp_path, suite="variance")
    binding = next(s for s in c.validation.suites if s.id == "variance")
    assert len(fake.sessions) == binding.target_calls
    assert all(len(case.attempts) == binding.attempts for case in source.cases)
    prep = study.prepare_variance_diagnostic(
        d,
        c,
        source,
        database_locator="synthetic.sqlite",
        document_hash=fingerprint(source.model_dump(mode="json")),
        case_id=source.cases[0].case_id,
        attempt_index=1,
        attempts=1,
        plan_id="synthetic-variance-c2",
    )
    assert len(prep.bundle.requests) == 1


def test_offline_inspect_and_recover_commands_never_construct_clients(
    tmp_path, monkeypatch
):
    import importlib

    _d, c, result, _ = capture(tmp_path)
    monkeypatch.syspath_prepend(str(Path("examples").resolve()))
    recipe = importlib.import_module("salesagent_study")

    def forbidden(*args, **kwargs):
        pytest.fail("offline journal command constructed a client")

    monkeypatch.setattr(recipe, "make_target", forbidden)
    monkeypatch.setattr(recipe, "make_judge", forbidden)
    from harness.core.prospective_io import _save

    contract_file = tmp_path / "synthetic-contract"
    _save(contract_file, c)
    args = ["--contract", str(contract_file), "--suite", "smoke"]
    assert recipe.main(["inspect-capture", *args]) == 0
    recovered = tmp_path / "export-recovered"
    assert recipe.main(["recover-capture", *args, "--output", str(recovered)]) == 0
    assert (
        SQLiteResultStore(recovered / "source.sqlite", read_only=True).load(
            result.run_id
        )
        == result
    )
    assert recipe.main(["recover-capture", *args, "--output", str(recovered)]) == 2


def test_recovery_refuses_to_write_while_capture_writer_is_active(tmp_path):
    _d, c = setup(tmp_path)
    writer = journal.StudyJournal(
        c.registry, c.digest, "smoke", {}, study.CAPTURE_PROFILE
    )
    try:
        with pytest.raises(journal.JournalError, match="busy"):
            journal.recover_save_only(
                c.registry,
                c.digest,
                "smoke",
                lambda _: pytest.fail("active writer recovery"),
            )
    finally:
        writer.close()


@pytest.mark.parametrize(
    "record",
    [
        "reservation.json",
        "http-0000-chat.json",
        "http-0000-turn.json",
        "outcome.json",
        "completion.json",
    ],
)
def test_valid_checksums_with_conflicting_bindings_are_rejected(tmp_path, record):
    _d, c, _result, _fake = capture(tmp_path)
    target = next(path_for(c).rglob(record))
    payload = journal._read(target)
    if record == "reservation.json":
        payload["index"] += 1
    elif record == "http-0000-chat.json":
        payload["evidence"]["trace_id"] = "foreign-trace"
    elif record == "http-0000-turn.json":
        payload["evidence"]["output"] = "foreign-response"
    elif record == "outcome.json":
        payload["index"] += 1
    else:
        payload["capture_id"] = "foreign-capture"
    target.write_text(
        canonical_json({"payload": payload, "sha256": fingerprint(payload)})
    )
    with pytest.raises(journal.JournalError):
        journal.recover_save_only(
            c.registry, c.digest, "smoke", lambda _: pytest.fail("conflicting recovery")
        )


def test_stripping_receipt_or_truncating_roster_cannot_prepare_a_v2_run(tmp_path):
    d, c, source, _fake = capture(tmp_path, suite="full")
    for change in ("receipt", "roster"):
        altered = source.model_copy(deep=True)
        if change == "receipt":
            del altered.config_snapshot["capture_completion"]
        else:
            altered.cases.pop()
        with pytest.raises((ValueError, journal.JournalError)):
            study.prepare_primary(
                d,
                c,
                altered,
                database_locator="synthetic.sqlite",
                document_hash=fingerprint(altered.model_dump(mode="json")),
                plan_id="synthetic-truncated",
                review_set_id="synthetic-review",
            )


def test_freeze_v2_binds_registry_without_changing_v1_evaluation_fields(tmp_path):
    from datetime import UTC, datetime

    from test_replay import settings
    from test_salesagent_study import target_freeze

    d = definition(tmp_path / "synthetic")
    registry = journal.initialize_registry(tmp_path / "registry")
    kwargs = {
        "diagnostic_judge_calls": 3,
        "author_review": "SYNTHETIC C2 contract only",
        "reviewed_at": datetime.now(UTC),
    }
    target = target_freeze()
    v1 = study.freeze_execution(d, target, settings(), **kwargs)
    v2 = study.freeze_execution(d, target, settings(), registry=registry, **kwargs)
    assert type(v1) is study.StudyExecutionContract
    assert type(v2) is study.StudyExecutionContractV2
    old_fields = v2.model_dump(
        mode="json",
        exclude={
            "registry",
            "capture_policy",
            "journal_version",
            "completion_requirement",
        },
    )
    old_fields["schema_version"] = "salesagent-study-execution-v1"
    assert old_fields == v1.model_dump(mode="json")
    assert v1.digest != v2.digest


@pytest.mark.parametrize("failure", [False, True])
def test_v2_capture_recipe_saves_results_and_reports_completion(
    tmp_path, monkeypatch, failure
):
    import importlib

    from harness.core.prospective_io import _save

    d, c = setup(tmp_path)
    monkeypatch.syspath_prepend(str(Path("examples").resolve()))
    recipe = importlib.import_module("salesagent_study")

    def mutate(request, payload):
        if failure:
            return httpx.Response(503)

    fake = FakeHTTP(mutate)
    monkeypatch.setattr(recipe, "make_target", lambda _: factory(fake)())
    contract_path = tmp_path / "synthetic-contract"
    _save(contract_path, c)
    args = [
        "capture",
        "--descriptor",
        str(d.dataset.descriptor_path),
        "--suites",
        *[str(s.suite_path) for s in d.suites],
        "--contract",
        str(contract_path),
        "--suite",
        "smoke",
        "--target-budget",
        "8",
        "--live",
        "--allow-target-calls",
        "--output",
        str(tmp_path / "export"),
    ]
    assert recipe.main(args) == (2 if failure else 0)
    source = RunResult.model_validate_json(
        (tmp_path / "export/capture.json").read_bytes()
    )
    assert ("capture_completion" in source.config_snapshot) is (not failure)
    assert len(fake.sessions) == (1 if failure else 8)
    # A second export directory still cannot dispatch the capture again.
    args[-1] = str(tmp_path / "other-export")
    previous = len(fake.requests)
    assert recipe.main(args) == 2
    assert len(fake.requests) == previous


def test_checksum_envelopes_reject_noncanonical_byte_changes(tmp_path):
    record = tmp_path / "record.json"
    journal._publish(record, {"value": "durable"})
    record.write_bytes(record.read_bytes() + b"\n")
    with pytest.raises(journal.JournalError):
        journal._read(record)


@pytest.mark.parametrize("stage", ["factory", "prepared"])
@pytest.mark.parametrize("replacement", ["symlink", "directory"])
def test_substituted_attempt_directory_blocks_first_dispatch(
    tmp_path, monkeypatch, stage, replacement
):
    d, c = setup(tmp_path)
    fake = FakeHTTP()
    redirected = tmp_path / "redirected"
    redirected.mkdir()

    def substitute():
        attempts = path_for(c) / "attempts"
        attempts.rename(tmp_path / "original-attempts")
        if replacement == "symlink":
            attempts.symlink_to(redirected, target_is_directory=True)
        else:
            attempts.mkdir()

    original = journal.StudyJournal.prepared

    def prepared(control, run, cases):
        original(control, run, cases)
        if stage == "prepared":
            substitute()

    monkeypatch.setattr(journal.StudyJournal, "prepared", prepared)

    def make():
        if stage == "factory":
            substitute()
        return factory(fake)()

    with pytest.raises(journal.JournalError, match="directory identity"):
        study.capture(d, c, "smoke", make)
    assert fake.requests == []
    assert list(redirected.iterdir()) == []


@pytest.mark.parametrize("boundary", ["complete", "completion.json", "run.json"])
def test_recovery_scans_existing_evidence_once_before_missing_publications(
    tmp_path, monkeypatch, boundary
):
    import os
    from collections import Counter

    d, c = setup(tmp_path)
    publish = journal._publish

    def interrupted(path, payload):
        if path.name == boundary:
            raise journal.JournalError("interrupted before " + boundary)
        publish(path, payload)

    monkeypatch.setattr(journal, "_publish", interrupted)
    if boundary == "complete":
        study.capture(d, c, "smoke", factory(FakeHTTP()))
    else:
        with pytest.raises(journal.JournalError):
            study.capture(d, c, "smoke", factory(FakeHTTP()))
    records = list(path_for(c).rglob("*.json"))
    identities = {(p.stat().st_dev, p.stat().st_ino) for p in records}
    counts = Counter()
    events = []
    fsync = journal.os.fsync

    def sync(descriptor):
        info = os.fstat(descriptor)
        identity = (info.st_dev, info.st_ino)
        if identity in identities:
            counts[identity] += 1
            events.append("existing")
        return fsync(descriptor)

    def published(path, payload):
        assert counts == Counter({identity: 1 for identity in identities})
        events.append(path.name)
        publish(path, payload)

    monkeypatch.setattr(journal.os, "fsync", sync)
    monkeypatch.setattr(journal, "_publish", published)
    restored = journal.recover_save_only(c.registry, c.digest, "smoke", lambda _: None)
    assert counts == Counter({identity: 1 for identity in identities})
    assert [event for event in events if event != "existing"] == (
        []
        if boundary == "complete"
        else ["completion.json"]
        if boundary == "completion.json"
        else ["run.json", "completion.json"]
    )
    assert (
        study.verify_capture(
            d, c, restored, fingerprint(restored.model_dump(mode="json"))
        )
        == "smoke"
    )


@pytest.mark.parametrize("failure", ["scan", "run.json", "completion.json"])
def test_recovery_failure_never_saves_or_reissues_and_keeps_committed_evidence(
    tmp_path, monkeypatch, failure
):
    d, c = setup(tmp_path)
    fake = FakeHTTP()
    publish = journal._publish

    def interrupt(path, payload):
        if path.name == "run.json":
            raise journal.JournalError("interrupted assembly")
        publish(path, payload)

    monkeypatch.setattr(journal, "_publish", interrupt)
    with pytest.raises(journal.JournalError):
        study.capture(d, c, "smoke", factory(fake))
    files = {p: p.read_bytes() for p in path_for(c).rglob("*.json")}
    requests = len(fake.requests)
    sync = journal._sync

    def fail_sync(directory):
        raise OSError("recovery fsync unavailable")

    def fail_publish(path, payload):
        if path.name == failure:
            raise journal.JournalError("recovery publication unavailable")
        publish(path, payload)

    monkeypatch.setattr(journal, "_publish", fail_publish)
    if failure == "scan":
        monkeypatch.setattr(journal, "_sync", fail_sync)
    with pytest.raises((OSError, journal.JournalError)):
        journal.recover_save_only(
            c.registry,
            c.digest,
            "smoke",
            lambda _: pytest.fail("saved before durability"),
        )
    assert all(path.read_bytes() == data for path, data in files.items())
    assert len(fake.requests) == requests
    monkeypatch.setattr(journal, "_sync", sync)
    monkeypatch.setattr(journal, "_publish", publish)
    restored = journal.recover_save_only(c.registry, c.digest, "smoke", lambda _: None)
    assert len(fake.requests) == requests
    assert journal.verify_completion(c.registry, c.digest, "smoke") == restored


@pytest.fixture
def recovery_recipe(monkeypatch):
    import importlib

    monkeypatch.syspath_prepend(str(Path("examples").resolve()))
    return importlib.import_module("salesagent_study")


@pytest.mark.parametrize("mask", [0o000, 0o022, 0o077, 0o777])
def test_recovery_recipe_exports_private_files_without_changing_umask(tmp_path, mask):
    import os
    import stat
    import subprocess
    import sys

    from harness.core.prospective_io import _save

    _d, c, result, fake = capture(tmp_path)
    bundle = tmp_path / "contract"
    _save(bundle, c)
    output = tmp_path / "export"
    parent_mode = stat.S_IMODE(tmp_path.stat().st_mode)
    script = """
import os, socket, sys
from pathlib import Path
import salesagent_study as recipe
def forbidden(*args, **kwargs):
    raise AssertionError('Recovery must not call factories, sockets or change umask')
recipe.make_target = recipe.make_judge = forbidden
socket.create_connection = socket.socket.connect = forbidden
os.umask(int(sys.argv[1]))
os.umask = forbidden
raise SystemExit(recipe.main([
    'recover-capture', '--contract', sys.argv[2], '--suite', 'smoke',
    '--output', sys.argv[3],
]))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(mask), str(bundle), str(output)],
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                [str(Path("src").resolve()), str(Path("examples").resolve())]
            ),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert stat.S_IMODE(tmp_path.stat().st_mode) == parent_mode
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    for name in ("capture.json", "source.sqlite"):
        assert stat.S_IMODE((output / name).stat().st_mode) == 0o600
    assert (
        RunResult.model_validate_json((output / "capture.json").read_bytes()) == result
    )
    assert (
        SQLiteResultStore(output / "source.sqlite", read_only=True).load(result.run_id)
        == result
    )
    assert len(fake.sessions) == 8


@pytest.mark.parametrize(
    "unsafe", ["directory", "file", "symlink", "parent", "writable"]
)
def test_recovery_export_rejects_unsafe_paths_without_modifying_them(
    tmp_path, recovery_recipe, unsafe
):
    _d, _c, result, _fake = capture(tmp_path)
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    output = parent / "export"
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"unchanged")
    if unsafe == "directory":
        output.mkdir(mode=0o755)
        (output / "preserve").write_bytes(b"unchanged")
    elif unsafe == "file":
        output.write_bytes(b"unchanged")
    elif unsafe == "symlink":
        output.symlink_to(sentinel)
    elif unsafe == "parent":
        alias = tmp_path / "alias"
        alias.symlink_to(parent, target_is_directory=True)
        output = alias / "export"
    else:
        parent.chmod(0o777)
    parent_mode = parent.stat().st_mode
    with pytest.raises((ValueError, FileExistsError)):
        recovery_recipe._save_recovery_export(result, output)
    assert sentinel.read_bytes() == b"unchanged"
    assert parent.stat().st_mode == parent_mode
    if unsafe == "directory":
        assert (output / "preserve").read_bytes() == b"unchanged"
    elif unsafe == "file":
        assert output.read_bytes() == b"unchanged"
    elif unsafe == "symlink":
        assert output.is_symlink()
    else:
        assert not output.exists()


@pytest.mark.parametrize("substitution", ["directory", "capture.json", "source.sqlite"])
def test_recovery_export_rejects_substitution_during_sqlite_save(
    tmp_path, monkeypatch, recovery_recipe, substitution
):
    import stat

    _d, _c, result, _fake = capture(tmp_path)
    output = tmp_path / "export"
    redirected = tmp_path / "redirected"
    redirected.mkdir()
    sentinel = redirected / "sentinel"
    sentinel.write_bytes(b"unchanged")
    save = recovery_recipe.SQLiteResultStore.save

    def substituted(store, restored):
        save(store, restored)
        if substitution == "directory":
            output.rename(tmp_path / "original-export")
            output.symlink_to(redirected, target_is_directory=True)
        else:
            (output / substitution).symlink_to(sentinel)

    monkeypatch.setattr(recovery_recipe.SQLiteResultStore, "save", substituted)
    with pytest.raises((ValueError, FileExistsError)):
        recovery_recipe._save_recovery_export(result, output)
    assert list(redirected.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"unchanged"
    private = tmp_path / "original-export" if substitution == "directory" else output
    assert stat.S_IMODE(private.stat().st_mode) == 0o700
    if substitution == "source.sqlite":
        assert stat.S_IMODE((private / "capture.json").stat().st_mode) == 0o600


def test_interrupted_export_stays_private_and_save_only_can_use_new_output(
    tmp_path, monkeypatch, recovery_recipe
):
    import os
    import stat

    _d, c, result, fake = capture(tmp_path)
    original = {p: p.read_bytes() for p in path_for(c).rglob("*.json")}
    requests = len(fake.requests)
    output = tmp_path / "interrupted-export"
    fsync = os.fsync
    reached = []

    def interrupted(descriptor):
        if (output / "capture.json").exists():
            info = os.fstat(descriptor)
            published = (output / "capture.json").stat()
            if (info.st_dev, info.st_ino) == (published.st_dev, published.st_ino):
                reached.append("capture.json")
                raise OSError("interrupted export fsync")
        fsync(descriptor)

    monkeypatch.setattr(os, "fsync", interrupted)
    with pytest.raises(OSError, match="interrupted export fsync"):
        journal.recover_save_only(
            c.registry,
            c.digest,
            "smoke",
            lambda restored: recovery_recipe._save_recovery_export(restored, output),
        )
    assert reached == ["capture.json"]
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE((output / "capture.json").stat().st_mode) == 0o600
    assert all(p.read_bytes() == data for p, data in original.items())
    monkeypatch.setattr(os, "fsync", fsync)
    replacement = tmp_path / "saved-export"
    restored = journal.recover_save_only(
        c.registry,
        c.digest,
        "smoke",
        lambda restored: recovery_recipe._save_recovery_export(restored, replacement),
    )
    assert restored == result
    assert len(fake.requests) == requests
    assert (
        SQLiteResultStore(replacement / "source.sqlite", read_only=True).load(
            result.run_id
        )
        == result
    )


def test_process_death_after_response_keeps_evidence_and_forbids_reissue(tmp_path):
    import os
    import subprocess
    import sys

    script = """
import os, socket, sys
from pathlib import Path
from harness.core.models import ScorerKind, TargetResponse, TestCase
from harness.core.runner import run
from harness.study.journal import StudyJournal, initialize_registry
def forbidden(*args, **kwargs):
    raise AssertionError('Synthetic death test cannot access network')
socket.create_connection = socket.socket.connect = forbidden
root = Path(sys.argv[1])
control = StudyJournal(initialize_registry(root / 'registry'), 'a' * 64,
                       'synthetic-death', {'synthetic': True}, 'synthetic')
class Target:
    name = 'synthetic'
    capabilities = set()
    def invoke(self, case):
        with (root / 'synthetic-dispatch').open('x') as stream:
            stream.write('one synthetic dispatch')
        return TargetResponse(output='synthetic evidence')
class Scorer:
    name = 'synthetic'
    kind = ScorerKind.DETERMINISTIC
    requires = frozenset()
    def score(self, case, response):
        os._exit(23)  # real process death; bypass finally/cleanup
run(Target(), [Scorer()], [TestCase(id='synthetic', input='synthetic')],
    fingerprint_scheme='dataset-cases-v2', execution_control=control)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env={**os.environ, "PYTHONPATH": str(Path("src").resolve())},
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert completed.returncode == 23, completed.stderr
    registry = journal.load_registry(tmp_path / "registry")
    records = journal.inspect_capture(registry, "a" * 64, "synthetic-death")["records"]
    assert any(name.endswith("reservation.json") for name in records)
    response = next(r for name, r in records.items() if name.endswith("response.json"))
    assert response["output"] == "synthetic evidence"
    assert not any(name.endswith("outcome.json") for name in records)
    assert "completion.json" not in records
    with pytest.raises(journal.JournalError, match="reserved"):
        journal.StudyJournal(registry, "a" * 64, "synthetic-death", {}, "synthetic")
    with pytest.raises(journal.JournalError):
        journal.recover_save_only(
            registry,
            "a" * 64,
            "synthetic-death",
            lambda _: pytest.fail("saved incomplete"),
        )
    assert (tmp_path / "synthetic-dispatch").read_text() == "one synthetic dispatch"
