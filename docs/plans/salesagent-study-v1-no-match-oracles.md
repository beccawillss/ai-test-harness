# Study v1 no-match oracle correction

## Final commit and PR authorization — 2026-10-26

The user reviewed the implementation, renewed human QA approval for the four
revised interpretations and authorized commit, push and a PR against `main`
after final verification. This supersedes the implementation-stage Git
restriction below. The formal human QA approval record is not modified or
adopted by this technical handoff. Actual Study freeze, live target/judge calls
and PR merge remain unauthorized. Earlier pending-review statements below
describe the implementation handoff at that time.

A fresh fetch and independent GitHub branch read confirm that current
`origin/main`, the feature branch HEAD and its merge base are exactly
`6bbb9cc59838cae9d1deeaedba95a4509c1f8e64`. No transfer, merge, rebase or
implementation reconciliation is required. The approved implementation remains
the same 14-file scope. Only this engineering authorization/verification note
is added during final PR preparation; case definitions, rule and tests retain
their reviewed bytes.

The final independent audit confirms exactly four changed reference rows and
46 byte-identical case rows; all other assertions and all 50 inputs, semantic
expectations and classifications remain unchanged. All six suite-definition
hashes, memberships and attempts are unchanged. Recomputed single-case,
descriptor, full-dataset and selected-case hashes match the implementation
record. The full dataset remains
`4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028`.
All 146 other tracked files match current main, including old scorer versions,
historical snapshots, generic engine, adapters, semantic contracts, approved
methodology, authoring specification, matrix, descriptor and suite files.
The original checkout, target application and supplied QA draft retain their
recorded pre-handoff hashes.

Acceptance-policy review confirms constrained and complete broader proofs,
including legitimate nonempty results; unrelated restrictions do not establish
absence. Incomplete/fabricated source results fail, malformed telemetry remains
ERROR, and historical v2/v3 scorers/reference profiles retain their pinned
behavior. Final `validate` / `preview`, Ruff, eight-file formatting and mypy
(41 source files) pass. Final full offline verification passed **2,438 tests in
117.76 seconds**, including all 198 no-match regressions and all historical
compatibility controls. Whitespace, exact-scope and protected-file checks pass.
No implementation change was needed after final verification.

## Authorization and scope — 2026-10-26

The user authorized implementation of the four reproduced no-match weaknesses,
offline verification and an implementation handoff. No actual Study freeze,
live target/judge execution, commit, push or merge is authorized. Work is on
`feat/study-v1-no-match-oracles`, isolated at
`/tmp/ai-test-harness-study-v1-no-match`, from reviewed current main
`6bbb9cc59838cae9d1deeaedba95a4509c1f8e64`. The original dirty checkout is preserved.

Read AGENTS.md, the approved preregistration and authoring specification, the
current candidate review/correction plan, rule/scorer implementation and public
Sales Agent search contract. The existing readiness implementation is complete;
this is a bounded follow-on correction, not a methodology change.

## Acceptance policy proposed before implementation

Exactly SA-CON-002 (£90), SA-CON-005 (£80), SA-RCV-003 (£50), and SA-RCV-004 (£70)
require renewed human confirmation of the revised oracle. Their shopper inputs,
semantic expectations, classifications and all other expectations stay intact.
The other 46 complete case definitions remain byte-identical.

A successful, current-turn `search_products` observation can establish no match
only when its search covers every waterproof jacket at the shopper's budget:

- Category is jacket or unrestricted; maximum price is the case budget or a
  broader ceiling (including no ceiling).
- Features are unrestricted or only waterproof. No activity, weather, colour,
  size or inventory-only restriction may narrow the proof search.
- Optional omitted arguments have the public API's declared defaults. Label
  comparisons within this new rule follow the public search contract's
  case-insensitive, surrounding-whitespace-insensitive matching; no aliases.
