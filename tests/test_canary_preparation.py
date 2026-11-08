"""Offline human preparation, control files and private storage regressions."""

import json
import logging
import os
import subprocess

import pytest

from harness.canary.driver import CanaryDriver, reveal_judgments
from harness.canary.human import (
    _HumanReviewStore,
    accept_human_draft,
    export_readable_packet,
    request_operator_stop,
    verify_human_ratings,
)
from harness.canary.inputs import judge_inputs
from harness.canary.recording import CanaryError, CanaryStore


@pytest.fixture
def store(tmp_path):
    return CanaryStore(tmp_path / "salesagent-preflight-canary" / "human")


def test_readable_packet_contains_all_original_evidence_and_blank_ratings(store):
    export_readable_packet(store)
    text = (store.path / "human-packet.md").read_text()
    packet = json.loads((store.path / "human-packet.json").read_text())
    assert [v["id"] for v in packet["examples"]] == list(judge_inputs())
    for example in packet["examples"]:
        assert f"## {example['id']}\n" in text
        turn = example["evidence"]["turns"][0]
        assert turn["shopper"] in text and turn["assistant"] in text
        assert example["evidence"] == json.loads(
            judge_inputs()[example["id"]].evidence_json
        )
    draft = json.loads((store.path / "human-draft.json").read_text())
    assert draft["judge_output_exposure"] == "unknown"
    assert all(v == {"score": None, "reason": ""} for v in draft["ratings"].values())
    assert all(p.stat().st_mode & 0o077 == 0 for p in store.path.iterdir())
    with pytest.raises(CanaryError):
        accept_human_draft(store)
    with pytest.raises(CanaryError):
        verify_human_ratings(store)
    with pytest.raises((CanaryError, FileNotFoundError)):
        reveal_judgments(store)


def test_saved_human_review_records_and_verifies_without_dispatch_capability(store):
    export_readable_packet(store)
    draft = json.loads((store.path / "human-draft.json").read_text())
    draft["judge_output_exposure"] = "not_seen"
    draft["ratings"] = {
        key: {"score": 0.6, "reason": "Synthetic test rating only."}
        for key in draft["ratings"]
    }
    (store.path / "human-draft.json").write_text(json.dumps(draft))
    review = _HumanReviewStore(store.path)
    accept_human_draft(review)
    assert verify_human_ratings(_HumanReviewStore(store.path)) == {
        "reviewer": "beccawillss",
        "examples": 8,
        "receipt_verified": True,
        "judge_authorised": False,
    }
    with pytest.raises(CanaryError):
        review.write("reserved-target-stage", {})
    with pytest.raises(CanaryError):
        accept_human_draft(review)
    ratings = json.loads((store.path / "human-ratings.json").read_text())
    ratings["ratings"]["J1"]["reason"] = "tampered"
    (store.path / "human-ratings.json").write_text(json.dumps(ratings))
    with pytest.raises(CanaryError):
        verify_human_ratings(review)
    assert not list(store.path.glob("reserved-*.json"))


@pytest.mark.parametrize("pause", [True, False])
def test_operator_controls_are_terminal_without_any_dispatch(store, pause):
    request_operator_stop(store, pause=pause)
    with pytest.raises(CanaryError):
        store.guard()
    assert store.stopped
    assert store.accounting()["attempts"] == 0
    assert json.loads((store.path / "stopped.json").read_text())["reason"] == (
        "operator_pause" if pause else "operator_stop"
    )


@pytest.mark.parametrize("which", ["directory", "namespace", "file"])
def test_permission_drift_prevents_dispatch(store, which):
    path = {
        "directory": store.path,
        "namespace": store.path.parent,
        "file": store.path / "manifest.json",
    }[which]
    original = path.stat().st_mode & 0o777
    try:
        path.chmod(original | 0o040)
        with pytest.raises(CanaryError):
            store.guard()
        assert store.stopped
    finally:
        path.chmod(original)


def test_replaced_run_directory_is_not_written_through(store):
    previous = store.path.with_name("preserved")
    store.path.rename(previous)
    store.path.mkdir(mode=0o700)
    with pytest.raises(CanaryError):
        store.write("reserved-target-stage", {})
    assert not list(store.path.iterdir())


def test_saved_review_rejects_changed_evidence(store):
    export_readable_packet(store)
    packet = json.loads((store.path / "human-packet.json").read_text())
    packet["examples"][0]["evidence"]["turns"][0]["assistant"] = "substituted"
    (store.path / "human-packet.json").write_text(json.dumps(packet))
    with pytest.raises(CanaryError):
        _HumanReviewStore(store.path)


