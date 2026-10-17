# Study v1 pre-freeze quality corrections

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
