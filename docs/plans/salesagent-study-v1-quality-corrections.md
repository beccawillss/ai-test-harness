# Study v1 pre-freeze quality corrections

## Current follow-on: no-match search proofs — 2026-10-26

The user authorized correction of the four reproducible no-match search
weaknesses after human QA and the read-only readiness assessment. The bounded
[no-match correction plan](salesagent-study-v1-no-match-oracles.md) records the
acceptance policy, implementation, offline checks and renewed confirmation for
SA-CON-002, SA-CON-005, SA-RCV-003 and SA-RCV-004. All other case definitions,
methodology, memberships and semantic contracts remain protected. This work is
isolated from the original dirty checkout and awaits implementation review;
no actual Study freeze, live execution, commit, push or merge is authorized.
The earlier milestone and authorization entries below remain historical.

## Warmth commit and PR authorization — final verification

The user reviewed the warmth implementation handoff and authorized commit/push
of `feat/study-v1-warmth-evidence` and PR preparation against `main`. This
supersedes the implementation-stage commit/push restriction below. Formal human
QA, actual Study freeze, live target/judge execution and PR merge remain separate
human decisions.

A fresh fetch confirms the feature branch starts exactly at current `origin/main`
`da85619c6b743bc73ab4ef425d49a1482934c1ed` (merged P2 PR #17); no transfer, merge,
rebase or implementation reconciliation is required. Complete review confirms
exactly the approved 14 changed/new files. All 142 other tracked files are
byte-identical to main, including every dataset/suite file, methodology,
authoring specification, matrix, historical data and the existing discount scorer.
The original dirty checkout and all 45 inspected Sales Agent application files
retain their pre-implementation hashes.

The explicit new Study tuple is adapter `3`, `salesagent-evidence-v3`,
`salesagent-semantic-evidence-v5`. Target metadata/configuration, prepared scorer
configuration and human rating bind the same selected versions. Every subsequent
Study stage reconstructs profiles from that recorded binding. Unsupported/mixed
pairs are rejected before live factories; the legacy defaults remain adapter 2 /
evidence v2 / Study semantic v4 (generic semantic v2). AST comparisons additionally
confirm the old product/search models, rubric, payload limit and historical
projection constants are unchanged. Historical prepared/configuration snapshots
and the archived synthetic execution remain valid without relabeling or backfill.

Final pre-commit verification re-ran the complete offline suite: **2,240 passed
in 100.47 seconds**, including all 120 warmth regressions, both recipe versions,
P1/P2 controls and historical compatibility checks. The prior **997 focused tests**
remain applicable: implementation, fixtures and tests are unchanged. Ruff,
mypy (40 source files), formatting of all seven changed Python files, whitespace
and protected-file checks pass again. Repository-wide formatting reports exactly
the same three inherited files (`docs/test-taxonomy-and-suites.md`,
`src/harness/targets/base.py`, `tests/test_dataset.py`); all match current main.

All 50 definitions remain unchanged, with full fingerprint
`4db62cceec19881853a2d921e886edd4866cfef976b5c209bd06da486ec5e257`.
The six suite fingerprints, memberships and attempts remain unchanged:
full 50×1, smoke 8×1, critical 12×1, multi-turn 20×1, adversarial 8×1,
variance 10×3. Rubric, anchors, thresholds, reserved human roster and methodology
are unchanged. Only this Git-handoff documentation and the candidate-review note
were added after implementation approval. The PR description includes exact
contract/version changes, verification, changed-file summary and limitations.
No actual Study execution contract, human approval or freeze is created by this
handoff; the compatibility fixtures and fake pipeline receipts remain test-only.

## Approved opt-in warmth extension — implemented; human review pending

The user approved adapter 3 / normalized evidence v3 / semantic evidence v5,
explicit Study version bindings and historical compatibility. Work starts from
current main `da85619` (merged P2 PR #17), in isolated branch
`feat/study-v1-warmth-evidence` at
`/private/tmp/ai-test-harness-study-v1-warmth`. Existing changes in the original
checkout are preserved. No live execution, commit, push, merge or Study freeze
is authorized.

Design recorded before production edits:

- Add separate strict warmth-aware product/search models and an explicit adapter
  evidence-version selector. Keep adapter 2/evidence v2 and its default bytes.
- Add semantic v5 with a separate product model and required evidence-v3 metadata;
  preserve every successful current-turn observation, ordering, conflicts,
  provenance and the 64 KiB UTF-8 limit. Warmth is an exact category, with no
  coercion, ranking, temperature inference or season expansion.
- Add explicit projection selection to Study profile/rating/contract creation.
  Reconstruct all later stages from the frozen rating projection binding and
  verify its target adapter/evidence pairing. Preserve old defaults and v1 JSON
  shapes; reject unsupported/mixed bindings before client construction.
- Use the same prepared evidence for human packets and semantic judging. Keep
  the reserved human roster, rubric, anchors, threshold, case/suite definitions,
  historical data, generic engine and target application unchanged.
- Pin pre-change semantic v2/v3/v4 prepared/configuration hashes and a clearly
  synthetic historical Study execution fixture before editing. Verify backwards
  interpretation as well as malformed/new evidence, client-construction guards,
  all four warmth scenarios and real multi-product/source-turn associations.

Baseline compatibility checks and snapshots preceded production edits: **181
existing compatibility tests passed** (5.69 seconds). The two test-only fixture
files pin pre-change v2/v3/v4 prepared/configuration hashes, unchanged profile and
rating hashes, and a clearly synthetic fixed-timestamp execution configuration.
They are not actual Study freeze artifacts or human approval records.

Implementation and verification complete:

- [x] Separate `WarmthProduct` / `WarmthSearchResult` and semantic `_WarmthProduct`
  require `none | light | medium | high | shell`. Existing product models and the
  discount rule remain unchanged. Every lookup/search product keeps its own
  value; no numeric ordering, inference, normalization aliases or season fields.
- [x] Explicit `SalesAgentTarget(..., evidence_version="salesagent-evidence-v3")`
  selects adapter 3, reports the matching configuration/response metadata, and
  preserves warmth in both trajectory views. The old constructor default and
  adapter 2 output remain unchanged. Unsupported selection fails before creating
  an HTTP client. Failed business tools/empty searches do not invent warmth.
- [x] V5 requires adapter-3/evidence-v3 metadata and retains successful product
  observations in their original turn and order, including duplicate/conflicting
  records. Valid warmth conflicts survive; missing/invalid source warmth is ERROR.
  Cards/prose never supply a replacement field. V4 inventory/promotion behavior
  and the exact 64 KiB UTF-8 boundary remain unchanged, with no truncation.
- [x] Study semantic/rating/creation factories accept explicit projection selection;
  legacy defaults stay v4. Existing recorded rating projection and target version
  fields reconstruct the exact profile in validation, primary/variance preparation,
  verification, packet export and judge construction. The two reviewed Study
  tuples are 2/evidence-v2/semantic-v4 and 3/evidence-v3/semantic-v5. Mixed/unknown
  tuples fail before live factories. No v1 contract JSON fields/schema were added.
- [x] The CLI's pure configuration command exposes `--projection-version`; omitting
  it with adapter 3 fails instead of silently upgrading. The target factory uses
  the frozen evidence version, and the judge factory uses the frozen projection.
  Both complete v4 and v5 recipe pipelines pass with injected fakes and synthetic
  human receipts. These tests do not freeze or execute the actual Study.
- [x] Positive complete HTTP-response controls cover REC-004/008, GRD-002, RCV-005,
  lookup/search, 17 products/all five values, multi-product associations and
  aggregate/per-turn correspondence. Negative controls cover malformed/missing
  values, invalid metadata, client-construction guards, old/mixed bindings,
  conflicting observations, source order, turn/attempt/case isolation, strict byte
  limits and preserved independent capture scores when projection errors.
- [x] The real 50 candidate definitions are also used with synthetic HTTP responses
  to exercise persistence, preparation and the exact 12-case blind human packet.
  Every prepared request matches direct preparation with the recorded scorer;
  every human packet evidence JSON matches its prepared judge request. Synthetic
  judgments/target responses are workflow tests, not live quality observations.
- [x] Historical prepared/configuration hashes and a complete pre-extension Study
  execution snapshot remain reproducible. Archived responses are never backfilled,
  relabeled or migrated. The shared old semantic product model/discount scorer,
  rubric, anchors, threshold, core runner/storage and historical datasets/results
  are untouched.

| Final check | Result |
| --- | --- |
| Focused adapter/semantic/Study/P1/P2/human/calibration selection | **997 passed**, 64.02 seconds |
| Full offline `python -m pytest -q` | **2,240 passed**, 101.47 seconds |
| New warmth regression module | 120 cases, covered in focused/full results |
| Additional parameterized v5 recipe pipeline | Passed alongside legacy v4 |
| `ruff check .` | Passed |
| `mypy src` | Passed, 40 source files |
| Changed-Python `ruff format --check` | Passed, 7 files |
| Repository-wide formatting | Same 3 inherited failures; 121 files already formatted |
| `git diff --check` and protected-file hashes | Passed |

All commands use the existing environment and `PYTHONPATH=src` from this isolated
worktree. The default pytest socket blocker remains active. The focused selection
includes `test_salesagent_warmth`, `test_salesagent_target`,
`test_salesagent_semantic`, all five `test_salesagent_study*` modules, `test_salesagent_human_calibration`,
`test_calibration_io` and `test_calibration_reporting`.

The inherited formatting failures are `docs/test-taxonomy-and-suites.md`,
`src/harness/targets/base.py` and `tests/test_dataset.py`; all match their pre-edit
main hashes and were left outside scope. All 142 other tracked files, all dataset
files, 50 candidate definitions, descriptor, six suite definitions/bindings,
methodology, authoring specification and matrix remain byte-identical. All nine
original dirty/untracked files and all 45 inspected Sales Agent application files
also match their pre-edit hashes. No application change or live request occurred.

### Warmth fingerprint impact

Full ordered candidate hash stays
`4db62cceec19881853a2d921e886edd4866cfef976b5c209bd06da486ec5e257`.
All six suite-definition and selected-case hashes remain unchanged from merged P2.
Capture schema/reference remain v3; its profile hash stays
`5f213df23d3281c4240b924b013c5740dca18343c113b81ff14d4086a69d1770`.
The rubric/expectations/prompt/judgment/anchor versions and threshold stay unchanged.
Adapter 3/evidence v3 changes target configuration and response evidence hashes;
semantic v5 changes prepared evidence/configuration, profile, human-rating and
execution bindings. Defaults and old-version hashes do not change.

For the same **synthetic** judge settings and fixed timestamps used in the
historical regression fixture (these are not deployment/freeze attestations):

| Binding | Historical v4 | Warmth v5 |
| --- | --- | --- |
| Semantic profile | `c2b40f58104d507fd193b60af000470c64b75c5eccdb2354191b84e08a8191db` | `a34c50f875c48cd2e87f43d79476fce6baa10b8c377bd552a1ec91ccdce57ebb` |
| Human rating contract | `03142bcc3c7eed90763fa1979cf2772c2f64b03a9881e5195ef651fed603701e` | `4dd7ded009ed718b4bfa8af730afc7c973339c215443a4b2cfd7f5dd36d724b8` |
| Synthetic execution contract | `e9f47d68a81aa476aeded815b83ffaed1a2ca6e2ec6b54074cb52ea478034219` | `c4025e1d09918e95c7a1c32c159d47bea03d216ffd2c9a979fb3afc0be59acb3` |

Actual future execution hashes must be generated from separately reviewed target,
judge and configuration facts. No existing execution or human annotation is
silently upgraded; the new binding is a distinct evaluation configuration.

Changed files (14):

- Adapter: `src/harness/targets/_salesagent_contract.py`, `src/harness/targets/salesagent.py`.
- Pack: `src/harness/packs/salesagent_semantic.py`, `src/harness/packs/salesagent_study.py`.
- Recipe: `examples/salesagent_study.py`.
- Tests: `tests/test_salesagent_study.py`, new `tests/test_salesagent_warmth.py`.
- Synthetic fixtures: `tests/fixtures/salesagent_study/pre-warmth-bindings.json`, `tests/fixtures/salesagent_study/pre-warmth-execution.json`.
- Guides: `docs/salesagent-evidence.md`, `docs/salesagent-semantic.md`, `docs/salesagent-study-adoption.md`.
- Review/plan: `docs/studies/sales-agent-evaluation-study-v1-authoring-review.md`, `docs/plans/salesagent-study-v1-quality-corrections.md`.

Remaining limitations: categorical warmth supplies no temperature guarantee or
numeric ranking; source observations can be absent or conflicting; added bytes
can cause a previously near-limit payload to become ERROR; season remains
excluded. Old configurations deliberately remain on their original projection.
The new Study must explicitly select v5 after human review. Fake judgments verify
routing/gates, not real semantic accuracy. Recorded formal QA for all 50 cases,
verified deployment/judge facts, final committed configuration identities and
separately authorized freeze/live execution remain outstanding. No commit, push,
merge or actual Study freeze was performed; the isolated changes await review.

## P2 commit and PR authorization and final verification

The user reviewed the P2 handoff and authorized committing/pushing
`feat/study-v1-p2-qa` and preparing a PR against `main`, after final verification.
This supersedes the earlier implementation-stage commit/push restriction below.
It does not approve formal candidate QA, warmth implementation, live evaluation,
Study freeze or PR merge.

A fresh fetch confirms current `origin/main` and the P2 branch base are both
`b99c84d162fbb6f4750f1374c6cdae2a63c8d9ac` (merged P1 PR #16). No transfer,
merge, rebase or implementation reconciliation was necessary. Complete review
against this main confirms exactly nine changed/new files: five edited candidate
references in one JSONL file, four Python test modules, two test-only fixtures,
and two review/planning documents. All 144 other tracked files are byte-identical
to current main. The original dirty checkout remains separately preserved.

The final structural audit compares each edited reference with main: the five
GRD capability assertions differ only by enumerating the six feature orders in
existing whole-observation `matches_any`/`any` checks; ADV-005 keeps its shared
and fabrication checks, replaces its null-only quote with the approved active
promotion/catalogue-price alternatives and existing validated-discount rule,
and clarifies only its semantic compromise/budget expectation. All 50 inputs,
classifications and memberships and 45 full definition rows remain unchanged.

The full dataset fingerprint remains
`4db62cceec19881853a2d921e886edd4866cfef976b5c209bd06da486ec5e257`.
All six suite-definition/selection hashes and counts match the candidate review
record. Memberships and suite-definition bindings are unchanged; changed case
content changes full/smoke/multi-turn/adversarial selected-case hashes only.
The historical five-oracle fixture reconstructs the old P1 full fingerprint.
No scorer/reference/projection/profile/rating version changes are introduced.

Final pre-commit verification re-ran the entire offline suite: **2,119 passed
in 70.09 seconds**, including all 152 P2 regressions and historical compatibility
checks. The previous 808-test focused receipt remains applicable: test code,
candidate definitions, fixtures, environment, source and evaluator bindings are
unchanged. Ruff, mypy (40 source files), formatting of all four changed Python
files, whitespace checks and the complete protected-file audit pass again.
Repository-wide formatting reports exactly the same three pre-existing files:
`docs/test-taxonomy-and-suites.md`, `src/harness/targets/base.py` and
`tests/test_dataset.py`. Each was compared byte-for-byte with freshly fetched
main and is unaffected. They are outside the PR scope.

Only this authorization/verification note and the corresponding candidate-review
handoff note were added after the approved implementation. No warmth or season
work, unrelated cleanup, live target/judge execution, freeze or merge is included.
The PR description carries the changed-file summary, verification evidence,
historical compatibility, accepted limitations and the separately approved-or-
accepted warmth follow-up required before freeze. Commit/PR preparation does
not itself constitute formal approval of any of the 50 candidate cases.

## Approved P2 corrections — 2026-10-24

The user approved only feature-order equivalence in GRD-001/002/003/006 and
grounded alternative quotes in ADV-005. Work starts from merged P1 main
`b99c84d` in an isolated `feat/study-v1-p2-qa` worktree; the original dirty
checkout is preserved. No commit, push, merge, live evaluation or freeze is
part of this authorization.

Design recorded before editing:

- Replace the five capability patterns with existing `matches_any`/`any`
  assertions enumerating all six permutations of each three-feature array.
  Each alternative binds the original tool, successful result, product ID,
  rating and complete feature list to one observation. No generic operator or
  comparison-policy changes; duplicates, additions and missing facts stay invalid.
- Replace ADV-005's unconditional null quote with explicit authoritative
  catalogue-price alternatives and the existing critical `validated-discount-v1`
  rule. Permit only the currently active WELCOME10/10% promotion or no offer.
  Keep fabrication/card grounding gates. Clarify the existing semantic no-match
  expectation: alternatives must disclose the £20/waterproof-jacket mismatch.
- Snapshot the old five oracles in an evaluator-only historical test fixture;
  preserve old full-case and scorer/prepared/configuration golden hashes.
  Refresh current definition hashes without upgrading historical snapshots.
- Document accepted trace/card requirements, STA-003 behavioral scope and season
  deferral. Assess warmth read-only, with no warmth normalization/projection edit.

Implementation complete; human review pending. Only five candidate references
changed, with no production-code edits. The candidate review record contains
before/after case and selected-suite hashes, accepted QA decisions, the read-only
warmth proposal and formal human-review prerequisites.

- [x] All six feature permutations pass in each of the four complete cases.
  Wrong/missing/extra/duplicate features, wrong products/ratings/tools, split
  observations and absent per-turn evidence cannot pass.
- [x] All 17 authoritative catalogue products pass as explicitly described
  alternative quotes from successful lookup or search observations. Refusal,
  retail card/prose, validated offer without quote, prose-only alternative and
  multiple consistent observations remain supported.
- [x] Negative controls reject absent/failed/conflicting validation, invented
  codes/products, wrong arguments, spoofed percentages/source prices, wrong
  final prices, ungrounded cards and fabricated nominations. Missing/malformed
  telemetry remains ERROR. A perfect fake semantic score cannot hide a critical
  invalid quote. Budget-disclosure contrast pairs exercise the semantic gate.
- [x] The historical oracle fixture reconstructs the original P1 full fingerprint
  `bde063c5b1fcb845e3b18d6c489f26b72c549a700423b69122d37d8fd29d4bf9`.
  Existing scorer v2 outcomes and semantic v2/v3 prepared/configuration golden
  hashes pass. Capture schema/reference stay v3 and semantic/human projection
  stays v4. The current capture scorer configuration remains
  `b9227d6fb09556dc4f38b13ff0866539a12c0f286c975e6919ca6eefdaf97c10`.
- [x] The current full fingerprint is
  `4db62cceec19881853a2d921e886edd4866cfef976b5c209bd06da486ec5e257`.
  Historical contracts verify with their old definitions and reject the new
  dataset before any target is constructed. No archived bindings are upgraded.
- [x] Identical responses under the four order-only edits produce identical
  semantic v2/v3/v4 payloads; ADV-005's clarified expectation changes its new
  payload under each projection. New case/source bindings identify all five
  definition changes even where the projection content is unchanged.
- [x] All 50 non-reference fields and 45 complete JSONL rows are unchanged.
  Baseline SHA-256 audit confirms 144 other tracked files unchanged, including
  all production code, preregistration, authoring specification, matrix,
  descriptor, suites, rubric/threshold definitions and historical datasets.
  Catalogue/promotions hashes were reconfirmed by reading their current files;
  the test-only catalogue snapshot matches the recorded source byte hash.

Verification uses the existing environment with `PYTHONPATH=src`, importing
this isolated worktree. No live target or judge is constructed; the default
pytest socket-blocking fixture remains active.

| Check | Result |
| --- | --- |
| New P2 oracle regression module | 152 passed, 3.22 seconds |
| Focused Study/semantic/calibration tests | 808 passed, 33.80 seconds |
| Full offline pytest | 2,119 passed, 69.83 seconds |
| Ruff over complete checkout | Passed |
| Mypy over source | Passed, 40 source files |
| Formatting of all four changed Python files | Passed |
| Repository-wide formatting | Three inherited failures, detailed below; 120 files already formatted |
| Diff whitespace and protected-file checks | Passed |

Commands: `python -m pytest -q`; focused selection includes
`test_salesagent_study_p2`, `test_salesagent_study_cases`,
`test_salesagent_study_corrections`, `test_salesagent_study_quality`,
`test_salesagent_study`, `test_salesagent_semantic`, `test_calibration_io` and
`test_calibration_reporting`; `ruff check .`; `mypy src`;
`ruff format --check .`; changed-Python-file `ruff format --check`;
`git diff --check`.

Repository-wide formatting reports `docs/test-taxonomy-and-suites.md`,
`src/harness/targets/base.py` and `tests/test_dataset.py`. Each matches its
pre-edit main SHA-256. They were left unchanged to preserve this slice's scope.

Changed files: `datasets/salesagent/study-v1/cases.jsonl`, this plan, the candidate
human-review record, three existing Study test modules, the new
`tests/test_salesagent_study_p2.py`, and two test-only fixtures under
`tests/fixtures/salesagent_study/` (historical oracles and catalogue snapshot).
No warmth/season normalization, generic assertion change, evaluator version bump,
live evaluation, dataset freeze, commit, push or merge was performed.
The original checkout remains untouched. Changes await human review in
`/private/tmp/ai-test-harness-study-v1-p2`, branch `feat/study-v1-p2-qa`.

Remaining limitations: truthful compromise wording and prose-only fabrication
require real semantic judgment; scripted judgments establish workflow only.
The feature alternatives preserve the existing existential successful-observation
requirement, rather than adding a new universal consistency rule. Current-turn
quote validation rejects conflicting prices/promotions. Warmth remains a
separate human acceptance/implementation decision; season expansion is deferred.
No approval/freeze of any candidate is implied.

## Approved PR preparation from latest main

The user reviewed the implementation handoff and approved the two P1 corrections
for commit, push and pull-request preparation, subject to final Git verification.
This supersedes the implementation-stage restriction on committing/pushing below;
formal Study v1 candidate approval, freeze, live evaluation and merge remain
separate human decisions.

PR #15 is merged. The dedicated `feat/study-v1-p1-quality` branch starts at
`origin/main` commit `e485c2da519ed9615175f3c93cc6a3823c582f0c`. Main also includes
the independently merged grounding diagnostic work. An isolated worktree was
used to preserve the original branch, index and all nine modified/untracked
files, including the unrelated grounding-review document. A separate temporary
backup also preserves the original files and approved patch.

Exactly the eight approved P1 files were transferred. Their tracked-file bases
were identical between the original branch and latest main, so the patch applied
without conflicts or implementation changes. Only this plan/review documentation
receives additional Git-handoff details. Complete comparison against main covers
the v3 comparison policy, v3 reference contract, v4 human/judge projection and
historical v2/v3 compatibility controls. All 142 other tracked files remain
byte-identical to main, including datasets, methodology, suites and grounding
artifacts. The candidate fingerprint remains
`bde063c5b1fcb845e3b18d6c489f26b72c549a700423b69122d37d8fd29d4bf9`.

Checks run from the isolated worktree reuse the existing project environment
with `PYTHONPATH=src`; the imported harness path was verified to point to the
isolated checkout. Earlier implementation verification remains a historical
record. Verification after transfer completed as follows:

| Check on the PR branch | Outcome |
| --- | --- |
| Focused Study/candidate/semantic/reporting tests | 613 passed, 66.84 seconds |
| Full offline pytest, including grounding tests already on main | 1,967 passed, 68.30 seconds |
| Ruff over the complete checkout | Passed |
| Formatting of all five changed Python files | Passed |
| Mypy over all source files | Passed, 40 files |
| Diff whitespace and new-file checks | Passed |
| Other tracked-file hashes against main | 142 unchanged |
| Original working tree and preserved-file hashes | Unchanged |

The earlier 1,726-test result remains valid for the original implementation base;
latest main adds 241 already-merged grounding tests, all passing in the new total.
The 122 P1 regressions, original scorer v2 snapshot/outcomes, semantic v2/v3
prepared/configuration bindings, and the v4 human/judge binding checks all pass.
Dataset and suite identities remain unchanged; only the previously recorded
evaluator/profile/rating fingerprints change. A second fetch verified that
origin/main still points to the branch base before committing. The reviewed PR
diff contains exactly the eight approved P1 files, with no implementation
reconciliation required. Known limits remain offline synthetic evidence, the
strict 64 KiB payload cap, and the excluded warmth/season and other P2 findings.

## Approved second correction slice — comparison labels and product evidence

Authorized by the user after review of the two-part implementation proposal.
The following design is recorded before implementation. Work stays on the
existing candidate feature branch; candidate approval and freeze remain pending.

1. Preserve `StudyAssertionsScorer` v2 and add a Study-specific v3 subclass.
   Compare copied evidence and copied assertion expectations using casefold only
   for resolved-constraint features/colour/size, search-products argument category,
   and check-inventory result colour/size. Bind normalization to typed evidence
   paths/tool names, never scenario IDs or arbitrary dictionary key names. Keep
   exact product IDs, numeric fields, status enums, prose, feature order and all
   other values. Preserve null/missing/malformed evidence semantics and never
   mutate the case or response. The Study reference contract becomes v3, with
   unchanged reference JSON shape and candidate definitions.
2. Add explicit `salesagent-semantic-evidence-v4`, retaining all allowlisted
   successful current-turn get-product/search-product observations in their
   original order, including duplicates/conflicts, without requiring cards or
   textual mentions. Preserve v3 inventory retention and promotion selection.
   Keep original turn provenance, the 64 KiB byte limit and ERROR behavior.
   Study human and judge contracts select v4 together. Historical default v2
   and explicit v3 projections keep their existing prepared/configuration bytes.
3. Preserve every candidate, descriptor, suite, preregistration, matrix, rubric,
   threshold, historical result and protected source file. Only evaluator
   configurations and their derived execution/preparation bindings change.
   Retain original-version scorer/projection access; reject stale Study execution
   snapshots instead of silently upgrading them. No warmth/season or other P2
   correction is included.

Verification will use complete synthetic responses plus positive/negative
operator controls (especially exclusions), representative single/multi-turn
projection examples, payload boundaries, human/judge binding checks, historical
byte/configuration baselines and protected-file hashes. Run focused/full offline
pytest, Ruff, formatting and mypy. No live clients, commits, pushes, merges or
candidate freeze are authorized by this slice.

- [x] Inspect contracts and record the approved design before editing source.
- [x] Capture compatibility/protected-file baselines and run initial offline checks.
- [x] Implement the two versioned changes and regression coverage.
- [x] Complete focused/full offline verification and compatibility checks.
- [x] Record actual outcomes, fingerprints, changed files and limitations.
- [x] Human implementation review; approved for commit/PR preparation, with
  formal candidate approval/freeze still pending.

### Second-slice verification record

The baseline full offline suite passed 1,604 tests in 64.38 seconds. The final
focused selection passed 613 tests in 63.49 seconds, including the 122 new
regression cases in `tests/test_salesagent_study_quality.py`. An additional
122-test run passed after adding pre-change no-card v2/v3 byte-hash controls.
These controls supplement existing historical regression tests rather than
replacing or relaxing their expected values.

| Final check | Outcome |
| --- | --- |
| Focused Study/candidate/semantic/reporting selection | 613 passed |
| New correction regression module, after final container guard | 122 passed, 3.03 seconds |
| Full offline pytest on final source | 1,726 passed, 66.30 seconds |
| `.venv/bin/ruff check .` | Passed |
| Ruff format check on all five changed Python files | Passed |
| `.venv/bin/mypy src` | Passed, 39 source files |
| `git diff --check`, new-file newline/whitespace checks | Passed |

Final review added a regression guard so malformed dictionaries under features
cannot activate the list-member comparison policy. The final full run above
includes that guard. No implementation-scope deviation was needed.

Regression evidence includes:

- Complete independently specified synthetic responses for every one of the
  23 directly affected candidates pass with canonical and equivalent-cased
  labels; wrong labels fail. The v2 scorer reproduces the old case-sensitive
  behavior. REC-008 rejects all tested capitalizations of the incorrectly
  hardened insulation constraint.
- Positive/negative contains, excludes, subset, equals, matches and matches-any
  checks, named tool patterns, quantifiers, indexed paths and expected-path
  comparisons. Exact semantics remain for other constraints, metadata, other
  tool types, IDs, numeric values/types, stock/status/availability, feature
  array order, whitespace and distinct colour names.
- V4 projects multiple source observations across eight representative Study
  cases. A complete CON-002 no-card response passes capture with either truthful
  or contradictory prose while retaining the source facts needed for later
  semantic review. This proves evidence delivery, not real judge accuracy.
- Search/get-product order, conflicting product records, failed-tool exclusion,
  unknown-field removal and unchanged input objects. Per-turn source facts stay
  in their originating turn, never backfill earlier turns, and do not leak into
  a later projection call. Inventory v3 retention and promotion filtering survive.
- Exact 65,536-byte UTF-8 payload acceptance and 65,537-byte rejection; malformed
  evidence errors before fake judge invocation. An ERROR preserves successful
  independent deterministic results. Human packets and judge requests use the
  same prepared v4 evidence across all 12 protected examples. Existing receipt,
  isolation, replay, persistence and comparison tests remain part of verification.
- Additional in-memory comparisons of synthetic old/new runs explicitly flag
  scorer v2/v3 and semantic v3/v4 as evaluator-configuration changes while
  reporting unchanged dataset identity. They do not imply target regressions.
- Historical v2/v3 prepared/configuration hashes across all 14 historical fake
  responses, plus pre-change hashes of no-card INV-002/ADV-003 projections. The
  original Study v2 scorer snapshot and synthetic outcome hashes across all 50
  candidates are unchanged; a v2-scored stored result reloads identically.
- All 86 baseline-protected files are byte-identical, covering datasets/suites,
  other source modules, examples, historical fixtures/results, preregistration
  and authoring specification. The pre-existing untracked grounding-review
  fixture remains untouched.

The full ordered dataset fingerprint stays
`bde063c5b1fcb845e3b18d6c489f26b72c549a700423b69122d37d8fd29d4bf9`.
Descriptor, case, selected-case and suite-definition fingerprints do not change.
The following canonical hashes record the actual evaluator configuration change;
the before values reconstruct the original profile from the retained v2 scorer.

| Binding | Before | After |
| --- | --- | --- |
| Capture scorer snapshot | `8697a7c138e4b36c2dcca0e0e0c28720086a5d9f68e5a44242156aa96b2be345` | `b9227d6fb09556dc4f38b13ff0866539a12c0f286c975e6919ca6eefdaf97c10` |
| Capture profile definition | `7c6dda91f0fe219f8d92358c8c90704880a3bfbd5b7d9dbe325a57821fd7502c` | `5f213df23d3281c4240b924b013c5740dca18343c113b81ff14d4086a69d1770` |
| Human rating contract | `42614c3993c1160d8bcd7bff09776041f51fd5742cfbaee1597cc86db9210ecf` | `03142bcc3c7eed90763fa1979cf2772c2f64b03a9881e5195ef651fed603701e` |

Semantic preparation/configuration and derived execution identities also change;
they depend on the explicit judge configuration and source evidence. No live
execution contract is created. Old projections/scorers stay accessible under
their original versions; stale Study execution snapshots are rejected instead
of reinterpreted. Stored historical results and bindings are not migrated.

Changed files in this slice: `src/harness/packs/salesagent_rules.py`,
`src/harness/packs/salesagent_semantic.py`,
`src/harness/packs/salesagent_study.py`,
`tests/test_salesagent_study_corrections.py`,
`tests/test_salesagent_study_quality.py` (new),
`docs/salesagent-study-adoption.md`,
`docs/studies/sales-agent-evaluation-study-v1-authoring-review.md`, and this plan.
No candidate, target/adapter, generic assertion/runner, dependency or historical
artifact edit was needed. Warmth/season and remaining P2 findings remain outside
scope. No live target/judge, commit, push, merge or formal freeze was performed.

## First approved correction slice — 2026-10-17

Authorized 2026-10-17 following human review and an offline reproduction of
three candidate-oracle weaknesses. This is a bounded correction on the existing
`feat/salesagent-study-v1-cases` workspace, not a study freeze or live run.

## Intended design, recorded before implementation

1. Add an evaluator-only `reference.salesagent_rules` opt-in for the versioned
   `validated-discount-v1` rule, selecting an explicit turn. Only SA-ADV-001 opts
   in. A Study-specific subclass composes this rule with existing structured
   assertion outcomes. It retains the scorer name and ordinary Score/gate/error
   contract, but records `salesagent-study-assertions-v2` as its schema version.
   The reference contract becomes `salesagent-study-v1-references-v2`.
   No scenario ID, risk or taxonomy selects behaviour. No generic operator,
   runner, result model or target adapter changes are needed.
   Null promotion and null pricing remain legitimate refusal. A displayed valid
   promotion requires matching successful current-turn validation, even without
   a quote. A quote additionally requires that promotion, matching current-turn
   product facts and authoritative Decimal pricing. Missing/malformed evidence
   is ERROR; complete but absent/contradictory validation is FAIL. A successful
   validation plus contradictory same-code evidence cannot prove the discount.
2. Preserve historical semantic factory defaults and v2 evidence bytes. Add an
   explicit `salesagent-semantic-evidence-v3` opt-in retaining typed, allowlisted
   successful current-turn inventory observations without the product-ID filter.
   These observed tool facts remain relevant to reviewing that turn even when
   the model did not fetch/display a product or names it only in prose. Do not
   infer a name-to-ID link or import the target catalogue into the evaluator.
   Study semantic and human-rating contracts select v3 together. Existing v2
   replay/calibration bindings, rubric, anchors and threshold remain unchanged.
3. Replace SA-INV-006's order-sensitive pattern with `matches_any`/`any` over
   the two complete permissible tool-result orderings. Keep exact variants,
   stock, total, product and successful-tool checks. The generic matching
   contract remains unchanged.

Both candidate-definition edits change case/full-dataset fingerprints; record
them through the existing descriptor-aware loader in the candidate review.
Logical suite IDs, profile IDs, membership, prompts and descriptor version stay
unchanged. Profile snapshots identify the new scorer/reference/projection
versions; old Study execution contracts must not silently acquire new meaning.
The approved preregistration, matrix and historical datasets/results are protected.

## Verification and progress

- [x] Read AGENTS.md, methodology, authoring specification and relevant contracts.
- [x] Record intended design before source/candidate edits.
- [x] Implement the three corrections and synthetic regression examples.
- [x] Run focused/full offline tests, Ruff, format checks and mypy.
- [x] Verify protected bytes, historical v2 prepared bytes/configurations and
  new Study configuration/fingerprint bindings.
- [x] Update candidate review with fingerprint changes and actual results.
- [x] Prepare handoff without committing, pushing, merging or live calls.
- [ ] Final human implementation review; candidate freeze remains separate.

## Verification outcome — 2026-10-17

All commands used the existing `.venv` environment, with no dependency changes.
Default pytest networking remains blocked by the repository's autouse fixture.

| Check | Before changes | Final result |
| --- | --- | --- |
| `.venv/bin/pytest -q` | 1545 passed, 62.94s | 1604 passed, 63.49s |
| Focused corrections, candidate, Study integration and semantic tests | — | 476 passed, 26.76s |
| `.venv/bin/ruff check .` | Passed | Passed |
| `.venv/bin/mypy src` | Passed, 38 source files | Passed, 39 source files |
| Ruff format check on five changed Python files | — | Passed |
| `git diff --check` | — | Passed |

The focused command selected `tests/test_salesagent_study_corrections.py`,
`tests/test_salesagent_study_cases.py`, `tests/test_salesagent_study.py` and
`tests/test_salesagent_semantic.py`. The full run includes all 59 new regression
examples plus existing baseline, adapter, runner, persistence, replay,
prospective, calibration and reporting checks. No pre-existing engineering-check
failure was observed; all final checks passed.

Verification also confirmed:

- Exactly SA-INV-006 and SA-ADV-001 references changed; all 50 inputs,
  classifications and semantic expectations are unchanged.
- The descriptor and all six suite files, selections and memberships are
  unchanged. Whole-study validation still returns 50/8/12/20/8/10 cases and the
  approved attempt counts. New definition fingerprints are recorded in the
  candidate review; full ordered case hash is
  `bde063c5b1fcb845e3b18d6c489f26b72c549a700423b69122d37d8fd29d4bf9`.
- Before/after byte comparison passed for 41 protected files, including generic
  core/scorers/adapters, existing fixtures, historical datasets, suite files,
  the preregistration and pinned matrix.
- Historical v2 prepared inputs for all 14 historical semantic cases and its
  default configuration/scorer snapshot match hashes obtained from pre-change
  source using the same deterministic mock HTTP responses. Tests also reproduce
  v2 inventory omission while verifying explicit v3 retention, so compatibility
  does not depend solely on examples unaffected by the correction.
- Study capture snapshots record the new rule version; semantic and human
  contracts bind v3 together. Older Study configuration values are rejected
  instead of silently reinterpreted. Historical v2 factories remain available.
- Missing/malformed evidence remains ERROR, independent successful scorer
  results survive, and a critical conditional failure cannot be averaged away.

No implementation-scope deviation or broader core contract change was needed.
The new conditional rule also permits a validated promotion offer without a
quote, preserving the previously allowed offer branch while requiring its
evidence. The dataset remains a candidate pending final review and freeze.

Changed files: `src/harness/packs/salesagent_rules.py` (new),
`src/harness/packs/salesagent_semantic.py`, `src/harness/packs/salesagent_study.py`,
`tests/test_salesagent_study_corrections.py` (new),
`tests/test_salesagent_study_cases.py`, `datasets/salesagent/study-v1/cases.jsonl`,
`docs/salesagent-study-adoption.md`,
`docs/studies/sales-agent-evaluation-study-v1-case-authoring-spec.md`,
`docs/studies/sales-agent-evaluation-study-v1-authoring-review.md`, and this new
implementation plan. Pre-existing candidate work and grounding fixtures remain
in place. No historical results were changed; no commit, push, merge, target or
judge service invocation was performed.
