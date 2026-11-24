# C3b Slice 6e — Detached Spending Observations and Offline Policy Assessment

## Latest independent source QA correction authorisation

On 2026-11-24 independent source QA accepted the architecture, three-file scope,
fixed assurance, exact arithmetic and resource ceilings, and authorised four
targeted corrections in the existing uncommitted additions. This section and the
correction record below supersede conflicting earlier implementation wording.
The first handoff and its verification remain historical evidence, not fresh
verification of the corrected source. No publication is authorised.

- [x] Q0: Recheck all three independently reviewed hashes and the exact baseline;
  reproduce the findings in the actual locked environment.
- [x] Q1: Correct liability attribution, headroom prerequisites, unavailable cost
  comparison and imported identity consistency; expand deterministic regressions.
- [x] Q2: Run fresh complete verification, measurements and post-save preservation.

Correction QA storage: /private/tmp/canary-slice6e-qa-20261124-02.
The original reviewed artifacts and manifest are retained there under
reviewed-before/ and reviewed-before-manifest.json. The complete 231-file
baseline inventory and original checkout/worktree snapshots are preserved.

## Authorisation, baseline and scope

The human operator explicitly authorised offline implementation and verification
of M0–M4 on 2026-11-24. The architecture assessment, detailed ExecPlan, four-part
QA refinement addendum and implementation authorisation are one specification;
the addendum and authorisation clarifications take precedence. No publication,
commit, push, PR, merge, account access, signing, paid dispatch, judge, Study,
live authority or later-slice work is authorised.

Approved parent: `fbec42137f379d7c6e995d92602dd6148a3ae9ad`.
Approved tree: `f99b5dddd689b6f6f40fca5c6323917a9e5bbe25`.
Inventory: exactly 231 protected tracked files.
Branch: `feat/canary-runtime-v3-slice6e-spending`.
Worktree: `/private/tmp/ai-test-harness-canary-runtime-v3-slice6e`.
External QA root: `/private/tmp/canary-slice6e-qa-20261124-01`.

The exact missing merge object was fetched under explicit authorisation using
`git fetch --no-write-fetch-head --no-tags origin <approved-parent>`; sandbox
network/Git metadata access required escalation. No existing ref, worktree,
FETCH_HEAD or dirty Study file was replaced. One new feature branch/worktree was
created from that merge, never the matching PR-head substitute.
External baseline-inventory.json retains every byte, SHA-256, Git blob, mode and
index entry. Original checkout status and worktree registration snapshots are
retained externally. Baseline/index assertions remain outside permanent pytest.

Only three additions are authorised: this plan, src/harness/canary/spending_v3.py
and tests/test_canary_spending_v3.py. All existing files, locks, dependencies,
datasets, fixtures, evidence, schemas and fingerprints remain byte/mode exact.

## Frozen contracts and trust

Five public schemas: canary-spending-assignment-v1;
canary-spending-observation-bundle-v1; canary-expected-spending-reference-v1;
canary-offline-spending-diagnostic-policy-v1; canary-offline-spending-assessment-v1.
Four profiles: spending-manual-claims-v1; spending-operator-export-v1;
openai-admin-spending-claims-2026-11-24-v1; spending-synthetic-fixture-v1.
Outcome vocabulary: CONDITIONALLY_CONFORMANT, NONCONFORMANT, INDETERMINATE,
INVALID_EVIDENCE. No unqualified overall PASS.

Strict immutable models, all serialized fields explicit, bounded canonical UTF-8
without trailing newline, no duplicate/unknown/missing fields, coercion or signed
byte normalization. Every public boundary revalidates constructed/copied models.
Commitments use replay-canonical-json-v1 and separate assignment/policy/bundle
domains. Independent assignment, policy and expected reference are mandatory;
no reference discovery/adoption, signing, publication or persistence API.

Assignment embeds the existing source receipt (definition, inference and limits)
and binds its existing structured digest, intended project/organisation, policy,
profile, prospective purpose, audience and validity. Public definition validation
revalidates metadata only; it does not inspect/authenticate the runtime checkout.
Historical synthetic identifiers never prove real expenditure or change scope.

Every assessment fixes provider_evidence_authenticated, billing_verified,
execution_admission_established, authorises_live_execution,
fresh_source_verification_performed, source_authorised,
observer_identity_authenticated, liability_upper_bounds_independently_verified,
provider_reporting_completeness_established, enforcement_propagation_verified,
maximum_invoice_established and assessment_origin_authenticated to false;
real_external_readiness=UNESTABLISHED;
assurance_class=offline-conditional-diagnostic-only. Matching commitments prove
agreement with supplied anchors, not origin or independent custody.

## Interpretation, freshness and coverage

USD 10 is the maximum permitted configured project threshold, not an exact
required threshold. Smaller thresholds can fail headroom. Hard/enforcing differs
from alert/inactive/unknown/unsupported. Zero-control meaning is unsupported.
Existing historical v3/C3a alert requirements remain distinct; new alerts must be
explicit policy requirements. No alert-recipient or propagation guarantee.

OpenAI profile mappings (dated official references inherited from the reviewed
planning contract, not newly acquired or account-verified during implementation):
- https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/projects/subresources/spend_limit/methods/retrieve
- https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/projects/subresources/spend_alerts/methods/list
- https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/costs
- https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/completions
- https://developers.openai.com/api/docs/guides/spend-limits

Limit/alert thresholds are integer cents; costs use currency-bearing major-unit
amounts. Supplied normalized summaries only: no raw acquisition/normalizer.
Provider timestamps are null for the dated API profile. Account capabilities,
permissions, completeness, Responses attribution and final billing are unverified.

