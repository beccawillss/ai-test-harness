# Exploratory human–judge agreement

This offline workflow compares independently entered human ratings against saved
judge observations of fixed response evidence. Status remains
`provisional_uncalibrated`. It neither calls a target/judge nor tunes anything.
Implementation acceptance does not constitute completed human collection.

The approved first pilot is intentionally selected, not a population sample:

| Selection | Responses |
| --- | ---: |
| `6c7f864209bd`, all 14 canonical semantic cases, attempt 0, dataset order | 14 |
| `bbeb64511171`, `sales-welcome10`, `sales-discount-override`, `sales-previous-product`, attempt 0 | 3 |
| `a68ace7dd819`, `sales-discount-override`, attempt 1 | 1 |

The last response is an explicitly selected known-instability diagnostic. Case
coverage does not guarantee weak, contradictory or incoherent responses. The
manifest records these coverage gaps; do not alter responses or search for
favorable agreement to fill them. The prior inspection inventory is in the
[ExecPlan](plans/human-judge-calibration.md). Each exported manifest pins every
selected source document and prepared response, dataset, case/input, evidence,
prompt and evaluator configuration. Duplicate source selectors are rejected;
repeated case IDs with distinct responses are retained. Evidence duplicates are
available through `manifest.evidence_duplicate_groups` and never silently removed.

For this intended annotator **all 18 examples are conservatively marked
`prior_results_seen`** because whole pre/post run summaries and the two replay
findings were disclosed. An anonymous packet prevents additional disclosure; it
cannot erase memory. The primary declared-unexposed/frozen-request-verified
cohort can be empty, with null metrics. Exposed results are exploratory agreement
evidence, never blind calibration. Do not delay the accepted pilot solely for
this reason.

## Rating contract and annotation schemas

`RatingContract` (`human-rating-contract-v1`) fingerprints the full unchanged
rubric/version, score-scale declaration/anchors, threshold, evidence/projection,
prompt and judgment versions/settings, human instructions and explicit
`instruction_version`, packet version, annotation schema version and declared
dimension keys. Changing human guidance produces a different contract even if
the evaluator prompt stays unchanged. Judge/provider identity stays private.

The Sales Agent recipe declares **0.0, 0.3, 0.6, 0.8, 1.0**. Only those human
scores are valid. The unchanged threshold is 0.7: 0.6 FAIL, 0.8 PASS. **0.7 is not
a human score anchor.** Generic core validation reads the contract; other
contracts may declare continuous [0,1] scales, including threshold-equality PASS.
The existing judge parser and rubric are unchanged.

The exported `human-annotation-draft-v1` JSONL has one line per opaque example:

```json
{"schema_version":"human-annotation-draft-v1","set_id":"<opaque>","example_id":"<opaque>","packet_hash":"<sha256>","binding_hash":"<salted-sha256>","annotator_id":"reviewer-1","score":null,"reason":"","prior_exposure":"unknown","ambiguous":null,"dimensions":null,"supersedes":null}
```

Only a human supplies score and concise nonblank reason (at most 1000 characters).
No score/reason is prefilled or generated. Exposure is `not_seen`,
`prior_results_seen`, `recognized_during_review` or `unknown`. Known private
exposure cannot be downgraded by a draft. `ambiguous` is boolean/null. Optional
`dimensions` is an array of `[declared_key, assessment]` pairs, with assessments
`adequate`, `minor_issue`, `material_issue`, `not_applicable`; keys cannot repeat.
These are human-only descriptions, not weights or invented judge dimensions.

Freeze produces `human-annotation-v1` with a fresh annotation ID, full bound
rating contract/hash, system UTC timestamp and derived `passed`. Unknown fields,
boolean/string/nonfinite/out-of-range/off-anchor scores, invalid timestamps,
blank reasons and contradictory imported verdicts are rejected. Frozen models
use tuples and canonical JSON for nested immutable data.

## Explicit manual commands

The following commands are **operator steps**, not a test or automatic workflow.
They have not been run for actual collection during implementation. There is no
`--live` option, no target parameter and no provider client construction.
Use new output directories; an existing destination or alias is refused.

```sh
uv run --frozen --extra salesagent --extra judge-openai python examples/salesagent_human_calibration.py export \
  --source-db runs/salesagent-semantic.sqlite \
  --output runs/calibration/pilot-01 --annotator reviewer-1
```

Export freezes the approved selection policy into `private/manifest.json`,
randomizes presentation once, and creates `review/packet.json`, `packet.md` and
blank `draft.jsonl`. The renderer accepts only `BlindPacket`, which contains the
contract, opaque item IDs/bindings and exact projected evidence. It excludes
source selectors, model/provider identity, deterministic results, judge scores,
verdicts/reasons, selection strata and public response/replay hashes. A private
random nonce prevents trivial linkage through published fingerprint values.
Share only the review directory with the annotator. All turns, semantic criteria
and selected commerce evidence remain intact; no issue hints are added.

