"""Strict descriptor-bound authoring alongside unchanged legacy loading."""

import json
from pathlib import Path

import pytest

from harness.core.dataset import (
    DatasetDescriptor,
    LoadedDataset,
    hash_cases,
    load_cases,
    load_dataset,
)
from harness.core.fingerprints import fingerprint

FIXTURE = Path(__file__).parent / "fixtures/taxonomy/organization/dataset.json"


def descriptor_data(**changes):
    return {
        "schema_version": "dataset-descriptor-v1",
        "id": "example",
        "version": "v1",
        "cases": "cases.jsonl",
        "fingerprint_scheme": "dataset-cases-v2",
        **changes,
    }


def write_dataset(tmp_path, *, descriptor=None, rows=None, text=None):
    path = tmp_path / "dataset.json"
    path.write_text(
        json.dumps(descriptor if descriptor is not None else descriptor_data())
    )
    (tmp_path / "cases.jsonl").write_text(
        text
        if text is not None
        else "\n".join(
            json.dumps(row)
            for row in (rows if rows is not None else [{"id": "a", "input": "hi"}])
        )
        + "\n"
    )
    return path


def test_complete_load_preserves_order_metadata_and_roundtrips(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    loaded = load_dataset(FIXTURE)
    assert [c.id for c in loaded.cases] == ["case-a", "case-b", "case-c"]
    assert loaded.cases[0].input == {"message": "alpha", "options": [None, True, 1]}
    assert loaded.cases[0].reference == {"expected": "alpha"}
    assert loaded.cases[0].extra == {"origin": {"revision": 1}}
    assert loaded.descriptor.extra == {
        "origin": {"version": 1, "notes": [None, True, "authored"]}
    }
    assert loaded.descriptor.cases == "cases.jsonl"
    assert loaded.cases_path == FIXTURE.parent / "cases.jsonl"
    assert loaded.descriptor_path == FIXTURE
    assert loaded.full_dataset_hash == hash_cases(
        loaded.cases, scheme="dataset-cases-v2"
    )
    assert loaded.descriptor_hash == fingerprint(
        loaded.descriptor.model_dump(mode="json")
    )
    assert loaded.descriptor_hash != loaded.full_dataset_hash
    assert (
        DatasetDescriptor.model_validate_json(loaded.descriptor.model_dump_json())
        == loaded.descriptor
    )
    assert LoadedDataset.model_validate_json(loaded.model_dump_json()) == loaded


def test_descriptor_hash_ignores_format_and_checkout_location_but_binds_definition(
    tmp_path,
):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    p = write_dataset(first)
    q = write_dataset(second)
    q.write_text(json.dumps(descriptor_data(), sort_keys=True, indent=4))
    a, b = load_dataset(p), load_dataset(q)
    assert a.descriptor_hash == b.descriptor_hash
    assert a.full_dataset_hash == b.full_dataset_hash
    q.write_text(
        json.dumps(
            descriptor_data(description="Updated description", extra={"revision": 2})
        )
    )
    changed = load_dataset(q)
    assert changed.full_dataset_hash == a.full_dataset_hash
    assert changed.descriptor_hash != a.descriptor_hash
    (second / "cases.jsonl").write_text('{"id":"a","input":"different"}\n')
    edited = load_dataset(q)
    assert edited.descriptor_hash == changed.descriptor_hash
    assert edited.full_dataset_hash != changed.full_dataset_hash


def test_descriptor_null_defaults_and_nested_bindings(tmp_path):
    (tmp_path / "sub").mkdir()
    path = write_dataset(tmp_path, descriptor=descriptor_data(cases="sub/cases.jsonl"))
    (tmp_path / "sub/cases.jsonl").write_text('{"id":"a","input":"hi"}\n')
    loaded = load_dataset(path)
    assert loaded.cases_path == tmp_path / "sub/cases.jsonl"
    descriptor = DatasetDescriptor.model_validate(
        descriptor_data(cases="sub/cases.jsonl", title=None, description=None, extra={})
    )
    assert descriptor.descriptor_hash == loaded.descriptor_hash


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema_version", "dataset-descriptor-v2"),
        ("schema_version", None),
        ("fingerprint_scheme", "dataset-cases-v1"),
        ("fingerprint_scheme", "unknown"),
        ("id", ""),
        ("id", " x"),
        ("id", "x\n"),
        ("id", True),
        ("version", ""),
        ("version", "v1 "),
        ("version", 1),
        ("title", " "),
        ("title", 1),
        ("description", 1),
        ("extra", []),
        ("extra", None),
        ("unknown", "sensitive-value"),
    ],
)
def test_invalid_descriptor_fields_report_path_and_field(tmp_path, key, value):
    path = write_dataset(tmp_path, descriptor=descriptor_data(**{key: value}))
    with pytest.raises(ValueError) as error:
        load_dataset(path)
    assert str(path) in str(error.value)
    assert key in str(error.value)
    assert "sensitive-value" not in str(error.value)


