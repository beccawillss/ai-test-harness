# 0002. Validate before executing; an errored scorer errors the whole attempt

Date: 2026-08-13
Status: Accepted

## Context
ADR 0001 settled what an error *means* once recorded, but not when the
harness should notice one. Two questions were left open by the time the
runner was built. First, a pack and a target can be mismatched — a RAG
pack needs `contexts`, a plain model adapter never populates it — and
that mismatch is knowable before a single case executes, but only if
somebody checks. Discovering it on case 400 of 500 wastes the money
already spent and buries the cause under a wall of scorer errors.
Second, when one scorer of five raises mid-attempt, the attempt has
partial evidence: real scores from four metrics, nothing from the fifth.
Something has to decide whether that is enough to call a pass or a fail.

## Decision
Everything knowable up front is checked up front and raised, and a
scorer exception errors the entire attempt rather than being isolated to
its own metric.

`validate_run` in `harness/core/runner.py` runs before any case executes
and raises `ConfigError`/`IncompatibleTargetError` (from
`harness/core/errors.py`) for duplicate case ids, duplicate scorer names,
an empty scorer set, and target/pack capability gaps — the last via the
existing `check_pack_compatibility` in `harness/targets/base.py`, with a
message naming which scorers wanted what. These escape the runner; they
are configuration bugs, not run outcomes. During execution the opposite
rule applies: `_execute_attempt` catches `Exception` from the target and
from every scorer and converts it to `Verdict.ERROR`. All scorers still
run after one fails, so a single run surfaces every broken scorer, and
the scores that succeeded are kept on the attempt for debugging — but
the verdict is ERROR, so the attempt is excluded from the pass rate.

`RunMode.EXPLORE` executes targets and records every attempt as SKIP with
no scorers at all, for inspecting what a new adapter actually returns
before paying to score with it. It relaxes validation to match: a
capability gap is recorded in `config_snapshot["warnings"]` rather than
raised, since finding out whether an adapter populates `contexts` is a
reason to explore in the first place.

## Alternatives considered
Isolating a scorer failure to its own metric — the attempt still gets a
pass or fail from the scorers that succeeded — keeps strictly more
signal, and for a five-metric pack losing one metric to a flaky judge,
throwing the attempt away feels wasteful. It lost because it silently
changes what the verdict *means*: an attempt that passed on four metrics
is not comparable to one that passed on five, nothing in the result says
which happened, and a judge that fails intermittently would make gates
quietly more permissive exactly when it is misbehaving. Deferring
capability checks to runtime (let `MissingFieldError` surface naturally)
was rejected as paying for the discovery; the runner still flags that
error specially, because reaching one means an adapter's declared
capabilities lied and validation was cheated.

## Consequences
A misconfigured run now costs nothing and says what to fix, and a run
that completes has verdicts that all mean the same thing. The price is
sensitivity: one flaky judge call discards an otherwise complete
attempt, so a partly-degraded judge endpoint can erode a run's usable
sample size while `aggregate_pass_rate` still looks healthy — the
remaining attempts really did pass, there are just fewer of them.
`error_rate` is the only thing standing between that and a false green,
which makes reporting it non-optional rather than nice to have. We are
also committed to keeping validation and execution in agreement: any
future scorer whose requirements aren't expressible as capabilities will
have to fail at runtime, and each one weakens the promise that a
validated run is a runnable one.
