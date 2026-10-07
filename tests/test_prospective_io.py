"""Exclusive reservations and immutable receipts, tested with local fakes."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from test_prospective import execute, material, revised

from harness.core.fingerprints import canonical_json
from harness.core.prospective import ProspectiveJudgmentResult
from harness.core.prospective_io import PreparedBundle


def test_concurrent_execution_reservation_has_one_winner(tmp_path):
    data = material(tmp_path, protected=False)
    store = data[5]
    request = data[4][0]
    barrier = Barrier(2)

    def reserve(_):
        barrier.wait()
        try:
            store.reserve(request)
        except FileExistsError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, range(2))) == [False, True]
    assert store.state(request) == "started_unresolved"
    with pytest.raises(FileExistsError):
        execute(data)


def test_save_failure_retains_result_and_allows_save_only_recovery(
    tmp_path, monkeypatch
):
    data = material(tmp_path, protected=False)
    store = data[5]
    request = data[4][0]
    result = execute(data)
    original = Path.open

    def fail_receipt(self, *args, **kwargs):
        if self.name == "receipt.json" and self.parent.name == "result-observation-0":
            raise OSError("disk unavailable")
        return original(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", fail_receipt)
        with pytest.raises(OSError):
            store.save_result(result)
    assert store.state(request) == "started_unresolved"
    with pytest.raises(OSError):
        store.load_result(store.directory / "result-observation-0")
    recovered = store.save_result(result, destination=tmp_path / "recovered")
    assert store.load_result(recovered) == result
    with pytest.raises(FileExistsError):
        execute(data)
    with pytest.raises(FileExistsError):
        store.save_result(result, destination=tmp_path / "duplicate")


def test_preparation_identity_cannot_be_reused_in_another_plan(tmp_path):
    data = material(tmp_path, protected=False)
    request = data[4][0]
    store = data[5]
    with pytest.raises(FileExistsError):
        store.save_prepared(PreparedBundle(plan=request.plan, requests=(request,)))


@pytest.mark.parametrize(
    "body", ["duplicate", "nonfinite", "unknown", "missing_receipt", "changed_bytes"]
)
def test_corrupt_bundle_rejected(tmp_path, body):
    data = material(tmp_path, protected=False)
    store = data[5]
    plan = data[4][0].plan
    path = store.directory / f"plan-{plan.plan_id}"
    if body == "missing_receipt":
        (path / "receipt.json").unlink()
    elif body == "duplicate":
        (path / "receipt.json").write_text('{"fingerprint": "x", "fingerprint": "x"}')
    elif body == "nonfinite":
        (path / "document.json").write_text('{"bad":NaN}')
    elif body == "unknown":
        (path / "receipt.json").write_text("{}")
    else:
        (path / "document.json").write_text((path / "document.json").read_text() + " ")
    with pytest.raises((ValueError, OSError)):
        store.load_prepared(plan)


@pytest.mark.parametrize(
    "field",
    ["anchor", "prompt", "input", "observation", "verdict", "count", "freeze", "time"],
)
def test_result_integrity_even_after_outer_checksum_recomputed(tmp_path, field):
    data = material(tmp_path, protected=False)
    result = execute(data)
    doc = result.model_dump(mode="json")
    attempts = json.loads(doc["attempts_json"])
    if field == "anchor":
        attempts[0]["score"]["value"] = 0.7
    if field == "prompt":
        attempts[0]["prompt_hash"] = "0" * 64
    if field == "input":
        attempts[0]["input_hash"] = "0" * 64
    if field == "observation":
        doc["observation_id"] = "unselected"
    if field == "verdict":
        attempts[0]["verdict"] = "FAIL"
    if field == "count":
        attempts.append(attempts[0])
    if field == "freeze":
        doc["input"]["plan"]["selections"][0]["requires_human"] = True
    if field == "time":
        attempts[0]["started_at"] = "2000-01-01T00:00:00Z"
    doc["attempts_json"] = canonical_json(attempts)
    with pytest.raises(ValueError):
        ProspectiveJudgmentResult.model_validate_json(canonical_json(doc))


def test_request_nested_mutation_cannot_rewrite_preparation(tmp_path):
    data = material(tmp_path, protected=False)
    request = data[4][0]
    saved = request.model_dump_json()
    data[0].cases[0].attempts[0].response.structured["turns"].clear()
    data[1][0].reference["expectation"] = "changed"
    assert request.model_dump_json() == saved
    with pytest.raises(ValueError):
        revised(request, response_json='{"x":1,"x":2}')


def test_boolean_persisted_score_cannot_be_coerced_into_anchor(tmp_path):
    data = material(tmp_path, protected=False)
    result = execute(data)
    attempts = json.loads(result.attempts_json)
    attempts[0]["score"]["value"] = True
    with pytest.raises(ValueError, match="coercion"):
        revised(result, attempts_json=canonical_json(attempts))