@pytest.mark.parametrize(
    "key", ["schema_version", "id", "version", "cases", "fingerprint_scheme"]
)
def test_descriptor_required_fields(tmp_path, key):
    data = descriptor_data()
    del data[key]
    with pytest.raises(ValueError, match=key):
        load_dataset(write_dataset(tmp_path, descriptor=data))


@pytest.mark.parametrize(
    "binding",
    [
        "",
        " ",
        ".",
        "/absolute.jsonl",
        "//host/share.jsonl",
        "../cases.jsonl",
        "sub/../cases.jsonl",
        "sub/../../cases.jsonl",
        "https://example.test/cases.jsonl",
        "file:cases.jsonl",
        "C:/cases.jsonl",
        "C:cases.jsonl",
        "..\\cases.jsonl",
        "\\\\host\\share.jsonl",
        "cases\x00.jsonl",
    ],
)
def test_nonportable_bindings_fail_before_reading_cases(tmp_path, binding):
    path = write_dataset(tmp_path, descriptor=descriptor_data(cases=binding))
    with pytest.raises(ValueError, match="cases"):
        load_dataset(path)


def test_symlink_case_binding_cannot_escape_descriptor_directory(tmp_path):
    outside = tmp_path / "outside.jsonl"
    outside.write_text('{"id":"a","input":"hi"}\n')
    root = tmp_path / "dataset"
    root.mkdir()
    path = write_dataset(root, descriptor=descriptor_data(cases="link.jsonl"))
    (root / "link.jsonl").symlink_to(outside)
    with pytest.raises(ValueError, match="leaves descriptor directory"):
        load_dataset(path)


@pytest.mark.parametrize(
    "text",
    [
        '{"id":"a","id":"b","input":"hi"}',
        '{"id":"a","input":{"key":1,"key":2}}',
        '{"id":"a","input":"hi","reference":{"key":1,"key":2}}',
        '{"id":"a","input":"hi","extra":{"key":1,"key":2}}',
        '{"id":"a","input":"hi","extra":{"number":NaN}}',
        '{"id":"a","input":{"number":Infinity}}',
        '{"id":"a","input":"hi","reference":{"number":-Infinity}}',
        '{"id":"a","input":"hi","extra":{"number":1e400}}',
        '{"id":',
        "[]",
        "null",
        '"text"',
    ],
)
def test_invalid_json_rows_report_physical_line(tmp_path, text):
    path = write_dataset(tmp_path, text='{"id":"good","input":"hi"}\n\n' + text)
    with pytest.raises(ValueError, match=r"cases\.jsonl:3: invalid v2 TestCase"):
        load_dataset(path)


@pytest.mark.parametrize(
    "text",
    [
        '{"id":"a","id":"b"}',
        '{"extra":{"a":1,"a":2}}',
        '{"extra":{"x":NaN}}',
        '{"extra":{"x":Infinity}}',
        '{"extra":{"x":1e400}}',
        "[]",
        "null",
        "{",
    ],
)
def test_invalid_descriptor_json(tmp_path, text):
    path = write_dataset(tmp_path)
    path.write_text(text)
    with pytest.raises(ValueError, match="dataset.json: invalid dataset descriptor"):
        load_dataset(path)


@pytest.mark.parametrize(
    "key,value",
    [
        ("id", ""),
        ("id", " a"),
        ("id", "a "),
        ("id", "\t"),
        ("id", 1),
        ("title", ""),
        ("title", " \n"),
        ("title", False),
        ("category", ""),
        ("category", "x "),
        ("category", 1),
        ("risk", ""),
        ("risk", " x"),
        ("risk", True),
        ("tags", [""]),
        ("tags", ["x", "x"]),
        ("tags", [" x"]),
        ("tags", ["x "]),
        ("tags", [1]),
        ("tags", [True]),
        ("tags", "x"),
        ("tags", None),
        ("input", []),
        ("input", False),
        ("reference", []),
        ("extra", []),
        ("unknown", "private body"),
    ],
)
def test_strict_v2_rows_reject_invalid_values_without_echoing_payload(
    tmp_path, key, value
):
    path = write_dataset(
        tmp_path, rows=[{"id": "a", "input": "private body", key: value}]
    )
    with pytest.raises(ValueError, match=r"cases\.jsonl:1:") as error:
        load_dataset(path)
    assert "private body" not in str(error.value)