- Search count equals product-list length; IDs are unique; product evidence is
  well formed. Returned IDs exactly match the complete result of that query
  against the reviewed, evaluator-owned catalogue facts. Product ID, category,
  price, feature membership and waterproof rating must agree with those facts.
  Product/feature ordering is irrelevant; duplicate features are not invented.
- No returned waterproof jacket is within the shopper's budget. Broader results
  may be nonempty: e.g. jackets under £90 return the two water-resistant shells;
  an unbounded jacket search returns all six jackets, whose waterproof members
  cost at least £110. These are valid proofs, not reasons to force an empty list.
- Additional exploratory/alternative searches can coexist with an independent
  proof. A narrowed search is never itself a proof. Malformed successful search
  telemetry is ERROR, not zero; complete but insufficient evidence is FAIL.
  Contradictory relevant result sets or source facts cannot be rescued by a
  second valid proof. Failed business-tool calls do not supply proof.

Existing shopper budget/waterproof constraint assertions, category intent,
catalogue/card checks and source-result integrity remain enforced. Replace only
the four `t0-no-exact-match` assertions with explicit, gated, noncritical
`no-match-search-v1` rule references. The catalogue snapshot is evaluator-only,
revision/hash bound, and never sent to the target. No target internals are imported.

Existing generic assertions cannot correlate arbitrary broad-query arguments,
complete variable result sets and the absence of an eligible product without
enumerating full response objects. Add a small pack rule and v4 capture scorer;
retain the original v2/v3 scorers and v3 capture profile explicitly. Semantic
scorer/profile, adapter/evidence, rubric, anchors and threshold do not change.
Execution validation/capture reconstruct the saved capture version and reject
unsupported reference/scorer combinations before target construction. Historical
contracts retain their original meaning; changed definitions require new bindings.

## Milestones

- [x] Inspect current contracts; reproduce scope; isolate reviewed main.
- [x] Record acceptance policy and compatibility design before production edits.
- [x] Implement opt-in rule, versioned capture binding and four reference edits.
- [x] Add positive/negative synthetic tests and historical compatibility controls.
- [x] Run focused/full offline tests, validate/preview, Ruff, mypy and integrity checks.
- [x] Record exact fingerprint changes, checks and review limitations.
- [x] Stop for human implementation review; no actual freeze or publishing.

## Implementation and verification receipts

The implementation follows the acceptance policy above. `salesagent_search.py`
owns the new rule, strict authored search-fact models and v4 scorer. It composes
the unchanged v3 label scorer and unchanged discount rules. Dispatch is by the
explicit reference rule, never case ID, risk or taxonomy. The rule reads only
the specified source turn. No generic engine, runner, result model, adapter,
semantic projection or target application code changed.

The new capture profile records v4; semantic profile/reference stays v3 because
its evidence/expectations did not change. Execution validation reconstructs the
saved capture profile rather than relabeling a historical artifact. The archived
synthetic execution JSON retains digest
`e9f47d68a81aa476aeded815b83ffaed1a2ca6e2ec6b54074cb52ea478034219` and verifies
against its reconstructed original definitions. It is rejected against the new
dataset before target construction. A deliberately downgraded v3 contract also
rejects the new v4 rules before any target factory. The v2/v3 scorer classes and
all old expected hashes remain unchanged.

Initial checks exposed historical tests that assumed the pre-correction
definitions/default capture snapshot. They now reconstruct the exact original
four assertions (including list positions) and explicitly request the old v3
capture profile for historical comparisons. No old golden hash was replaced to
make a regression pass. New current-candidate pins identify the revised dataset.
There was no production-policy deviation from the recorded design.

