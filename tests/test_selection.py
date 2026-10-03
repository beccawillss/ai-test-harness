"""Pure selection truth table and definition-only preview contracts."""

import json
from pathlib import Path

import pytest

from harness.core.dataset import hash_cases, load_dataset
from harness.core.models import TestCase as Case
from harness.core.selection import (
    CaseSelection,
    SelectionPreview,
    preview_selection,
    select_cases,
)

FIXTURE = Path(__file__).parent / "fixtures/taxonomy/organization/dataset.json"


@pytest.mark.parametrize(
    "expression,ids",
    [
        ({}, ["case-a", "case-b", "case-c"]),
        ({"case_ids": ["case-c", "case-a"]}, ["case-a", "case-c"]),
        ({"categories": ["family-a"], "tags_any": ["quick"]}, ["case-a"]),
        ({"tags_all": ["quick", "cross-cutting"]}, ["case-a"]),
        ({"case_ids": ["case-a", "case-b"], "risks": ["high"]}, ["case-a"]),
        ({"categories": ["family-a"], "risks": ["low"]}, []),
        ({"categories": ["family-b", "family-a"]}, ["case-a", "case-b", "case-c"]),
        ({"risks": ["low", "high"]}, ["case-a", "case-b"]),
        ({"tags_any": ["quick", "cross-cutting"]}, ["case-a", "case-b", "case-c"]),
        ({"tags_any": ["quick"], "tags_all": ["cross-cutting"]}, ["case-a"]),
        ({"tags_any": ["Quick"]}, []),
        ({"categories": ["unknown"]}, []),
        ({"risks": ["unknown"]}, []),
        ({"tags_all": ["unknown"]}, []),
        (
            {
                "categories": ["family-a"],
                "risks": ["high"],
                "tags_any": ["quick"],
                "tags_all": ["cross-cutting"],
                "case_ids": ["case-a", "case-c"],
            },
            ["case-a"],
        ),
    ],
)
def test_selection_truth_table(expression, ids):
    dataset = load_dataset(FIXTURE)
    selection = CaseSelection.model_validate(expression)
    before = dataset.model_dump_json()
    selected = select_cases(dataset.cases, selection)
    assert [c.id for c in selected] == ids
    assert selection.model_dump() == expression
    assert dataset.model_dump_json() == before
    assert [c.id for c in select_cases(dataset.cases, selection)] == ids


@pytest.mark.parametrize(
    "field", ["case_ids", "categories", "tags_any", "tags_all", "risks"]
)
@pytest.mark.parametrize(
    "value",
    [[], None, "x", ("x",), [""], [" x"], ["x "], ["x", "x"], [1], [True], [None]],
)
def test_invalid_selector_arrays_and_values(field, value):
    with pytest.raises(ValueError):
        CaseSelection.model_validate({field: value})


def test_selection_roundtrip_unknown_keys_and_internal_whitespace():
    expression = {
        "categories": ["family a"],
        "tags_all": ["tag one"],
        "risks": ["risk a"],
    }
    selection = CaseSelection(**expression)
    assert CaseSelection.model_validate_json(selection.model_dump_json()) == selection
    case = Case(
        id="case a", input="hi", category="family a", tags=["tag one"], risk="risk a"
    )
    assert select_cases([case], selection) == [case]
    assert CaseSelection.model_validate_json("{}").model_dump() == {}
    with pytest.raises(ValueError):
        CaseSelection.model_validate({"tags": ["tag one"]})


def test_unknown_explicit_id_checked_before_taxonomy_filters():
    cases = load_dataset(FIXTURE).cases
    with pytest.raises(ValueError, match="Unknown explicit case ID"):
        select_cases(
            cases, CaseSelection(case_ids=["missing"], categories=["not present"])
        )


def test_missing_classification_and_legacy_duplicate_tags():
    case = Case(id="a", input="hi", tags=["x", "x"])
    assert select_cases([case]) == [case]
    assert select_cases([case], CaseSelection(tags_all=["x"])) == [case]
    assert select_cases([case], CaseSelection(categories=["family-a"])) == []
    assert select_cases([case], CaseSelection(risks=["low"])) == []
    assert case.tags == ["x", "x"]
    with pytest.raises(ValueError, match="Duplicate case IDs"):
        select_cases([case, case])
    assert select_cases([]) == []


