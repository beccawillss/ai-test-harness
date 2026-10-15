"""Offline CLI contract: explicit files, unchanged evidence, no quality gates."""

import builtins
import copy
import importlib.util
import json
import runpy
import sys
from pathlib import Path

import pytest

from harness.packs.salesagent_grounding import GroundingDiagnosticReport

ROOT = Path(__file__).parents[1]
EXAMPLE = ROOT / "examples/salesagent_grounding.py"
CORPUS = ROOT / "tests/fixtures/salesagent_grounding/v1"
ROWS = [json.loads(line) for line in (CORPUS / "cases.jsonl").read_text().splitlines()]
GOLD = {
    row["id"]: row["expected"]
    for row in map(json.loads, (CORPUS / "expected.jsonl").read_text().splitlines())
}


@pytest.fixture
def cli(monkeypatch, tmp_path, capsys):
    original_import = builtins.__import__

    def offline_import(name, *args, **kwargs):
        forbidden = (
            "harness.targets",
            "harness.judges",
            "harness.core.runner",
            "harness.core.store",
            "harness.core.prospective",
            "httpx",
            "openai",
        )
        assert not any(
            name == prefix or name.startswith(prefix + ".") for prefix in forbidden
        )
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", offline_import)
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("grounding_example", EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert list(tmp_path.iterdir()) == []
    assert capsys.readouterr() == ("", "")
    return module


def inputs(tmp_path, data):
    argv = []
    for name in ("response", "context", "authority"):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(data[name], ensure_ascii=False), encoding="utf-8")
        argv.extend([f"--{name}", str(path)])
    return argv


def snapshot(tmp_path):
    return {p.name: p.read_bytes() for p in tmp_path.iterdir()}


@pytest.mark.parametrize("row", ROWS, ids=lambda row: row["id"])
def test_cli_frozen_reports_exit_status_and_input_immutability(
    cli, row, tmp_path, capsys
):
    argv = inputs(tmp_path, row["input"])
    before = snapshot(tmp_path)
    code = cli.main(argv)
    captured = capsys.readouterr()
    assert captured.err == ""
    report = GroundingDiagnosticReport.model_validate_json(captured.out)
    assert report.semantic_projection() == GOLD[row["id"]]
    assert code == (0 if report.execution_status == "complete" else 1)
    assert captured.out == report.canonical_body() + "\n"
    assert cli.main(argv) == code
    assert capsys.readouterr().out == captured.out
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "mode",
    ["partial", "null_authority", "invalid_authority", "hash_mismatch", "real_context"],
)
def test_cli_boundaries(cli, mode, tmp_path, capsys):
    data = copy.deepcopy(next(row["input"] for row in ROWS if row["id"] == "S06"))
    status, code = "error", 1
    if mode == "partial":
        del data["response"]["structured"]["turns"][0]["output"]
        status = "partial"
    elif mode == "null_authority":
        data["authority"] = None
        status, code = "complete", 0
    elif mode == "invalid_authority":
        data["authority"] = []
    elif mode == "hash_mismatch":
        data["context"]["expected_response_sha256"] = "0" * 64
    else:
        data["context"]["synthetic"] = False
    argv = inputs(tmp_path, data)
    before = snapshot(tmp_path)
    assert cli.main(argv) == code
    captured = capsys.readouterr()
    assert not captured.err
    report = GroundingDiagnosticReport.model_validate_json(captured.out)
    assert report.execution_status == status
    if mode == "partial":
        assert report.candidates and report.errors
    if mode == "null_authority":
        assert report.counts["indeterminate"] > 0
        assert report.counts["unsupported"] == 0
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("role", ["response", "context", "authority"])
@pytest.mark.parametrize(
    "content",
    [
        b'{"sensitive":',
        b'{"sensitive":1,"sensitive":2}',
        b'{"sensitive":NaN}',
        b'{"sensitive":Infinity}',
        b'{"sensitive":1e999}',
        b'"\\ud800"',
        b"\xff",
    ],
)
def test_invalid_json_is_safe_input_error(cli, tmp_path, capsys, role, content):
    argv = inputs(tmp_path, ROWS[0]["input"])
    (tmp_path / f"{role}.json").write_bytes(content)
    before = snapshot(tmp_path)
    assert cli.main(argv) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(role + ":")
    assert "sensitive" not in captured.err
    assert str(tmp_path) not in captured.err
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "role,value",
    [
        ("response", {}),
        ("response", {"output": 123}),
        ("response", {"output": "sensitive", "unexpected": True}),
        ("context", {"source_id": "sensitive", "attempt_index": True}),
        ("context", {"source_id": "sensitive", "attempt_index": -1}),
        ("context", None),
    ],
)
def test_invalid_envelope_or_configuration(cli, tmp_path, capsys, role, value):
    data = copy.deepcopy(ROWS[0]["input"])
    data[role] = value
    assert cli.main(inputs(tmp_path, data)) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(role + ": invalid ")
    assert "sensitive" not in captured.err


def test_unreadable_file(cli, tmp_path, capsys):
    argv = inputs(tmp_path, ROWS[0]["input"])
    argv[1] = str(tmp_path / "missing-sensitive.json")
    assert cli.main(argv) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("response:")
    assert "sensitive" not in captured.err


@pytest.mark.parametrize(
    "args", [[], ["--live"], ["--response", "unused", "--context", "unused"]]
)
def test_explicit_inputs_required_and_no_live_mode(cli, args, capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2
    assert capsys.readouterr().out == ""


def test_script_entrypoint_and_help(cli, tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["--help"])
    assert error.value.code == 0
    assert "--authority" in capsys.readouterr().out
    argv = inputs(tmp_path, ROWS[0]["input"])
    monkeypatch.setattr(sys, "argv", [str(EXAMPLE), *argv])
    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(EXAMPLE), run_name="__main__")
    assert error.value.code == 0
    assert json.loads(capsys.readouterr().out)["execution_status"] == "complete"


def test_programming_errors_propagate(cli, tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("implementation failure")

    monkeypatch.setattr(cli, "diagnose_numeric_waterproof_claims", broken)
    with pytest.raises(RuntimeError, match="implementation failure"):
        cli.main(inputs(tmp_path, ROWS[0]["input"]))
