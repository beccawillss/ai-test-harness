# Study v1 pre-freeze quality corrections

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
