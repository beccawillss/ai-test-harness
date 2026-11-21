"""Immutable selection and read-only source checks, without live authority.

Receipts contain unauthenticated claims. Matching source or a receipt digest
does not authenticate its author or establish approval. Source authorisation is
unavailable in Slice 1. No receipt issuer, live approval, controller, provider,
reservation or recovery API belongs here.
"""

from __future__ import annotations

import importlib.metadata
import os
import platform
import stat
import subprocess
import sys
import tomllib
from hashlib import sha1, sha256
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from harness.core.fingerprints import fingerprint

C1 = "salesagent-canary-c1-v1"
V3 = "salesagent-canary-selected-preferences-v3"
V2_FINGERPRINT = "3c632f6ce5e8b9eda42b4a0a0f91ccb82f4f34783da3b9638762b84351c9c2f9"
V3_FINGERPRINTS = (
    "564b98533b5b48b13d7d97fec8c150c329a6bf5d7ed38f0f165bae32a8493e17",
    "e76fd0e10f1176d6aa421a2b5de93f9503dceaa422b0631c2c8f7c957aa75607",
    "575e304da8203b537d281d82a667e73dbf419fc95caee8df82dea6e7feabfce7",
    "a4d8cdaaa4960ddf406c37703965d164595cea320cfa83c0ddd40fad797fa551",
)
APPLICATION_REVISION = "3320e556540d3f95bee1e8509f13e558ce266b6c"
FIXTURE_HASHES = (
    (
        "products.json",
        "70960848556e1e63c1bd3337203ab057a9fae1e7f6d343fb383f85a838c541ab",
    ),
    (
        "discounts.json",
        "3147b6863b9458c928459cbb824d01b0e3b73aa2c5da2979debb78de4e1caf0c",
    ),
)
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Revision = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
Reference = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")]


class SourceError(ValueError):
    """Only fixed diagnostic codes; never echo receipt or subprocess content."""


class Frozen(BaseModel):
    model_config = ConfigDict(
        frozen=True, strict=True, extra="forbid", hide_input_in_errors=True
    )


class Turn(Frozen):
    slot: str
    conversation: str
    message: str


class Inference(Frozen):
    model: str = "gpt-5.6-terra"
    reasoning_effort: str = "low"
    max_output_tokens: int = 2000
    timeout_seconds: int = 30
    sdk_retries: int = 2
    # Absence is deliberate: preserve the target's existing request settings.
    temperature: None = None
    cache_retention_override: None = None


class Limits(Frozen):
    shopper_posts: int = 4
    logical_calls_per_turn: int = 6
    logical_calls_total: int = 24
    attempts_per_call: int = 3
    provider_attempts_total: int = 72
    target_allowance_usd: str = "3"
    contingency_usd: str = "2"
    estimated_pause_usd: str = "5"
    project_monthly_limit_usd: str = "10"
    alerts_usd: tuple[str, ...] = ("2", "4", "5")


class DefinitionBinding(Frozen):
    identifier: str
    turns: tuple[Turn, ...]
    roster_fingerprint: Digest
    # Historical C1 has no separately versioned definition/execution policy.
    definition_fingerprint: Digest | None
    acceptance_policy: str
    acceptance_fingerprint: Digest
    execution_policy: str | None
    execution_fingerprint: Digest | None
    v2_1_fingerprint: Digest
    application_revision: Revision
    fixture_hashes: tuple[tuple[str, Digest], ...]
    inference: Inference
    limits: Limits
    storage_schema: str
    scope: Literal["target-only"] = "target-only"
    authorises_live_execution: Literal[False] = False