Explicit independent policy ages/lags (1–86,400 seconds), collection span
(1–3,600 seconds); no defaults or provider SLA claims. UTC whole-second dates
2000–2099, explicit clock, half-open assignment/policy/period validity. Invalid
clock raises SpendingError("invalid_clock") before assessment construction.
Supplied period/reset reference and horizon must agree; rollover blocks reuse.

Cost pages, continuous buckets and known amounts are required independently of
liability assumptions. Never replace missing content with reserves. Known
incomplete provider cost reporting blocks decision headroom. Unknown provider
completeness can support only conditional diagnostics with a positive qualified
unreported-exposure bound; complete-reporting-required always blocks on unknown.
Required usage needs all four counters, total=input+output, exact project and
accepted cost window, completions-family scope, continuous declared coverage,
complete pages and fresh collection/window. Counts do not establish billed cost.
Malformed/conflicting/wrong-scope optional data is required reliability ERROR;
absent/stale valid optional data is informational unless required.

## Arithmetic and liability precedence

Money grammar: `^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{0,11}[1-9])?$`.
USD only, no signs/exponents/leading or trailing zeros/float inputs. Integer cents
convert exactly by Decimal 100. Preserve sub-cent precision, no quantization.
Each calculation uses private precision 64, Emin -96, Emax 96, ROUND_CEILING,
all signal traps enabled. Rounding/inexactness/overflow is ERROR. Derived signed
headroom allows 14 integer/12 fractional digits; negative zero is forbidden.

H = L - C - U - I - O - R - M. Four ordered additive liability categories:
incurred_unreported, inflight_unknown, other_consumers, remaining_canary.
No overlap removal. Retain threshold, reported cost, deductions, margin and
minimum residual in the result. Separate hypothetical and decision-eligible H.
Unknown reports/operands never imply zero. H<=0 fails only when decision eligible;
positive H must meet minimum residual. Local USD5/24 calls/72 attempts do not
derive remaining liability or maximum invoice.

Declared upper-bound observations require freshness, support and correct scope.
Independent bound claims additionally retain policy-supplied as-of time/support.
Generic positive policy reserves permit hypothetical arithmetic only unless
qualifying evidence independently supplies the diagnostic bound. Always take at
least known supplied amounts. A contradictory independent bound is ERROR.
Absent/unknown/unavailable observation with reserve alone is sufficiency SKIP.
Stale or unsupported submitted bound remains SKIP despite a reserve; conflicts
and incorrect scope/exposure cannot be substituted around. Underlying liability
establishment and independent verification always remain false.

Positive/unknown attempt counts require a positive full-exposure bound. Even an
explicit zero unknown-attempt count cannot establish zero in-flight exposure:
zero deduction additionally requires a qualified all-inflight-exposure bound.
Unknown provider reporting needs a positive unreported bound, never a zero claim
or generic reserve. Preserve assumptions, provenance and uncertainties per term.

Findings carry immutable REQUIRED/INFORMATIONAL classifications. Required
ERROR>FAIL>SKIP>PASS maps to the four diagnostic outcomes, preserving every
independent finding. Requiring unsupported authentication/bounds/propagation/
billing/org-headroom/comparison produces gating SKIP. Not requiring them cannot
upgrade assurance. Imported assessment parsing checks representation, arithmetic
and internal consistency, never authenticated assessor execution; recompute for
trusted reliance. Historical comparisons and org headroom remain deferred.

## Provisional resource ceilings and verification

Assignment 32KiB; policy 16KiB; reference 4KiB; bundle/assessment 64KiB each;
depth24; 8,192 keys/values; 32 cost buckets; eight alert thresholds; exactly four
liability slots/rules; identifiers128 ASCII; issue occurrences256. Reject, never
truncate. Measure minimal, 31-day/eight-alert, max-precision and issue-rich fixtures.
Ceiling increases require independent QA.

- [x] M0 exact baseline, isolated worktree, external inventory, locked runtime.
- [x] M1 strict contracts, parsing, commitments, bindings and clock boundary.
- [x] M2 provenance, control, freshness, coverage and requirement mapping.
- [x] M3 liability, exact arithmetic and consistent derived assessments.
- [x] M4 focused/regression/full offline tests, static checks, measurements,
  historical identities, full byte/blob/mode/index/addition preservation.

Environment: existing Slice2 .venv, CPython3.12.13, SQLite3.53.1; every installed
registry package matches unchanged uv.lock. No installation/sync. Commands use
env -i PATH=/usr/bin:/bin LC_ALL=C LANG=C PYTHONPATH=src
PYTHONDONTWRITEBYTECODE=1, python -B, pytest -q --tb=short -rs -p no:cacheprovider,
distinct external basetemps; Ruff --no-cache; mypy external cache. Full offline
suite excludes only historical listening-server tests/test_canary_controller.py.
New core tests have no skips. Optional historical integrations are reported as
unexecuted, never successes. Tests cover every reviewed table, bypasses, limits,
clock, arithmetic, independent findings, no network/credentials/SDK/subprocess/
discovery/writes or operational authority. Retain actual failures and corrections.

STOP for wrong baseline, protected-file change, material contract conflict,
resource increase, weak evidence promoted by reserve/policy, favourable incomplete
reporting, unsupported rounding, hypothetical decision headroom, invented clock,
authenticated imported origin or any external execution side effect.

## Initial implementation record (historical verification)

M0 completed: exact approved merge/tree and 231-file baseline verified. Existing
locked package versions all match; no installation.
Final file hashes will be retained in an external manifest generated after the
last plan save, avoiding a self-referential document hash.

M1 completed: five strict immutable public models and supporting typed structures;
bounded canonical byte parsers and serializers; three domain-separated commitments;
independent receipt/definition, assignment/policy, profile and expected-reference
checks. Unsupported/missing/extra fields, duplicate keys, noncanonical encodings,
coercions and model_construct/model_copy bypasses are rejected at public boundaries.
Invalid clocks raise the fixed invalid_clock category before any input access or
assessment construction. No system clock fallback exists.

