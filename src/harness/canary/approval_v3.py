"""Synthetic signature verification only: no consumption or execution authority.

Trust policy, expected proposal, clock, system verifier and Python process are
trusted inputs. No source observation, human enrolment, signing, credential
discovery, provider I/O, journal access or persistent replay registry occurs here.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from harness.canary.runtime_v3 import (
    APPLICATION_REVISION,
    V3,
    Digest,
    Frozen,
    SourceApprovalReceipt,
    _plain,
    validate_binding,
)
from harness.core.fingerprints import canonical_json, fingerprint

APPROVAL_NAMESPACE = "canary-approval-v3@ai-test-harness.invalid"
APPROVAL_ROLE = "synthetic-canary-approver"
_SSH_KEYGEN = "/usr/bin/ssh-keygen"
_MAX_PAYLOAD = 65536
_MAX_SIGNATURE = 4096

AuthorisationID = Annotated[str, Field(pattern=r"^synthetic-auth-[0-9a-f]{32}$")]
Audience = Annotated[str, Field(pattern=r"^synthetic-[a-z0-9][a-z0-9._-]{0,95}$")]
Principal = Annotated[
    str, Field(pattern=r"^synthetic-[a-z0-9][a-z0-9._-]{0,63}@canary\.invalid$")
]
Timestamp = Annotated[
    str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
]
ProvisioningReference = Annotated[
    str, Field(pattern=r"^synthetic-provisioning-[a-z0-9][a-z0-9._-]{0,63}$")
]


class ApprovalError(ValueError):
    """Only fixed categories may cross the public verification boundary."""

    def __init__(self, code: str):
        allowed = {
            "invalid_manifest",
            "noncanonical_manifest",
            "invalid_expected_proposal",
            "invalid_trust_policy",
            "principal_mismatch",
            "role_not_authorised",
            "signer_revoked",
            "execution_binding_mismatch",
            "invalid_verification_time",
            "approval_not_yet_valid",
            "approval_expired",
            "validity_window_exceeded",
            "invalid_signature",
            "signature_not_verified",
            "verifier_unavailable",
            "verifier_protocol_error",
            "verification_storage_unavailable",
        }
        super().__init__(code if code in allowed else "invalid_manifest")


def _time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


class ProposedCanary(Frozen):
    """An exact proposed configuration, never an observed or admitted execution.

    The receipt embeds commit/tree, locks, runtime and DefinitionBinding. That
    binding embeds all roster/policy/fixture/inference/limit identities, including
    decimal strings. The explicit digest must agree; no second editable copy of
    those settings is introduced. All identities here are synthetic assertions.
    """

    authorisation_id: AuthorisationID
    execution_audience: Audience
    source_receipt: SourceApprovalReceipt
    source_receipt_sha256: Digest
    project_id: Annotated[
        str, Field(pattern=r"^proj_synthetic_[a-z0-9][a-z0-9_]{0,63}$")
    ]
    organization_id: Annotated[
        str, Field(pattern=r"^org_synthetic_[a-z0-9][a-z0-9_]{0,63}$")
    ]
    credential_provisioning_reference: ProvisioningReference | None

    @model_validator(mode="after")
    def _consistent(self) -> ProposedCanary:
        receipt = self.source_receipt
        validate_binding(receipt.binding)
        worker = receipt.runtime.dependency_lock == "application"
        if (
            receipt.binding.identifier != V3
            or receipt.provenance != "synthetic-test"
            or receipt.execution_profile != "offline-verification-v1"
            or receipt.application.commit != APPLICATION_REVISION
            or not receipt.runtime.python.startswith("3.13." if worker else "3.12.")
            or self.source_receipt_sha256
            != fingerprint(receipt.model_dump(mode="json"))
        ):
            raise ValueError("inconsistent_synthetic_proposal")
        return self


class ApprovalManifest(Frozen):
    schema_id: Literal["canary-synthetic-approval-v1"]
    purpose: Literal["synthetic-offline-target-only-canary-v3"]
    environment: Literal["synthetic-offline"]
    signature_namespace: Literal["canary-approval-v3@ai-test-harness.invalid"]
    execution: ProposedCanary
    issuer_principal: Principal
    created_at: Timestamp
    not_before: Timestamp
    expires_at: Timestamp
    judge_authority: Literal[False]
    study_authority: Literal[False]
    replacement_authority: Literal[False]
    resume_authority: Literal[False]
    authorises_live_execution: Literal[False]

    @model_validator(mode="after")
    def _ordered_times(self) -> ApprovalManifest:
        created, start, end = map(
            _time, (self.created_at, self.not_before, self.expires_at)
        )
        if not created <= start < end or end - created > timedelta(hours=1):
            raise ValueError("invalid_approval_time_window")
        return self


def _key_blob(public_key: str) -> bytes:
    """Accept one canonical Ed25519 public key, without comments or options."""
    if not isinstance(public_key, str) or len(public_key) > 128:
        raise ValueError("invalid_synthetic_public_key")
    algorithm, separator, encoded = public_key.partition(" ")
    if algorithm != "ssh-ed25519" or separator != " ":
        raise ValueError("invalid_synthetic_public_key")
    blob = base64.b64decode(encoded, validate=True)
    if (
        base64.b64encode(blob).decode("ascii") != encoded
        or len(blob) != 51
        or blob[:19] != b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"
    ):
        raise ValueError("invalid_synthetic_public_key")
    return blob


class SyntheticTrustPolicy(Frozen):
    """One explicitly enrolled test key; no ambient key or signer discovery.

    Roles, revocations and maximum lifetime come from the trusted caller, never
    from the signed manifest. Revocation is only relative to this supplied policy.
    """

    schema_id: Literal["canary-synthetic-trust-v1"]
    policy_id: Annotated[
        str, Field(pattern=r"^synthetic-policy-[a-z0-9][a-z0-9._-]{0,63}$")
    ]
    expected_principal: Principal
    public_key: str
    roles: tuple[Annotated[str, Field(pattern=r"^synthetic-[a-z][a-z-]{0,63}$")], ...]
    revoked_public_keys: tuple[str, ...] = Field(default=(), max_length=32)
    max_validity_seconds: int = Field(default=3600, ge=1, le=3600)
    assurance_class: Literal["synthetic-offline-only"] = "synthetic-offline-only"

    @model_validator(mode="after")
    def _keys(self) -> SyntheticTrustPolicy:
        for key in (self.public_key, *self.revoked_public_keys):
            _key_blob(key)
        if len(set(self.roles)) != len(self.roles) or len(
            set(self.revoked_public_keys)
        ) != len(self.revoked_public_keys):
            raise ValueError("duplicate_synthetic_policy_entry")
        return self


class ApprovalVerification(Frozen):
    schema_id: Literal["canary-synthetic-approval-verification-v1"]
    payload_sha256: Digest
    signature_sha256: Digest
    trust_policy_sha256: Digest
    source_receipt_sha256: Digest
    authorisation_id: AuthorisationID
    execution_audience: Audience
    signer_principal: Principal
    signer_public_key_sha256: Digest
    verified_at: Timestamp
    payload_structurally_valid: Literal[True] = True
    signature_cryptographically_verified: Literal[True] = True
    signer_matches_synthetic_policy: Literal[True] = True
    required_role_verified: Literal[True] = True
    purpose_and_execution_bindings_match: Literal[True] = True
    time_valid: Literal[True] = True
    revocation_status: Literal["not_revoked_under_supplied_policy"] = (
        "not_revoked_under_supplied_policy"
    )
    assurance_class: Literal["synthetic-offline-only"] = "synthetic-offline-only"
    real_human_authorisation_authenticated: Literal[False] = False
    source_authorised: Literal[False] = False
    provider_evidence_authenticated: Literal[False] = False
    authorises_live_execution: Literal[False] = False


def _checked[Model: Frozen](model: type[Model], value: object, code: str) -> Model:
    try:
        # Revalidate nested constructed/copied models and preserve unknown fields.
        plain = _plain(value)
        checked = model.model_validate(plain)
        if canonical_json(plain) != canonical_json(checked.model_dump(mode="json")):
            raise ValueError
        return checked
    except Exception:  # noqa: BLE001 - external inputs never enter diagnostics
        raise ApprovalError(code) from None


def serialize_manifest(manifest: ApprovalManifest) -> bytes:
    """Create canonical bytes for a synthetic proposal; never sign or save it."""
    checked = _checked(ApprovalManifest, manifest, "invalid_manifest")
    raw = canonical_json(checked.model_dump(mode="json")).encode("utf-8")
    if len(raw) > _MAX_PAYLOAD:
        raise ApprovalError("invalid_manifest")
    return raw


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def parse_manifest(payload: bytes) -> ApprovalManifest:
    """Require exact canonical UTF-8 JSON bytes; never repair signed content."""
    if type(payload) is not bytes or not 0 < len(payload) <= _MAX_PAYLOAD:
        raise ApprovalError("invalid_manifest")
    try:
        plain = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique)
        if canonical_json(plain).encode("utf-8") != payload:
            raise ApprovalError("noncanonical_manifest")
        # JSON mode permits arrays for immutable tuples, but no scalar coercion.
        manifest = ApprovalManifest.model_validate_json(payload)
        if canonical_json(manifest.model_dump(mode="json")).encode("utf-8") != payload:
            raise ApprovalError("invalid_manifest")
        return manifest
    except ApprovalError:
        raise
    except Exception:  # noqa: BLE001 - malformed payloads remain private
        raise ApprovalError("invalid_manifest") from None


def _private_file(directory: Path, name: str, data: bytes) -> Path:
    path = directory / name
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
    return path


def _verify_signature(
    payload: bytes, signature: bytes, policy: SyntheticTrustPolicy
) -> None:
    if type(signature) is not bytes or not 0 < len(signature) <= _MAX_SIGNATURE:
        raise ApprovalError("invalid_signature")
    try:
        with tempfile.TemporaryDirectory(prefix="canary-approval-synthetic-") as temp:
            directory = Path(temp)
            allowed = _private_file(
                directory,
                "allowed-signers",
                (
                    f'{policy.expected_principal} namespaces="{APPROVAL_NAMESPACE}" '
                    f"{policy.public_key}\n"
                ).encode("ascii"),
            )
            detached = _private_file(directory, "approval.sig", signature)
            revoked = _private_file(
                directory,
                "revoked-keys",
                "".join(key + "\n" for key in policy.revoked_public_keys).encode(
                    "ascii"
                ),
            )
            try:
                completed = subprocess.run(
                    [
                        _SSH_KEYGEN,
                        "-Y",
                        "verify",
                        "-f",
                        str(allowed),
                        "-I",
                        policy.expected_principal,
                        "-n",
                        APPROVAL_NAMESPACE,
                        "-s",
                        str(detached),
                        "-r",
                        str(revoked),
                    ],
                    input=payload,
                    capture_output=True,
                    check=False,
                    timeout=5,
                    cwd=directory,
                    env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C"},
                )
            except (OSError, subprocess.SubprocessError):
                raise ApprovalError("verifier_unavailable") from None
            if completed.returncode != 0:
                raise ApprovalError(
                    "signer_revoked"
                    if policy.public_key in policy.revoked_public_keys
                    else "signature_not_verified"
                )
            key_digest = base64.b64encode(sha256(_key_blob(policy.public_key)).digest())
            expected = (
                f'Good "{APPROVAL_NAMESPACE}" signature for {policy.expected_principal} '
                f"with ED25519 key SHA256:{key_digest.decode('ascii').rstrip('=')}\n"
            ).encode("ascii")
            if (
                completed.stdout != expected
                or completed.stderr != b""
                or policy.public_key in policy.revoked_public_keys
            ):
                raise ApprovalError("verifier_protocol_error")
    except ApprovalError:
        raise
    except Exception:  # noqa: BLE001 - paths/signatures/subprocess output stay private
        raise ApprovalError("verification_storage_unavailable") from None


def verify_approval(
    payload: bytes,
    signature: bytes,
    *,
    expected: ProposedCanary,
    trust_policy: SyntheticTrustPolicy,
    now: datetime,
) -> ApprovalVerification:
    """Authenticate only a synthetic proposal, without consuming its identifier.

    Repeated verification is intentionally possible. The returned data is not an
    admission token and cannot establish actual source matching or real identity.
    """
    manifest = parse_manifest(payload)
    proposal = _checked(ProposedCanary, expected, "invalid_expected_proposal")
    policy = _checked(SyntheticTrustPolicy, trust_policy, "invalid_trust_policy")
    if manifest.issuer_principal != policy.expected_principal:
        raise ApprovalError("principal_mismatch")
    if APPROVAL_ROLE not in policy.roles:
        raise ApprovalError("role_not_authorised")
    if manifest.execution != proposal:
        raise ApprovalError("execution_binding_mismatch")
    if type(now) is not datetime or now.utcoffset() != timedelta(0) or now.microsecond:
        raise ApprovalError("invalid_verification_time")
    if now < _time(manifest.not_before):
        raise ApprovalError("approval_not_yet_valid")
    if now >= _time(manifest.expires_at):
        raise ApprovalError("approval_expired")
    if _time(manifest.expires_at) - _time(manifest.created_at) > timedelta(
        seconds=policy.max_validity_seconds
    ):
        raise ApprovalError("validity_window_exceeded")
    _verify_signature(payload, signature, policy)
    return ApprovalVerification(
        schema_id="canary-synthetic-approval-verification-v1",
        payload_sha256=sha256(payload).hexdigest(),
        signature_sha256=sha256(signature).hexdigest(),
        trust_policy_sha256=fingerprint(policy.model_dump(mode="json")),
        source_receipt_sha256=proposal.source_receipt_sha256,
        authorisation_id=proposal.authorisation_id,
        execution_audience=proposal.execution_audience,
        signer_principal=policy.expected_principal,
        signer_public_key_sha256=sha256(_key_blob(policy.public_key)).hexdigest(),
        verified_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