def test_human_review_rejects_symlink_and_study_namespace(store, tmp_path):
    export_readable_packet(store)
    alias = store.path.with_name("alias")
    alias.symlink_to(store.path, target_is_directory=True)
    with pytest.raises(CanaryError):
        _HumanReviewStore(alias)
    with pytest.raises(CanaryError):
        CanaryStore(tmp_path / "salesagent-study-v1" / "human")
    assert not (store.path / "reserved-judge-stage.json").exists()


def test_incomplete_ratings_never_construct_a_judge(store, monkeypatch):
    import httpx

    from harness.canary import driver

    export_readable_packet(store)

    def forbidden(*args, **kwargs):
        pytest.fail("Judge construction is forbidden before independent ratings")

    monkeypatch.setattr(driver, "OpenAIJudge", forbidden)
    with pytest.raises(CanaryError):
        CanaryDriver(store).run_judge(httpx.MockTransport(forbidden))
    assert not list(store.path.glob("reserved-judge*.json"))
    assert store.accounting()["attempts"] == 0


def test_private_file_controls_do_not_depend_on_umask(tmp_path):
    previous = os.umask(0)
    try:
        store = CanaryStore(tmp_path / "salesagent-preflight-canary" / "umask")
        export_readable_packet(store)
    finally:
        os.umask(previous)
    assert store.path.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in store.path.iterdir())


@pytest.fixture
def source_history(tmp_path, monkeypatch):
    from harness.canary import controller

    root = tmp_path / "synthetic-source"
    root.mkdir()

    def git(*args):
        return subprocess.check_output(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=Synthetic",
                "-c",
                "user.email=synthetic@example.invalid",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            text=True,
        ).strip()

    git("init", "-q")
    (root / "baseline.txt").write_text("Synthetic unchanged engine\n")
    git("add", "baseline.txt")
    git("commit", "-qm", "Synthetic baseline")
    monkeypatch.setattr(controller, "HARNESS_REVISION", git("rev-parse", "HEAD"))
    return root, git


def test_committed_c3a_revision_remains_valid_but_unrelated_edits_do_not(
    source_history,
):
    from harness.canary.controller import _harness_revision

    root, git = source_history
    baseline = git("rev-parse", "HEAD")
    assert _harness_revision(root) == baseline
    path = root / "docs/study-v1-c3a-canary-preparation.md"
    path.parent.mkdir()
    path.write_text("Synthetic scoped preparation\n")
    git("add", "docs/study-v1-c3a-canary-preparation.md")
    git("commit", "-qm", "Synthetic C3a patch")
    committed = git("rev-parse", "HEAD")
    assert committed != baseline and _harness_revision(root) == committed
    (root / "baseline.txt").write_text("Unapproved engine change\n")
    with pytest.raises(CanaryError):
        _harness_revision(root)


def test_untracked_source_beyond_c3a_inventory_blocks_runtime(source_history):
    from harness.canary.controller import _harness_revision

    root, _ = source_history
    (root / "unapproved.py").write_text("# synthetic unreviewed module\n")
    with pytest.raises(CanaryError):
        _harness_revision(root)


def test_provider_sensitive_fields_do_not_enter_telemetry_or_info_logs(store, caplog):
    import httpx

    from harness.canary.inputs import TARGET_MODEL
    from harness.canary.recording import ProviderTransport

    markers = [
        "synthetic-key-never-log",
        "synthetic-provider-input-never-log",
        "synthetic-hidden-instructions-never-log",
        "synthetic-reasoning-content-never-log",
        "synthetic-provider-error-body-never-log",
    ]
    caplog.set_level(logging.INFO)

    def reply(request):
        return httpx.Response(
            200,
            json={
                "model": TARGET_MODEL,
                "status": "completed",
                "output": [{"type": "reasoning", "summary": markers[3]}],
                "error": {"message": markers[4]},
                "private_extra": request.content.decode(),
                "usage": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
            },
        )

    provider = ProviderTransport(store, httpx.MockTransport(reply), role="target")
    with (
        httpx.Client(
            transport=provider, trust_env=False, follow_redirects=False
        ) as client,
        provider.logical("A1"),
    ):
        response = client.post(
            "https://api.openai.com/v1/responses",
            headers={"authorization": "Bearer " + markers[0]},
            json={
                "model": TARGET_MODEL,
                "max_output_tokens": 2000,
                "input": markers[1],
                "instructions": markers[2],
            },
        )
        assert response.status_code == 200
    saved = "".join(p.read_text() for p in store.path.glob("*.json")) + caplog.text
    assert all(marker not in saved for marker in markers)
    assert store.accounting()["attempts"] == 1
