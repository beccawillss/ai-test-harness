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

from typing import Any, Protocol, runtime_checkable

from harness.core.models import Score, ScorerKind, TargetResponse, TestCase


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
    pass_threshold: float = 0.7

    def __init__(self, judge_fn: Any, judge_model: str) -> None:
        """
        judge_fn: Callable[[str], str] — takes a prompt, returns the
            judge model's raw text. Kept as a plain callable so the
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
        for field in self.requires:
            if getattr(response, field, None) is None:
                raise MissingFieldError(self.name, field)

        raw = self._judge_fn(self.build_prompt(case, response))
        value, rationale = self.parse_judgement(raw)
        return Score(
            name=self.name,
            kind=ScorerKind.JUDGED,
            value=value,
            passed=value >= self.pass_threshold,
            reason=rationale,
            extra={"judge_model": self.judge_model},
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


__all__ = ["JudgedScorer", "MissingFieldError", "Scorer"]
