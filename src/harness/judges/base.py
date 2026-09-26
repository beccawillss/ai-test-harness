"""Small normalized reply for injected judge callables."""

from pydantic import BaseModel, ConfigDict, Field


class JudgeObservation(BaseModel):
    """Safe per-call observations, also available when judgment parsing fails."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    observed_model: str | None = Field(default=None, min_length=1, pattern=r"\S")
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class JudgeReply(JudgeObservation):
    """Judge text and optional observations, never an SDK/provider envelope."""

    text: str

    @property
    def observation(self) -> JudgeObservation:
        return JudgeObservation.model_validate(self.model_dump(exclude={"text"}))


class JudgeScoringError(ValueError):
    """Safe parse failure retaining only normalized observations."""

    def __init__(self, observation: JudgeObservation) -> None:
        super().__init__("Malformed judge judgment")
        self.observation = observation
