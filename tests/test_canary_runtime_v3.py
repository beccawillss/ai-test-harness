"""Synthetic receipts and temporary Git sources; no production approvals.

Git observation and pure receipt matching are exercised separately so that the
default suite needs neither the pinned external application nor its credentials.
No test substitutes a configurable production policy or mutates its constants.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from harness.canary import runtime_v3 as runtime


@pytest.fixture(scope="module")
def binding():
    return runtime.resolve_definition(runtime.V3)


@pytest.fixture
def receipt(binding):
    return runtime.SourceApprovalReceipt(
        schema_id="canary-source-approval-v1",
        scope="source-only",
        approval_reference="synthetic:unit-test-only",
        provenance="synthetic-test",
        execution_profile="offline-verification-v1",
        harness=runtime.GitIdentity(commit="a" * 40, tree="b" * 40),
        application=runtime.GitIdentity(
            commit=runtime.APPLICATION_REVISION, tree="c" * 40
        ),
        binding=binding,
        harness_lock_sha256="d" * 64,
        application_lock_sha256="e" * 64,
        runtime=runtime.RuntimeIdentity(
            implementation="CPython",
            python="3.12.13",
            system="Darwin",
            machine="arm64",
            dependency_lock="harness",
        ),
    )


@pytest.fixture
def observed(receipt):
    return runtime._Observation(
        harness=receipt.harness,
        application=receipt.application,
        fixtures=receipt.binding.fixture_hashes,
        harness_lock=receipt.harness_lock_sha256,
        application_lock=receipt.application_lock_sha256,
        runtime=receipt.runtime,
    )


def git(root, *args):
    return (
        subprocess.check_output(
            ["git", "-C", str(root), *args],
            stderr=subprocess.DEVNULL,
            env={
                "PATH": os.defpath,
                "HOME": str(root),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
            },
        )
        .decode()
        .strip()
    )


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Synthetic Test")
    git(root, "config", "user.email", "synthetic@example.invalid")
    (root / "src").mkdir()
    (root / "src/example.py").write_text("VALUE = 1\n")
    (root / "uv.lock").write_text("version = 1\npackage = []\n")
    (root / ".gitignore").write_text("ignored/\n*.pyc\n__pycache__/\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "Synthetic source only")
    return root


def test_historical_default_is_exact_and_has_no_v3_policy():
    from harness.canary.inputs import TARGET_TURNS, roster_hash

    default = runtime.resolve_definition()
    assert default.identifier == runtime.C1
    assert default == runtime.resolve_definition(runtime.C1)
    assert tuple(t.model_dump() for t in default.turns) == tuple(
        vars(t) for t in TARGET_TURNS
    )
    assert default.roster_fingerprint == roster_hash()
    assert default.definition_fingerprint is None
    assert default.execution_fingerprint is None
    assert default.execution_policy is None
    assert default.acceptance_policy == runtime.C1
    assert default.storage_schema == "nonstudy-canary-v1"
    assert default.authorises_live_execution is False


def test_explicit_v3_binding_and_exact_approved_identities(binding):
    from harness.canary.selection_v3 import TURNS

    assert tuple(t.model_dump() for t in binding.turns) == tuple(vars(t) for t in TURNS)
    assert tuple(t.slot for t in binding.turns) == ("A1", "B1", "A2", "B2")
    assert tuple(t.conversation for t in binding.turns) == ("A", "B", "A", "B")
    assert (
        binding.roster_fingerprint,
        binding.definition_fingerprint,
        binding.acceptance_fingerprint,
        binding.execution_fingerprint,
    ) == runtime.V3_FINGERPRINTS
    assert binding.v2_1_fingerprint == runtime.V2_FINGERPRINT
    assert binding.fixture_hashes == runtime.FIXTURE_HASHES
    assert binding.scope == "target-only"
    assert binding.authorises_live_execution is False
    runtime.validate_binding(binding)


@pytest.mark.parametrize(
    "identifier", ["", "v3", "V3", runtime.V3 + " ", "unknown", 3, False]
)
def test_unknown_selection_never_falls_back(identifier):
    with pytest.raises(runtime.SourceError, match="^unknown_definition$"):
        runtime.resolve_definition(identifier)


@pytest.mark.parametrize(
    "change",
    [
        {"identifier": runtime.C1},
        {"roster_fingerprint": "0" * 64},
        {"definition_fingerprint": "0" * 64},
        {"acceptance_fingerprint": "0" * 64},
        {"execution_fingerprint": "0" * 64},
        {"v2_1_fingerprint": "0" * 64},
        {"application_revision": "0" * 40},
        {"fixture_hashes": ()},
        {"acceptance_policy": runtime.C1},
        {"execution_policy": None},
        {"storage_schema": "Study-v1"},
        {"scope": "judge"},
        {"turns": ()},
        {"authorises_live_execution": True},
        {"undeclared_judge_capability": True},
        {"limits": runtime.Limits(logical_calls_total=25)},
        {"inference": runtime.Inference(sdk_retries=3)},
    ],
)
def test_mixed_binding_rejected_even_for_validation_bypassing_copies(binding, change):
    with pytest.raises(runtime.SourceError):
        runtime.validate_binding(binding.model_copy(update=change))


def test_binding_deeply_immutable_and_limits_unchanged(binding):
    for instance, field, value in (
        (binding, "identifier", runtime.C1),
        (binding.turns[0], "message", "new"),
        (binding.inference, "model", "different"),
        (binding.limits, "shopper_posts", 5),
    ):
        with pytest.raises(ValidationError):
            setattr(instance, field, value)
    assert binding.limits == runtime.Limits()
    assert (
        binding.limits.logical_calls_total,
        binding.limits.provider_attempts_total,
    ) == (24, 72)
    assert binding.inference.sdk_retries == 2
    assert binding.inference.temperature is None
    assert binding.inference.cache_retention_override is None


def test_receipt_roundtrip_and_matching_synthetic_clean_observations(receipt, observed):
    assert runtime.parse_receipt(receipt.model_dump_json()) == receipt
    assert runtime.parse_receipt(receipt.model_dump()) == receipt
    assert runtime.parse_receipt(receipt) == receipt
    runtime.validate_binding(receipt.binding)
    result = runtime._check_observation(receipt, observed)
    assert result.source_matches_receipt is True
    assert result.source_authorised is False
    assert result.authorises_live_execution is False
    assert receipt.provenance == "synthetic-test"
    assert receipt.scope == "source-only"


def test_provenance_claim_cannot_authenticate_matching_source(receipt, observed):
    synthetic = runtime._check_observation(receipt, observed)
    claimed = runtime.parse_receipt(
        receipt.model_copy(update={"provenance": "external-review"}).model_dump_json()
    )
    assert claimed.model_dump(exclude={"provenance"}) == receipt.model_dump(
        exclude={"provenance"}
    )
    external = runtime._check_observation(claimed, observed)
    for result in (synthetic, external):
        assert result.source_matches_receipt is True
        assert result.harness == observed.harness
        assert result.application == observed.application
        assert result.binding.fixture_hashes == observed.fixtures
        assert result.source_authorised is False
        assert result.authorises_live_execution is False
        assert result.model_dump(mode="json")["source_authorised"] is False
    assert synthetic.claimed_provenance == "synthetic-test"
    assert external.claimed_provenance == "external-review"
    assert synthetic.receipt_sha256 != external.receipt_sha256
    # A digest binds the changed claim, without authenticating either author.
    assert synthetic.model_dump(exclude={"claimed_provenance", "receipt_sha256"}) == (
        external.model_dump(exclude={"claimed_provenance", "receipt_sha256"})
    )


@pytest.mark.parametrize("value", [None, {}, [], True, "{}", "not-json"])
def test_missing_malformed_receipt_is_safe(value, tmp_path):
    with pytest.raises(runtime.SourceError, match="^invalid_source_receipt$"):
        runtime.verify_source(value, harness_root=tmp_path, application_root=tmp_path)


@pytest.mark.parametrize(
    "change",
    [
        {"schema_id": "other"},
        {"scope": "live"},
        {"approval_reference": ""},
        {"provenance": "self-approved"},
        {"execution_profile": "judge"},
        {"api_key": "synthetic-sensitive-marker"},
        {"source_authorised": True},
        {"authorises_live_execution": True},
        {"harness_lock_sha256": "bad"},
        {"application_lock_sha256": "bad"},
        {"runtime": {}},
        {"binding": {}},
        {"harness": {"commit": "bad", "tree": "bad"}},
    ],
)
def test_bad_receipt_fields_do_not_echo_values(receipt, change):
    with pytest.raises(runtime.SourceError, match="^invalid_source_receipt$") as error:
        runtime.parse_receipt(receipt.model_copy(update=change))
    assert "synthetic-sensitive-marker" not in str(error.value)
    assert error.value.__suppress_context__


@pytest.mark.parametrize("provenance", ["synthetic-test", "external-review"])
@pytest.mark.parametrize(
    ("field", "change", "error"),
    [
        (
            "harness",
            runtime.GitIdentity(commit="0" * 40, tree="b" * 40),
            "harness_identity_mismatch",
        ),
        (
            "harness",
            runtime.GitIdentity(commit="a" * 40, tree="0" * 40),
            "harness_identity_mismatch",
        ),
        (
            "application",
            runtime.GitIdentity(commit="0" * 40, tree="c" * 40),
            "application_identity_mismatch",
        ),
        (
            "application",
            runtime.GitIdentity(commit=runtime.APPLICATION_REVISION, tree="0" * 40),
            "application_identity_mismatch",
        ),
        ("fixtures", (), "fixture_identity_mismatch"),
        ("harness_lock", "0" * 64, "dependency_lock_mismatch"),
        ("application_lock", "0" * 64, "dependency_lock_mismatch"),
    ],
)
def test_source_identity_mismatches(
    receipt, observed, field, change, error, provenance
):
    receipt = runtime.parse_receipt(
        receipt.model_copy(update={"provenance": provenance})
    )
    with pytest.raises(runtime.SourceError, match="^" + error + "$"):
        runtime._check_observation(receipt, observed.model_copy(update={field: change}))


def test_receipt_cannot_override_pinned_application(receipt, observed):
    wrong = runtime.GitIdentity(commit="f" * 40, tree="c" * 40)
    with pytest.raises(runtime.SourceError, match="application_identity_mismatch"):
        runtime._check_observation(
            receipt.model_copy(update={"application": wrong}),
            observed.model_copy(update={"application": wrong}),
        )


def test_receipt_cannot_mix_definition(receipt, observed):
    changed = receipt.binding.model_copy(update={"execution_policy": "different"})
    with pytest.raises(runtime.SourceError, match="definition_binding_mismatch"):
        runtime.validate_binding(
            runtime.parse_receipt(
                receipt.model_copy(update={"binding": changed})
            ).binding
        )


def test_runtime_mismatch(receipt, observed):
    altered = observed.runtime.model_copy(update={"python": "3.12.99"})
    with pytest.raises(runtime.SourceError, match="runtime_identity_mismatch"):
        runtime._check_observation(
            receipt, observed.model_copy(update={"runtime": altered})
        )


@pytest.mark.parametrize(
    ("version", "lock", "profile", "allowed"),
    [
        ("3.12.13", "harness", "offline-verification-v1", True),
        ("3.13.9", "application", "offline-verification-v1", True),
        ("3.13.9", "application", "target-only-canary-v3", True),
        ("3.12.13", "application", "offline-verification-v1", False),
        ("3.13.9", "harness", "offline-verification-v1", False),
        ("3.12.13", "harness", "target-only-canary-v3", False),
    ],
)
def test_supported_runtime_profiles(receipt, observed, version, lock, profile, allowed):
    identity = receipt.runtime.model_copy(
        update={"python": version, "dependency_lock": lock}
    )
    approved = receipt.model_copy(
        update={"runtime": identity, "execution_profile": profile}
    )
    actual = observed.model_copy(update={"runtime": identity})
    if allowed:
        runtime._check_observation(approved, actual)
    else:
        with pytest.raises(runtime.SourceError, match="unsupported_execution_profile"):
            runtime._check_observation(approved, actual)


def test_clean_git_observation_is_read_only(repository):
    before = (repository / ".git/index").read_bytes()
    actual = runtime._git_identity(repository)
    assert actual.commit == git(repository, "rev-parse", "HEAD")
    assert actual.tree == git(repository, "rev-parse", "HEAD^{tree}")
    assert (repository / ".git/index").read_bytes() == before
    assert git(repository, "status", "--porcelain") == ""


def test_genuine_git_linked_worktree_accepted(repository, tmp_path):
    linked = tmp_path / "linked"
    git(repository, "worktree", "add", "--detach", str(linked), "HEAD")
    assert (linked / ".git").is_file()
    assert runtime._git_identity(linked) == runtime._git_identity(repository)


@pytest.mark.parametrize(
    "kind",
    ["working", "index", "assume-unchanged", "skip-worktree", "executable", "deleted"],
)
def test_git_rejects_source_changes_including_hidden_edits(repository, kind):
    source = repository / "src/example.py"
    if kind in ("assume-unchanged", "skip-worktree"):
        git(repository, "update-index", "--" + kind, "src/example.py")
    if kind == "executable":
        source.chmod(0o755)
    elif kind == "deleted":
        source.unlink()
    else:
        source.write_text("VALUE = 2\n")
    if kind == "index":
        git(repository, "add", "src/example.py")
    with pytest.raises(runtime.SourceError):
        runtime._git_identity(repository)


@pytest.mark.parametrize(
    "name",
    [
        "src/new.py",
        "notes.txt",
        "src/ignored/hidden.py",
        "src/orphan.pyc",
        "src/ignored/config.json",
        "src/__pycache__/hidden.py",
    ],
)
def test_git_rejects_untracked_even_ignored_source(repository, name):
    path = repository / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("synthetic\n")
    with pytest.raises(runtime.SourceError, match="unexpected_untracked"):
        runtime._git_identity(repository)


def test_tracked_symlinks_rejected(repository):
    (repository / "src/link.py").symlink_to("example.py")
    git(repository, "add", "src/link.py")
    git(repository, "commit", "-qm", "Synthetic symlink")
    with pytest.raises(runtime.SourceError, match="unsupported_source_entry"):
        runtime._git_identity(repository)


def test_source_nested_root_and_symlink_indirection_rejected(repository, tmp_path):
    with pytest.raises(runtime.SourceError, match="unexpected_git_root"):
        runtime._git_identity(repository / "src")
    (repository / "alias.py").symlink_to(repository / "src/example.py")
    with pytest.raises(runtime.SourceError, match="source_path_indirection"):
        runtime._regular_file(repository, "alias.py")
    with pytest.raises(runtime.SourceError, match="source_path_indirection"):
        runtime._regular_file(repository, "../outside")


def test_git_errors_do_not_expose_external_diagnostics(tmp_path):
    with pytest.raises(runtime.SourceError, match="^git_identity_unavailable$"):
        runtime._git_identity(tmp_path)


def test_module_origins_match_only_current_harness_checkout(tmp_path):
    root = Path(runtime.__file__).resolve().parents[3]
    runtime._module_origins(root, tmp_path)
    with pytest.raises(runtime.SourceError, match="unexpected_module_origin"):
        runtime._module_origins(tmp_path, tmp_path)


def test_public_verifier_cannot_approve_wrong_import_origin(receipt, tmp_path):
    with pytest.raises(runtime.SourceError, match="unexpected_module_origin"):
        runtime.verify_source(receipt, harness_root=tmp_path, application_root=tmp_path)


def test_clean_public_verifier_with_synthetic_receipt_and_optional_pinned_app(tmp_path):
    """Complete composition test, optional only because the real app is external.

    The harness approval names a temporary synthetic commit, never the actual
    implementation worktree. The real pinned application is inspected read-only.
    The child receives no ambient configuration/credentials and cannot network.
    """
    if sys.version_info[:2] != (3, 13):
        pytest.skip(
            "Complete source check requires the optional pinned CPython 3.13 worker"
        )
    spec = importlib.util.find_spec("salesagent")
    if spec is None or spec.origin is None:
        pytest.skip(
            "Complete source check requires the optional pinned Sales Agent checkout"
        )
    application_root = Path(spec.origin).resolve().parents[2]
    root = tmp_path / "synthetic-harness"
    root.mkdir()
    original = Path(runtime.__file__).resolve().parents[3]
    shutil.copytree(
        original / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copyfile(original / "uv.lock", root / "uv.lock")
    (root / ".gitignore").write_text("__pycache__/\n*.pyc\n")
    git(root, "init", "-q")
    git(root, "config", "user.name", "Synthetic Test")
    git(root, "config", "user.email", "synthetic@example.invalid")
    git(root, "add", ".")
    git(root, "commit", "-qm", "Synthetic receipt test only")
    program = """
