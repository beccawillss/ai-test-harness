"""Local immutable prospective artifacts. No targets, providers or SQL changes."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from harness.core.fingerprints import canonical_json, fingerprint, text_hash
from harness.core.prospective import (
    Frozen,
    PreparedProspectiveJudgment,
    ProspectiveJudgingPlan,
    ProspectiveJudgmentResult,
    strict_json,
)


class PreparedBundle(Frozen):
    schema_version: Literal["prospective-bundle-v1"] = "prospective-bundle-v1"
    plan: ProspectiveJudgingPlan
    requests: tuple[PreparedProspectiveJudgment, ...]

    @model_validator(mode="after")
    def valid(self) -> Self:
        if tuple(r.request_id for r in self.requests) != tuple(
            s.request_id for s in self.plan.selections
        ) or any(r.plan != self.plan for r in self.requests):
            raise ValueError(
                "Prepared bundle must contain the exact ordered plan roster"
            )
        return self


def _write(path: Path, value: dict) -> None:
    # Exclusive creation makes concurrent duplicate IDs fail before provider work.
    with path.open("x", encoding="utf-8") as file:
        file.write(canonical_json(value) + "\n")


def _save(path: Path, model: Frozen) -> None:
    path.mkdir()
    value = model.model_dump(mode="json")
    _write(path / "document.json", value)
    # Publish the receipt last: interrupted bundles cannot be loaded.
    _write(
        path / "receipt.json",
        {
            "schema_version": "prospective-receipt-v1",
            "fingerprint": fingerprint(value),
            "bytes": text_hash((path / "document.json").read_text()),
        },
    )


def _load[M: Frozen](path: Path, model: type[M]) -> M:
    receipt = strict_json((path / "receipt.json").read_bytes())
    raw = (path / "document.json").read_text()
    value = strict_json(raw)
    if receipt != {
        "schema_version": "prospective-receipt-v1",
        "fingerprint": fingerprint(value),
        "bytes": text_hash(raw),
    }:
        raise ValueError("Incomplete or altered prospective artifact")
    return model.model_validate_json(canonical_json(value))


class ProspectiveStore:
    """Use one store for an experiment; do not split an observation across stores.

    Reservation markers survive failures. An interrupted write is not repaired
    automatically. A failed result save leaves the caller's result available;
    retry only that save to an unused path, never invoke the judge again.
    """

    def __init__(self, directory: Path):
        self.directory = directory

    def save_prepared(self, bundle: PreparedBundle) -> None:
        bundle = PreparedBundle.model_validate_json(bundle.model_dump_json())
        self.directory.mkdir(parents=True, exist_ok=True)
        for request in bundle.requests:
            for prefix, identifier in (
                ("request", request.request_id),
                ("observation", request.selection.observation_id),
            ):
                _write(
                    self.directory / f"identity-{prefix}-{identifier}.json",
                    {"request_hash": request.digest},
                )
        _save(self.directory / f"plan-{bundle.plan.plan_id}", bundle)

    def load_prepared(self, plan: ProspectiveJudgingPlan) -> PreparedBundle:
        bundle = _load(self.directory / f"plan-{plan.plan_id}", PreparedBundle)
        if bundle.plan != plan:
            raise ValueError("Stored plan differs")
        return bundle

    def reserve(self, request: PreparedProspectiveJudgment) -> None:
        bundle = self.load_prepared(request.plan)
        if request not in bundle.requests:
            raise ValueError("Unregistered request")
        _write(
            self.directory / f"reserved-{request.selection.observation_id}.json",
            {
                "schema_version": "prospective-reservation-v1",
                "request_hash": request.digest,
            },
        )

    def save_result(
        self, result: ProspectiveJudgmentResult, *, destination: Path | None = None
    ) -> Path:
        result = ProspectiveJudgmentResult.model_validate_json(result.model_dump_json())
        request = result.input
        reservation = strict_json(
            (self.directory / f"reserved-{result.observation_id}.json").read_bytes()
        )
        if reservation != {
            "schema_version": "prospective-reservation-v1",
            "request_hash": request.digest,
        }:
            raise ValueError("Result does not match its exclusive reservation")
        terminal = self.directory / f"completed-{result.observation_id}.json"
        if terminal.exists():
            raise FileExistsError("Observation already completed")
        path = destination or self.directory / f"result-{result.observation_id}"
        _save(path, result)
        _write(terminal, {"result_hash": result.digest})
        return path

    def state(
        self, request: PreparedProspectiveJudgment
    ) -> Literal["prepared", "started_unresolved", "completed"]:
        self.load_prepared(request.plan)
        if (
            self.directory / f"completed-{request.selection.observation_id}.json"
        ).exists():
            return "completed"
        if (
            self.directory / f"reserved-{request.selection.observation_id}.json"
        ).exists():
            return "started_unresolved"
        return "prepared"

    @staticmethod
    def load_result(path: Path) -> ProspectiveJudgmentResult:
        return _load(path, ProspectiveJudgmentResult)
