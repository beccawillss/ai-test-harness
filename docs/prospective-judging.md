# Prospective judging of captured responses

The generic prospective API judges an existing unjudged `TargetResponse` after
optional human-first review. It never accepts a target and never reruns a
conversation. Historical [judge replay](judge-replay.md) still requires recorded
matching evaluator configuration unless explicitly reconfigured. Prospective
preparation declares a **future** evaluator; it does not fabricate historical
scores or configuration.

This is readiness Milestone 1. The Sales Agent Study v1 profile factory,
independent matrix validator, study orchestration and combined study analysis
remain Milestone 2. No Study v1 cases have been authored by this work.

## Prepare and register

1. Load the source `RunResult` with `SQLiteResultStore(..., read_only=True)` and
   `load_with_fingerprint()`. Supply its original document fingerprint and the
   source cases. `bind_source()` verifies the selected/full dataset, case
   definition, classification snapshot, response and source attempt. A source
   containing a judged score or recorded judged scorer is not an unjudged capture.
   Both v1 and v2 are supported. V2 hashes-only sources require external verified
   cases; full snapshots do not imply that omitted metadata is reconstructible.
2. Freeze `EvaluatorConfiguration` from a reviewed, named/versioned projection
   and explicit safe `JudgeConfiguration`. Construct the preparer with a judge
   callable that raises if invoked. Provider/client construction belongs in the
   later factory, not preparation.
3. Construct a `ProspectiveJudgingPlan` with ordered `ProspectiveSelection`s.
   Each selection declares source provenance, a unique request ID, reserved
   observation ID, role, attempt count and `requires_human`. Primary requests
   have one attempt. Set `taxonomy_evidence` explicitly to `excluded` or
   `explicitly_included`; exclusion requires a reviewed integration projection.
   The default rubric projection includes tags and cannot claim exclusion.
4. Explicitly accept `sharing_policy="evaluation_data"`. Private prospective
   requests preserve the complete normalized response and exact prepared
   evidence/prompt. This is an evaluator artifact, not a public or redacted view.
   Source case payload persistence remains governed independently by the run's
   existing `case_payload_snapshot` policy; neither policy sends evaluator data
   to the target.
5. For protected selections, predeclare the review-set ID and `RatingContract`
   hash. `prepare_prospective()` verifies the source against the plan, clones
   inputs, rejects builder mutation and returns a `PreparedProspectiveJudgment`
   with required `kind="prospective"`. The plan is embedded and its digest
   recorded; observation/source/evaluator/attempt properties derive from that
   immutable plan. The existing replay input hash binds prepared bytes, while
   the whole-request digest additionally binds identities and policy.
6. Save a `PreparedBundle(plan=plan, requests=...)` using
   `ProspectiveStore.save_prepared()`. Its ordered roster must equal the plan.
   Use one store directory for the experiment. Exclusive identity files reserve
   request and observation IDs before human review, even across plans.

Plans, requests and results use schema versions ending in `v1`, frozen models
and canonical JSON strings for nested response/configuration/attempt bodies.
Bundle loading rejects unknown fields/versions, duplicate keys, non-finite
numbers and checksum differences. Nested result attempts are returned as fresh
objects; changing one cannot change a saved result.

## Human review and execution

Create `CalibrationExample`s with `ObservationPolicy(kind="prospective",
artifact_id=request.selection.observation_id)`. The manifest set ID and rating
contract must match the plan. One manifest cannot mix historical and prospective
preparations. Keep its private manifest separate from the reviewer directory.
Existing export/annotation/freeze APIs and exposure declarations are unchanged;
exports contain blank rating fields. This workflow never creates human ratings.

The blind packet contains opaque example IDs and nonce bindings, human rating
instructions, and exactly the projected evidence. It does not expose plan/source
selectors, experimental strata, provider identities, scores or reasons. A
projection's content must itself be reviewed by its integration before export.

Call `execute_prospective(request, source_loader=..., verification_scorer=...,
scorer_factory=..., store=..., frozen_bundle=...)`. The source loader returns
`(RunResult, source_cases, original_document_fingerprint)` from read-only storage.
The verification scorer is a pure preparer. The factory returns
`ProspectiveJudge(scorer, configuration_callback, close_callback)`; it owns client
construction and cleanup. The configuration callback reads actual safe settings.

