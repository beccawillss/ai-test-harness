"""Pure case selection and dataset previews; no execution dependencies."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from harness.core.dataset import LoadedDataset, hash_cases
from harness.core.models import TestCase


class CaseSelection(BaseModel):
    """AND across fields, OR within value lists, explicit any/all tag matching."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    case_ids: list[str] | None = Field(default=None, exclude_if=lambda v: v is None)
    categories: list[str] | None = Field(default=None, exclude_if=lambda v: v is None)
    tags_any: list[str] | None = Field(default=None, exclude_if=lambda v: v is None)
    tags_all: list[str] | None = Field(default=None, exclude_if=lambda v: v is None)
    risks: list[str] | None = Field(default=None, exclude_if=lambda v: v is None)

    @field_validator(
        "case_ids", "categories", "tags_any", "tags_all", "risks", mode="before"
    )
    @classmethod
    def nonempty_array(cls, value: Any) -> Any:
        if not isinstance(value, list) or not value:
            raise ValueError("Supplied selectors must be nonempty arrays")
        return value

    @field_validator("case_ids", "categories", "tags_any", "tags_all", "risks")
    @classmethod
    def unique_values(cls, value: list[str] | None) -> list[str] | None:
        assert value is not None
        if any(not item or item != item.strip() for item in value):
            raise ValueError(
                "Selector values must be nonblank without boundary whitespace"
            )
        if len(set(value)) != len(value):
            raise ValueError("Selector values must be unique")
        return value


def _validated_selection(selection: CaseSelection | None) -> CaseSelection:
    if selection is None:
        return CaseSelection()
    # Recheck mutable lists/model_copy updates; exclude_if must not hide an
    # explicit null supplied via an unchecked copy/construct operation.
    return CaseSelection.model_validate(
        {
            field: getattr(selection, field)
            for field in type(selection).model_fields
            if field in selection.model_fields_set
            or getattr(selection, field) is not None
        }
    )


def select_cases(
    cases: Sequence[TestCase], selection: CaseSelection | None = None
) -> list[TestCase]:
    """Select already validated cases in source order, without modifying them."""
    selection = _validated_selection(selection)
    ids = [case.id for case in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate case IDs prevent unambiguous selection")
    if selection.case_ids is not None and not set(selection.case_ids) <= set(ids):
        raise ValueError("Unknown explicit case ID in selection")
    return [
        case
        for case in cases
        if (selection.case_ids is None or case.id in selection.case_ids)
        and (selection.categories is None or case.category in selection.categories)
        and (selection.risks is None or case.risk in selection.risks)
        and (
            selection.tags_any is None
            or any(tag in case.tags for tag in selection.tags_any)
        )
        and (
            selection.tags_all is None
            or all(tag in case.tags for tag in selection.tags_all)
        )
    ]


class SelectionPreview(BaseModel):
    """Definition-only membership preview, not target/scorer execution preflight."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    dataset_version: str
    descriptor_hash: str
    descriptor_fingerprint_scheme: Literal["dataset-descriptor-v1"]
    full_dataset_hash: str
    selected_dataset_hash: str
    case_fingerprint_scheme: Literal["dataset-cases-v2"]
    selection: CaseSelection
    case_ids: list[str]
    total_case_count: int
    selected_case_count: int
    executable: bool
    reason: str | None


def preview_selection(
    dataset: LoadedDataset, selection: CaseSelection | None = None
) -> SelectionPreview:
    """Revalidate the whole loaded source before returning portable membership."""
    # Public nested objects are mutable; detect drift, including unselected
    # cases, rather than displaying stale hashes or hiding invalid definitions.
    checked = LoadedDataset.model_validate(dataset.model_dump(mode="python"))
    selection = _validated_selection(selection)
    selected = select_cases(checked.cases, selection)
    return SelectionPreview(
        dataset_id=checked.descriptor.id,
        dataset_version=checked.descriptor.version,
        descriptor_hash=checked.descriptor_hash,
        descriptor_fingerprint_scheme=checked.descriptor.schema_version,
        full_dataset_hash=checked.full_dataset_hash,
        selected_dataset_hash=hash_cases(
            selected, scheme=checked.descriptor.fingerprint_scheme
        ),
        case_fingerprint_scheme=checked.descriptor.fingerprint_scheme,
        selection=selection,
        case_ids=[case.id for case in selected],
        total_case_count=len(checked.cases),
        selected_case_count=len(selected),
        executable=bool(selected),
        reason=None if selected else "No cases selected",
    )


__all__ = ["CaseSelection", "SelectionPreview", "preview_selection", "select_cases"]
