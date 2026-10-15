# Sales Agent numeric waterproof grounding diagnostics v1

## Status and authorization

Milestone 1 is reviewed, frozen and merged into main by PR #12. On 12 October
2026 the user explicitly authorized Milestone 2 implementation and offline
verification. After reviewing the completed Milestone 2 handoff, the user
approved the implementation and authorized a focused commit and branch push.
Merge and Milestone 3 remain unauthorized. The frozen inputs, labels, manifest
and signed review must remain unchanged.

Implementation uses the existing isolated grounding worktree, on dedicated
branch `feat/salesagent-grounding-v1-m2` from merged main
`d0e75e99afe4ce03983140c276fb402f328eb7df`. The separate Study v1 checkout remains
protected. This authorization supersedes the historical gates recorded below.

Approved workspace:

- `/Users/rebeccawilliams/Developer/ai-test-harness-grounding-v1`
- `feat/salesagent-grounding-v1`
- Base `5b475993bdac179b6ae21b7306dd76e22b068f90`

Original workspace remains on `feat/salesagent-study-v1-cases` at
`50c2a50c7450b5c93cf129826e0f97d4c78e6768`. Its ten untracked candidate files must
not be modified, moved, staged, copied into this worktree, or deleted. The user
explicitly approved main's pinned revision instead of AGENTS.md's stale
`codex-evaluation` branch convention; AGENTS.md itself is not changed.

## Purpose and acceptance

Prepare a reviewable contract, ADR, exact synthetic corpus/labels and independent
review guide for an offline evaluator-side diagnostic. V1 assesses reference
agreement of explicit numeric waterproof/hydrostatic-head claims against reviewed
authority valid for the turn. It does not establish real-world product truth or
grounding in evidence actually available to/used by the agent. The normalized
product contract carries no numeric rating; all findings explicitly leave agent
grounding unassessed. Missing normalized fields never prove authoritative absence.

Use one diagnostic contract version covering the behavior, one corpus envelope
version, and exact content/configuration hashes. No independent contract registry
or generic claim framework. Existing TargetResponse, runner, Scorer/Score,
semantic workflow and Study v1 methodology remain unchanged. No live target or
judge, LLM extractor, target-side claim reporting, or dependency installation.

Milestone 1 acceptance means artifacts and exact labels are ready for independent
review, not that the review occurred or the detector exists. Every fixture binds
input hashes, text spans, normalization, subject resolution, evidence references,
findings/reasons, errors and report counts. Authority completeness is explicitly
reviewed/version-bound and conditional on the declared source set. Report metrics
only for supported grammar with raw counts and the small corpus limitation.

## Progress

- [x] Confirm user approval of isolated worktree, branch and pinned main baseline.
- [x] Verify destination/branch unused and baseline commit exists.
- [x] Record original candidate/protected/historical artifact byte hashes.
- [x] Create the approved worktree without switching the original checkout.
- [x] Read inherited AGENTS.md and existing adapter/model/fingerprint contracts.
- [x] Draft the versioned specification and ADR.
- [x] Author 24 synthetic text fixtures and eight evidence-error fixtures.
- [x] Author exact expected labels, hash manifest and independent review guide.
- [x] Complete offline structural verification and compatibility checks.
- [x] Recheck original artifacts and record final Milestone 1 verification.
- [x] Independent human review of exact corpus/specification revision.
- [x] Record signed review, exact hashes and offline corpus verification.
- [x] User approval of corpus freeze.
- [x] Mark the exact reviewed corpus frozen and verify its integrity.
- [x] User authorization to commit the reviewed corpus, documentation and manifest.
- [x] Explicit Milestone 2 source-implementation authorization.
- [x] Milestone 2 implementation and offline verification.
- [x] Human review and approval of the Milestone 2 implementation.
- [x] User authorization to commit and push Milestone 2.
- [ ] Milestone 3 example/documentation/compatibility acceptance (not authorized).

## File map

All Milestone 1 files are new in the isolated worktree:

| File | Purpose |
| --- | --- |
| `docs/plans/salesagent-waterproof-grounding-diagnostics.md` | This plan, approvals, progress and verification |
| `docs/salesagent-grounding-diagnostics-v1.md` | Normative behavior/data contract and metric definitions |
| `docs/adr/0008-numeric-waterproof-diagnostics.md` | Rationale, alternatives and limitations |
| `tests/fixtures/salesagent_grounding/v1/README.md` | Inventory and independent human review procedure |
| `tests/fixtures/salesagent_grounding/v1/cases.jsonl` | 32 synthetic diagnostic inputs, separate from Study v1 |
| `tests/fixtures/salesagent_grounding/v1/expected.jsonl` | Exact authored semantic report expectations |
| `tests/fixtures/salesagent_grounding/v1/manifest.json` | Versions, splits/counts, byte checksums, approved review |
| `tests/fixtures/salesagent_grounding/v1/independent-review.md` | Unchanged signed human review, added during review finalisation |

No existing repository file should change. No package modules, executable tests,
CLI, scorer integration, source schema classes or output generators are part of
Milestone 1. Temporary authoring/validation probes are not a detector and are
not repository implementation artifacts.

## Milestone sequence

### Milestone 1: contract and review corpus (authorized)

Create only the file map above. The diagnostic report is separate from Score and
study verdicts. Define temporal projection, claim/slot spans, bounded grammar,
subject resolution, Decimal normalization, reviewed reference completeness,
findings, execution errors and provenance. Specify missing-authority uncertainty
versus malformed-required-evidence errors. Specify positive reference agreement
without implying the agent observed that reference.

Corpus: S01–S06 supported, V01–V06 violations (three contradicted, three
unsupported), A01–A06 indeterminate, N01–N06 excluded, E01–E08 execution errors.
Each text group has four development and two visible acceptance fixtures; all
eight error fixtures are acceptance. S05 checks Unicode spans/name normalization;
S06 checks earlier reference validity; V06 rejects future evidence and preserves
an earlier finding after correction. Exact inputs and labels are in JSONL, not
left to a future implementer to invent.

No synthetic authority review field attests independent human review. The corpus
manifest was pending at authoring handoff; the subsequent human review now approves
all 32 IDs and the exact input/label hashes. The user has approved the corpus
freeze, bounded artifact commit and subsequent merge. Milestone 2 source
implementation is authorized by the 12 October instruction.

### Milestone 2: bounded response-to-report path (implemented; approved)

Expected new `src/harness/packs/salesagent_grounding.py` and
`tests/test_salesagent_grounding.py`. Planned public entry point takes
TargetResponse, context and optional reviewed authority; returns a separate
GroundingDiagnosticReport. Internal projection/detection/resolution/comparison
functions are pure. No Scorer implementation, runner integration or model change.

Exit only when independently reviewed corpus expectations all pass; errors,
uncertainty, subject attribution, spans, exact units and temporal scope match;
canonical round-trips and input immutability hold. Add engineering boundary tests
for no authority/open authority, unreviewed references, partial errors, duplicate
names, invalid caller configuration and isolation. New language expectations
require corpus review, not tuning labels to detector output. Record precision,
recall, false positives/negatives, abstention and gold-extraction comparison
correctness separately; never claim broad detection accuracy from these fixtures.

### Milestone 3: offline usage and compatibility (not authorized)

Expected new `examples/salesagent_grounding.py` and usage documentation; update
this new specification/plan as appropriate. A thin example may consume explicit
saved response/authority JSON and emit diagnostics to stdout. It must create no
target/judge client or live-service option. Do not modify saved runs or study
profiles. Full tests/static checks and protected artifact hashes must retain
their prior meaning. Findings are not process quality gates; execution errors
are distinct. Seek human acceptance before any commit/integration action.

## Verification strategy

For Milestone 1, use a temporary read-only structural probe with installed Python:
strict JSON (duplicate keys/nonfinite constants rejected), unique matching IDs,
manifest byte checksums, canonical input/provenance/source hashes, all reference
pointers, all Unicode slot slices, expected counts/splits, positive unit
equivalence, reviewed temporal evidence eligibility and exact error mutations.
Verify legitimate TargetResponse inputs still parse with the existing model.
This checks fixture consistency only, not extraction or natural-language accuracy.
Check Markdown relative links, whitespace, final newlines and balanced fences.

Use the original existing `.venv` without installation. Set PYTHONPATH explicitly
to this worktree's `src` and disable bytecode/pytest caches. This avoids silently
testing the original checkout through its editable install. The pinned main
baseline has 1,468 tests; the original checkout's extra 77 candidate-study tests
are intentionally not copied here. Existing offline tests block socket access.