All commands ran from this worktree with the existing environment at
`/Users/rebeccawilliams/Developer/ai-test-harness/.venv/bin`. Python commands use
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src` and `-B`; pytest uses
`-p no:cacheprovider`. The default socket-blocking fixture stayed active.

| Check | Result |
| --- | --- |
| Focused pytest: new no-match module; all Study cases/P1/P2/quality/corrections/warmth/integration modules; prospective and Study reporting | **1,057 passed**, 114.03 seconds |
| Full `python -B -m pytest -q -p no:cacheprovider` | **2,438 passed**, 118.64 seconds |
| New synthetic regression coverage | **198 tests**, including all four prior false passes, all forbidden filter types, strict/broader proofs, completeness/source faults, malformed telemetry, ERROR/FAIL separation, independent scorer preservation, per-turn scope, authoring validation and all 46 unchanged-case outcomes |
| Study recipe `validate` and `preview`, descriptor plus all six suites | Passed; 50 cases, unchanged exact classifications/selections/attempts, 12 protected human IDs |
| `ruff check --no-cache src tests examples` | Passed |
| `ruff format --check` on all eight changed/new Python files | Passed |
| `mypy --cache-dir=/tmp/study-v1-no-match-mypy src` | Passed, **41 source files** |
| `git diff --check` and explicit new-file newline/whitespace check | Passed |
| Main byte-hash audit | **146 protected tracked files unchanged**, including all prior fixtures/snapshots and all generic/adapter/semantic code |
| Exact JSONL and non-reference comparison | Only the four approved rows differ; **46 full rows byte-identical**; all 50 inputs/semantic expectations/classifications unchanged; all other assertions unchanged |
| Original checkout / application read-only audits | All eight recorded original changed/untracked files and all 92 recorded target files retain their baseline hashes |

The current [review record](../studies/sales-agent-evaluation-study-v1-authoring-review.md#current-no-match-correction-handoff--2026-10-26)
records exact before/after single-case, full-dataset, selected-case, scorer and
profile fingerprints. The full new `dataset-cases-v2` fingerprint is
`4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028`.
Descriptor and all suite-definition hashes remain unchanged. Full, smoke,
multi-turn and variance selected-case hashes change; critical/adversarial stay
unchanged. All 333 gates (49 critical) and all suite counts/attempts are retained.

## Files changed (14)

- `datasets/salesagent/study-v1/cases.jsonl`: four reference replacements only.
- `src/harness/packs/salesagent_search.py`: new bounded rule and v4 scorer.
- `src/harness/packs/salesagent_study.py`: reference validation, new capture
  profile and recorded-version reconstruction/pre-client compatibility checks.
- `tests/test_salesagent_no_match.py`: positive/negative synthetic coverage.
- `tests/fixtures/salesagent_study/pre-no-match-oracles.json`: original four
  assertions, their positions and exact original definition/full hashes.
- `tests/test_salesagent_study_cases.py`,
  `tests/test_salesagent_study_corrections.py`,
  `tests/test_salesagent_study_p2.py`,
  `tests/test_salesagent_study_quality.py`, `tests/test_salesagent_warmth.py`:
  revised positive evidence, current pins and explicit historical reconstruction.
- `docs/salesagent-study-adoption.md`,
  `docs/studies/sales-agent-evaluation-study-v1-authoring-review.md`,
  `docs/plans/salesagent-study-v1-quality-corrections.md`, and this plan:
  acceptance policy, version/fingerprint impact and review/verification handoff.

## Human review and limits

Implementation is complete and uncommitted on the dedicated branch, based on
main `6bbb9cc`; no commit, push, merge, actual Study freeze or live target/judge
call occurred. Exactly **SA-CON-002, SA-CON-005, SA-RCV-003 and SA-RCV-004** await
renewed human confirmation of the policy and revised references. Existing
authoring QA decisions for the other 46 cases are preserved as reported by the
user; this implementation does not sign or adopt the consolidated QA draft.

The policy checks proof against the reviewed controlled catalogue, not arbitrary
future fixtures. Deployment/fixture identity still requires the existing target
freeze verification; a new source revision must be reviewed rather than silently
accepted. Source labels/digests are authored provenance, not remote attestation.
Truthful tool evidence does not establish truthful/helpful prose. Semantic v5 and
the protected 12-response blind human exercise remain separately configured and
authorized future work. No synthetic test result is a Study target quality score.
