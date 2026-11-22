"""Actual OpenSSH signatures over synthetic proposals; never canary authority."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from harness.canary import approval_v3 as approval
from harness.canary import runtime_v3 as runtime
from harness.core.fingerprints import canonical_json, fingerprint

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
PRINCIPAL = "synthetic-operator@canary.invalid"
ENVIRONMENT = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C"}


@dataclass(frozen=True)
class SyntheticKeys:
    directory: Path
    primary: Path
    unknown: Path
    public_key: str
    unknown_public_key: str

    def sign(self, payload: bytes, *, unknown: bool = False, namespace=None) -> bytes:
        result = subprocess.run(
            [
                "/usr/bin/ssh-keygen",
                "-Y",
                "sign",
                "-f",
                str(self.unknown if unknown else self.primary),
                "-n",
                namespace or approval.APPROVAL_NAMESPACE,
            ],
            input=payload,
            capture_output=True,
            check=False,
            timeout=5,
            cwd=self.directory,
            env=ENVIRONMENT,
        )
        if result.returncode != 0:
            pytest.fail("Required synthetic OpenSSH signing capability unavailable")
        return result.stdout


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    # TemporaryDirectory removes private key material even though pytest retains
    # its own test directories. No private key content enters Python diagnostics.
    parent = tmp_path_factory.mktemp("synthetic-approval-keys")
    with tempfile.TemporaryDirectory(dir=parent) as name:
        directory = Path(name)
        paths = [directory / "synthetic-primary", directory / "synthetic-unknown"]
        for path in paths:
            try:
                result = subprocess.run(
                    [
                        "/usr/bin/ssh-keygen",
                        "-q",
                        "-t",
                        "ed25519",
                        "-N",
                        "",
                        "-C",
                        "synthetic-test-only",
                        "-f",
                        str(path),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=5,
                    cwd=directory,
                    env=ENVIRONMENT,
                )
            except (OSError, subprocess.SubprocessError):
                pytest.fail("Required system OpenSSH Ed25519 verifier unavailable")
            if result.returncode != 0:
                pytest.fail("Required system OpenSSH Ed25519 verifier incompatible")
        public = [
            " ".join(p.with_suffix(".pub").read_text().split()[:2]) for p in paths
        ]
        yield SyntheticKeys(directory, paths[0], paths[1], public[0], public[1])
    assert not directory.exists()


@pytest.fixture(scope="module")
def proposal():
    receipt = runtime.SourceApprovalReceipt(
        schema_id="canary-source-approval-v1",
        scope="source-only",
        approval_reference="synthetic:contract-test",
        provenance="synthetic-test",
        execution_profile="offline-verification-v1",
        harness=runtime.GitIdentity(commit="a" * 40, tree="b" * 40),
        application=runtime.GitIdentity(
            commit=runtime.APPLICATION_REVISION, tree="c" * 40
        ),
        binding=runtime.resolve_definition(runtime.V3),
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
    return approval.ProposedCanary(
        authorisation_id="synthetic-auth-" + "1" * 32,
        execution_audience="synthetic-slice6a-host",
        source_receipt=receipt,
        source_receipt_sha256=fingerprint(receipt.model_dump(mode="json")),
        project_id="proj_synthetic_slice6a",
        organization_id="org_synthetic_slice6a",
        credential_provisioning_reference="synthetic-provisioning-test-only",
    )


@pytest.fixture(scope="module")
def manifest(proposal):
    return approval.ApprovalManifest(
        schema_id="canary-synthetic-approval-v1",
        purpose="synthetic-offline-target-only-canary-v3",
        environment="synthetic-offline",
        signature_namespace=approval.APPROVAL_NAMESPACE,
        execution=proposal,
        issuer_principal=PRINCIPAL,
        created_at="2026-11-22T11:59:00Z",
        not_before="2026-11-22T12:00:00Z",
        expires_at="2026-11-22T12:30:00Z",
        judge_authority=False,
        study_authority=False,
        replacement_authority=False,
        resume_authority=False,
        authorises_live_execution=False,
    )


@pytest.fixture(scope="module")
def policy(keys):
    return approval.SyntheticTrustPolicy(
        schema_id="canary-synthetic-trust-v1",
        policy_id="synthetic-policy-unit-tests",
        expected_principal=PRINCIPAL,
        public_key=keys.public_key,
        roles=(approval.APPROVAL_ROLE,),
    )


@pytest.fixture(scope="module")
def signed(keys, manifest):
    payload = approval.serialize_manifest(manifest)
    return payload, keys.sign(payload)


def verify(signed, proposal, policy, *, now=NOW):
    return approval.verify_approval(
        *signed, expected=proposal, trust_policy=policy, now=now
    )


def changed_payload(manifest, path, value, *, receipt_digest=True):
    document = manifest.model_dump(mode="json")
    current = document
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = value
    if path[:2] == ("execution", "source_receipt") and receipt_digest:
        document["execution"]["source_receipt_sha256"] = fingerprint(
            document["execution"]["source_receipt"]
        )
    return canonical_json(document).encode()


def test_real_synthetic_signature_and_exact_manifest_roundtrip(
    signed, manifest, proposal, policy
):
    payload, signature = signed
    assert approval.parse_manifest(payload) == manifest
    assert approval.serialize_manifest(approval.parse_manifest(payload)) == payload
    result = verify(signed, proposal, policy)
    assert result.payload_sha256 == sha256(payload).hexdigest()
    assert result.signature_sha256 == sha256(signature).hexdigest()
    assert result.source_receipt_sha256 == proposal.source_receipt_sha256
    assert result.signer_principal == PRINCIPAL
    assert result.trust_policy_sha256 == fingerprint(policy.model_dump(mode="json"))
    for field in (
        "payload_structurally_valid",
        "signature_cryptographically_verified",
        "signer_matches_synthetic_policy",
        "required_role_verified",
        "purpose_and_execution_bindings_match",
        "time_valid",
    ):
        assert getattr(result, field) is True
    assert result.revocation_status == "not_revoked_under_supplied_policy"
    assert result.assurance_class == "synthetic-offline-only"
    for field in (
        "real_human_authorisation_authenticated",
        "source_authorised",
        "provider_evidence_authenticated",
        "authorises_live_execution",
    ):
        assert getattr(result, field) is False
    assert (
        approval.ApprovalVerification.model_validate_json(result.model_dump_json())
        == result
    )


def test_tampered_valid_payload_requires_a_new_signature(
    signed, manifest, proposal, policy
):
    payload = changed_payload(manifest, ("expires_at",), "2026-11-22T12:29:00Z")
    assert approval.parse_manifest(payload).expires_at == "2026-11-22T12:29:00Z"
    with pytest.raises(approval.ApprovalError, match="^signature_not_verified$"):
        verify((payload, signed[1]), proposal, policy)


def test_altered_signature_fails_actual_verification(signed, proposal, policy):
    lines = signed[1].splitlines()
    wire = bytearray(base64.b64decode(b"".join(lines[1:-1]), validate=True))
    wire[-1] ^= 1
    encoded = base64.b64encode(wire)
    signature = b"\n".join([lines[0], encoded, lines[-1], b""])
    with pytest.raises(approval.ApprovalError, match="^signature_not_verified$"):
        verify((signed[0], signature), proposal, policy)


def test_unknown_key_cannot_select_its_own_trust(keys, signed, proposal, policy):
    signature = keys.sign(signed[0], unknown=True)
    with pytest.raises(approval.ApprovalError, match="^signature_not_verified$"):
        verify((signed[0], signature), proposal, policy)


@pytest.mark.parametrize(
    "namespace",
    [
        "file",
        "canary-human-review-v3@ai-test-harness.invalid",
        "canary-evidence-seal-v3@ai-test-harness.invalid",
    ],
)
def test_other_signature_domains_are_not_approval(
    keys, signed, proposal, policy, namespace
):
    signature = keys.sign(signed[0], namespace=namespace)
    with pytest.raises(approval.ApprovalError, match="^signature_not_verified$"):
        verify((signed[0], signature), proposal, policy)


def test_claimed_principal_must_match_separately_supplied_policy(
    keys, manifest, proposal, policy
):
    payload = changed_payload(
        manifest, ("issuer_principal",), "synthetic-other@canary.invalid"
    )
    with pytest.raises(approval.ApprovalError, match="^principal_mismatch$"):
        verify((payload, keys.sign(payload)), proposal, policy)


def test_role_does_not_follow_key_possession(signed, proposal, policy):
    other_role = policy.model_copy(update={"roles": ("synthetic-human-reviewer",)})
    with pytest.raises(approval.ApprovalError, match="^role_not_authorised$"):
        verify(signed, proposal, other_role)


def test_revocation_and_unrelated_revoked_key(signed, proposal, policy, keys):
    revoked = policy.model_copy(update={"revoked_public_keys": (keys.public_key,)})
    with pytest.raises(approval.ApprovalError, match="^signer_revoked$"):
        verify(signed, proposal, revoked)
    unrelated = policy.model_copy(
        update={"revoked_public_keys": (keys.unknown_public_key,)}
    )
    assert verify(signed, proposal, unrelated).time_valid


@pytest.mark.parametrize(
    "instant,category",
    [
        (NOW - timedelta(seconds=1), "approval_not_yet_valid"),
        (NOW, None),
        (NOW + timedelta(minutes=29, seconds=59), None),
        (NOW + timedelta(minutes=30), "approval_expired"),
        (NOW + timedelta(hours=1), "approval_expired"),
    ],
)
def test_half_open_time_boundaries_use_actual_verifier(
    signed, proposal, policy, instant, category
):
    if category:
        with pytest.raises(approval.ApprovalError, match="^" + category + "$"):
            verify(signed, proposal, policy, now=instant)
    else:
        assert verify(signed, proposal, policy, now=instant).time_valid


@pytest.mark.parametrize(
    "instant",
    [
        None,
        "2026-11-22T12:00:00Z",
        NOW.replace(tzinfo=None),
        NOW.replace(microsecond=1),
        datetime(2026, 11, 22, 12, 0, tzinfo=timezone(timedelta(hours=1))),
    ],
)
def test_clock_is_explicit_aware_utc_seconds(signed, proposal, policy, instant):
    with pytest.raises(approval.ApprovalError, match="^invalid_verification_time$"):
        verify(signed, proposal, policy, now=instant)


def test_policy_can_tighten_maximum_validity(signed, proposal, policy):
    short = policy.model_copy(update={"max_validity_seconds": 1800})
    with pytest.raises(approval.ApprovalError, match="^validity_window_exceeded$"):
        verify(signed, proposal, short)


def test_exact_maximum_lifetime_and_policy_lifetime_boundaries(
    manifest, proposal, policy, keys
):
    payload = changed_payload(manifest, ("created_at",), "2026-11-22T11:30:00Z")
    assert verify((payload, keys.sign(payload)), proposal, policy).time_valid
    exact = policy.model_copy(update={"max_validity_seconds": 1860})
    original = approval.serialize_manifest(manifest)
    assert verify((original, keys.sign(original)), proposal, exact).time_valid
    shorter = exact.model_copy(update={"max_validity_seconds": 1859})
    with pytest.raises(approval.ApprovalError, match="^validity_window_exceeded$"):
        verify((original, keys.sign(original)), proposal, shorter)


@pytest.mark.parametrize(
    "path,value",
    [
        (("created_at",), "2026-11-22T12:00:01Z"),
        (("created_at",), "2026-11-22T11:29:59Z"),
        (("expires_at",), "2026-11-22T12:00:00Z"),
        (("not_before",), "2026-11-22T12:31:00Z"),
        (("created_at",), "2026-02-30T11:59:00Z"),
        (("created_at",), "2026-11-22T11:59:00+00:00"),
        (("created_at",), "2026-11-22T11:59:00.000Z"),
        (("created_at",), "2026-11-22t11:59:00z"),
    ],
)
def test_invalid_timestamp_representations_and_order(manifest, path, value):
    with pytest.raises(approval.ApprovalError, match="^invalid_manifest$"):
        approval.parse_manifest(changed_payload(manifest, path, value))


@pytest.mark.parametrize(
    "change",
    [
        lambda raw: raw + b"\n",
        lambda raw: b" " + raw,
        lambda raw: json.dumps(json.loads(raw), indent=2).encode(),
        lambda raw: (
            json.dumps(json.loads(raw), sort_keys=False).replace(":", ": ").encode()
        ),
        lambda raw: raw.replace("£".encode(), b"\\u00a3"),
    ],
)
def test_noncanonical_bytes_are_rejected_without_normalisation(signed, change):
    with pytest.raises(approval.ApprovalError, match="^noncanonical_manifest$"):
        approval.parse_manifest(change(signed[0]))


@pytest.mark.parametrize("nested", [False, True])
def test_duplicate_keys_are_rejected_even_if_values_agree(signed, nested):
    needle = (
        b'"model":"gpt-5.6-terra"' if nested else b'"environment":"synthetic-offline"'
    )
    payload = signed[0].replace(needle, needle + b"," + needle, 1)
    with pytest.raises(approval.ApprovalError, match="^invalid_manifest$"):
        approval.parse_manifest(payload)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "{}",
        bytearray(b"{}"),
        b"",
        b"[]",
        b"null",
        b"\xff",
        b"{}",
        b"NaN",
        b"{" + b" " * 65536 + b"}",
    ],
)
def test_malformed_and_oversized_input_has_fixed_diagnostics(payload):
    with pytest.raises(approval.ApprovalError, match="^invalid_manifest$"):
        approval.parse_manifest(payload)


@pytest.mark.parametrize("field", list(approval.ApprovalManifest.model_fields))
def test_every_top_level_field_is_required(manifest, field):
    document = manifest.model_dump(mode="json")
    del document[field]
    with pytest.raises(approval.ApprovalError, match="^invalid_manifest$"):
        approval.parse_manifest(canonical_json(document).encode())


@pytest.mark.parametrize(
    "path",
    [
        ("execution", "authorisation_id"),
        ("execution", "source_receipt_sha256"),
        ("execution", "credential_provisioning_reference"),
        ("execution", "source_receipt", "harness_lock_sha256"),
        ("execution", "source_receipt", "binding", "inference", "temperature"),
        ("execution", "source_receipt", "binding", "limits", "alerts_usd"),
        ("execution", "source_receipt", "binding", "authorises_live_execution"),
    ],
)
def test_nested_missing_fields_are_never_filled_into_signed_bytes(manifest, path):
    document = manifest.model_dump(mode="json")
    current = document
    for part in path[:-1]:
        current = current[part]
    del current[path[-1]]
    if path[:2] == ("execution", "source_receipt"):
        document["execution"]["source_receipt_sha256"] = fingerprint(
            document["execution"]["source_receipt"]
        )
    with pytest.raises(approval.ApprovalError, match="^invalid_manifest$"):
        approval.parse_manifest(canonical_json(document).encode())


@pytest.mark.parametrize(
    "path,value",
    [
        (("schema_id",), "canary-live-approval-v1"),
        (("purpose",), "live-canary"),
        (("environment",), "production"),
        (("signature_namespace",), "file"),
        (("issuer_principal",), "beccawillss"),
        (("issuer_principal",), "synthetic-operator@canary.invalid\nother"),
        (("judge_authority",), True),
        (("study_authority",), True),
        (("replacement_authority",), True),
        (("resume_authority",), True),
        (("authorises_live_execution",), True),
        (("judge_authority",), 0),
        (("judge_authority",), "false"),
        (("execution", "project_id"), "proj_live"),
        (("execution", "organization_id"), "org_live"),
        (("execution", "authorisation_id"), "../synthetic-auth-" + "1" * 32),
        (("execution", "authorisation_id"), "synthetic-auth-" + "A" * 32),
        (("execution", "execution_audience"), "synthetic-host "),
        (("execution", "credential_provisioning_reference"), "sk-PRIVATE_SECRET"),
        (("execution", "source_receipt_sha256"), "0" * 64),
        (("execution", "source_receipt", "provenance"), "external-review"),
        (("execution", "source_receipt", "execution_profile"), "target-only-canary-v3"),
        (("execution", "source_receipt", "application", "commit"), "0" * 40),
        (("execution", "source_receipt", "binding", "identifier"), runtime.C1),
        (("execution", "source_receipt", "binding", "roster_fingerprint"), "0" * 64),
        (
            ("execution", "source_receipt", "binding", "definition_fingerprint"),
            "0" * 64,
        ),
        (
            ("execution", "source_receipt", "binding", "acceptance_fingerprint"),
            "0" * 64,
        ),
        (("execution", "source_receipt", "binding", "execution_fingerprint"), "0" * 64),
        (
            ("execution", "source_receipt", "binding", "inference", "model"),
            "wrong-model",
        ),
        (
            ("execution", "source_receipt", "binding", "inference", "reasoning_effort"),
            "high",
        ),
        (
            (
                "execution",
                "source_receipt",
                "binding",
                "inference",
                "max_output_tokens",
            ),
            2001,
        ),
        (
            (
                "execution",
                "source_receipt",
                "binding",
                "inference",
                "max_output_tokens",
            ),
            "2000",
        ),
        (("execution", "source_receipt", "binding", "inference", "sdk_retries"), 3),
        (("execution", "source_receipt", "binding", "limits", "shopper_posts"), True),
        (
            ("execution", "source_receipt", "binding", "limits", "logical_calls_total"),
            25,
        ),
        (
            (
                "execution",
                "source_receipt",
                "binding",
                "limits",
                "provider_attempts_total",
            ),
            73,
        ),
        (
            ("execution", "source_receipt", "binding", "limits", "estimated_pause_usd"),
            "5.00",
        ),
        (
            ("execution", "source_receipt", "binding", "limits", "estimated_pause_usd"),
            5,
        ),
        (
            (
                "execution",
                "source_receipt",
                "binding",
                "limits",
                "project_monthly_limit_usd",
            ),
            "1e1",
        ),
        (("execution", "source_receipt", "binding", "fixture_hashes"), []),
        (
            ("execution", "source_receipt", "binding", "fixture_hashes"),
            [[name, "0" * 64] for name, _ in runtime.FIXTURE_HASHES],
        ),
        (
            ("execution", "source_receipt", "binding", "inference", "timeout_seconds"),
            31,
        ),
        (("execution", "source_receipt", "binding", "inference", "temperature"), 0.5),
        (
            (
                "execution",
                "source_receipt",
                "binding",
                "inference",
                "cache_retention_override",
            ),
            "24h",
        ),
        (
            (
                "execution",
                "source_receipt",
                "binding",
                "limits",
                "logical_calls_per_turn",
            ),
            7,
        ),
        (("execution", "source_receipt", "binding", "limits", "attempts_per_call"), 4),
        (
            (
                "execution",
                "source_receipt",
                "binding",
                "limits",
                "target_allowance_usd",
            ),
            "4",
        ),
        (("execution", "source_receipt", "binding", "limits", "contingency_usd"), "3"),
        (
            ("execution", "source_receipt", "binding", "limits", "alerts_usd"),
            ["2", "4"],
        ),
        (
            ("execution", "source_receipt", "binding", "limits", "estimated_pause_usd"),
            "NaN",
        ),
        (("execution", "source_receipt", "runtime", "python"), "3.13.15"),
    ],
)
def test_invalid_or_conflicting_contract_fields(manifest, path, value):
    with pytest.raises(approval.ApprovalError, match="^invalid_manifest$"):
        approval.parse_manifest(changed_payload(manifest, path, value))


@pytest.mark.parametrize(
    "path",
    [
        (),
        ("execution",),
        ("execution", "source_receipt"),
        ("execution", "source_receipt", "binding"),
        ("execution", "source_receipt", "binding", "inference"),
    ],
)
def test_unknown_fields_and_embedded_trust_policy_are_forbidden(manifest, path, policy):
    document = manifest.model_dump(mode="json")
    current = document
    for part in path:
        current = current[part]
    current["trust_policy"] = policy.model_dump(mode="json")
    with pytest.raises(approval.ApprovalError, match="^invalid_manifest$"):
        approval.parse_manifest(canonical_json(document).encode())


@pytest.mark.parametrize(
    "path,value",
    [
        (("execution", "authorisation_id"), "synthetic-auth-" + "2" * 32),
        (("execution", "execution_audience"), "synthetic-other-host"),
        (("execution", "project_id"), "proj_synthetic_other"),
        (("execution", "organization_id"), "org_synthetic_other"),
        (("execution", "credential_provisioning_reference"), None),
        (("execution", "source_receipt", "harness", "commit"), "0" * 40),
        (("execution", "source_receipt", "harness", "tree"), "0" * 40),
        (("execution", "source_receipt", "application", "tree"), "0" * 40),
        (("execution", "source_receipt", "harness_lock_sha256"), "0" * 64),
        (("execution", "source_receipt", "application_lock_sha256"), "0" * 64),
        (("execution", "source_receipt", "approval_reference"), "synthetic:unrelated"),
    ],
)
def test_validly_signed_substitution_does_not_match_expected_proposal(
    keys, manifest, proposal, policy, path, value
):
    payload = changed_payload(manifest, path, value)
    approval.parse_manifest(payload)
    with pytest.raises(approval.ApprovalError, match="^execution_binding_mismatch$"):
        verify((payload, keys.sign(payload)), proposal, policy)


def test_reverification_is_repeatable_but_grants_no_replay_or_consumption(
    signed, proposal, policy
):
    first = verify(signed, proposal, policy)
    assert verify(signed, proposal, policy) == first
    assert first.authorises_live_execution is False
    assert not hasattr(first, "consumed")


@pytest.mark.parametrize(
    "change",
    [
        {"public_key": "ssh-rsa AAAA"},
        {"public_key": "ssh-ed25519 AAAA"},
        {"public_key": "ssh-ed25519 !PRIVATE_KEY"},
        {"roles": (approval.APPROVAL_ROLE, approval.APPROVAL_ROLE)},
        {"roles": ("synthetic-canary-approver\ninjected",)},
        {"roles": ()},
        {"max_validity_seconds": 0},
        {"max_validity_seconds": 3601},
        {"assurance_class": "real-human-authenticated"},
        {"expected_principal": "synthetic-operator@canary.invalid extra"},
        {"untrusted_role_grant": True},
    ],
)
def test_untrusted_or_invalid_policy_cannot_enrol_itself(
    signed, proposal, policy, change
):
    category = (
        "role_not_authorised" if change == {"roles": ()} else "invalid_trust_policy"
    )
    with pytest.raises(approval.ApprovalError, match="^" + category + "$"):
        verify(signed, proposal, policy.model_copy(update=change))


def test_public_key_comments_options_and_duplicate_revocations_are_rejected(
    signed, proposal, policy
):
    for change in (
        {"public_key": policy.public_key + " synthetic-comment"},
        {"public_key": 'namespaces="file" ' + policy.public_key},
        {"revoked_public_keys": (policy.public_key, policy.public_key)},
    ):
        with pytest.raises(approval.ApprovalError, match="^invalid_trust_policy$"):
            verify(signed, proposal, policy.model_copy(update=change))


@pytest.mark.parametrize("field", ["manifest", "proposal", "policy"])
def test_constructed_and_copied_models_are_revalidated(
    manifest, proposal, policy, signed, field
):
    if field == "manifest":
        unsafe = manifest.model_copy(update={"untrusted_extra": "PRIVATE_SENTINEL"})
        operation = lambda: approval.serialize_manifest(unsafe)
    elif field == "proposal":
        unsafe = proposal.model_copy(update={"source_receipt_sha256": "0" * 64})
        operation = lambda: verify(signed, unsafe, policy)
    else:
        unsafe = policy.model_copy(update={"max_validity_seconds": True})
        operation = lambda: verify(signed, proposal, unsafe)
    with pytest.raises(approval.ApprovalError) as caught:
        operation()
    assert "PRIVATE" not in str(caught.value)
    assert caught.value.__suppress_context__


def test_all_nested_contracts_and_results_are_immutable(
    manifest, proposal, policy, signed
):
    result = verify(signed, proposal, policy)
    for instance, field, value in (
        (manifest, "issuer_principal", "other"),
        (proposal, "project_id", "other"),
        (proposal.source_receipt.harness, "commit", "0" * 40),
        (proposal.source_receipt.binding.inference, "max_output_tokens", 1),
        (proposal.source_receipt.binding.limits, "shopper_posts", 1),
        (policy, "public_key", "other"),
        (result, "authorises_live_execution", True),
    ):
        with pytest.raises(ValidationError):
            setattr(instance, field, value)


@pytest.mark.parametrize("signature", [None, "PRIVATE_SIGNATURE", b"", b"x" * 4097])
def test_invalid_signature_input_is_private(signed, proposal, policy, signature):
    with pytest.raises(approval.ApprovalError, match="^invalid_signature$"):
        verify((signed[0], signature), proposal, policy)


@pytest.mark.parametrize(
    "failure",
    [
        FileNotFoundError("PRIVATE_PATH"),
        PermissionError("PRIVATE_KEY"),
        subprocess.TimeoutExpired(
            "PRIVATE_COMMAND", 5, output=b"PRIVATE_STDOUT", stderr=b"PRIVATE_STDERR"
        ),
    ],
)
def test_missing_unavailable_and_timed_out_verifier_fail_closed(
    signed, proposal, policy, monkeypatch, failure
):
    def unavailable(*args, **kwargs):
        raise failure

    monkeypatch.setattr(approval.subprocess, "run", unavailable)
    with pytest.raises(
        approval.ApprovalError, match="^verifier_unavailable$"
    ) as caught:
        verify(signed, proposal, policy)
    assert "PRIVATE" not in str(caught.value)


def test_actual_missing_verifier_is_a_blocker(signed, proposal, policy, monkeypatch):
    monkeypatch.setattr(approval, "_SSH_KEYGEN", "/nonexistent/synthetic-ssh-keygen")
    with pytest.raises(approval.ApprovalError, match="^verifier_unavailable$"):
        verify(signed, proposal, policy)


def test_temporary_storage_failure_is_private_and_terminal(
    signed, proposal, policy, monkeypatch
):
    def unavailable(*args, **kwargs):
        raise OSError("PRIVATE_STORAGE_PATH")

    monkeypatch.setattr(approval.tempfile, "TemporaryDirectory", unavailable)
    with pytest.raises(
        approval.ApprovalError, match="^verification_storage_unavailable$"
    ):
        verify(signed, proposal, policy)


@pytest.mark.parametrize(
    "returncode,stdout,stderr,category",
    [
        (0, b"PRIVATE_FAKE_SUCCESS", b"", "verifier_protocol_error"),
        (0, b"", b"PRIVATE_STDERR", "verifier_protocol_error"),
        (1, b"PRIVATE_STDOUT", b"PRIVATE_STDERR", "signature_not_verified"),
    ],
)
def test_unexpected_subprocess_output_cannot_be_success_or_leak(
    signed, proposal, policy, monkeypatch, returncode, stdout, stderr, category, capsys
):
    monkeypatch.setattr(
        approval.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], returncode, stdout, stderr
        ),
    )
    with pytest.raises(approval.ApprovalError, match="^" + category + "$") as caught:
        verify(signed, proposal, policy)
    assert "PRIVATE" not in repr(caught.value)
    assert capsys.readouterr() == ("", "")


def test_verifier_receives_only_explicit_public_policy_and_original_bytes(
    signed, proposal, policy, monkeypatch
):
    original = approval.subprocess.run
    invocations = []

    def observe(arguments, **options):
        assert arguments[:3] == ["/usr/bin/ssh-keygen", "-Y", "verify"]
        assert options["input"] is signed[0]
        assert options["env"] == ENVIRONMENT
        assert options["timeout"] == 5
        directory = options["cwd"]
        assert directory.stat().st_mode & 0o777 == 0o700
        assert {p.name for p in directory.iterdir()} == {
            "allowed-signers",
            "revoked-keys",
            "approval.sig",
        }
        for path in directory.iterdir():
            assert path.stat().st_mode & 0o777 == 0o600
        assert (directory / "approval.sig").read_bytes() == signed[1]
        assert policy.public_key in (directory / "allowed-signers").read_text()
        invocations.append(directory)
        return original(arguments, **options)

    monkeypatch.setattr(approval.subprocess, "run", observe)
    assert verify(signed, proposal, policy).signature_cryptographically_verified
    assert len(invocations) == 1 and not invocations[0].exists()


def test_no_ambient_environment_ssh_agent_or_credential_lookup(
    signed, proposal, policy, monkeypatch
):
    original = type(os.environ).__getitem__

    def guarded(environment, key):
        if key.startswith(("SSH_", "OPENAI_", "SALESAGENT_")) or key in {
            "HOME",
            "USERPROFILE",
        }:
            raise AssertionError("Ambient identity or credential access")
        return original(environment, key)

    monkeypatch.setattr(type(os.environ), "__getitem__", guarded)
    assert verify(signed, proposal, policy).signature_cryptographically_verified


def test_no_signing_key_or_sensitive_material_in_outputs(
    signed, proposal, policy, capsys
):
    result = verify(signed, proposal, policy)
    saved = result.model_dump_json()
    assert "PRIVATE KEY" not in saved and "PRIVATE KEY" not in signed[0].decode()
    assert "ssh-ed25519" not in saved
    assert capsys.readouterr() == ("", "")


def test_import_and_verification_do_not_construct_network_sdk_or_read_private_files(
    tmp_path, signed, proposal, policy
):
    # Child audit guards cover imports/files/subprocesses without trusting the
    # pytest process's existing imports. Only synthetic fixture data is saved.
    data = tmp_path / "synthetic-input.json"
    data.write_text(
        canonical_json(
            {
                "payload": signed[0].decode(),
                "signature": signed[1].decode(),
                "expected": proposal.model_dump(mode="json"),
                "policy": policy.model_dump(mode="json"),
            }
        )
    )
    program = r"""
