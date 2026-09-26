# ADR 0004: Fixed-response replay is a separate judge experiment

Status: accepted, 2026-09-26. Implements the approved
[ExecPlan](../plans/judge-replay-calibration.md).

Repeated normal runner attempts invoke both target and judge. Their score
distribution cannot isolate judge variance. Historical semantic results already
persist complete normalized TargetResponses, but do not retain exact judge
request bytes. Re-executing a target or changing stored runs would answer a
different question and erase provenance.

Use a provider-neutral prepare/replay API accepting a saved RunResult, a
verified compatible frozen dataset and an existing JudgedScorer. Accept no Target
and never invoke the normal runner. Verify the entire source selection hash,
selected case and stored attempt index. Reject missing evidence instead of
reconstructing it. Prepare one immutable prompt/evidence snapshot and invoke the
existing parser/threshold path repeatedly. Compare actual invocation hashes and
current explicit settings. Preserve per-call errors and safe observations without
raw replies or mutable last-response state.

Persist a separate versioned ReplayResult in a `replays` table, with a new ID,
source identity/fingerprints and ordered outcomes. The recipe opens the source
database read-only and requires a different destination. Source RunResults and
datasets remain unchanged. The replay artifact contains the safe prepared
evaluation content, not copied target responses or historical scores. Source
locators are logical or repository-relative; absolute local paths are execution
details. Evaluation prose can contain sensitive information despite operational
field allowlists, so replay artifacts remain evaluation data.

Strict source-configuration compatibility is the default. Explicit reconfigured
experiments record differences/unknowns without bypassing evidence verification.
Matching recorded settings does not prove bytes of an unsaved historical prompt;
new replay calls do prove identical prepared input. Requested and observed model
identities remain distinct, and stateless requests do not prove IID samples.

Statistics are descriptive: successful-score distribution, population standard
deviation, errors separately, and threshold-crossing instability. No acceptable
variance threshold, calibration claim or target release verdict is introduced.
ReplayResult is deliberately separate from compare_runs and target quality
gates. Full source context remains available through the unchanged source
document, while stable fingerprints support later human-rating joins.

Consequences: existing score(case,response) and scorer subclass hooks remain
usable; replay adds a preparation boundary instead of a second semantic framework.
Generic callers must provide reviewed projections, trustworthy recorded-config
translation and stateless judges. Runs without a recoverable matching dataset
cannot replay. End-of-run persistence does not offer crash recovery. Live judge
acceptance remains explicit and is never part of the default offline test suite.