@pytest.mark.parametrize("expression", [{}, {"risks": ["missing"]}])
def test_preview_fingerprints_counts_and_serialization(expression):
    dataset = load_dataset(FIXTURE)
    selection = CaseSelection(**expression)
    preview = preview_selection(dataset, selection)
    selected = select_cases(dataset.cases, selection)
    assert preview.case_ids == [c.id for c in selected]
    assert preview.total_case_count == 3
    assert preview.selected_case_count == len(selected)
    assert preview.full_dataset_hash == dataset.full_dataset_hash
    assert preview.descriptor_hash == dataset.descriptor_hash
    assert preview.selected_dataset_hash == hash_cases(
        selected, scheme="dataset-cases-v2"
    )
    assert preview.executable is bool(selected)
    assert preview.reason == (None if selected else "No cases selected")
    assert SelectionPreview.model_validate_json(preview.model_dump_json()) == preview
    document = json.loads(preview.model_dump_json())
    assert document["selection"] == expression
    assert (
        "input" not in document
        and "reference" not in document
        and "extra" not in document
    )


@pytest.mark.parametrize(
    "mutation",
    ["invalid_unselected", "valid_unselected", "duplicate", "descriptor", "nonfinite"],
)
def test_preview_revalidates_entire_loaded_dataset_before_selecting(mutation):
    dataset = load_dataset(FIXTURE)
    if mutation == "invalid_unselected":
        dataset.cases[-1].tags.append("")
    elif mutation == "valid_unselected":
        dataset.cases[-1].input = "changed"
    elif mutation == "duplicate":
        dataset.cases[-1].id = dataset.cases[0].id
    elif mutation == "descriptor":
        dataset.descriptor.extra["changed"] = True
    else:
        dataset.cases[-1].extra["bad"] = float("inf")
    with pytest.raises(ValueError):
        preview_selection(dataset, CaseSelection(case_ids=["case-a"]))


def test_invalid_unselected_disk_row_prevents_preview(tmp_path):
    descriptor = json.loads(FIXTURE.read_text())
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(descriptor))
    (tmp_path / "cases.jsonl").write_text(
        '{"id":"a","input":"ok"}\n{"id":"b","input":"bad","tags":[""]}\n'
    )
    with pytest.raises(ValueError, match=r"cases.jsonl:2"):
        preview_selection(load_dataset(path), CaseSelection(case_ids=["a"]))


def test_mutated_selectors_revalidate_and_preview_does_not_alias_them():
    dataset = load_dataset(FIXTURE)
    selection = CaseSelection(tags_any=["quick"])
    preview = preview_selection(dataset, selection)
    selection.tags_any.append("cross-cutting")
    assert preview.selection.tags_any == ["quick"]
    selection.tags_any.append("quick")
    with pytest.raises(ValueError, match="unique"):
        select_cases(dataset.cases, selection)
    with pytest.raises(ValueError):
        select_cases(dataset.cases, CaseSelection.model_construct(tags_any=None))


def test_unrelated_opaque_taxonomies_have_no_special_rules():
    cases = [
        Case(
            id="one",
            input="x",
            category="bucket z",
            tags=["dimension q"],
            risk="bespoke severity",
        ),
        Case(id="two", input="y", category="other bucket", tags=["dimension q"]),
    ]
    assert select_cases(
        cases, CaseSelection(categories=["bucket z"], risks=["bespoke severity"])
    ) == [cases[0]]
    assert select_cases(cases, CaseSelection(tags_any=["dimension q"])) == cases


def test_load_and_preview_do_not_import_execution_modules():
    # An isolated interpreter proves module imports themselves remain inert.
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            """
import sys
from harness.core.dataset import load_dataset
from harness.core.selection import preview_selection
preview_selection(load_dataset(sys.argv[1]))
assert not any(name.startswith(('harness.targets', 'harness.scorers', 'harness.judges')) or name == 'harness.core.runner' for name in sys.modules)
""",
            str(FIXTURE),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