Execution rebuilds the source/input first. For protected requests it then calls
`load_frozen()`, checks checksums and bindings, and requires the exact complete
protected roster from the plan, including the selected request's precise input
and reserved observation. Partial freezes are never enough. Only after these
checks does it acquire an exclusive execution-start reservation and call the
factory. It rechecks the factory's scorer, projection and actual configuration,
then verifies actual prompt/configuration bytes immediately before each call.
The result records receipt/manifest/packet/annotation hashes, revision and call
start times. A call cannot precede its verified freeze.

An unprotected request requires no human receipt and records `freeze: null`.
Passing an unrelated receipt cannot upgrade it. This is a reproducible workflow
contract, not provider access control: the future study integration must enforce
its full protected-ID policy rather than accepting a replacement unprotected
plan. Independent provider calls are outside the generic API's control.

## Output contracts and failures

`ScoreOutputContract` is optional. It declares a versioned opaque ID,
`kind="anchors"`, and a nonempty ordered unique tuple of finite anchors in [0,1].
Booleans, duplicate/out-of-range/non-finite anchors and malformed contracts fail.
Core contains no study-specific anchor values. `RubricJudgeScorer` accepts the
contract as `output_validation`; absent contracts add no configuration keys and
retain the continuous legacy parser, including 0.7.

When enabled, the exact contract is included in scorer/run configuration and
prepared evaluator fingerprints. Parsing, execution verification, result loading
and calibration observation validation enforce it. There is no rounding,
clamping or retry. The human anchor scale must match an enabled output contract.
The threshold remains separate from permitted scores. Rubric/prompt changes are
integration-owned; enabling validation does not rewrite the legacy prompt.

Malformed/off-anchor output is ERROR with no quality score. JudgeReply safe
provider observations survive parser failure. Timeout/provider failure is ERROR,
not zero; raw responses and exception messages are not persisted. Successful
calls retain their individual score/verdict. Actual input/configuration drift
at invocation is an input-integrity ERROR. Preflight failures raise before judge
invocation; failures after reservation leave that reservation intact.

## Save, recover and analyze

Execution returns the full in-memory `ProspectiveJudgmentResult`; explicitly
call `store.save_result(result)`. Each immutable bundle writes its canonical
document first and checksummed receipt last. An incomplete bundle is unreadable.
A completed observation marker is published after saving the result. Existing
identities/results are not overwritten. `state(request)` distinguishes prepared,
started-unresolved and completed local workflow states; it is not a remote-call
status oracle.

If persistence fails, retain the returned result and retry **only saving**, to
an unused destination if the first write left partial files. Do not rerun the
judge. Construction failure/crash leaves an unresolved reservation; generic code
cannot establish whether an external call occurred and never retries it
implicitly. Partial identity/bundle creation also requires explicit recovery;
no automatic deletion or overwrite occurs. Concurrent execution of an observation
has one reservation winner. This does not promise exactly-once remote execution
across process failure or separately copied stores.

For human comparison, rebuild with `verify_prospective()` and join using
`prospective_observations(example, result, rebuilt, frozen_bundle=...)`. It
verifies the exact reserved observation and recorded receipt before returning
ordinary calibration observations with `frozen_request_verified`. Existing
cohort/exposure rules and arithmetic remain unchanged. `RunResult` and
`ReplayResult` are never rewritten or impersonated. This milestone does not
combine deterministic and delayed semantic outcomes into a study result.

Follow-up judge variance needs a new plan/request/observation ID, diagnostic role
and parent request digest. Supply the original parent to execution. Protected
diagnostics must preserve source, prepared bytes, evaluator, taxonomy policy and
human protection, and use the original parent's complete receipt. A diagnostic
cannot replace a primary human observation; all attempts and errors remain
visible. Parent chains are deliberately limited to the original request.

## Compatibility

New readers must support `prospective-judging-plan-v1`,
`prepared-prospective-judgment-v1`, `prospective-judgment-result-v1`,
`prospective-bundle-v1`, `prospective-receipt-v1` and optional
`score-output-contract-v1`. No package release version is assigned by this
milestone. Older tooling must not resave new artifacts after dropping fields.
Historical replay, calibration envelopes/bindings, dataset schemes and SQLite
schemas remain unchanged. The new pre-change synthetic golden fixture protects
legacy JSON and fingerprints; normal tests require no private runs or providers.