def resolve_definition(identifier: str | None = None) -> DefinitionBinding:
    """Exact opt-in only. Imports prepare metadata, never execute a judge."""
    selected = C1 if identifier is None else identifier
    if selected not in (C1, V3):
        raise SourceError("unknown_definition")
    from harness.canary import acceptance, inputs

    v2 = acceptance.policy_fingerprint()
    if (
        v2 != V2_FINGERPRINT
        or inputs.TARGET_REVISION != APPLICATION_REVISION
        or inputs.TARGET_MODEL != Inference().model
    ):
        raise SourceError("dependency_identity_mismatch")
    turns: tuple[inputs.ShopperTurn, ...]
    if selected == C1:
        roster = inputs.roster_hash()
        policy = acceptance.policy_fingerprint(C1)
        if (
            roster != "e8778ce74a270e6efbe490198d01e8b9c50bcc43387a02bff5f00b42304d5794"
            or policy
            != "646fd93488667251a67a02d98548e1aface9353d2a4bb7594a7343d664f1aa65"
        ):
            raise SourceError("historical_identity_mismatch")
        turns = inputs.TARGET_TURNS
        definition = execution = execution_policy = None
        acceptance_policy = C1
        storage = "nonstudy-canary-v1"
    else:
        from harness.canary import execution_policy as execution_module
        from harness.canary import selection_acceptance, selection_v3

        roster = selection_v3.roster_fingerprint()
        definition = selection_v3.definition_fingerprint()
        policy = selection_acceptance.acceptance_fingerprint()
        execution = execution_module.execution_fingerprint()
        if (roster, definition, policy, execution) != V3_FINGERPRINTS or (
            selection_v3.DEFINITION != V3
            or selection_acceptance.ACCEPTANCE_POLICY
            != "salesagent-canary-selection-v3"
            or execution_module.EXECUTION_POLICY
            != "salesagent-canary-behavioural-continuation-v1"
        ):
            raise SourceError("v3_identity_mismatch")
        turns = selection_v3.TURNS
        acceptance_policy = selection_acceptance.ACCEPTANCE_POLICY
        execution_policy = execution_module.EXECUTION_POLICY
        # Reserved namespace only; no journal/schema writer is implemented.
        storage = "nonstudy-canary-v3-reserved-v1"
    return DefinitionBinding(
        identifier=selected,
        turns=tuple(Turn(**vars(t)) for t in turns),
        roster_fingerprint=roster,
        definition_fingerprint=definition,
        acceptance_policy=acceptance_policy,
        acceptance_fingerprint=policy,
        execution_policy=execution_policy,
        execution_fingerprint=execution,
        v2_1_fingerprint=v2,
        application_revision=APPLICATION_REVISION,
        fixture_hashes=FIXTURE_HASHES,
        inference=Inference(),
        limits=Limits(),
        storage_schema=storage,
    )


def validate_binding(binding: DefinitionBinding) -> None:
    """Recompute every identity; reject partial/mixed or manually copied models."""
    try:
        checked = DefinitionBinding.model_validate(_plain(binding))
    except (ValidationError, ValueError, TypeError):
        raise SourceError("invalid_definition_binding") from None
    if checked != resolve_definition(checked.identifier):
        raise SourceError("definition_binding_mismatch")


class GitIdentity(Frozen):
    commit: Revision
    tree: Revision


class RuntimeIdentity(Frozen):
    implementation: Literal["CPython"]
    python: Annotated[str, Field(pattern=r"^3\.(12|13)\.[0-9]+$")]
    system: Literal["Darwin", "Linux"]
    machine: Literal["arm64", "aarch64", "x86_64"]
    dependency_lock: Literal["harness", "application"]


class SourceApprovalReceipt(Frozen):
    schema_id: Literal["canary-source-approval-v1"]
    scope: Literal["source-only"]
    approval_reference: Reference
    # Caller-supplied claim only, including "external-review"; never authenticated.
    provenance: Literal["synthetic-test", "external-review"]
    execution_profile: Literal["offline-verification-v1", "target-only-canary-v3"]
    harness: GitIdentity
    application: GitIdentity
    binding: DefinitionBinding
    harness_lock_sha256: Digest
    application_lock_sha256: Digest
    runtime: RuntimeIdentity


def parse_receipt(value: object) -> SourceApprovalReceipt:
    """Accept a strict model, JSON string or mapping. Never inspect a file/env."""
    try:
        if isinstance(value, str):
            return SourceApprovalReceipt.model_validate_json(value)
        # Revalidate even model instances: model_copy/model_construct bypass validation.
        return SourceApprovalReceipt.model_validate(_plain(value))
    except (ValidationError, ValueError, TypeError):
        raise SourceError("invalid_source_receipt") from None


def _plain(value: object) -> object:
    # Preserve unexpected fields on validation-bypassing model copies. Using a
    # serializer would silently drop these and can emit sensitive input warnings.
    if isinstance(value, BaseModel):
        return _plain({**vars(value), **(value.__pydantic_extra__ or {})})
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return tuple(_plain(v) for v in value)
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


class SourceVerification(Frozen):
    receipt_sha256: Digest
    # Both the reference and provenance remain unauthenticated receipt claims.
    approval_reference: Reference
    claimed_provenance: Literal["synthetic-test", "external-review"]
    binding: DefinitionBinding
    harness: GitIdentity
    application: GitIdentity
    runtime: RuntimeIdentity
    source_matches_receipt: Literal[True] = True
    # No authentication mechanism exists here. No receipt can establish approval.
    source_authorised: Literal[False] = False
    authorises_live_execution: Literal[False] = False