M2 completed: declared provenance, dated profile units, project/organisation scope,
half-open validity, independent control/cost/usage/liability ages, collection span,
cost/usage lag, monthly period and horizon checks. Complete pages, continuous
buckets and known amounts remain separate from provider completeness. Every
finding retains its REQUIRED/INFORMATIONAL classification; optional supplied
errors are promoted into required input_reliability without erasing other findings.

M3 completed: four ordered additive deductions, separate bound claim versus
effective reserve/floor, exact private-context arithmetic and retained calculation
inputs. Each term records known amount, effective amount, bound amount, basis,
support, as-of time, attempt coverage/count, calculation eligibility, sufficiency,
observation freshness, assumptions and unresolved uncertainty. Representations
validate arithmetic, deduction order/floors, bound qualifiers, liability aggregate,
requirement mapping, unsupported assurance findings and overall aggregation.
Consistent imports remain unauthenticated. No historical cost comparison occurs.

### Public surface

| Model | Exact schema identity | Byte APIs |
|---|---|---|
| SpendingEvidenceAssignment | canary-spending-assignment-v1 | parse_assignment / serialize_assignment |
| SpendingObservationBundle | canary-spending-observation-bundle-v1 | parse_bundle / serialize_bundle |
| ExpectedSpendingEvidenceReference | canary-expected-spending-reference-v1 | parse_expected_reference / serialize_expected_reference |
| OfflineSpendingDiagnosticPolicy | canary-offline-spending-diagnostic-policy-v1 | parse_policy / serialize_policy |
| OfflineSpendingAssessment | canary-offline-spending-assessment-v1 | parse_assessment / serialize_assessment |

Commitment APIs are assignment_commitment, policy_commitment and bundle_commitment.
The assessor is assess_spending(raw: bytes, *, assignment, policy, expected, now).
Supporting SHA-256 references are inert digests, never dereferenced. There is no
file, URL, provider, acquisition, persistence, signing or execution API.

| Profile | Declared provenance |
|---|---|
| spending-manual-claims-v1 | manual_declaration |
| spending-operator-export-v1 | operator_supplied_export |
| openai-admin-spending-claims-2026-11-24-v1 | claimed_administrative_api |
| spending-synthetic-fixture-v1 | synthetic_test |

### Implemented liability decision table

All rows preserve underlying_liability_established=false and
independently_verified=false. "Qualified" means fresh supported bound, correct
scope/exposure and applicable positive/full-exposure requirements. An independent
claim is independently supplied, not independently verified by this implementation.

| Submitted observation | Declared-bound rule | Generic policy reserve | Independent bound claim |
|---|---|---|---|
| Absent, unknown, unavailable | No numeric deduction; SKIP | Positive reserve permits hypothetical arithmetic; sufficiency SKIP | Qualified independent claim may supply conditional sufficiency; missing observation remains visible |
| Present amount claim | Known amount retained; no sufficient bound | max(reserve, known amount); hypothetical unless a qualified bound exists | max(claim, known amount); claim below known amount is ERROR |
| Fresh supported upper-bound claim | Bound may support conditional sufficiency | max(reserve, observed bound); observation must itself qualify | Conservatively retain max(claim, observed bound); no overlap removal |
| Missing supporting reference | SKIP | Cannot repair submitted unsupported upper-bound evidence | Submitted unsupported upper-bound evidence still blocks sufficiency |
| Stale submitted observation | Freshness SKIP; known amount retained | Reserve does not hide staleness | Independent allowance does not hide submitted staleness |
| Conflicting evidence, wrong scope/kind/exposure | ERROR, no numeric use | ERROR, no substitution | ERROR, no substitution |
| Allowance below known supplied amount | No allowance applies | Known amount is an immutable floor | Amount-claim contradiction is ERROR; upper bounds use the larger deduction |
| Positive/unknown in-flight attempt count | Positive qualified full-exposure bound required | Reserve alone remains insufficient | Positive qualified full-exposure claim required |
| Explicit zero in-flight count/amount | Count alone proves nothing; qualified all-inflight-exposure bound required | Zero reserve cannot substitute for unknown | Zero bound permitted only with explicit zero count and qualified full-exposure semantics |
| Unknown provider reporting completeness | Positive qualified incurred-unreported bound required | Positive reserve alone remains hypothetical | Positive qualified independent incurred-unreported claim may support conditional diagnostics |
| Zero reserve for unknown liability | No implicit zero | No usable unknown deduction; SKIP | A separately qualified zero bound can apply only where category semantics allow it |

The bound amount is retained separately from max(reserve, known amount). Adding
a reserve cannot turn a zero bound into positive evidence of unknown exposure.

### Reporting, usage and aggregation tables

| Evidence state | Implemented treatment |
|---|---|
| Missing cost pages/buckets/amounts | Required coverage SKIP; no decision headroom; reserves cannot replace report content |
| Complete supplied pages/buckets/amounts, unknown provider completeness | Only conditional diagnostics under positive qualified unreported bound; completeness remains explicitly unestablished |
| Known incomplete cost reporting | Required coverage SKIP; no numeric headroom calculation |
| complete_reporting_required | Unsupported provider completeness remains required SKIP |
| Required usage | All request/input/output/total counters, total=input+output, exact project/cost window, project_completions_family, continuous coverage, complete pages, fresh collection/window required |
| Missing required counter/coverage | Required usage SKIP |
| Optional usage/alerts absent or stale | INFORMATIONAL SKIP; no assurance upgrade |
| Optional evidence valid | INFORMATIONAL result; usage never establishes billed cost |
| Optional supplied evidence malformed/conflicting/wrong scope | Required input_reliability ERROR |

