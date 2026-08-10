# 0001. Errors are never quality failures

Date: 2026-08-08
Status: Accepted

## Context
Eval runs involve two unreliable systems: the target under test and the
scoring infrastructure (judge APIs, network, adapters). Both can fail
mid-run. If an infrastructure failure is recorded as a failed case, a
flaky judge endpoint looks identical to a product regression, and a CI
gate can block a release for a problem that has nothing to do with the
product. Traditional test frameworks distinguish failures from errors
for the same reason.

## Decision
Exceptions raised by the target or a scorer are recorded as
Verdict.ERROR and are excluded from pass-rate calculations entirely.
Pass rates are computed only over attempts that produced a genuine
pass/fail judgment (CaseResult.pass_rate in harness/core/models.py).
Runs report their error rate separately so infrastructure problems are
visible rather than silently absorbed.

## Alternatives considered
Counting errors as failures (simpler, one number) was rejected because
it makes gates untrustworthy — teams learn to re-run and ignore red.
Retrying errors transparently was rejected as a default because it
hides instability in the harness itself; retries may be added later as
explicit, counted behaviour.

## Consequences
Regression gates only fire on evidence about the product, which keeps
them credible. The cost is a second number to monitor: a run can be
"green" on quality while degraded on errors, so reports must surface
error rates prominently or broken infrastructure could go unnoticed.