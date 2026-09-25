"""Small normalized reply for injected judge callables."""

from pydantic import BaseModel, ConfigDict, Field


class JudgeReply(BaseModel):
    """Judge text and optional observations, never an SDK/provider envelope."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    text: str
    observed_model: str | None = Field(default=None, min_length=1, pattern=r"\S")
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
