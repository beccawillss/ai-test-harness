"""Opt-in versioned judgment validation; no application vocabulary or defaults."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScoreOutputContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["score-output-contract-v1"] = "score-output-contract-v1"
    id: str = Field(min_length=1)
    kind: Literal["anchors"] = "anchors"
    anchors: tuple[Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)], ...]

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.id != self.id.strip():
            raise ValueError("Output contract ID has boundary whitespace")
        if not self.anchors or tuple(sorted(set(self.anchors))) != self.anchors:
            raise ValueError("Anchors must be nonempty, unique and increasing")
        return self

    def check_score(self, value: float) -> None:
        if (
            isinstance(value, bool)
            or not math.isfinite(value)
            or value not in self.anchors
        ):
            raise ValueError("Judge score is outside the recorded output contract")