import sys
from pathlib import Path
from hashlib import sha256
def guard(event, arguments):
    if event.startswith("socket."):
        raise AssertionError("Network construction forbidden")
    if event == "import" and arguments[0].split(".")[0] in ("openai", "salesagent", "uvicorn"):
        raise AssertionError("SDK/application construction forbidden")
sys.addaudithook(guard)
from harness.canary import runtime_v3 as r
harness, application = map(Path, sys.argv[1:])
binding = r.resolve_definition(r.V3)
receipt = r.SourceApprovalReceipt(
    schema_id="canary-source-approval-v1", scope="source-only",
    approval_reference="synthetic:temporary-git-test-only", provenance="synthetic-test",
    execution_profile="target-only-canary-v3",
    harness=r._git_identity(harness), application=r._git_identity(application),
    binding=binding,
    harness_lock_sha256=sha256((harness / "uv.lock").read_bytes()).hexdigest(),
    application_lock_sha256=sha256((application / "uv.lock").read_bytes()).hexdigest(),
    runtime=r._runtime("application"),
)
for provenance in ("synthetic-test", "external-review"):
    claimed = receipt.model_copy(update={"provenance": provenance})
    result = r.verify_source(claimed.model_dump_json(), harness_root=harness, application_root=application)
    assert result.source_matches_receipt is True
    assert result.claimed_provenance == provenance
    assert result.source_authorised is False
    assert result.authorises_live_execution is False