def test_duplicate_case_id_reports_both_lines(tmp_path):
    path = write_dataset(
        tmp_path, text='{"id":"a","input":"hi"}\n\n{"id":"a","input":"other"}\n'
    )
    with pytest.raises(ValueError) as error:
        load_dataset(path)
    assert "cases.jsonl:3:" in str(error.value)
    assert "first declared at" in str(error.value)
    assert "cases.jsonl:1" in str(error.value)


def test_missing_empty_and_unreadable_sources(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="Cannot read"):
        load_dataset(tmp_path / "missing.json")
    path = write_dataset(tmp_path, descriptor=descriptor_data(cases="missing.jsonl"))
    with pytest.raises(ValueError, match="Cannot read.*missing.jsonl"):
        load_dataset(path)
    path = write_dataset(tmp_path, text="\n \n")
    with pytest.raises(ValueError, match="contains no test cases"):
        load_dataset(path)

    def denied(*args, **kwargs):
        raise PermissionError("private body")

    monkeypatch.setattr(Path, "read_text", denied)
    with pytest.raises(ValueError, match="PermissionError") as error:
        load_dataset(path)
    assert "private body" not in str(error.value)


def test_invalid_utf8_is_a_source_error(tmp_path):
    path = write_dataset(tmp_path)
    (tmp_path / "cases.jsonl").write_bytes(b"\xff")
    with pytest.raises(ValueError, match="UnicodeDecodeError"):
        load_dataset(path)


def test_internal_whitespace_prose_and_array_order_survive(tmp_path):
    row = {
        "id": "case a",
        "input": {"text": " unchanged "},
        "category": "family a",
        "risk": "opaque risk",
        "tags": ["z tag", "a tag"],
        "title": " Title ",
        "description": " \n ",
        "reference": None,
        "extra": {"values": [1, True, None, 1.5]},
    }
    path = write_dataset(
        tmp_path,
        descriptor=descriptor_data(
            id="data set", version="version one", description=" \n "
        ),
        rows=[row],
    )
    loaded = load_dataset(path)
    assert loaded.cases[0].model_dump() == row
    assert loaded.descriptor.id == "data set"
    assert loaded.descriptor.version == "version one"
    assert loaded.descriptor.description == " \n "


@pytest.mark.parametrize("extra", [{"x": float("nan")}, {"x": (1, 2)}, {1: "bad"}])
def test_direct_descriptor_construction_cannot_normalize_metadata(extra):
    with pytest.raises(ValueError):
        DatasetDescriptor(**descriptor_data(extra=extra))


def test_legacy_loader_retains_permissive_behavior(tmp_path):
    text = '{"id":" a ","input":"hi","unknown":true,"tags":["", "x", "x"]}\n{"id":" a ","input":"hi"}\n'
    path = write_dataset(tmp_path, text=text)
    legacy = load_cases(tmp_path / "cases.jsonl")
    assert [c.id for c in legacy] == [" a ", " a "]
    assert legacy[0].tags == ["", "x", "x"]
    assert "unknown" not in legacy[0].model_dump()
    with pytest.raises(ValueError):
        load_dataset(path)


def test_valid_unicode_line_separators_inside_values_are_not_jsonl_boundaries(tmp_path):
    row = {"id": "a", "input": "preserve\u2028and\u0085inside text"}
    path = write_dataset(tmp_path, text=json.dumps(row, ensure_ascii=False) + "\n")
    assert load_dataset(path).cases[0].input == row["input"]


def test_descriptor_binding_changes_hash_even_when_case_content_is_identical(tmp_path):
    path = write_dataset(tmp_path)
    original = load_dataset(path)
    (tmp_path / "same.jsonl").write_text((tmp_path / "cases.jsonl").read_text())
    path.write_text(json.dumps(descriptor_data(cases="same.jsonl")))
    rebound = load_dataset(path)
    assert rebound.full_dataset_hash == original.full_dataset_hash
    assert rebound.descriptor_hash != original.descriptor_hash


@pytest.mark.parametrize("field", ["full_dataset_hash", "descriptor_hash"])
def test_loaded_dataset_roundtrip_rejects_inconsistent_hashes(field):
    loaded = load_dataset(FIXTURE)
    document = json.loads(loaded.model_dump_json())
    document[field] = "0" * 64
    with pytest.raises(ValueError, match="fingerprint differs"):
        LoadedDataset.model_validate_json(json.dumps(document))
