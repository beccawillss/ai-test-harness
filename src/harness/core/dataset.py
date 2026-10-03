"""Load and fingerprint evaluation datasets."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from harness.core.case_fingerprints import (
    CASE_SCHEME_V1,
    CASE_SCHEME_V2,
    case_payload,
    validate_case_scheme,
    validate_json_data,
    validate_v2_case,
)
from harness.core.fingerprints import fingerprint
from harness.core.models import TestCase


def load_cases(path: str | Path) -> list[TestCase]:
    """Load one TestCase per non-blank line from a JSONL file."""
    dataset_path = Path(path)
    try:
        text = dataset_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read dataset '{dataset_path}': {exc}") from exc

    cases: list[TestCase] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(TestCase.model_validate_json(line))
        except ValueError as exc:
            raise ValueError(
                f"{dataset_path}:{line_number}: invalid TestCase: {exc}"
            ) from exc

    if not cases:
        raise ValueError(f"Dataset '{dataset_path}' contains no test cases.")
    return cases


def hash_cases(cases: Iterable[TestCase], *, scheme: str = CASE_SCHEME_V1) -> str:
    """Hash ordered definitions; the default retains the exact legacy format."""
    validate_case_scheme(scheme)
    if scheme == CASE_SCHEME_V2:
        return fingerprint(
            {"scheme": scheme, "cases": [case_payload(c, scheme=scheme) for c in cases]}
        )
    digest = hashlib.sha256()
    for case in cases:
        payload = json.dumps(
            case_payload(case, scheme=scheme),
            sort_keys=True,
            separators=(",", ":"),
        )
        digest.update(payload.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


class DatasetDescriptor(BaseModel):
    """Portable authored dataset identity; version labels are not content hashes."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["dataset-descriptor-v1"]
    id: str
    version: str
    title: str | None = None
    description: str | None = None
    cases: str
    extra: dict[str, Any] = Field(default_factory=dict)
    fingerprint_scheme: Literal["dataset-cases-v2"]

    @field_validator("id", "version")
    @classmethod
    def identity(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("Identity must be nonblank without boundary whitespace")
        return value

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Title must not be blank")
        return value

    @field_validator("cases")
    @classmethod
    def local_binding(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            not value.strip()
            or "\x00" in value
            or "\\" in value
            or path.is_absolute()
            or PureWindowsPath(value).drive
            or urlsplit(value).scheme
            or ".." in path.parts
            or not path.parts
        ):
            raise ValueError(
                "Case binding must be a local relative file without parent traversal"
            )
        return value

    @field_validator("extra", mode="before")
    @classmethod
    def finite_metadata(cls, value: Any) -> Any:
        validate_json_data(value)
        return value

    @property
    def descriptor_hash(self) -> str:
        # Explicit schema_version is the domain marker. I/O paths and derived
        # hashes are not fields of the normalized authored descriptor.
        validate_json_data(self.extra)
        return fingerprint(self.model_dump(mode="json"))


def _strict_case(value: Any) -> TestCase:
    """A private authoring boundary returning the existing public case model."""
    case = TestCase.model_validate(value, strict=True, extra="forbid")
    validate_v2_case(case)
    return case


class LoadedDataset(BaseModel):
    """Validated source material and distinct descriptor/full-case fingerprints."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    descriptor: DatasetDescriptor
    cases: list[TestCase] = Field(min_length=1)
    descriptor_path: Path
    cases_path: Path
    full_dataset_hash: str
    descriptor_hash: str

    @field_validator("cases", mode="before")
    @classmethod
    def strict_cases(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [
                _strict_case(c) if not isinstance(c, TestCase) else c for c in value
            ]
        return value

    @model_validator(mode="after")
    def verified_content(self) -> Self:
        seen: set[str] = set()
        for case in self.cases:
            validate_v2_case(case)
            if case.id in seen:
                raise ValueError("Duplicate case ID in loaded dataset")
            seen.add(case.id)
        if self.full_dataset_hash != hash_cases(
            self.cases, scheme=self.descriptor.fingerprint_scheme
        ):
            raise ValueError("Loaded dataset case fingerprint differs")
        if self.descriptor_hash != self.descriptor.descriptor_hash:
            raise ValueError("Loaded dataset descriptor fingerprint differs")
        return self


def _strict_json(text: str) -> Any:
    def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON object key")
            result[key] = value
        return result

    def nonfinite(_: str) -> Any:
        raise ValueError("Non-finite JSON number")

    value = json.loads(text, object_pairs_hook=unique_keys, parse_constant=nonfinite)
    # Also catches numeric overflow such as 1e400, which parse_constant misses.
    validate_json_data(value)
    return value


def _validation_detail(exc: ValueError) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(
            f"{'.'.join(map(str, error['loc'])) or '<root>'}: {error['msg']}"
            for error in exc.errors(
                include_input=False, include_context=False, include_url=False
            )
        )
    return str(exc)


def _read_authoring_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(
            f"Cannot read dataset file '{path}': {type(exc).__name__}"
        ) from None


def load_dataset(descriptor_path: str | Path) -> LoadedDataset:
    """Validate a complete descriptor-bound dataset before any selection."""
    path = Path(descriptor_path).resolve()
    try:
        descriptor = DatasetDescriptor.model_validate(
            _strict_json(_read_authoring_file(path))
        )
    except ValueError as exc:
        raise ValueError(
            f"{path}: invalid dataset descriptor: {_validation_detail(exc)}"
        ) from None
    cases_path = (path.parent / descriptor.cases).resolve()
    if not cases_path.is_relative_to(path.parent):
        raise ValueError(
            f"{path}: cases: resolved case binding leaves descriptor directory"
        )
    seen: dict[str, int] = {}
    cases: list[TestCase] = []
    for line_number, line in enumerate(_read_authoring_file(cases_path).split("\n"), 1):
        if not line.strip():
            continue
        try:
            case = _strict_case(_strict_json(line))
            if case.id in seen:
                raise ValueError(
                    f"Duplicate case ID; first declared at {cases_path}:{seen[case.id]}"
                )
            seen[case.id] = line_number
            cases.append(case)
        except ValueError as exc:
            raise ValueError(
                f"{cases_path}:{line_number}: invalid v2 TestCase: {_validation_detail(exc)}"
            ) from None
    if not cases:
        raise ValueError(f"Dataset '{cases_path}' contains no test cases.")
    return LoadedDataset(
        descriptor=descriptor,
        cases=cases,
        descriptor_path=path,
        cases_path=cases_path,
        full_dataset_hash=hash_cases(cases, scheme=descriptor.fingerprint_scheme),
        descriptor_hash=descriptor.descriptor_hash,
    )


__all__ = [
    "DatasetDescriptor",
    "LoadedDataset",
    "hash_cases",
    "load_cases",
    "load_dataset",
]