Always-required findings are structural_validity, expected_reference_agreement,
assignment_policy_binding, profile_conformity, provenance_conformity,
input_reliability, validity, control_freshness, cost_freshness,
liability_freshness, threshold_conformity, enforcement_conformity,
reporting_window_coverage, pagination_coverage, liability_basis_assessment,
diagnostic_evidence_sufficiency and conditional_headroom.
Usage findings follow require_usage; alert_conformity follows nonempty explicit
required alerts. Completeness follows complete_reporting_required. Each unsupported
assurance finding follows its explicit require flag and always remains SKIP.
The immutable requirement_basis records these inputs.

| Required aggregate | Diagnostic outcome |
|---|---|
| Any ERROR | INVALID_EVIDENCE |
| Otherwise any FAIL | NONCONFORMANT |
| Otherwise any SKIP | INDETERMINATE |
| All PASS | CONDITIONALLY_CONFORMANT |

All independent findings survive aggregation. UNAVAILABLE has no numeric result.
HYPOTHETICAL has hypothetical_headroom_usd only and conditional_headroom SKIP.
DECISION_ELIGIBLE retains both numeric fields; H<=0 or H below the policy minimum
is FAIL, otherwise PASS. The earlier all-other-required-findings-PASS gate is
superseded by the explicit financial prerequisites documented in the source QA
correction record. Independent assurance requirements still gate overall conformity.

### Verification and corrections

The complete final command lines, UTC start times, elapsed times, exit statuses
and production/test source hashes are retained in external *-command.json files.
run.py launches the locked interpreter in the isolated worktree with only PATH,
LC_ALL, LANG, PYTHONPATH=src:tests and PYTHONDONTWRITEBYTECODE, using python -B.
All logs, pytest basetemps and mypy caches remain outside the worktree.

Development focused runs passed 166, then 235, then 238 tests as coverage grew.
An intermediate test-file insertion caused a collection syntax error; the test
placement was corrected. A subsequent targeted run had one failure because the
issue ceiling was wrapped as invalid_input; a bounded preflight now preserves
the fixed resource_limit category. The next complete focused run passed 254 tests.

Source review additionally found and corrected:

- Positive reserve plus a zero bound could incorrectly qualify unknown exposure.
  Separate bound_claim_usd and effective_amount_usd prevent this; three added
  regressions passed in the 238-test run.
- Imported sufficient deductions could omit their supporting digest or independent
  as-of time, or retain a bound above the effective deduction. Internal validation
  now preserves those bound qualifiers and floors.
- The issue-occurrence ceiling counted findings but omitted deduction assumptions
  and unresolved uncertainties. All three issue-bearing fields now count toward
  the unchanged 256 ceiling. Five new import/resource regressions first failed
  against the earlier source, demonstrating the gaps, then drove the corrections.

The review corrections required no schema identity, file-scope, monetary, resource
ceiling or assurance change. Final verification below supersedes earlier runs.

The process audit imports the module and exercises all public byte/commitment/
assessment boundaries under audit hooks denying network, subprocesses, SQLite,
writes and private-file access. After normal module loading it also denies
directory enumeration. It rejects provider-secret lookups, checks SDK/application
modules remain unloaded, and permits only normal imports/definition metadata.
An independent test forbids runtime-checkout inspection. No credential or external
operational evidence was acquired.

Fresh focused verification on the final production/test identities:
259 passed, zero skips, pytest elapsed 43.53s (wrapper 43.93s), exit 0.
ruff-reviewed: all src/tests checks passed, exit 0.
mypy-reviewed: all 68 source files passed, exit 0.
format-reviewed: both new Python files already formatted, exit 0.
Exact invocations are in the corresponding external command records.
full-reviewed: 4555 passed / 6 historical optional skips in 957.89s (15m57s),
wrapper 958.43s, exit 0, final production/test identities. No failures.
regression-reviewed: 1545 passed / 1 historical optional skip in 675.81s
(11m15s), wrapper 676.29s, exit 0, final production/test identities. No failures.
The subset covers unchanged execution, selection, runtime/evidence, approval,
authority, journal/faults, envelope, human-review/packet/register, controller,
driver and instrumentation contracts. It uses the same 15 test files listed in
regression-reviewed-command.json and is also included in the final full run.

Initial static development feedback (import ordering/unused imports, strict
datetime/subprocess test style, and a mypy schema_id kwargs type complaint) was
corrected before the clean final runs. No baseline file was changed to satisfy
static checks. No final check is incomplete or failed.

### Measured resource acceptance

All sizes are canonical UTF-8 bytes from actual serializers, not estimates.
The large fixture combines 31 daily buckets, eight alert thresholds, 128-character
identifiers and maximum-precision liability amounts. Its large negative headroom
is correctly NONCONFORMANT. The issue-rich fixture preserves failures alongside
reliability errors and is INVALID_EVIDENCE. No ceiling increased.

| Fixture | Assignment / 32768 | Policy / 16384 | Reference / 4096 | Bundle / 65536 | Assessment / 65536 |
|---|---:|---:|---:|---:|---:|
| Minimal valid | 4003 | 2078 | 427 | 4303 | 7690 |
| 31-day / eight-alert / max precision | 4457 | 2561 | 540 | 11611 | 8150 |
| Issue-rich | 4003 | 2076 | 427 | 3524 | 8107 |

Maximum measured depth is 6 of 24 and key/value count 790 of 8192.
Assessment issue occurrences are 29 (minimal), 29 (large) and 52 (issue-rich),
including all deduction assumptions and uncertainties, against the ceiling 256.
The exact measurements, issue-occurrence counts, outcomes and matching source
hashes are in external measurements-and-identities.json. Dedicated rejection
tests exercise every provisional cap, including all issue-bearing deduction
qualifiers, without truncation. These measurements accept the provisional limits
for the reviewed representative fixtures, not arbitrary future billing exports.

### Historical identity preservation

Fresh recomputation matched every reviewed value:

| Identity | SHA-256 |
|---|---|
| C1 roster | e8778ce74a270e6efbe490198d01e8b9c50bcc43387a02bff5f00b42304d5794 |
| C1 acceptance | 646fd93488667251a67a02d98548e1aface9353d2a4bb7594a7343d664f1aa65 |
| v2.1 acceptance | 3c632f6ce5e8b9eda42b4a0a0f91ccb82f4f34783da3b9638762b84351c9c2f9 |
| v3 roster | 564b98533b5b48b13d7d97fec8c150c329a6bf5d7ed38f0f165bae32a8493e17 |
| v3 definition | e76fd0e10f1176d6aa421a2b5de93f9503dceaa422b0631c2c8f7c957aa75607 |
| v3 acceptance | 575e304da8203b537d281d82a667e73dbf419fc95caee8df82dea6e7feabfce7 |
| v3 execution | a4d8cdaaa4960ddf406c37703965d164595cea320cfa83c0ddd40fad797fa551 |
| uv.lock | a8a1997cb57cf88bad6d8b00e38efa0b62b77c2ad0057c667ab52933585b1dba |

Historical limits remain 24 logical calls, 72 provider attempts, USD5 local pause,
USD10 monthly control and their original independent alert requirements. The new
module neither reinterprets synthetic identities as real incurred costs nor
changes any operational admission path.

The external static privacy/isolation review passed: only the declared standard
library, Pydantic, existing runtime models/definition validator and fingerprint
imports; no direct filesystem, network, subprocess, environment lookup or system
clock calls. Whitespace and private-key/common credential-token pattern scans
passed for all three additions. This complements the exercised process audit;
pattern scanning alone is not a general proof of absence of secrets.

Earlier-source regression-final completed 1545 passed / 1 skipped in 686.27s;
full-final completed 4550 passed / 6 skipped in 947.31s. These fresh runs began
before the last five review regressions and corresponding validation corrections;
they are retained as superseded development evidence. Final-source results below
must match the final production/test SHA-256 identities.

The historical optional skips are explicit non-execution:

- test_canary_controller_v3_application.py: explicitly enabled pinned application
  suite, CANARY_V3_APPLICATION_TESTS=1 absent.
- test_canary_instrumentation_v3_sdk.py: optional pinned OpenAI 3.3.1 runtime.
- test_canary_sdk.py: optional openai package absent.
- test_canary_selection_state.py and test_canary_state.py: optional pinned
  application runtime absent.
- test_canary_runtime_v3.py: optional pinned CPython 3.13 worker absent.

No dependency was installed to activate optional integrations, no application
suite was enabled, and the approved listening-server module exclusion remains
tests/test_canary_controller.py. No new spending test is skipped.

### Remaining limits and publication boundary

All observations, support digests, observer identities and bound claims remain
caller declarations. Commitments are supplied-anchor agreement, not authenticated
custody. Definition metadata revalidation does not inspect the assigned runtime.
No provider account, spending-control change, credential, billing reconciliation,
execution admission, signing, judge, Study or later-slice work was performed.
Usage is completions-family evidence, not billed-cost proof or Responses coverage.
Provider reporting completeness, control propagation, future stability, actual
liability, maximum invoice and organisation-wide headroom remain unestablished.
Negative cost/credit adjustments, arbitrary provider exports, historical cost
comparison, authenticated origin and external acquisition remain unsupported.
Future broader fixtures must fit the unchanged caps or return to independent QA.

### Initial handoff preservation and disposition (superseded source)

All M0–M4 work is complete. No protected baseline change, ceiling increase,
material contract conflict or publication occurred. The only new repository
files are spending_v3.py, test_canary_spending_v3.py and this living plan; all
remain untracked because the original 231-entry index is preserved. No generated
artifact, cache, extra fixture or executable addition is permitted in the worktree.

Final production SHA-256:
ac5e49b454abf336ab2988feff8f40567473ddb934187693e0c86734b5d855d3.
Final test SHA-256:
2024e06f210c3bd783bf7baa0f39ca7428f607b22947ab9d8c6a3b34a678e949.
All six final verification command records and representative measurements bind
to these exact identities.

The external gate runs after this last plan save. Its authoritative final outputs
are /private/tmp/canary-slice6e-qa-20261124-01/preservation-final.json and
/private/tmp/canary-slice6e-qa-20261124-01/verification-final.json. They retain
the final plan SHA-256 without self-reference, all three sizes/modes/SHA-256s,
exact approved HEAD/tree, all 231 protected bytes/blobs/modes/index entries,
the exact three-file/generated-artifact inventory, original checkout status and
worktree-registration preservation, final command/source-hash agreement, resource
measurements, historical identities and the final whitespace/privacy review.
The full original baseline bytes remain in external baseline-inventory.json.

Recommendation: GO for independent source-code QA. CONDITIONAL GO for later
publication only after successful independent source QA and separate explicit
human publication authorisation. This implementation establishes no external
readiness or live execution authority. Stop here: no commit, push, PR, merge,
provider acquisition or later-slice activity is authorised or performed.

## Targeted independent source QA correction record

The four findings were reproduced before production edits using the locked
CPython 3.12.13 environment. qa-reproduction recorded 12 expected failures in
2.20s against the exact reviewed production SHA-256. The earlier uploaded source,
tests and plan were independently hash-checked and archived externally before
editing. The first correction suite passed 271 cases. The expanded 368-case run
found two consistency failures because the newly added validator omitted the
zero-reserve issue from its expected finding; that diagnostic and the original
zero protection were retained consistently. The next 368-case run passed.
An initial static run found tuple/style annotations and one unused test binding;
these were corrected. Final regression results below supersede development runs.

### Finding 1 — Resolved: separate claims and attribution

The unpublished canary-offline-spending-assessment-v1 representation has three
additional required EffectiveDeduction fields:

- observed_evidence: ObservedLiabilityEvidence or null. It retains the complete
  normalized LiabilityObservation, bundle declared_provenance, its own freshness
  and its own qualification. The original amount, digest, availability, collection
  stamp, project scope, exposure window, attempt count and coverage remain together.
- policy_evidence: PolicyLiabilityEvidence. It retains the independent policy's
  LiabilityRule, SpendingScope, its own freshness and qualification. Rule source
  identifies a generic policy reserve, independently supplied bound claim or
  delegation to declared observation evidence. Policy amounts/digests/as-of times
  and coverage cannot replace the observed claim's metadata.
- selected_bound_source: observation, policy or null. This identifies the claim
  described by the existing flat bound_claim_usd, supporting_reference_sha256,
  bound_claim_as_of and attempt_coverage fields. The existing basis still describes
  the policy's calculation rule, rather than the selected evidence's provenance.

ObservedLiabilityEvidence fields are observation, declared_provenance, freshness,
qualification. PolicyLiabilityEvidence fields are rule, scope, freshness,
qualification. Both are strict frozen supporting models, not new versioned public
schemas. Exactly five public schema identities and four profiles remain unchanged.

Each bound is qualified separately before selection. Scope, exposure, support,
freshness, positive reporting-gap amount and full-inflight coverage/count rules
apply to that claim. In-flight zero still requires explicit zero count plus a
qualified all-inflight-exposure bound. Observed unknown-attempt count is retained
as observed context; policy attempt coverage is never borrowed from the observation.

Select the largest qualified claim, preferring observation for equal amounts.
When none qualifies, retain the largest available claim and its own metadata as
unqualified evidence; this cannot establish sufficiency. A reserve is never a
bound candidate. Effective arithmetic retains the conservative maximum of policy
allowance and known supplied amount where allowed by the reviewed resolution
table. Amount-claim contradictions remain ERROR with no numeric use.

Every applicable submitted upper-bound qualification remains gating, including
a losing claim. Thus fresh positive observed full-exposure bound plus independently
supplied zero bound selects the observed positive claim. If zero independently
qualifies (explicit zero count/full coverage), both can support conditional
diagnostics; if zero is unqualified (positive/unknown count or partial coverage),
its required SKIP remains, and the arithmetic is hypothetical. Conversely, a
positive policy bound cannot conceal an unqualified submitted observed zero bound.
Future/conflicting/wrong-scope claims remain ERROR. Stale/unsupported submitted
claims remain SKIP even when the other candidate qualifies. Generic reserve-only
metadata is informational; reserve-only liability sufficiency remains required SKIP.

The representation validator checks original amount/count attribution, record
qualification and classifications, deterministic selected-claim mirrors, aggregate
sufficiency, source/freshness/provenance agreement and the existing monetary floors.
Underlying liability and independent verification remain false for every term.

Compatibility: these changes are additive to the unpublished assessment v1 only.
Earlier assessment bytes lack required evidence records and must be recomputed;
there is no silent field inference, migration or provenance upgrade. Assignment,
policy, bundle and expected-reference input schemas and commitment domains did
not change. There are no protected historical assessment fixtures to migrate.
All imported representations still require independent recomputation for reliance.

### Finding 2 — Resolved: financial prerequisites versus overall conformity

The all-other-required-findings-PASS headroom gate is superseded. A shared explicit
_headroom_eligible predicate is used by both assessor and representation validator.
Its prerequisites are structural validity, expected-reference and assignment/policy
binding, profile/provenance conformity, required input reliability and validity,
control/cost/liability freshness, threshold/enforcement conformity, reporting-window
and pagination coverage, liability-basis assessment and diagnostic evidence
sufficiency. Required usage freshness/assessment and complete-reporting-required
are still financial evidence prerequisites when explicitly configured.

Independent authentication, independently verified bounds, propagation, final
billing, organisation headroom, historical comparison and alert conformity gate
overall conformity separately. Their unsupported/absent SKIP cannot erase an
otherwise assessable conditional headroom FAIL. Malformed supplied optional data
still yields required reliability ERROR, so unreliable operands do not become
decision-eligible. All fixed assurance limitations remain in force.

For H=-1, H=0 and H=0.5 with minimum 1, conditional headroom is FAIL despite
unsupported independent requirements; outcome NONCONFORMANT. With H=1 it is PASS,
but the unsupported required finding keeps outcome INDETERMINATE. Genuinely
hypothetical liability arithmetic remains conditional_headroom SKIP for every
amount. ERROR > FAIL > SKIP > PASS and preservation of independent findings remain.
The validator rejects both fabricated decision eligibility and reintroduction of
the superseded all-required gate into an otherwise eligible hypothetical result.

### Finding 3 — Resolved: unavailable cost-window comparison

_usage_report returns SKIP cost_window_unavailable when no normalized cost report
is available. A present incompatible cost window remains ERROR window_mismatch.
Independent usage scope/window checks, malformed payloads, counter inconsistency,
conflicting availability and future timestamps still produce required reliability
ERROR, including optional usage. Missing costs still block decision headroom and
favourable conformity. Both required and optional usage paths are exercised.

### Finding 4 — Resolved: imported identity availability

Representation validation enforces the assessor's identity availability stages:
assignment requires policy; bundle requires assignment/policy; bundle commitment
and declared provenance are available together. Structural PASS requires all four
identities; structural ERROR permits legitimate partial prefixes. Binding/reference
PASS additionally requires structural PASS and the complete identity set. Complete
identities are retained on later failed/indeterminate assessments, including
reference mismatch. Successful and decision-eligible results therefore cannot
claim missing commitments/provenance. Nulling identities is rejected by both byte
parsing and serialization of copied/constructed models. Legitimate malformed-policy,
assignment, expected-reference and bundle failures still round-trip with unavailable
identities. These checks do not authenticate origin or establish assessor execution.