import json, os, sys
from pathlib import Path
def audit(event, args):
    if event == "import" and args[0].split(".")[0] in {"openai", "salesagent", "uvicorn"}:
        raise AssertionError("external construction")
    if event.startswith("socket."):
        raise AssertionError("socket activity")
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = os.fsdecode(args[0])
        if "/.ssh/" in path or path.endswith(("/.env", "/id_ed25519", "/id_rsa")):
            raise AssertionError("private identity access")
    if event == "subprocess.Popen" and args[0] != "/usr/bin/ssh-keygen":
        raise AssertionError("unexpected executable")
sys.addaudithook(audit)
from datetime import UTC, datetime
from harness.canary.approval_v3 import ProposedCanary, SyntheticTrustPolicy, verify_approval
data = json.loads(Path(sys.argv[1]).read_text())
result = verify_approval(data["payload"].encode(), data["signature"].encode(),
    expected=ProposedCanary.model_validate_json(json.dumps(data["expected"])),
    trust_policy=SyntheticTrustPolicy.model_validate_json(json.dumps(data["policy"])),
    now=datetime(2026, 11, 22, 12, tzinfo=UTC))
assert result.authorises_live_execution is False
assert "openai" not in sys.modules and "salesagent" not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", program, str(data)],
        capture_output=True,
        check=False,
        timeout=15,
        env={**ENVIRONMENT, "PYTHONPATH": "src", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert result.returncode == 0, "Isolated synthetic verification failed"
    assert result.stdout == result.stderr == b""


def test_existing_definition_identities_remain_exact():
    binding = runtime.resolve_definition(runtime.V3)
    assert (
        binding.roster_fingerprint,
        binding.definition_fingerprint,
        binding.acceptance_fingerprint,
        binding.execution_fingerprint,
    ) == runtime.V3_FINGERPRINTS
    assert runtime.resolve_definition().identifier == runtime.C1