Commands for implementation acceptance (focused test file is future work):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/rebeccawilliams/Developer/ai-test-harness/.venv/bin/python -m pytest -q -p no:cacheprovider
/Users/rebeccawilliams/Developer/ai-test-harness/.venv/bin/ruff check --no-cache .
/Users/rebeccawilliams/Developer/ai-test-harness/.venv/bin/ruff format --check --no-cache .
/Users/rebeccawilliams/Developer/ai-test-harness/.venv/bin/mypy --cache-dir=/dev/null src/
/Users/rebeccawilliams/Developer/ai-test-harness/.venv/bin/mypy --cache-dir=/dev/null src/ examples/
```

M2 must additionally run focused pytest on the new test module and format/type
checks on new source/examples. Do not install missing tooling or invoke live
services. Any inaccessible check must be reported, not presented as passed.

Previously observed baseline issues: formatter findings in
`docs/test-taxonomy-and-suites.md`, `src/harness/targets/base.py`, and
`tests/test_dataset.py`; nine typing errors in `examples/salesagent_study.py`
under the expanded src/examples scope. Reconfirm these and distinguish them
from new failures. The original authoring branch's two trailing-space findings
are absent from the pinned-main worktree and must not be fixed here.

## Workspace and artifact safety

Before writing artifacts, original HEAD/status were read-only verified and ten
candidate file hashes recorded. Also recorded the historical baseline/semantic
datasets, preregistration, study matrix and all 20 existing files under runs:
34 files total. Do not open stores for writing or copy local run files into this
worktree. At completion compare exact hashes, original HEAD/branch/status, and
new worktree tracked diff. Review finalisation adds the unchanged signed review
to the seven Milestone 1 files; no source or Study v1 files may change.

An approved worktree shares Git objects/refs but has its own working files/index.
Its creation changes shared worktree metadata; it does not move original work.
Never reset, stash, clean, stage, delete a branch, or remove either worktree as
an automatic cleanup. The eight reviewed artifacts were committed and merged
under the earlier approvals. Milestone 2 permits the new pack module, focused
tests and living-plan updates only. The subsequent user approval permits staging
and committing those three files and pushing the dedicated branch. No history
rewrite, merge or live run is authorized.

## Human gates and open questions

Workspace and independent review gates are fulfilled. Rebecca Williams approved
the exact candidate-1 grammar, policies, corpus labels and metric denominators on
11 October 2026 at 11:30 BST, with no unresolved objections. The manifest binds
the input/label hashes and unchanged signed review. The reviewer declares
independence from fixture authoring, with involvement in overall project design
and supporting analysis from ChatGPT. Automatic validation is not human approval.

The signed review accepts the narrow grammar and visible acceptance set for
initial contract conformance only. It acknowledges that S06 includes a fresh
turn-1 lookup and does not isolate earlier-only tool evidence reuse. Real-source
authority/completeness requires separate review; no production authority manifest
is fabricated by Milestone 1.

Milestone 2 implementation is complete and approved for its focused commit and
branch push. Milestone 3, subsequent commits and integration need their own
authorization.
Broadening claim families,
adding LLM extraction, gates or target-side changes is a new proposal. Study v1
live outputs must never tune this diagnostic.

## Verification log

Milestone 1 authoring verification at original handoff (review was then pending):

- Strict structural probe passed all 32 input/label pairs, 117 source spans,
  JSON pointers, canonical source/input/provenance hashes, byte checksums, unit
  equivalence, temporal applicability, group/split counts and expected outcomes.
  Existing TargetResponse containers parse. This is fixture consistency checking,
  not a detector run or independent review.
- All seven files passed UTF-8, trailing-whitespace, final-newline, Markdown-fence
  and relative-link checks. Ruff format accepted all four new Markdown files.
  Ruff lint found no Python files in the new artifact set, as intended.
- Full pinned-main offline suite: **1,468 passed in 62.34 seconds**. Explicit
  worktree PYTHONPATH was used with the existing environment; no installs or live
  calls. The original checkout's 77 untracked candidate tests were not copied.
- Ruff lint of the baseline passed. Mypy src passed for 38 files.
- Repository format check reproduced only the same three baseline files above.
  Expanded mypy src/examples reproduced exactly the same nine errors in the
  unchanged study CLI (44 checked files). These are not new-file failures.
- All 34 recorded original candidate/protected/historical file hashes matched;
  original branch/HEAD and the ten untracked paths were unchanged. New destination
  paths were verified unused before publishing the artifacts into the worktree.
- No source, existing tracked file, original candidate, historical artifact,
  authority deployment record, Study v1 setting or AGENTS.md changed. No commit,
  push, merge, live evaluation or implementation of Milestones 2/3 occurred.

Corpus bindings at handoff (candidate-1, not frozen):

| File | Byte SHA-256 |
| --- | --- |
| `cases.jsonl` | `1bfb96ec6a381ed313db86957e03843cdf7a020363793e9bb7bd04d75a19f5ce` |
| `expected.jsonl` | `8682d235f38e90ab5ab78a79ba0d7c97c28a3ddc5d27e592dc52753dbc67e962` |

Meaningful refinements from the initial proposal: one diagnostic contract version
replaces six independently versioned components; reference agreement is explicitly
separated from unassessed agent grounding; source as well as fact validity limits
subject/fact use; corpus gold spans and evidence bindings are materialized before
any detector. These implement the user's requested refinements, not a scope
expansion. Subsequent artifact review is recorded below; separate Milestone 2
authorization remains open.

### Independent review finalisation

The user authorized recording the signed human review and preparing the corpus
for freezing, without changing cases/labels, starting Milestone 2 or committing.
The repository review was copied byte-for-byte into this isolated worktree.
The manifest records Rebecca Williams, APPROVED, candidate-1 and the signed
11/10/2026 11:30 BST timestamp as 2026-10-11T11:30:00+01:00. It binds both
approved corpus hashes and the signed review file hash. At this handoff, freeze
approval was pending.

Fresh offline validation passed all 32 paired records, 117 spans, input/source/
provenance hashes, pointers, unit conversions, temporal applicability and counts.
All 32 explicit decisions have rationales and are endorsed in Section 7; the
policy decisions, 15-claim denominator and S06 limitation are documented.
The 34 protected Study v1/historical artifact hashes remain unchanged.
These are structural checks, not detector measurements. The full test suite
was not rerun for this metadata/documentation-only update; its earlier results
above remain historical. No commit, push, merge or implementation was performed.

### Approved corpus freeze

The user subsequently stated: "Freeze is now approved". The manifest status is
now `frozen`; the reviewed revision remains `candidate-1`. The signed review,
review identity/date, both corpus files and all approved hashes are unchanged.
The README and specification now reflect the approved freeze. Any later input or
label change requires a new revision and review under the existing contract.

Offline corpus structural validation and signed-review bindings were rechecked,
including all 32 pairs, 117 spans, the 15-claim denominator and error fixtures.
All 34 protected artifact hashes remain unchanged. No source implementation,
commit, push or merge is authorized or performed by this freeze approval.

### Authorized artifact commit

The user explicitly authorized committing the reviewed corpus, documentation and
manifest on `feat/salesagent-grounding-v1`. This commit contains only the eight
files in the file map, including the unchanged signed review. Authorization notes
are updated to record this decision; cases, labels, review details and frozen
manifest bindings remain unchanged. Fresh offline corpus validation passed all
32 pairs, 117 spans, review bindings, error fixtures and 34 protected hashes.
No diagnostic implementation, push, merge or live evaluation is included.

### Approved commit amendment and draft publication

On 11 October 2026 the user authorized pushing the dedicated branch and opening
a draft pull request against main, then explicitly approved amending the existing
commit to `test(evaluation): freeze reviewed waterproof grounding corpus v1`.
The six signed-review Markdown hard breaks are accepted and preserved byte-for-byte.
Only this plan's authorization/verification record changes; the other seven
Milestone 1 artifacts, including corpus, labels, signed review and manifest,
remain unchanged. Milestones 2/3, live evaluation and merge remain unauthorized.

Fresh pre-publication validation:

- Both corpus SHA-256 hashes match the frozen manifest and approved review.
- Structural validation passes all 32 pairs, 117 spans, source/input/provenance
  hashes, evidence pointers, unit conversions, temporal eligibility, split/count
  checks, eight deliberate error fixtures and the 15-claim recall denominator.
- The signed review hash, 32 explicit approvals and timestamp bindings match.
- All 1,468 existing offline tests pass in 64.46 seconds with this worktree's
  source path, network blocking, bytecode disabled and pytest caching disabled.
- Whitespace checks pass outside the signed review; its only trailing spaces
  are the six explicitly accepted Markdown hard breaks.
- Original Study v1 branch, HEAD and working-tree status remain unchanged;
  all 34 protected candidate/historical artifact hashes match the saved baseline.
- Remote main still matches the pinned base. No remote grounding branch or PR
  existed at the pre-publication check. Push and draft creation follow this commit.

These checks establish artifact consistency and existing-engine compatibility,
not detector performance. No detector or Milestone 2 implementation was started.

### Milestone 2 preflight (12 October 2026)

- Read AGENTS.md, this plan, specification, ADR, corpus/review, existing model,
  fingerprint utilities, adapter projection and semantic pack/tests.
- Clean grounding worktree at merged main; dedicated M2 branch created.
- Frozen input/label/review hashes and all 34 protected hashes verified.
- Structural probe passes all 32 pairs, 117 spans and review bindings.
- Baseline Ruff lint passes. Ruff format reproduces the three documented files.
  Expanded mypy reproduces exactly the nine documented study-example errors.
- Planned changes: one pack module, one focused test module and this living plan.
  No frozen artifacts or existing engine/Study v1 files will change.
- Engineering reasons outside the corpus are explicit: authority_missing,
  authority_unbound, authority_unreviewed, authority_not_applicable and
  authority_incomplete. Boundary tests exercise these without adding scored
  language examples or revising the frozen oracle.

### Milestone 2 implementation and review handoff

Changes are limited to `src/harness/packs/salesagent_grounding.py`,
`tests/test_salesagent_grounding.py`, and this plan. No approved input, expected
label, manifest, signed review, specification or ADR was edited. No existing
TargetResponse, runner, scorer, target adapter, Study v1 or persistence code changed.

Implementation decisions:

- One pure pack entry point returns a separate GroundingDiagnosticReport;
  there is no Score, quality verdict, runner hook, target call or persistence.
- Strict context validation raises GroundingConfigurationError at the entry
  point. Authority remains a JSON envelope so malformed supplied evidence can
  become a safe report error instead of an eager model-construction exception.
- Envelope/version validation precedes authority integrity and field semantics;
  turn errors preserve unaffected turns. Only defined evidence exceptions are
  caught. Programming errors propagate. Error bodies contain codes and pointers,
  never raw exceptions/provider payloads. Each source content is bounded to 1 MiB;
  this bound and grammar/exclusions are recorded in configuration provenance.
- Detection uses the bounded reviewed clause forms and original Unicode offsets.
  Decimal conversion is exact, including values longer than the ambient default
  precision. Categories are never converted to numbers. Identity and evidence
  applicability are evaluated per turn, with no state shared across calls.
- Runtime candidates retain every eligible identity reference separately from
  the primary subject reference in the frozen semantic projection. Source text,
  context, configuration, response/authority/projection hashes and an optional
  caller-supplied harness revision support deterministic report round-trips.
- Reviewed `human` and synthetic `synthetic_simulation` authority review kinds
  are recognized; real contexts reject simulated review. Unreviewed/pending
  references and null bindings stay indeterminate. Missing fact-level bindings
  for applicable source facts prevent a claim of definitive agreement/absence.
  These are conservative evidence-boundary rules, not new language families.

Focused verification covers all 32 exact frozen projections plus engineering
boundaries: missing/null/open/unreviewed/unbound authority, authority conflicts,
invalid types/values/hashes/versions/pointers (including oversized indices),
real/simulated review separation, partial and all-turn failures, prior-only
identity reuse, future-evidence exclusion, duplicate names, failed tools,
search-products provenance, repeated-attempt isolation, input immutability,
canonical round-trips, safe errors, source/configuration hashes, numeric and
whitespace boundaries, and a saved response produced by the existing adapter
with its offline fake transport. No new scored natural-language corpus was added.

Measured frozen-corpus results (visible, authored examples only):

| Measure | Development | Acceptance |
| --- | --- | --- |
| Exact text projections | 16/16 | 8/8 |
| Exact error projections | N/A (none) | 8/8 |
| Detection TP / FP / FN | 9 / 0 / 0 | 6 / 0 / 0 |
| Supported-grammar precision | 9/9 | 6/6 |
| Supported-grammar recall | 9/9 | 6/6 |
| Matched value/unit, subject and span correctness (each) | 9/9 | 6/6 |
| Comparator agreement with gold extraction, including exclusions | 16/16 | 8/8 |
| Indeterminate among exact affirmative claims | 1/9 | 2/6 |
| Candidate abstention (union, no double counting) | 4/16 | 0/8 |
| Recognized hedge/range/shorthand challenges | 3/3 | N/A (none) |
| Correct exclusions | 4/4 | 2/2 |

Overall: all 32 frozen fixtures agree exactly; all 15 eligible exact affirmative
claims are detected. Findings remain six supported, three contradicted, three
unsupported, six indeterminate and six exclusions, plus eight separate execution
errors. Empty denominators are N/A, not assumed perfect performance.

Further evaluation before claiming broader language performance: a separately
reviewed, blinded challenge set with varied phrasing, punctuation, product names,
quotations/endorsement, multi-claim text and unsupported units; independently
reviewed real source/revision/completeness/deployment bindings; and larger-input
resource/performance testing. Expanded language expectations need a reviewed
corpus/contract revision. S06's existing fresh-lookup limitation remains; an
engineering test now separately verifies earlier-only identity reuse, without
changing S06 or claiming that the agent received numeric facts.

Known limitations: narrow English clause recognition, no pronoun/fuzzy/multi-
product inference, no scientific truth or measured agent grounding, no guarantee
that unrecognized paraphrases produce abstentions, and a visible small synthetic
acceptance set. No additional dependencies or live services were introduced.
Milestone 3 examples/CLI/persistence and any commit/push/merge remain unauthorized.

Final verification on the implementation handed off for review:

- Focused offline tests: **171 passed in 0.29 seconds**.
- Full offline suite: **1,639 passed in 63.17 seconds** (1,468 existing plus 171
  new tests). Both use `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src`, the original
  installed `.venv/bin/python`, and `pytest -q -p no:cacheprovider` from the
  grounding worktree. The focused command additionally selects
  `tests/test_salesagent_grounding.py`. Network blocking remains enabled.
- `ruff check --no-cache .`: passes. `ruff format --check --no-cache` on the two
  new Python files passes. The full format check reproduces only the three
  baseline findings in `docs/test-taxonomy-and-suites.md`,
  `src/harness/targets/base.py`, and `tests/test_dataset.py`.
- `mypy --cache-dir=/dev/null src/`: passes, 39 source files. Expanded
  `mypy --cache-dir=/dev/null src/ examples/` reproduces exactly the nine baseline
  errors in unchanged `examples/salesagent_study.py` (45 files checked).
- The last inspection fixed oversized local-pointer indices escaping as Python
  conversion errors and malformed reviewer identities on unreviewed evidence;
  regression tests cover both. The final full suite includes these fixes.
- Frozen corpus/review hashes match; all original tracked files other than this
  plan are byte-identical to merged main. Original Study v1 branch/HEAD/status
  and all 34 protected candidate/historical artifact hashes remain unchanged.
- Working branch: `feat/salesagent-grounding-v1-m2`, still based at
  `d0e75e99afe4ce03983140c276fb402f328eb7df`. No staging, commit, push, merge,
  dependency installation, live service or Milestone 3 work was performed.

Milestone 2 is ready for human review. Its implementation and new boundary
reason labels have not been independently approved by the corpus reviewer;
Milestone 1 approval applies to the unchanged frozen oracle only.

### Milestone 2 approval and publication authorization

The user reviewed the completed handoff and stated: "this is approved and ready
to commit and push". This approves the Milestone 2 implementation for a focused
commit and push on `feat/salesagent-grounding-v1-m2`; it does not authorize merge,
Milestone 3 or live evaluation. No additional independent corpus review is implied.

Pre-commit verification confirms that implementation and tests are byte-identical
to the tested handoff (171 focused and 1,639 full offline tests passed). Only this
plan's authorization record is updated. Frozen corpus and signed-review hashes,
all other existing tracked files, and the separate Study v1 state and 34 protected
artifact hashes remain unchanged. The earlier baseline Ruff-format and expanded
mypy findings remain unchanged. No code changed, so the test suite was not rerun
for this authorization-only update.