The human now reads the rubric/evidence and edits `review/draft.jsonl`, without
consulting judge results or asking an AI to generate ratings. Complete the whole
set before disclosure, then explicitly run:

```sh
uv run --frozen --extra salesagent --extra judge-openai python examples/salesagent_human_calibration.py freeze \
  --export runs/calibration/pilot-01 \
  --annotations runs/calibration/pilot-01/review/draft.jsonl \
  --output runs/calibration/pilot-01-frozen-v1
```

Freeze accepts no judge store. It verifies the original packet/Markdown and
private manifest, preserves exact draft bytes, writes canonical annotations and
snapshots, then publishes the checksummed receipt last. Missing labels require
explicit `--partial` with missing IDs listed; a partial set is not complete manual
acceptance. Incomplete, edited or missing receipts stop analysis **before any
judge source opens**.

```sh
uv run --frozen --extra salesagent --extra judge-openai python examples/salesagent_human_calibration.py analyze \
  --frozen runs/calibration/pilot-01-frozen-v1 \
  --source-db runs/salesagent-semantic.sqlite \
  --replay-db runs/judge-replay.sqlite \
  --output runs/calibration/pilot-01-analysis-v1
```

The manifest preselects replay `c11e321ea3b84d85ac91ec9963789d18` for the
post-fix discount-override response and `577d69b37cf7456f8992d75713d6db83` for the
known-instability response. All other responses use their one recorded semantic
score. The historical source score is not counted again when a replay is used.
Saved sources are read-only. Joining rebuilds prepared input with the verified
frozen dataset/configuration, checks exact source and all fingerprints, validates
replay actual-call hashes and rejects incompatible experiments/duplicate attempts.
A matching case ID or equal prose is insufficient.

Replay observations are `frozen_request_verified`; historical scores are
`historical_input_reconstructed` because old request bytes were not recorded.
Cohorts remain separate. Selected semantic scores survive unrelated scorer errors;
missing selected scores have an explicit unknown-cause error, never zero. Missing
selected artifacts in this concrete recipe stop analysis; the generic API can
explicitly return missing judge records and report them. No fallback distribution
is silently substituted.

## Corrections and optional issue review

Do not edit a frozen directory or canonical result. Derived Markdown may be
explicitly refreshed with the presentation-only command below. To correct ratings, write a new
JSONL file containing only corrected/additional drafts, with each correction's
`supersedes` set to the exact active annotation ID in the prior frozen bundle.
Run `freeze` with the original `--export`, new `--annotations`, new `--output`,
and `--previous <prior-frozen-directory>`. The new revision retains complete
history, explicitly pins every active chain tip and binds the predecessor receipt.
All revision additions are conservatively `post_disclosure`; they cannot enter
blind-primary analysis. This conservative rule also applies if the operator has
not yet opened a report. Cross-example corrections, forks, cycles, unknown/stale
supersedes and duplicate active ratings fail. Earlier bundles/reports stay readable.

Optional `analyze --issues <manual-issues.jsonl>` accepts separately authored
`human-issue-review-v1` records. Each requires exact frozen annotation digest,
observation-set digest, call index, aware review timestamp after freeze, nonblank
reason and one of the manual relations defined below. Obtain hashes from the post-freeze `result.json`
models using their `.digest` properties. Relations default to `unreviewed`.
Only a manual `same_issue` relation combined with unequal scores yields
`same_issue_different_severity`. Keyword matching never generates relations.
This is unblinded interpretation, not a second independent human rating.

## Interpretation and integrity

JSON/Markdown reports retain source/configuration provenance, exact human versions,
ordered judge calls/reasons/errors, missingness, exposure and verification cohorts,
score/verdict disagreements, human-only dimensions and nonadditive case families.
Headlines weight each fixed response equally: MAE averages per-call absolute
differences within each response, then averages those response means. Signed
differences and verdict-agreement fractions use the same response weighting.
Opposite signed errors must not cancel absolute distances. A separate integer
human-PASS/FAIL × judge-PASS/FAIL matrix and call-weighted/exact-score rates show
numerators and denominators. ERROR and ungated SKIP do not enter verdict rates.
No evidence gives null, not zero or perfect agreement.

Repeated observations retain mean/min/max/range/population stddev, crossing and
inclusive human-within-range flags. A single observation has zero range/stddev
and is marked `single_observation`; that is not repeatability evidence. No mean
threshold verdict, majority vote or “true judge score” is manufactured.

MAE, signed differences and related metrics are **descriptive distances on this
rubric's numeric scale**, not statistically calibrated prediction errors. Rubric
intervals have no assumed universal quantitative meaning. Five calls do not
establish a general judge variance rate or statistical reliability estimate;
neither does this selected 18-response pilot. No significance, reliability,
correlation, tuning or automatic status promotion is performed.

Loading reports recomputes summaries and validates rendered content. Exclusive
writes/checksums detect ordinary accidental alteration; local receipts are not
proof of human authorship or a tamper-proof audit service. The workflow does not
prevent an operator deliberately opening private sources before annotation.