assert "salesagent" not in sys.modules
assert "openai" not in sys.modules
print("synthetic-source-match; no-source-approval; no-live-authority")
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", program, str(root), str(application_root)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
        env={"PATH": os.defpath, "PYTHONPATH": str(root / "src")},
    )
    assert (
        result.stdout.strip()
        == "synthetic-source-match; no-source-approval; no-live-authority"
    )
    assert result.stderr == ""
    assert git(root, "status", "--porcelain") == ""


def test_dependency_lock_installed_versions(tmp_path):
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname="pydantic"\nversion="0.0.0"\nsource={registry="synthetic.invalid"}\n'
    )
    with pytest.raises(runtime.SourceError, match="installed_dependency_mismatch"):
        runtime._dependencies(tmp_path)


def test_dependency_check_matches_selected_harness_lock_only():
    runtime._dependencies(Path(runtime.__file__).resolve().parents[3])


@pytest.mark.parametrize("provenance", ["synthetic-test", "external-review"])
@pytest.mark.parametrize(
    "authority_field", ["source_authorised", "authorises_live_execution"]
)
def test_source_result_cannot_grant_authority(receipt, provenance, authority_field):
    values = {
        "receipt_sha256": "0" * 64,
        "approval_reference": receipt.approval_reference,
        "claimed_provenance": provenance,
        "binding": receipt.binding,
        "harness": receipt.harness,
        "application": receipt.application,
        "runtime": receipt.runtime,
    }
    result = runtime.SourceVerification(**values)
    assert result.source_authorised is False
    assert result.authorises_live_execution is False
    with pytest.raises(ValidationError):
        runtime.SourceVerification(**values, **{authority_field: True})
    with pytest.raises(ValidationError):
        setattr(result, authority_field, True)


