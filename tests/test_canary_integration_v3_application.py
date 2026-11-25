"""Explicit public source/controller gates; disabled gates alone may skip."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from time import monotonic

import pytest
import test_canary_integration_v3 as c
import test_canary_integration_v3_faults as faults

keys = c.keys


def enabled(name):
    value = os.environ.get(name, "0")
    assert value in {"0", "1"}, "gate flags require exactly 0 or 1"
    if value == "0":
        pytest.skip("Explicit Slice 6f gate disabled: " + name)
    assert sys.version_info[:2] == (3, 13), "Enabled gate requires pinned CPython 3.13"
    root = Path(os.environ["CANARY_V3_SLICE6F_APPLICATION_ROOT"])
    assert root.is_absolute() and (root / "src/salesagent/__init__.py").is_file()
    return root.resolve()


def local_git(root, *args):
    return (
        subprocess.check_output(
            [
                "/usr/bin/git",
                "--no-optional-locks",
                "-C",
                str(root),
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            env={
                "PATH": "/usr/bin:/bin",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_NO_REPLACE_OBJECTS": "1",
            },
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        .decode()
        .strip()
    )


def source_copy(tmp_path):
    root = tmp_path / "synthetic-source"
    root.mkdir(mode=0o700)
    original = Path(__file__).resolve().parents[1]
    shutil.copytree(
        original / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copyfile(original / "uv.lock", root / "uv.lock")
    (root / ".gitignore").write_text("__pycache__/\n*.pyc\n")
    template = tmp_path / "empty-git-template"
    template.mkdir(mode=0o700)
    local_git(root, "init", "-q", "--template=" + str(template))
    local_git(root, "add", "--", "src", "uv.lock", ".gitignore")
    local_git(
        root,
        "-c",
        "user.name=Synthetic Test",
        "-c",
        "user.email=synthetic@canary.invalid",
        "commit",
        "--no-gpg-sign",
        "--no-verify",
        "-qm",
        "Synthetic exact-source fixture only",
    )
    assert not local_git(root, "status", "--porcelain")
    return root


def source_receipt(source, application):
    def identity(root):
        lines = local_git(root, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
        return c.runtime.GitIdentity(commit=lines[0], tree=lines[1])

    return c.runtime.SourceApprovalReceipt(
        schema_id="canary-source-approval-v1",
        scope="source-only",
        approval_reference="synthetic:slice6f-clean-source",
        provenance="synthetic-test",
        execution_profile="offline-verification-v1",
        harness=identity(source),
        application=identity(application),
        binding=c.runtime.resolve_definition(c.runtime.V3),
        harness_lock_sha256=sha256((source / "uv.lock").read_bytes()).hexdigest(),
        application_lock_sha256=sha256(
            (application / "uv.lock").read_bytes()
        ).hexdigest(),
        runtime=c.runtime.RuntimeIdentity(
            implementation=platform.python_implementation(),
            python=platform.python_version(),
            system=platform.system(),
            machine=platform.machine(),
            dependency_lock="application",
        ),
    )


def origins(source, application):
    result = {}
    for name, module in tuple(sys.modules.items()):
        if name == "harness" or name.startswith("harness."):
            root = source / "src/harness"
        elif name == "salesagent" or name.startswith("salesagent."):
            root = application / "src/salesagent"
        else:
            continue
        path = Path(module.__file__).resolve()
        assert path.is_relative_to(root) and path.suffix == ".py", (
            "unexpected loaded module origin"
        )
        assert Path(module.__spec__.origin).resolve() == path
        result[name] = str(path)
    return result


def run_child(mode, source, application, scratch, signing=None):
    """Fresh interpreter imports harness only from exact clean source fixture."""
    import tomllib

    import httpx
    from test_canary_approval_v3 import SyntheticKeys

    source, application, scratch = map(Path, (source, application, scratch))
    assert Path(c.runtime.__file__).resolve().is_relative_to(source / "src/harness")
    assert sys.version_info[:2] == (3, 13)
    assert local_git(application, "rev-parse", "HEAD") == c.runtime.APPLICATION_REVISION
    assert not local_git(application, "status", "--porcelain")
    for name, digest in c.runtime.FIXTURE_HASHES:
        assert sha256((application / "data" / name).read_bytes()).hexdigest() == digest
    lock = tomllib.loads((application / "uv.lock").read_text())
    for package in lock["package"]:
        if "registry" in package.get("source", {}) and package["name"] not in {
            "colorama",
            "httpx2-jsfetch",
        }:
            assert importlib.metadata.version(package["name"]) == package["version"]
    # Imports, runtime preflight, source copy/commit and this exact tracked-file
    # inventory are trusted preparation, performed before installing the audit.
    # Public verification/controller execution and subsequent imports run under it.
    tracked = local_git(application, "ls-files", "-z").split("\0")
    observations = faults.isolation(
        Path(os.environ["TMPDIR"]).parent,
        read_roots=(source / "src", application / "src"),
        read_files=(
            source / "uv.lock",
            source / ".gitignore",
            *(application / os.fsdecode(name) for name in tracked if name),
        ),
        git_roots=(source, application),
        signing_keys=(signing["primary"], signing["unknown"]) if signing else (),
    )
    receipt = source_receipt(source, application)
    verified = c.runtime.verify_source(
        receipt, harness_root=source, application_root=application
    )
    assert (
        verified.source_matches_receipt
        and not verified.source_authorised
        and not verified.authorises_live_execution
    )
    record = {
        "mode": mode,
        "python": platform.python_version(),
        "runtime": receipt.runtime.model_dump(mode="json"),
        "source_matches": True,
        "source_authorised": False,
        "source_commit": receipt.harness.commit,
    }
    if mode == "source":
        with pytest.raises(c.runtime.SourceError, match="^harness_identity_mismatch$"):
            c.runtime.verify_source(
                receipt.model_copy(
                    update={
                        "harness": receipt.harness.model_copy(
                            update={"commit": "f" * 40}
                        )
                    }
                ),
                harness_root=source,
                application_root=application,
            )
        (source / "src/harness/py.typed").write_text("synthetic tracked change\n")
        with pytest.raises(c.runtime.SourceError, match="^dirty_worktree$"):
            c.runtime.verify_source(
                receipt, harness_root=source, application_root=application
            )
        assert "salesagent" not in sys.modules and "openai" not in sys.modules
        record["negative_cases"] = ["harness_identity_mismatch", "dirty_worktree"]
    else:
        from test_canary_controller_v3_application import Script

        from harness.canary.controller_v3 import OfflineCanaryControllerV3

        assert importlib.metadata.version("openai") == "3.3.1"
        signing = dict(signing)
        for key in ("directory", "primary", "unknown"):
            signing[key] = Path(signing[key])
        keys = SyntheticKeys(**signing)
        flow = c.consume(
            c.prepare(scratch / "chosen-sequence", keys, source_receipt=receipt)
        )
        script = Script()
        controller = OfflineCanaryControllerV3(
            offline=True,
            harness_root=source,
            application_root=application,
            source_receipt=receipt,
            evidence_parent=scratch,
            provider_mock=httpx.MockTransport(script),
        )
        report = controller.run()
        assert report["controller_status"] == report["driver_status"] == "completed", (
            report.get("controller_error")
        )
        assert report["controller_error"] is None and not report["development_only"]
        assert report["source_verification"] == "clean_source_match_only"
        assert report["shopper_posts"] == 4 and report["trace_reads"] == 8
        assert (
            report["accounting"]["logical_calls"]
            == report["accounting"]["provider_attempts"]
            == 12
        )
        assert report["completion_certified"] and report["accounting_reconciled"]
        assert (
            report["mechanical_assessment"]["status"]
            == report["operational_assessment"]["status"]
            == "PASS"
        )
        assert (
            report["assessment"]["status"] == "SKIP"
            and report["human_review"] == "PENDING"
            and report["billing"] == "unknown"
        )
        assert (
            not report["source_authorised"]
            and not report["provider_evidence_authenticated"]
            and not report["authorises_live_execution"]
        )
        resources = report["resources"]
        assert (
            resources["cleanup_verified"]
            and resources["owned_threads"] >= 2
            and resources["surviving_owned_threads"] == 0
        )
        assert (
            resources["application_lifespan_exited"]
            and resources["sdk_closed"]
            and resources["http_closed"]
        )
        flow.registry = c.journal.load_registry(Path(report["registry_path"]))
        observed = c.journal.inspect_run(flow.registry, report["run_id"])
        assert observed["completion_certified"] and not observed["issues"]
        chats = {
            r["payload"]["slot"]: r["payload"]["chat"]
            for r in observed["records"]
            if r["kind"] == "chat"
        }
        traces = {
            r["payload"]["slot"]: r["payload"]["trace"]
            for r in observed["records"]
            if r["kind"] == "trace"
        }
        assert (
            chats["A1"]["session_id"]
            == chats["A2"]["session_id"]
            != chats["B1"]["session_id"]
            == chats["B2"]["session_id"]
        )
        assert len({trace["trace_id"] for trace in traces.values()}) == 4
        assert chats["A1"]["recommendations"][0]["price"] == "55.00"
        assert chats["A2"]["pricing"]["final_price"] == "49.50"
        assert chats["B2"]["recommendations"][0]["price"] == "22.00"
        assert [t["tool_name"] for t in traces["A1"]["tool_calls"]] == [
            "search_products",
            "get_product",
            "check_inventory",
        ]
        assert [t["tool_name"] for t in traces["A2"]["tool_calls"]] == [
            "get_product",
            "validate_discount",
        ]
        assert traces["A1"]["tool_calls"][-1]["result"]["data"]["stock"] == 5
        assert traces["B2"]["tool_calls"][-1]["result"]["data"]["stock"] == 6
        first = {
            slot: body
            for slot, n, retry, body in script.requests
            if n == 1 and retry == 0
        }
        assert [len(first[slot]["input"]) for slot in c.ORDER] == [2, 2, 4, 4]
        assert first["A2"]["input"][0]["content"] == receipt.binding.turns[0].message
        assert first["B2"]["input"][0]["content"] == receipt.binding.turns[1].message
        profile = next(
            r["payload"]["binding"]
            for r in observed["records"]
            if r["kind"] == "instrumentation_profile"
        )
        assert (
            profile["project_id"]
            == "proj_offline_synthetic"
            != flow.proposal.project_id
        )
        assert (
            profile["organization_id"]
            == "org_offline_synthetic"
            != flow.proposal.organization_id
        )
        assert (
            report["run_id"].startswith("run-")
            and report["run_id"] != flow.consumed.intended_run_id
        )
        assert observed["records"][0]["payload"]["approval_id"].startswith(
            "synthetic-offline-"
        )
        before = c.snapshot(flow.registry.path)
        with pytest.raises(c.envelope.EnvelopeError, match="^invalid_input$"):
            c.envelope.assemble_envelope(
                **{**c.envelope_arguments(flow), "run_id": report["run_id"]}
            )
        with pytest.raises(c.envelope.EnvelopeError, match="^journal_unavailable$"):
            c.envelope.assemble_envelope(**c.envelope_arguments(flow))
        assert c.snapshot(flow.registry.path) == before
        assert (
            c.authority.inspect_consumption(
                flow.store, flow.proposal.authorisation_id
            ).record
            == flow.consumed
        )
        assert c.runtime.verify_source(
            receipt, harness_root=source, application_root=application
        ).source_matches_receipt
        record.update(
            controller_status="completed",
            mechanical="PASS",
            historical_overall="SKIP",
            calls=12,
            attempts=12,
            shopper_posts=4,
            trace_reads=8,
            resources=resources,
            incompatibility=["invalid_input", "journal_unavailable"],
            caller_selected_consumption_sequence=True,
            mandatory_authority_enforcement=False,
        )
    assert observations["network"] == 0
    record["origins"] = origins(source, application)
    record["subprocesses"] = observations["subprocesses"]
    print(json.dumps(record))


def invoke(mode, tmp_path, application, keys=None):
    started = monotonic()
    deadline = started + (120 if mode == "source" else 180)
    root = source_copy(tmp_path)
    scratch = tmp_path / "execution"
    scratch.mkdir(mode=0o700)
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "LANG": "C",
        "TMPDIR": os.environ["TMPDIR"],
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join(
            [
                str(root / "src"),
                str(Path(__file__).resolve().parent),
                str(application / "src"),
            ]
        ),
    }
    if mode == "controller":
        env["CANARY_V3_APPLICATION_TESTS"] = "1"
    data = {
        "mode": mode,
        "source": str(root),
        "application": str(application),
        "scratch": str(scratch),
    }
    if keys:
        data["signing"] = {
            name: str(getattr(keys, name))
            for name in (
                "directory",
                "primary",
                "unknown",
                "public_key",
                "unknown_public_key",
            )
        }
    program = "import json,sys; from test_canary_integration_v3_application import run_child; run_child(**json.load(sys.stdin))"
    result = subprocess.run(
        [sys.executable, "-B", "-c", program],
        input=json.dumps(data),
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=max(0.001, deadline - monotonic()),
        check=False,
    )
    if result.returncode:
        (tmp_path / "child-failure.txt").write_text(result.stderr)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert monotonic() <= deadline, "total explicit-gate deadline exceeded"
    record = json.loads(result.stdout)
    record["seconds"] = monotonic() - started
    (tmp_path / "gate-result.json").write_text(json.dumps(record, indent=2))
    return record


def test_gate_a_public_source(tmp_path):
    application = enabled("CANARY_V3_SLICE6F_SOURCE")
    result = invoke("source", tmp_path, application)
    assert result["source_matches"] and result["negative_cases"] == [
        "harness_identity_mismatch",
        "dirty_worktree",
    ]


def test_gate_b_public_controller(tmp_path, request):
    application = enabled("CANARY_V3_SLICE6F_CONTROLLER")
    result = invoke(
        "controller", tmp_path, application, request.getfixturevalue("keys")
    )
    assert (
        result["controller_status"] == "completed"
        and not result["mandatory_authority_enforcement"]
    )