def _git(root: Path, *arguments: str) -> bytes:
    """No network, hooks, index refresh, filters, ambient Git overrides or stderr."""
    try:
        return subprocess.check_output(
            [
                "git",
                "--no-optional-locks",
                "-C",
                str(root),
                "-c",
                "core.fsmonitor=false",
                *arguments,
            ],
            stderr=subprocess.DEVNULL,
            env={
                "PATH": os.defpath,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_NO_REPLACE_OBJECTS": "1",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_TERMINAL_PROMPT": "0",
            },
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        raise SourceError("git_identity_unavailable") from None


def _regular_file(root: Path, relative: str) -> Path:
    path = root / relative
    if (
        not path.resolve().is_relative_to(root)
        or any(
            p.is_symlink()
            for p in (path, *path.parents)
            if p != root and p.is_relative_to(root)
        )
        or not path.is_file()
    ):
        raise SourceError("source_path_indirection")
    return path


def _git_identity(root: Path) -> GitIdentity:
    """Verify index and actual bytes, including edits hidden by index flags.

    Git status/diff filters are deliberately avoided; they can execute local
    commands. Submodules, symlinks and non-SHA1 repositories are unsupported.
    """
    root = root.resolve(strict=True)
    if (
        Path(os.fsdecode(_git(root, "rev-parse", "--show-toplevel")).strip()).resolve()
        != root
    ):
        raise SourceError("unexpected_git_root")
    identity = GitIdentity(
        commit=_git(root, "rev-parse", "HEAD").decode().strip(),
        tree=_git(root, "rev-parse", "HEAD^{tree}").decode().strip(),
    )
    tracked: dict[str, tuple[str, str]] = {}
    for item in _git(root, "ls-tree", "-r", "-z", "HEAD").split(b"\0"):
        if not item:
            continue
        metadata, name = item.decode().split("\t", 1)
        mode, kind, oid = metadata.split()
        if mode not in ("100644", "100755") or kind != "blob":
            raise SourceError("unsupported_source_entry")
        tracked[name] = (mode, oid)
    index: dict[str, tuple[str, str]] = {}
    for item in _git(root, "ls-files", "--stage", "-z").split(b"\0"):
        if not item:
            continue
        metadata, name = item.decode().split("\t", 1)
        mode, oid, stage = metadata.split()
        if stage != "0":
            raise SourceError("dirty_index")
        index[name] = (mode, oid)
    if index != tracked:
        raise SourceError("dirty_index")
    for name, (mode, oid) in tracked.items():
        path = _regular_file(root, name)
        content = path.read_bytes()
        actual = sha1(
            b"blob " + str(len(content)).encode() + b"\0" + content
        ).hexdigest()
        executable = bool(path.stat().st_mode & stat.S_IXUSR)
        if actual != oid or executable != (mode == "100755"):
            raise SourceError("dirty_worktree")
    if _git(root, "ls-files", "--others", "--exclude-standard", "-z"):
        raise SourceError("unexpected_untracked_files")
    # .gitignore must not hide source or configuration inside the package tree.
    source = root / "src"
    if source.exists():
        for path in source.rglob("*"):
            if path.is_symlink() or (
                path.is_file()
                and not (path.parent.name == "__pycache__" and path.suffix == ".pyc")
                and path.relative_to(root).as_posix() not in tracked
            ):
                raise SourceError("unexpected_untracked_source")
    return identity


def _module_origins(harness_root: Path, application_root: Path) -> None:
    """Inspect loaded modules only. Never import the app or consult credentials."""
    for name, module in tuple(sys.modules.items()):
        root = (
            harness_root
            if name == "harness" or name.startswith("harness.")
            else (
                application_root
                if name == "salesagent" or name.startswith("salesagent.")
                else None
            )
        )
        if root is None:
            continue
        package_root = root / "src" / name.split(".")[0]
        source = getattr(module, "__file__", None)
        spec = getattr(module, "__spec__", None)
        origin = getattr(spec, "origin", None)
        if (
            not isinstance(source, str)
            or not isinstance(origin, str)
            or Path(source).resolve() != Path(origin).resolve()
            or not Path(source).resolve().is_relative_to(package_root)
            or Path(source).suffix != ".py"
        ):
            raise SourceError("unexpected_module_origin")
        for path in getattr(module, "__path__", ()):
            if not Path(path).resolve().is_relative_to(package_root):
                raise SourceError("unexpected_module_origin")


def _runtime(lock: Literal["harness", "application"]) -> RuntimeIdentity:
    return RuntimeIdentity(
        implementation=platform.python_implementation(),  # type: ignore[arg-type]
        python=platform.python_version(),
        system=platform.system(),  # type: ignore[arg-type]
        machine=platform.machine(),  # type: ignore[arg-type]
        dependency_lock=lock,
    )


def _dependencies(root: Path) -> None:
    lock = tomllib.loads((root / "uv.lock").read_text())
    for package in lock["package"]:
        if "registry" not in package.get("source", {}) or package["name"] in {
            "colorama",
            "httpx2-jsfetch",
        }:
            continue  # Same POSIX exclusions as the approved worker verifier.
        if importlib.metadata.version(package["name"]) != package["version"]:
            raise SourceError("installed_dependency_mismatch")


class _Observation(Frozen):
    """Internal observations, not caller-supplied source authority."""

    harness: GitIdentity
    application: GitIdentity
    fixtures: tuple[tuple[str, Digest], ...]
    harness_lock: Digest
    application_lock: Digest
    runtime: RuntimeIdentity


def _check_observation(
    receipt: SourceApprovalReceipt, observed: _Observation
) -> SourceVerification:
    """Pure matching seam; the public verifier always collects its own facts."""
    if observed.harness != receipt.harness:
        raise SourceError("harness_identity_mismatch")
    if (
        observed.application != receipt.application
        or observed.application.commit != APPLICATION_REVISION
    ):
        raise SourceError("application_identity_mismatch")
    if observed.fixtures != receipt.binding.fixture_hashes:
        raise SourceError("fixture_identity_mismatch")
    if (observed.harness_lock, observed.application_lock) != (
        receipt.harness_lock_sha256,
        receipt.application_lock_sha256,
    ):
        raise SourceError("dependency_lock_mismatch")
    if observed.runtime != receipt.runtime:
        raise SourceError("runtime_identity_mismatch")
    worker = observed.runtime.dependency_lock == "application"
    if not observed.runtime.python.startswith("3.13." if worker else "3.12.") or (
        receipt.execution_profile == "target-only-canary-v3"
        and (receipt.binding.identifier != V3 or not worker)
    ):
        raise SourceError("unsupported_execution_profile")
    return SourceVerification(
        receipt_sha256=fingerprint(receipt.model_dump(mode="json")),
        approval_reference=receipt.approval_reference,
        claimed_provenance=receipt.provenance,
        binding=receipt.binding,
        harness=observed.harness,
        application=observed.application,
        runtime=observed.runtime,
    )


def verify_source(
    receipt: object, *, harness_root: Path, application_root: Path
) -> SourceVerification:
    """Check source matches only; neither authenticate approval nor enable execution.

    This is a point-in-time check in a trusted Python process, not a filesystem
    lock, cryptographic reviewer authentication or a hostile-process sandbox.
    Source authorisation requires a separately reviewed authentication mechanism.
    Future integration must also recheck before startup/dispatch and add separate
    live authority. No result from this function can replace the old C3a gate.
    """
    approved = parse_receipt(receipt)
    try:
        harness_root = harness_root.resolve(strict=True)
        application_root = application_root.resolve(strict=True)
        _module_origins(harness_root, application_root)
        validate_binding(approved.binding)
        before = (_git_identity(harness_root), _git_identity(application_root))
        observed = _Observation(
            harness=before[0],
            application=before[1],
            fixtures=tuple(
                (
                    name,
                    sha256(
                        _regular_file(application_root, "data/" + name).read_bytes()
                    ).hexdigest(),
                )
                for name, _ in FIXTURE_HASHES
            ),
            harness_lock=sha256(
                _regular_file(harness_root, "uv.lock").read_bytes()
            ).hexdigest(),
            application_lock=sha256(
                _regular_file(application_root, "uv.lock").read_bytes()
            ).hexdigest(),
            runtime=_runtime(approved.runtime.dependency_lock),
        )
        result = _check_observation(approved, observed)
        _dependencies(
            harness_root
            if approved.runtime.dependency_lock == "harness"
            else application_root
        )
        _module_origins(harness_root, application_root)
        validate_binding(approved.binding)
        if before != (_git_identity(harness_root), _git_identity(application_root)):
            raise SourceError("source_changed_during_verification")
        return result
    except SourceError:
        raise
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        importlib.metadata.PackageNotFoundError,
    ):
        raise SourceError("source_verification_failed") from None