def test_c1_source_gate_and_protected_files_remain_exact():
    root = Path(runtime.__file__).resolve().parents[3]
    protected = (
        "controller.py",
        "driver.py",
        "recording.py",
        "inputs.py",
        "acceptance.py",
        "selection_v3.py",
        "selection_acceptance.py",
        "execution_policy.py",
    )
    for name in protected:
        relative = "src/harness/canary/" + name
        assert (
            sha256((root / relative).read_bytes()).hexdigest()
            == sha256(
                subprocess.check_output(
                    ["git", "-C", str(root), "show", "HEAD:" + relative]
                )
            ).hexdigest()
        )
    from harness.canary.controller import _harness_revision

    source = inspect.getsource(_harness_revision)
    assert "C3A_FILES" in source
    assert "runtime_v3" not in source


def test_import_and_resolution_never_construct_network_sdk_or_read_credentials(
    tmp_path,
):
    """Fresh process: detect activity, not merely a pre-existing import cache."""
    root = Path(runtime.__file__).resolve().parents[3]
    program = """
import sys
def guard(event, arguments):
    if event.startswith("socket.") or event in ("subprocess.Popen", "os.system"):
        raise AssertionError("I/O construction forbidden")
    if event == "import" and arguments[0].split(".")[0] in ("openai", "salesagent", "uvicorn"):
        raise AssertionError("External SDK/application import forbidden")
sys.addaudithook(guard)
import os
class NoCredentials(dict):
    def __getitem__(self, key):
        if key.startswith(("OPENAI_", "SALESAGENT_")):
            raise AssertionError("Credential/config inspection forbidden")
        return super().__getitem__(key)
    def get(self, key, default=None):
        if key.startswith(("OPENAI_", "SALESAGENT_")):
            raise AssertionError("Credential/config inspection forbidden")
        return super().get(key, default)
os.environ = NoCredentials(os.environ)
from harness.canary.runtime_v3 import resolve_definition, V3
assert not resolve_definition().authorises_live_execution
assert not resolve_definition(V3).authorises_live_execution
print("offline-only")
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", program],
        cwd=tmp_path,
        env={"PATH": os.defpath, "PYTHONPATH": str(root / "src")},
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout.strip() == "offline-only"
    assert result.stderr == ""


def test_no_live_controller_or_provider_factory_interface():
    names = set(vars(runtime))
    assert not names & {
        "TargetCanaryController",
        "CanaryStore",
        "OpenAI",
        "ProviderTransport",
        "run_target",
        "run_judge",
        "issue_receipt",
    }
    assert importlib.util.find_spec("harness.canary.runtime_v3") is not None
    assert (
        json.loads(runtime.resolve_definition().model_dump_json())[
            "authorises_live_execution"
        ]
        is False
    )