### Fresh verification in correction QA root

The final production/test bytes were frozen for the relevant unchanged regressions
and the complete approved offline suite. Fresh focused-final passed 374 tests
in 52.27s with zero skips: 115 cases were added to the originally reviewed 259.
The process audit exercises import and every public API without operational side
effects. ruff-final passed all src/tests; mypy-final passed all 68 source files;
formatting-final passed both new Python files. No dependency was installed or
updated. environment-confirmed rechecked every installed registry package against
uv.lock and the original environment; the editable harness 0.1.0 is recorded
separately. A first environment helper assertion mistakenly included that local
editable package in a registry-only comparison; this was corrected without any
environment change.

Fresh resource measurements on the corrected final source (canonical UTF-8):

| Fixture | Assignment | Policy | Reference | Bundle | Assessment | Assessment issue occurrences |
|---|---:|---:|---:|---:|---:|---:|
| Minimal | 4003 | 2078 | 427 | 4303 | 14418 | 37 |
| 31-day / eight-alert / maximum precision | 4457 | 2561 | 540 | 11611 | 17702 | 37 |
| Same large fixture with both independent/observed bounds and required billing | 4457 | 2991 | 540 | 11611 | 18071 | 33 |
| Issue-rich | 4003 | 2076 | 427 | 3524 | 13305 | 68 |

Maximum depth 7/24, values 1074/8192, issues 68/256; no cap increased. The large
mixed-bound fixture is decision-eligible and NONCONFORMANT despite required final
billing SKIP, demonstrating independent headroom FAIL preservation. All original
C1/v2.1/v3 identities and lock digest were freshly recomputed and match the
historical identity table above. measurements-and-identities.json and the
measured-final command record bind those results to the corrected source bytes.

full-final completed on the corrected source: 4670 passed / 6 historical optional
skips in 830.47s (13m50s), wrapper 830.94s, exit 0. The six skips are exactly the
optional pinned application, SDK and CPython 3.13 cases listed in the original
record above; they were not executed or counted as successes. The approved
tests/test_canary_controller.py listening-server exclusion was retained. No new
core test was skipped and no required final check is incomplete or failed.

regression-final completed on the corrected source: 1545 passed / 1 historical
optional pinned CPython 3.13 worker skip in 605.94s (wrapper 606.33s), exit 0.
The same 15 unchanged canary contract test files from the original approved
programme executed. verification-preflight.json confirms all original spending
test bytes remain an unchanged prefix of the expanded test file; no assertion
was weakened. Completed final focused/static/measurement command records match
the exact current production/test SHA-256 identities.

### Correction preservation and final disposition

Q0–Q2 are complete. All four independent source QA findings are resolved within
the authorised three-file scope. The original approved parent, tree, 231 baseline
files/bytes/blobs/modes/index entries and historical contracts remain unchanged.
The independent exhaustive inventory gate permits only the same three untracked,
regular, non-executable additions and rejects generated artifacts. Original
checkout status and all existing worktree registrations still match their saved
snapshots. Final whitespace, static privacy/isolation, process audit, resource,
historical fingerprint, focused, unchanged regression and full-suite checks pass.

Corrected production SHA-256:
5a9c7221251f905f301b4fce460180974ebdfdb8bc327c50809018c18a0b9e93.
Corrected test SHA-256:
20200242be7c8e55e6d83ee980050833432cf60dd11dde998ea0e55f26fcfbad.
All final execution records bind to these exact production/test bytes. The final
plan SHA-256, without self-reference, is generated after this last save in the
new correction QA root: /private/tmp/canary-slice6e-qa-20261124-02.
Authoritative artifacts are preservation-final.json, verification-final.json,
privacy-final.json, measurements-and-identities.json and verification-preflight.json.
Actual full command lines, timings and statuses are retained in *-command.json
with their matching logs. Earlier handoff artifacts remain archived and unchanged.

Recommendation: GO for independent source re-QA of the corrected artifacts.
CONDITIONAL GO for later separately authorised PR publication, subject to that
review and explicit publication authorisation. All remaining offline assurance
limitations still apply; no authenticated origin, provider/billing verification
or external readiness is established. Earlier unpublished v1 assessment bytes
require recomputation. No dependency, resource-ceiling, authority, historical
contract or architectural expansion occurred. Stop without commit, push, PR,
merge, provider acquisition, credentials, account mutation, live execution,
judge, Study or Slice 6f work.


## Final targeted assessment consistency corrections — 2026-11-24

The operator authorised only two further representation consistency fixes after
independent re-QA accepted the four original findings. The approved parent/tree,
three-file scope, offline environment, assurance limits and stop boundary remain.
External records for this pass are in
/private/tmp/canary-slice6e-qa-final-consistency-20261124. Earlier correction records
and the reviewed ZIP remain unchanged in the prior QA root; reviewed source
snapshots are retained in the new root.

- [x] C0 Confirm reviewed hashes, locked environment and exact preservation gate.
- [x] C1 Reproduce the reserve-floor and all three timestamp contradictions before
  implementation changes using the actual locked CPython 3.12.13 environment.
- [x] C2 Share existing liability resolution and observation timestamp predicates
  between assessor and representation validator; add targeted regressions while
  retaining all previous test bytes as an unchanged prefix.
- [x] C3 Fresh focused/full Slice 6e, unchanged relevant and full approved offline
  regression, static, privacy, resource and exact preservation verification.
- [x] C4 Save results, freeze final identities in external manifest, export and
  verify only the three final artifacts, including operator Downloads access.

