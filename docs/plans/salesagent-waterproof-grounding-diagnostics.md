# Sales Agent numeric waterproof grounding diagnostics v1

## Status and authorization

Milestone 1 only is authorized. Architecture is approved in principle; the user
subsequently approved the exact workspace path, branch name and pinned main base.
The user has authorized committing the reviewed corpus, documentation and manifest
on this dedicated feature branch. The user additionally authorized pushing the
branch and creating a draft pull request against main, then explicitly approved
amending the existing commit and preserving the signed Markdown hard breaks.
Milestones 2 and 3, implementation and merge remain unauthorized.
This plan is a living record of the bounded slice, not a source implementation.

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
- [ ] Explicit Milestone 2 source-implementation authorization.
- [ ] Milestone 2 implementation (not authorized).
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
freeze and the bounded artifact commit. Explicit source implementation
authorization remains pending.

### Milestone 2: bounded response-to-report path (not authorized)

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
an automatic cleanup. Only the eight reviewed artifacts listed above may be
staged and committed under the subsequent user authorization. The approved
commit amendment, branch push and draft pull request are permitted. No other
history rewrite, merge or live run is authorized.

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

Milestone 2 needs explicit authorization after corpus review. The reviewed
artifact commit is authorized; Milestone 3, further commits and integration need
their own authorization. Broadening claim families,
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
