"""The Scorer Protocol and the base class for LLM-as-judge scorers.

Two-tier scoring is a core design commitment:

- Deterministic scorers are cheap, stable, and run everywhere (PR smoke
  suites). They implement the Protocol directly.
- Judged scorers are expensive, nondeterministic, and — crucially — are
  themselves systems that need testing. JudgedScorer therefore builds in
  the hooks for calibration against human labels. A judge without a
  measured agreement score is an untested test.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from harness.core.fingerprints import canonical_json, text_hash
from harness.core.models import Score, ScorerKind, TargetResponse, TestCase
from harness.judges.base import JudgeReply, JudgeScoringError


class PreparedJudgeInput(BaseModel):
    """Immutable evaluator input; its content is evaluation data, not public data."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    prompt: str
    configuration_json: str
    evidence_json: str | None = None

    @property
    def prompt_hash(self) -> str:
        return text_hash(self.prompt)

    @property
    def evidence_hash(self) -> str | None:
        return text_hash(self.evidence_json) if self.evidence_json is not None else None

    @property
    def configuration_hash(self) -> str:
        return text_hash(self.configuration_json)


@runtime_checkable
class Scorer(Protocol):
    """One metric applied to one attempt.

    Contract:
    - `name` is stable across runs; it is the key that regression
      comparison and trend charts join on. Renaming a scorer silently
      breaks history — treat names like public API.
    - `kind` lets the runner filter suites (e.g. smoke = deterministic
      only) without knowing anything else about the scorer.
    - `requires` names the TargetResponse fields this scorer reads
      ("contexts", "trajectory"). The runner unions these across a pack
      to validate target compatibility up front.
    - `score` must not raise for *quality* problems — a bad answer is a
      low Score, not an exception. Raise only for infrastructure
      problems (missing required field, judge API failure); the runner
      records those as Verdict.ERROR so they never pollute pass rates.
    """

    @property
    def name(self) -> str: ...

    @property
    def kind(self) -> ScorerKind: ...

    @property
    def requires(self) -> frozenset[str]: ...

    def score(self, case: TestCase, response: TargetResponse) -> Score: ...


class MissingFieldError(RuntimeError):
    """Raised when a scorer's required response field is absent.

    Distinct type so the runner can report 'adapter/pack mismatch'
    instead of a generic scorer failure — these should have been caught
    at config validation, so reaching one at runtime is a harness bug
    worth flagging loudly.
    """

    def __init__(self, scorer_name: str, field: str) -> None:
        super().__init__(
            f"Scorer '{scorer_name}' requires response field '{field}', "
            "which the target did not populate."
        )


class JudgedScorer:
    """Base for LLM-as-judge scorers.

    Subclasses implement `build_prompt` and `parse_judgement`; this base
    owns the shape of the result and the calibration contract. The
    actual model call is injected (`judge_fn`) so every judged scorer is
    unit-testable with a stub and swapping judge models is a config
    change, not a code change.
    """

    #: Subclasses set these.
    name: str = "judged"
    requires: frozenset[str] = frozenset()
    #: Score threshold for `passed`. Tune during calibration, then freeze.
    pass_threshold: float | None = 0.7
    projection_version: str | None = None
    prompt_version: str | None = None
    judgment_version: str | None = None
    rubric_version: str | None = None
    projection_reviewed: bool = False

    @property
    def evidence_settings(self) -> dict[str, str | int]:
        return {}

    @property
    def preparation_configuration(self) -> dict[str, Any]:
        """Explicit authored configuration; never inspect a judge's attributes."""
        return {
            "name": self.name,
            "kind": self.kind.value,
            "requires": sorted(self.requires),
            "judge_model": self.judge_model,
            "pass_threshold": self.pass_threshold,
            "rubric": getattr(self, "rubric", None),
            "rubric_version": self.rubric_version,
            "projection_version": self.projection_version,
            "prompt_version": self.prompt_version,
            "judgment_version": self.judgment_version,
            "evidence_settings": self.evidence_settings,
        }

    def __init__(
        self, judge_fn: Callable[[str], str | JudgeReply], judge_model: str
    ) -> None:
        """
        judge_fn: takes a prompt, returns text or a normalized JudgeReply.
            Kept as a plain callable so the
            harness core has no dependency on any provider SDK.
        judge_model: pinned identifier, recorded into every Score and
            into RunResult.model_versions.
        """
        self._judge_fn = judge_fn
        self.judge_model = judge_model

    @property
    def kind(self) -> ScorerKind:
        return ScorerKind.JUDGED

    # -- subclass surface -------------------------------------------------

    def build_prompt(self, case: TestCase, response: TargetResponse) -> str:
        raise NotImplementedError

    def parse_judgement(self, raw: str) -> tuple[float, str]:
        """Return (value in 0..1, rationale). Raise ValueError if the
        judge output is unparseable — that's an ERROR, not a low score."""
        raise NotImplementedError

    # -- Protocol implementation -----------------------------------------

    def score(self, case: TestCase, response: TargetResponse) -> Score:
        return self.score_prepared(self.prepare(case, response))

    def prepare(self, case: TestCase, response: TargetResponse) -> PreparedJudgeInput:
        self._check_fields(response)
        return PreparedJudgeInput(
            prompt=self.build_prompt(case, response),
            configuration_json=canonical_json(self.preparation_configuration),
        )

    def _check_fields(self, response: TargetResponse) -> None:
        for field in self.requires:
            if getattr(response, field, None) is None:
                raise MissingFieldError(self.name, field)

    def score_prepared(
        self,
        prepared: PreparedJudgeInput,
        *,
        on_call: Callable[[str], None] | None = None,
    ) -> Score:
        """Judge fixed bytes through the ordinary parser and threshold path.

        on_call observes the actual prompt immediately before invocation. It may
        reject a request but cannot replace its content.
        """
        if prepared.configuration_json != canonical_json(
            self.preparation_configuration
        ):
            raise ValueError("Prepared scorer configuration changed")
        prompt = prepared.prompt
        if on_call is not None:
            on_call(prompt)
        raw = self._judge_fn(prompt)
        extra: dict[str, Any] = {"judge_model": self.judge_model}
        if isinstance(raw, JudgeReply):
            extra["judge"] = raw.model_dump(
                mode="json", exclude={"text"}, exclude_none=True
            )
            try:
                value, rationale = self.parse_judgement(raw.text)
            except Exception:  # noqa: BLE001 - parser failures retain safe observations only
                raise JudgeScoringError(raw.observation) from None
        else:
            value, rationale = self.parse_judgement(raw)
        return Score(
            name=self.name,
            kind=ScorerKind.JUDGED,
            value=value,
            passed=(value >= self.pass_threshold)
            if self.pass_threshold is not None
            else None,
            reason=rationale,
            extra=extra,
        )

    # -- calibration hook -------------------------------------------------

    def score_labelled(
        self, labelled: list[tuple[TestCase, TargetResponse, bool]]
    ) -> list[tuple[bool, bool]]:
        """Run the judge over a human-labelled set.

        Returns (human_pass, judge_pass) pairs, ready for an agreement
        statistic (e.g. Cohen's kappa) computed by the calibration
        module. Publish the agreement score alongside any results this
        judge produced — it is the error bar on every judged metric.
        """
        pairs: list[tuple[bool, bool]] = []
        for case, response, human_pass in labelled:
            judged = self.score(case, response)
            pairs.append((human_pass, bool(judged.passed)))
        return pairs


__all__ = ["JudgedScorer", "MissingFieldError", "PreparedJudgeInput", "Scorer"]