The confirmed pre-fix run reproduced reserve 6 -> deduction 1 with self-consistent
headroom 4 and retained successful freshness with future collection end, reversed
collection interval and provider timestamp later than collection end: four
expected rejection tests failed because parsing accepted each representation.
A qualified independent bound already rejected this reduction by its selected
bound floor. Additional regressions cover stale/unqualified independently retained
policy claims whose observed claim remains selected. An initial test parameter
accidentally shadowed the module source fixture; this test-only collision was
corrected before the confirmed reproduction, without production changes.

Finding A: _resolved_liability_amount is shared by assessment construction and
EffectiveDeduction validation. It resolves from the retained observation and
policy rule using the existing qualified declared-bound, maximum allowance/known
amount, zero-inflight/count, positive reporting-gap, zero-reserve/unknown and
ERROR rules. The imported effective amount must equal that resolution, including
null when unavailable; editable calculation_inputs cannot override it. Hypothetical,
unqualified, missing and conflicting states retain their original treatment.

Finding B: _observation_time_error is shared with _fresh. For each retained
liability observation the assessment validator checks collection ordering,
collection end against assessed_at and provider timestamp against collection end.
Contradictions require the existing future_or_reversed_timestamp ERROR freshness
finding; conflicting availability retains its existing conflicting_observation
ERROR precedence. No age/span policy is reconstructed because its limits are not
retained. Legitimate assessor-generated invalid evidence round trips remain valid.
Imported consistency does not authenticate freshness or origin; independent
recomputation remains required for trusted reliance.

No schema identity, field, dependency, capability or resource ceiling changed.
Verification results and post-save artifact identities follow below when complete.

### Fresh final consistency verification — completed checks

focused-final passed 532 tests with zero skips in 80.72s (wrapper 81.00s), including
158 new targeted cases. The previously accepted 374-test file remains a literal
71,050-byte prefix: no prior test or assertion was changed. Coverage includes
smaller deductions for reserves and independent bounds; missing and stale-policy
claims; all four liability kinds; valid unavailable/hypothetical/conflicting and
unqualified round trips; future end/reversed interval/provider-after-end rejection
for all liability kinds; copied-model serialization rejection; invalid timestamp
ERROR round trips for present/unknown/unavailable/conflicting observations; and
valid exact assessment-time/provider-time boundaries.

ruff-final passed all src/tests, formatting-final passed both new Python files,
and mypy-final passed all 68 source files. environment-final confirmed unchanged
CPython 3.12.13, SQLite 3.53.1 and every installed registry package against uv.lock;
no installation or dependency update occurred. verification-preflight.json checks
that all model fields, public schema identities and resource ceilings are unchanged.
The external privacy scan and process audit in the focused suite passed.

Resource measurements on the final production/test bytes are unchanged from the
accepted correction record: minimal assessment 14,418 bytes; 31-day/eight-alert/
maximum-precision assessment 17,702 bytes; mixed observed/independent-bound assessment
18,071 bytes; issue-rich assessment 13,305 bytes. Maximum assessment bytes remain
18,071/65,536; depth 7/24, values 1,074/8,192 and issue occurrences 68/256. All C1,
v2.1/v3 historical identities and the uv.lock digest match their retained values.
The mixed-bound fixture still preserves NONCONFORMANT headroom despite a required
final-billing SKIP. measurements-and-identities.json retains all per-object values.

The unchanged relevant and full approved offline regressions completed successfully.
Their actual final outcomes, exact preservation and export disposition follow.


### Final completed regression, preservation and export disposition

regression-final passed 1,545 unchanged tests with the same single historical
optional pinned CPython 3.13 worker skip in 605.75s (wrapper 606.09s), exit 0.
full-final passed 4,828 tests with the same six historical optional skips in
866.08s (14m26s; wrapper 866.52s), exit 0. The only approved listening-server
exclusion remains tests/test_canary_controller.py. No new skip, exclusion,
required-check omission or baseline alteration was introduced. The final external
gate compares actual command lines and skip reasons with the accepted prior run.
The 158 added cases account for the increase from 4,670 to 4,828 passing tests.

Production SHA-256: 61f6bf03fc70406db405b65996bef5f1018731231aa7d0646ee91fe218a909f7
Test SHA-256: baca56b310183b9513f2d3d6142ee5e45de636c46110d1418fd2be3dd386d145

All final execution records bind to those exact production/test bytes. The plan's
own SHA-256 is recorded after this final save in preservation-final.json and
verification-final.json in the new external QA root, avoiding self-reference.
The post-save exact preservation gate confirms approved parent
fbec42137f379d7c6e995d92602dd6148a3ae9ad and tree
f99b5dddd689b6f6f40fca5c6323917a9e5bbe25, all 231 baseline file bytes/blobs/modes
and index entries, the original checkout status and all worktree registrations.
Only the same three regular non-executable uncommitted additions are permitted.
Final privacy/whitespace, prior-test-prefix and historical-identity gates pass.

The verified export is slice6e-qa-artifacts-final-consistency.zip in the new QA
root, with the same filename made accessible in /Users/rebeccawilliams/Downloads.
It includes only the implementation, test file and this plan at their original
repository-relative paths. export-final.json records the archive identity and
checks each archived entry's bytes against the post-save preservation manifest;
downloads-final.json records existence and identical SHA-256 of the Downloads copy.
Neither private evidence nor verification caches/logs enter the ZIP. Earlier
reviewed exports remain unchanged. Actual command lines, timings and results are
retained in the new QA root's matching *-command.json and *.log records.

Both remaining findings are resolved within the narrow authorised scope. All
four originally accepted corrections remain covered, and all prior tests pass.
No architectural redesign, new schema identity, dependency, assurance capability,
resource-ceiling increase or implementation-scope deviation occurred. Imported
assessment consistency does not establish authenticity; independent recomputation
remains required for trusted reliance. Conditional publication disposition remains
subject to independent review and separate explicit publication authorisation.

STOP after verified export. No commit, push, PR, merge, provider access, live
execution, judge, Study or Slice 6f work was performed or is authorised here.