All packets, prepared snapshots, annotations and reports are **evaluation data**.
Reviewed allowlists exclude known raw/provider/operational material, but cannot
prove arbitrary shopper/assistant prose or human reasons contain no sensitive
information. Markdown renders evaluation text in escaped inert blocks without
active links/images/HTML. Persisted source locators are logical or repository
relative; local absolute paths remain execution-only. Keep actual collection
under ignored `runs/calibration/`; tests use clearly synthetic labels only.

## Concise report and analyst appendix

`result.json` remains the complete canonical machine-readable result. Agreement
calculations, observation order, frozen human annotations and calibration status
are unchanged by rendering. New analysis bundles contain three files:

- `report.md`: a compact collection summary, exposure/verification limitations,
  one headline metrics table (including confusion counts), cohort table, notable
  disagreement table and short findings/limitations. For the current 18-response
  pilot this is about 570 words, intended for roughly 1–3 pages; actual pagination
  depends on the Markdown viewer.
- `analyst_appendix.md`: complete per-response comparisons/distributions, ordered
  human/judge reasons, observations/errors, confusion counts, collected human-only
  dimensions, overlapping case families, verification levels, full contract and
  manifest, fingerprints, source/configuration provenance and manual issue reviews.
- `result.json`: the unchanged complete result and derived summary. Rendering
  neither removes empty fields from this file nor changes its schema or values.

The concise table includes score differences, verdict disagreements, threshold
crossing, human scores outside the observed range and missing/error evidence.
Exact-match rows without those conditions remain available in the appendix.
Stable `E01`-style display labels link to full opaque example identities there;
they convey neither source identity nor quality. Long repeat distributions are
summarized in the concise table, with every ordered attempt retained in the
appendix/JSON. Signed differences and MAE remain separate to avoid cancellation.

When no human dimensions were recorded, both Markdown documents say “Human
dimension ratings were not collected in this pilot.” Empty category matrices are
omitted from the appendix; they remain unchanged in JSON. Issue review that has
not occurred is described as unreviewed, not zero recognition disagreement.

To update only presentation for an existing verified analysis:

```sh
uv run --frozen --extra salesagent --extra judge-openai python examples/salesagent_human_calibration.py render \
  --analysis runs/calibration/salesagent-human-v1-analysis
```

This command validates the existing JSON summary and current or original legacy
Markdown before staging/replacing `report.md` and `analyst_appendix.md`. It never
rewrites `result.json`, opens a source/judge database, re-freezes ratings or changes
issue comparisons. Both documents are deterministic. Existing legacy bundles
remain loadable without modification; new bundles require a matching appendix.
An interrupted two-file publication is detected on reload (each file replacement
is atomic; the pair is not a filesystem transaction). Do not hand-edit derived
Markdown to resolve integrity errors.

## Manual issue relations

These additive `human-issue-review-v1` values require explicit post-freeze,
unblinded human review of the recorded concise reasons:

| Relation | Definition |
| --- | --- |
| `same_issue` | Both identify substantially the same primary issue. |
| `partial_overlap` | Identified issues overlap but differ materially in scope/detail. |
| `different_issue` | Both identify shortcomings but their primary issues differ. |
| `human_only_issue` | The human identifies a substantive shortcoming; the judge does not identify a corresponding shortcoming. |
| `judge_only_issue` | The judge identifies a substantive shortcoming; the human does not identify a corresponding shortcoming. |
| `no_issue_both` | Neither identifies a substantive shortcoming. |
| `unclear` | The relation cannot be determined confidently from the recorded reasons. |

Score disagreement and verdict disagreement are numerical comparisons.
Issue-recognition disagreement is a manual relation (different issues, partial
overlap, human-only or judge-only issue). A manually supplied `same_issue` with
different numeric scores may be described as “same issue, different severity”.
The default remains `unreviewed`: score equality, score differences, a score of
1.0 or shared keywords never generate an issue relation. Per-call classifications
remain separate when repeated judges differ. Changing issue review creates a
separately analyzed result; it never changes the frozen human rating. Presentation
refresh does not add or modify any issue review.

## Versioned case definitions

V2 suite sources retain execution-time classification snapshots and definition
hashes under an explicit fingerprint scheme. Replay preparation verifies these
against the complete supplied source cases before calibration identity/binding
construction. Both hashes-only and full payload policies support that verified
path; hashes-only cannot reconstruct absent input/reference, and full still
needs external cases when a subset or omitted metadata prevents full source
reconstruction. See [replay source requirements](judge-replay.md#versioned-v2-suite-sources).

Classification changes alter the case/source identity even when a reviewed
judge projection leaves prompt bytes unchanged. They must not be applied to an
already bound human example. Historical v1 serialization and existing human
bindings remain exact: no stored snapshots are backfilled, no golden hashes
change, and no annotations or calibration artifacts are regenerated. This change
does not alter calibration cohort/strata meanings or report calculations.
