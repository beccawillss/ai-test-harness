# Human ↔ LLM judge calibration evidence

This ExecPlan is **approved for Milestones 1–4** on 2026-09-27, including
architectural decisions 1–5 and the bounded 18-response exploratory pilot. Work
on `feat/human-judge-calibration`; integration is `codex-evaluation`. Do not
collect or invent human ratings, invoke targets/judges, change datasets, rubric,
threshold or historical artifacts, tune anything, or merge. Manual collection
is separately invoked; implementation does not authorize running it automatically.

## Purpose and acceptance

Compare a human's independently recorded rating with judge ratings of the same
frozen response and evaluator evidence. Report score differences, threshold
agreement, repeated-judge distributions, and inspectable disagreements. Separate
numeric disagreement from disagreement about the underlying quality issue.
Human ratings are observations, not an infallible answer key. Keep status
`provisional_uncalibrated`; this milestone produces human-agreement evidence,
not an automatic declaration of judge correctness or statistical calibration.

Acceptance requires an auditable selection policy, strictly validated annotation
format, blind review packet, freeze-before-join workflow, immutable fingerprint
bindings, generic descriptive analysis, JSON/Markdown reports, offline tests and
a documented small manual procedure. No web UI or new scoring framework.

## Progress

- [x] Inspect AGENTS.md, models, replay/scorer/configuration boundaries, store,
  semantic pack, previous ExecPlan/ADR, comparison/reporting utilities and tests.
- [x] Inspect source/replay artifacts read-only; verify both saved replays against
  their exact sources and rebuilt prepared inputs, without target/judge calls.
- [x] Identify candidate coverage, historical-evidence limits and prior exposure.
- [x] Draft this ExecPlan and implementation approval decisions.
- [x] Obtain approval for architectural choices 1–5 and the 18-response pilot.
- [x] Milestone 1: strict models, selection manifest and verified example binding.
- [x] Milestone 2: blind export and immutable human annotation freeze.
- [x] Milestone 3: judge import/join, descriptive analysis and reports.
- [x] Milestone 4: offline regression matrix, documentation and acceptance recipe.
- [ ] Separate manual acceptance: select/freeze, export, human rate, freeze labels,
  join saved judgments, review disagreements and produce the first report.

## Repository findings

Inspected revision: `d4a8ed38947e76f908fef3e80b1736904fbf2fbe`. The worktree was
clean on the requested branch. Follow AGENTS.md and the existing living ExecPlan
convention; no additional plan template was found in the previous milestone.

| Component | Finding and implication |
| --- | --- |
| `core/models.py` | RunResult persists full normalized response and independent Scores per attempt; CaseResult has ID/tags but not the full TestCase. Use the verified frozen dataset, not reconstructed target expectations. No human annotation models exist. |
| `core/replay.py` | prepare_replay validates source selection/dataset, case, stored attempt index, response availability and evaluator compatibility, then freezes PreparedJudgeInput inside PreparedReplay. ReplayResult retains ordered attempts and safe observations. Reuse these boundaries, never the normal target runner. |
| `core/fingerprints.py` | `replay-canonical-json-v1` hashes exact normalized UTF-8 JSON with sorted keys, compact separators, no NaN. Existing dataset hash_cases is a separate unchanged algorithm. |
| PreparedReplay privacy | Includes source IDs/selection/model observations and source evaluator configuration. It is an analyst artifact, **not** a blind review packet. A full ReplayResult additionally contains scores/reasons/verdicts. Do not export either wholesale to the human. |
| JudgedScorer | Existing prepare/score_prepared hooks support generic scoring. score_labelled invokes the judge and returns only boolean pairs; it loses fixed-input provenance, distributions and annotation history, so it is unsuitable as this workflow's engine. |
| RubricJudgeScorer | One holistic [0,1] score and concise reason. Threshold equality passes. Rubric, projection, prompt and judgment versions are explicit. No per-dimension judge scores or machine-readable issue labels exist. |
| Semantic pack | Rubric `salesagent-shopper-quality-v1`, projection `salesagent-semantic-evidence-v2`, prompt `rubric-untrusted-json-v1`, schema `score-reason-v1`, provisional threshold 0.7. Dimensions: relevance/helpfulness, clarity/actionability, prose agreement with commerce facts, conversation coherence. |
| Semantic evidence | Current builder exposes semantic expectations and ordered turns with shopper/assistant text, displayed commerce, constraints and selected normalized facts. It excludes deterministic assertions/results and operational/raw/provider material. Preserve it exactly, including nulls, contradictions and every turn. |
| Config snapshots | Semantic runs retain full selected-scorer rubric, settings/versions, dataset selection/full hashes and resolved_cases excluding extra. Recent generic scorer snapshots add preparation versions/settings; historical runs lack saved prompt bytes. |
| `core/store.py` | Read-only load and same-read document hashing exist; replay load validates internal input/score/verdict consistency. Immutable run/replay IDs are enforced. No human/calibration tables exist. Read-only source access needs no schema mutation. |
| `examples/salesagent_judge_replay.py` | Provides historical semantic-config translation and source preparation. Keep pack-specific translation in the recipe layer. Its preparation_summary leaks source/model information for human review; its result_summary exposes judge results. Neither is a blind renderer. |
| Comparison/reporting | compare_runs compares target runs and averages by case/scorer; it does not implement paired human judgments. `reporting/__init__.py` is empty. Add a dedicated calibration report, not target regression deltas or a judge quality score. |
| Tests | 457 passing tests were recorded at the prior milestone. Relevant coverage includes fixed actual prompts, dataset/config rejection, normalized observations, no target/runner calls, read-only stores, invalid reloads and secret sentinels. conftest blocks socket/DNS access. These counts are historical; no suite was run for this planning-only change. |

### Read-only artifact findings

Six semantic runs contain 56 attempts. Strict preparation with the current v2
pack accepts 41: `bbeb64511171` (14), `71724f5ec996` (4), `6c7f864209bd` (14),
and `a68ace7dd819` (9). The 15 projection-v1 attempts in `c929629bc0a0` and
`55344c3d1dbd` are incompatible under strict current settings. This is a version
eligibility finding, not a judgment that every v1 response is intrinsically bad
or unscorable under its original contract. Do not upgrade or repair them silently.

The separate structured-run database was inventoried read-only. Its baseline
dataset/recipe differs from the semantic dataset; the presence of a
semantic_evaluation key is not proof of a compatible semantic Score/configuration.
Exclude those records from the initial semantic cohort rather than borrowing
current expectations or deterministic pass/fail results.

The two ReplayResults in `runs/judge-replay.sqlite` load successfully. Rebuilding
their inputs from source data/configuration reproduces their response, evidence,
prompt and replay-input fingerprints. Both use observed judge `gpt-6-sol`:

| Replay | Source | Already disclosed observation |
| --- | --- | --- |
| `c11e321ea3b84d85ac91ec9963789d18` | `bbeb64511171 / sales-discount-override / 0` | Five scores of 1.0; all PASS, zero ERROR, no observed crossing. |
| `577d69b37cf7456f8992d75713d6db83` | `a68ace7dd819 / sales-discount-override / 1` | Scores 0.8, 0.6, 0.6, 0.8, 0.8; mean 0.72, range about 0.2, population stddev about 0.09798; three PASS/two FAIL, zero ERROR, crossing. |

The second replay's omitted £130.50 quote and judge-severity disagreement have
already been discussed with the intended annotator. **It cannot be made blind
retroactively.** The first replay's scores are also known. Earlier run summaries
and case findings may have exposed further candidates. An anonymous packet can
avoid new disclosure; it cannot undo memory or guarantee examples are unrecognized.

These two results establish no human agreement: no human labels have yet been
collected by this workflow. Do not reuse the illustrative human score 0.6 from
the request as an actual annotation.

Inspection left these database byte SHA-256 values unchanged:

| Database locator | SHA-256 |
| --- | --- |
| `runs/salesagent-semantic.sqlite` | `293156e08238d03658fbe73199a853a033d703fbb20db9c64a0b18271a77da67` |
| `runs/judge-replay.sqlite` | `7ab0ebe516415be162807f8d68299afc44b3a93bda6005133072f15d330b2a6d` |
| `runs/salesagent.sqlite` | `24d904f855b11e5def7e577d942994439fed9fac743932c29c351093c39b2b05` |

The semantic dataset's canonical hash remains
`33654c3f4870efc67edd8e30a6ae0a82c17eb58c8c30cb323add5d0efe414849`.

## Calibration-set selection before annotation

Approved: an **18-response pilot**, with selectors below frozen before any human
ratings are collected. This is a deliberately selected diagnostic set, not a
random sample of production traffic. Selection uses scenario coverage, source
phase and fixed attempt rules, not numeric judge scores or human/judge agreement.
The mandated known-instability example is an explicit exception/supplement,
kept identifiable in analyst reports rather than hidden in representative rates.

| Group | Predeclared selection rule | Count |
| --- | --- | --- |
| Scenario coverage | All 14 canonical semantic cases from pre-fix v2 run `6c7f864209bd`, stored attempt 0, in frozen dataset order. No ranking by scores/verdicts/reasons. | 14 |
| Promotion comparison | Post-fix run `bbeb64511171`, attempt 0 for the complete predefined trio `sales-welcome10`, `sales-discount-override`, `sales-previous-product`. | 3 |
| Known instability diagnostic | `a68ace7dd819 / sales-discount-override / 1`, explicitly requested because fixed-input threshold crossing was observed. | 1 |

Inspection confirmed all 18 selectors exist, build current semantic evidence,
and have 18 distinct projected-evidence fingerprints. Five selected responses
contain multiple turns. Repeated case IDs are intentional: each fixed response
is a separate example with immutable identity. Do not collapse by case ID or
pretend multiple responses from one scenario are independent scenario samples.

Coverage includes recommendation/budget/no-match/out-of-stock, retain/replace/
clear constraints, active/inactive promotions, previous-product reference,
conversation, claimed authority, fabricated price and discount override inputs.
Pre/post promotion material supplies known omissions and intended stronger
comparators; the instability source supplies the threshold-sensitive diagnostic.
Those selection rationales never appear in human-facing packets.

**Coverage gap:** an adversarial input is not proof that the response contains a
factual contradiction, and a multi-turn case is not proof of a coherence failure.
Inspection establishes eligible evidence, not human quality labels. Do not promise
that this pool contains clearly weak responses, actual factual contradictions or
actual coherence failures solely from scenario names or judge ratings.

Before freezing the manifest, an evidence-only curation checklist records whether
those desired phenomena are visibly represented, without using judge scores.
If absent, record them as coverage gaps. Do not fabricate altered responses,
rerun targets, force a “weak” label, or search by disagreement to satisfy quotas.
The user accepted the bounded pilot with disclosed gaps on 2026-09-27; no
additional saved material is required before this exploratory collection. The first collection pass never changes rubric or
threshold to create the desired balance. Final quality/dimension summaries are
based on actual human annotations, not curation labels.

Freeze a manifest recording policy/version, candidate pool/source document
hashes, selected selectors, full identity/config bindings, reasons for any
eligibility exclusion, evidence-duplicate groups, case-family tags, and prior
exposure flags. Blind ordering is a one-time randomized permutation recorded in
the private manifest; filenames and positions must not encode source phase,
quality, judge outcome or paired-case relationships. Corrections to selection
produce a new manifest/set ID before rating, not silent replacement.

## Approved architecture and files

The flow is:

```text
read-only saved response + verified dataset/configuration
    → frozen CalibrationExample and private selection manifest
    → allowlisted blind packet + blank annotation template
    → human-authored annotation saved and frozen
    → compatible saved judge observations loaded and joined by fingerprints
    → CalibrationResult + descriptive JSON/Markdown report
    → optional separate post-rating issue comparison
```

No Target parameter, normal runner call, live judge adapter construction or
network path exists in export/freeze/analyze. Optional additional judging uses
the already implemented replay workflow separately after annotations freeze.
No judge result is passed into human annotation creation, and no model writes
human scores/reasons. Do not call score_labelled or add another judge framework.

| Proposed file | Scope |
| --- | --- |
| `src/harness/core/calibration.py` | Versioned frozen models, verified example identities, annotation validation, fingerprint joins and pure descriptive analysis. No pack/provider schemas. |
| `src/harness/core/calibration_io.py` | JSONL/JSON loading with file/line errors, exclusive creation of frozen bundles, canonical checksums and manifest/receipt validation. Keep existing SQLite schemas unchanged. |
| `src/harness/reporting/calibration.py` | Explicit blind renderer and separate post-freeze report renderer; Markdown plus machine-readable JSON, safe escaping, no automatic score-based hints. |
| `examples/salesagent_human_calibration.py` | Pack-aware manifest construction, existing historical-config translation, export/freeze/analyze commands. Reuse prepare_replay and semantic make_scorer with a judge callable that fails if invoked. |
| `tests/test_calibration.py`, `test_calibration_io.py`, `test_salesagent_human_calibration.py` | Offline math, models, isolation, blinding, immutable storage and example workflow. Use temporary synthetic stores/fake scorers. |
| `docs/human-judge-calibration.md`, `docs/adr/0005-human-judge-agreement.md` | Operator instructions, boundaries, interpretation and approved decisions. |

Reuse `PreparedJudgeInput`, `PreparedReplay`, `EvaluatorConfiguration`,
`SourceProvenance`, canonical hashes, read-only SQLiteResultStore and existing
variance_summary. No change to TargetResponse, RunResult, ReplayResult, datasets,
live runner, current rubric, threshold or calibration status is needed. A small
recipe helper extraction is allowed only if necessary to share config translation;
do not move Sales Agent knowledge into core or broadly refactor earlier examples.

### Models and annotation schema

Use strict Pydantic models with unknown fields forbidden, finite bounded numeric
values (booleans/strings are not scores), timezone-aware timestamps and explicit
schema versions. Frozen models must also freeze nested content: canonical JSON
strings/tuples, not mutable dictionaries behind a frozen outer object.

| Model | Required content |
| --- | --- |
| CalibrationExample (analyst-only) | Set/example ID, source document and response identity, dataset/case/input hashes, exact prepared evidence/prompt, evaluator/rating-contract versions and hashes, blind binding, private scenario strata and exposure information. No copied historical scores or reasons. |
| BlindReviewItem | Opaque example ID and binding, packet/set identity, full unchanged rubric and score anchors, threshold, required evaluation material, optional generic dimension names and blank rating fields. No source mapping or judge observations. |
| HumanAnnotation | Version, immutable annotation ID, set/example/packet binding, annotator pseudonym, human score, derived PASS/FAIL, concise reason, rubric/version/threshold binding, recorded_at, exposure declaration, optional ambiguity and dimension assessments, optional supersedes ID. |
| FrozenAnnotationSet | Manifest/packet hashes, exact submitted annotation file hash, canonical annotation hashes, active annotation IDs, annotator, freeze timestamp/receipt and immutable set revision. Required before analysis can load judge results. |
| JudgeObservationSet | Source kind/document ID, ordered score/error observations, actual or reconstructed input verification level, source/response/evidence/prompt/evaluator fingerprints, config/observed-model context. Reuses Score/JudgeObservation types. |
| CalibrationResult / CalibrationSummary | Input manifest/annotation/judge artifact hashes, per-example comparisons and missing/error statuses, dimension/case-family breakdowns with counts, exposure/verification cohorts, explicit weighting and descriptive aggregates. Status stays provisional_uncalibrated. |
| IssueComparison (optional, post-freeze) | Frozen human annotation and judge-observation IDs/hashes, manual issue relation, concise evidence-based explanation and review timestamp; never overwrites the human rating. |

Prefer JSONL over YAML to reuse existing tooling and avoid another dependency.
One human-editable draft line per example contains these fields (illustrative
schema only; do not prefill an actual score or a reason):

```json
{"schema_version":"human-annotation-draft-v1","set_id":"<opaque>","example_id":"<opaque>","packet_hash":"<sha256>","binding_hash":"<opaque-sha256>","annotator_id":"reviewer-1","score":null,"reason":"","prior_exposure":"unknown","ambiguous":null,"dimensions":null,"supersedes":null}
```

Drafts are incomplete until the human supplies a score allowed by the rating contract, concise
nonblank reason (proposed maximum 1000 characters), and exposure declaration.
The freeze command validates against the exported manifest and creates
`human-annotation-v1`, adding a new annotation ID, rubric/threshold/hash fields,
system-recorded UTC timestamp and `passed = score >= threshold`. These derived
fields never create or change the human rating. The importer rejects any supplied
passed/verdict contradicting the score/threshold rather than accepting two
inconsistent judgments. Sales Agent permits only 0.0, 0.3, 0.6, 0.8 and 1.0.
Threshold 0.7 is unchanged: 0.6 fails and 0.8 passes; 0.7 is not a human
anchor. Generic continuous contracts retain threshold-equality PASS.

Annotator identity is a pseudonym, not an email/account credential. Optional
ambiguity is a boolean/null, not a numerical certainty claim. Optional dimensions
use declared rubric dimension keys and `adequate | minor_issue | material_issue |
not_applicable`; these are qualitative human assessments, not new scoring
weights or inferred judge sub-scores. An optional short issue description may
reference a turn/field in the already supplied evidence. Do not request lengthy
reasoning, chain-of-thought, hidden prompts or target implementation details.

Expose no field for credentials, provider bodies or arbitrary metadata. The
schema and explicit projections reject known forbidden fields. They cannot
prove free-text reasons or natural-language evaluation content contain no
sensitive information; annotations, packets and reports remain evaluation data.

## Blinding and freezing mechanism

Separate analyst and human artifacts by construction:

1. The analyst prepares verified examples. Source-side code may read saved run
   metadata to validate eligibility, but selection does not consume judge scores
   and the blind renderer accepts only a BlindReviewItem, never RunResult,
   ReplayResult, source configuration wholesale or their summary dictionaries.
2. Human packets contain exact projected evidence (all turns/facts/expectations),
   unchanged rubric/anchors, scoring instructions and the recorded threshold.
   Showing the same local threshold allows aligned human PASS/FAIL; it does not
   add the threshold to the judge's existing request. No omitted fields are
   silently replaced, summarized or selectively highlighted.
3. Exclude historical/replay Scores, attempt verdicts, deterministic results,
   judge reasons, model/provider identity, source run/case/attempt IDs, source
   locators, known-issue labels, selection rationale and operational fields.
   Omit published response/replay hashes that could trivially link an item to
   the already disclosed results. Use a per-export random nonce in the opaque
   binding, retained privately, rather than an unsalted public response hash.
4. A binding covers the private example's exact identity and rating contract;
   a packet hash covers the ordered human-visible items/instructions (excluding
   the hash field itself). Human annotations reference that binding/packet.
   This permits verification without exposing the source mapping while rating.
   The private manifest maps it to full source/evidence hashes for later joining.
5. Export makes a static Markdown packet plus strict JSONL drafts in a review
   directory. Render untrusted text as inert escaped data, with no interpreted
   HTML, remote images or active links. No score defaults, judge-generated
   examples or annotations, source tables or feedback about expected agreement.
6. Freeze reads only the human drafts, packet and private identity manifest,
   validates them, writes an immutable annotation set, and returns a receipt.
   It accepts no judge-observation store and prints only completeness/validation
   status, never scores/reasons from a judge. Freeze the entire planned set before
   disclosure to reduce learning from early items influencing later ones.
7. Analyze first verifies the freeze receipt and all annotation hashes, then
   opens the judge result sources. Missing/unfrozen/edited annotations stop this
   step before judge loading or report generation. A partial exploratory report
   is allowed only from an explicitly frozen partial set with missing IDs listed;
   it is not complete manual acceptance and never silently shrinks the set.

Blinding protects against accidental disclosure by this workflow, not a user
opening the private database/manifest or recognizing text from prior work. The
packet instructions require independent human scoring and no consultation of
judge outputs or AI-generated ratings during the collection pass.

Exposure values: `not_seen`, `prior_results_seen`, `recognized_during_review`,
`unknown`. Known previous disclosures are recorded privately before export and
cannot be overridden by a more optimistic draft flag. Unexpected recognition
must be declared by the human. Effective exposure uses the conservative union.
The two known replay sources are always prior-results-seen for this annotator;
earlier full-run summaries may contaminate more or all of this proposed set.

Do not promise a fully blind primary cohort from these already discussed runs.
Report declared-unexposed, exposed and unknown groups separately; if none qualifies,
the blind aggregate is null with “no eligible blind ratings.” The pilot can still
demonstrate the workflow and exploratory human agreement. Achieving a fresh blind
cohort may require other existing unseen material under a new selection manifest;
another human rater is outside v1 unless separately approved. Prior exposure is
an approval decision, not something the exporter can repair by renaming examples.

## Fingerprints and judge joining

Use existing canonicalization unchanged. Preserve at least source document,
normalized response, TestCase/input, projected evidence, exact prompt and full
evaluator/replay-input hashes. A rating-contract hash covers full rubric, version,
threshold, projection/prompt/judgment versions and evidence settings, declared
score scale/anchors, human instructions/version, annotation/packet schema versions
and dimension names. Human and judge share the unchanged evaluator rubric and
evidence contract; added human guidance is separately bound and does not alter
the judge prompt. Source/model provenance stays analyst-only. Presentation order
is also bound in the packet and private manifest, separate from evaluator input.

The join verifies manifest/annotation binding first, then source run/case/attempt
plus full response/evidence/prompt/config hashes. Case ID alone, equal prose
alone, matching numeric scores or a claimed hash copied from another record
are never sufficient. Recompute hashes from stored payloads, not just supplied
hash strings. Load and validate ReplayResult, rebuild source evidence through
prepare_replay, and compare all relevant identities. Judge attempts must have
matching actual prompt/input fingerprints; reject corrupt/incompatible records
instead of interpreting them as a quality disagreement.

Support two explicitly distinct verification levels:

- `frozen_request_verified`: a saved ReplayResult with prepared input, actual
  per-call fingerprints and source/evidence/config matches. This supports the
  strongest fixed-input comparison.
- `historical_input_reconstructed`: a semantic Score from one exact saved source
  attempt, with verified dataset and matching recorded scorer/config versions,
  and evidence/prompt rebuilt locally. Older runs did not save request bytes.
  This is a qualified historical comparison, not proof of the historical prompt
  bytes. Missing necessary source settings or changed projection is ineligible;
  do not label current defaults as historical truth.

Keep these levels separate in summaries; never hide the distinction inside a
single “same input verified” flag. The primary strictly verified, declared-blind
cohort may initially be empty. A reconstructed/exposed cohort can still produce
an explicitly qualified exploratory report. Additional explicit replay after
annotation freeze can improve request verification but cannot erase prior exposure.

Historical import uses only the selected semantic Score, not the source attempt's
aggregate PASS/FAIL (which may reflect deterministic gates or another scorer's
failure). A valid selected Score survives unrelated source errors. A missing
semantic Score is missing/errored judge data, never a score of zero; without
reliable typed diagnostics mark the cause unknown rather than parsing unsafe
exception text or inferring an invented score.

Predeclare the observation policy in the manifest: prefer an explicitly named
compatible replay for a source; otherwise use its one historical semantic call.
For the two known examples name the two verified replay IDs above. Do not choose
the replay with the most favorable agreement, silently combine historical and
replay calls, or treat the same attempt referenced twice as two observations.
Keep original source scores separately available for inspection only after
freeze. If future additional replay batches are selected, create a new analysis
manifest listing every batch and deduplicated (artifact ID, attempt index).

Default analysis requires one scorer/rubric/threshold/projection and requested
judge configuration per report cohort. Changed judge models/settings are separate
cohorts/analysis revisions; observed-model differences remain visible and qualify
interpretation. No automatic rubric tuning, threshold tuning, model ranking or
pooling incompatible experiments.

## Agreement metrics and repeated judgments

For matched example i with human score h_i and n_i valid judge values j_ik,
record each d_ik = j_ik − h_i and |d_ik| in attempt order. ERROR slots remain
visible with null numeric differences. No completed judge scores means no
agreement evidence for that example. Missing human labels and missing judge
records are distinct statuses and are counted in coverage, not converted to FAIL.

Use **equal weight per fixed response** for headline descriptive aggregates:

- Per-example signed difference b_i = mean_k(d_ik).
- Per-example absolute difference a_i = mean_k(|d_ik|).
- MAE = mean_i(a_i) across examples with both human and valid judge evidence.
- Mean signed difference = mean_i(b_i); positive means judge scores higher than
  the human, negative lower. This describes this selected set, not population bias.
- Per-example verdict agreement q_i = matching gated judge verdicts / valid
  gated judge verdicts. Headline agreement rate = mean_i(q_i).

This prevents a five-call replay from outweighing a one-call example fivefold.
Do not replace a_i with |mean(j_i) − h_i|: opposite signed differences could cancel.
Report the difference of means as a separately labelled descriptive field only.
The mean is an observed average, never “the judge's true score.” Do not assign
one synthetic judge verdict by thresholding the mean or majority voting in v1.

Show an additional **call-level confusion matrix with integer counts** over valid
gated pairs, labelled as call-weighted and separate from the equal-response rate:

| | Judge PASS | Judge FAIL |
| --- | --- | --- |
| Human PASS | both PASS | human PASS / judge FAIL |
| Human FAIL | human FAIL / judge PASS | both FAIL |

Print numerator/denominator for every rate, number of rated responses and total
paired calls. ERROR/SKIP/missing entries do not enter this matrix. SKIP has a
numeric comparison if a valid informational score exists but no verdict agreement;
the first Sales Agent cohort requires a gated threshold. Exact-score agreement
count/rate is secondary, based on equality of stored numeric scores with no
post-hoc tolerance; round only displays, not stored scores or calculations.

For each repeated example retain ordered scores/errors, mean/min/max/range,
population stddev, PASS/FAIL counts, crossing, q_i, and whether h_i lies within
the inclusive observed score range. One call has range/stddev zero but is marked
`single_observation`; it supplies no evidence of repeatability. Empty distributions
have null summaries/inside-range/quality rates; avoid division by zero.

Worked **synthetic** acceptance fixture, not a real human rating: h=0.6 and
j=[0.8,0.6,0.6,0.8,0.8] at 0.7. Human FAIL; mean 0.72, min 0.6, max 0.8,
range 0.2, stddev approximately 0.09798; mean signed/absolute difference 0.12;
two of five judge verdicts match the human (0.4), crossing true, human inside
range true, exact-score matches 2/5. Matrix adds two human-FAIL/judge-FAIL and
three human-FAIL/judge-PASS calls. A separate [0.4,0.8] fixture at h=0.6 must have
zero mean signed difference but MAE 0.2, proving absolute errors are not cancelled.

Reports list numeric disagreement and threshold-disagreement cases separately.
Optional dimension/case-family tables show exact group sizes, human issue counts,
and the same descriptive differences/agreement rates. Overlapping groups are
explicitly nonadditive; unassessed dimensions remain unknown. Small cell counts
can suggest follow-up questions, not establish systematically difficult dimensions.
Do not claim dimension-level human/judge agreement when the judge has no dimension
ratings. No Pearson/Spearman, p-values, confidence intervals, significance tests,
calibration curves or inter-rater reliability in this one-rater small pilot.

### Issue recognition versus severity

Scores alone cannot establish that human and judge recognized the same issue.
Judge reasons are unstructured concise prose; string/keyword equality is not a
semantic agreement metric. Initially the report shows numerical/verdict
differences with `issue_relation=unreviewed` and the frozen human reason beside
each judge reason, only after annotation freeze.

Optionally, the same operator manually records a separate post-rating
IssueComparison for each relevant human-annotation/judge-attempt pair:
`same_issue | different_issue | partial_overlap | no_issue_both | unclear`.
If same_issue and scores differ, the report may label it
`same_issue_different_severity`; if issue relation differs, say so explicitly.
Record short references to the affected turn/claim, no chain-of-thought. Mixed
relations across a replay stay per-attempt, not collapsed into a single verdict.
This is an unblinded interpretive review, not a second independent human rating,
automated adjudication or inter-rater reliability statistic.

The known £130.50 omission is a diagnostic motivating this feature. It must not
be prefilled into a human draft or used to generate the human reason. The earlier
observation that judge reasons agree with one another is not evidence that they
agree with an as-yet-uncollected human judgment.

## Persistence and immutability

Choose **human-editable JSONL plus immutable file bundles**, without new SQLite
tables in v1. Existing source/replay databases remain read-only. Store local
evaluation artifacts under ignored `runs/calibration/<set-id>/`; commit only
schemas, synthetic fixtures, policy/docs and recipe code. Live annotation content
does not enter Git by default. An operator may separately authorize publication
of a reviewed non-sensitive annotation corpus later.

Separate `private/manifest.json` and verified example snapshots from
`review/packet.md`, `review/packet.json` and editable `review/draft.jsonl`.
Exporters create new directories and refuse overwrite. Freeze writes a new
bundle containing exact draft bytes, canonical validated annotation JSONL,
manifest/packet hashes, and `receipt.json`. Write staged files then publish the
receipt last only after integrity verification; incomplete bundles cannot analyze.
Exclusive file/directory creation prevents normal overwrite, and load verifies
content hashes. Document that hashes detect accidental alteration; local file
access controls/receipts are not cryptographic proof of human authorship or a
tamper-proof audit service.

Corrections produce a new annotation ID with supersedes pointing to the previous
record; original frozen files/results remain loadable unchanged. Reject duplicate
IDs, conflicting active annotations for the same set/example/annotator, cycles,
cross-example corrections and unspecified choices among revisions. An analysis
manifest pins exactly which version is active; never choose “latest” silently.
The corrected record is independently frozen and creates a new CalibrationResult.
If judge results were already disclosed, mark the correction `post_disclosure`
and exclude it from the blind-primary cohort even if the original rating was blind.

Store CalibrationResult as a new immutable `result.json`, with rendered
`report.md` and exact input/checksum/version manifests in a new analysis directory.
Reload validates and recomputes summary values from individual comparisons;
never trust separately editable aggregate metrics. Joining existing results is
offline and repeatable; failures cannot mutate earlier annotations or artifacts.
No Baseline promotion or RunResult/ReplayResult migration is involved.

## Reporting and interpretation

The concise report begins with planned/selected/frozen-human/matched example
counts, missing labels/judges, judge completed/error counts, distinct case-family
count, scorer/rubric/threshold/projection and requested/observed judge configuration.
Show exposure and input-verification cohorts before aggregate agreement numbers.
The primary cohort requires frozen-request verification and declared unexposed
ratings. A zero-size cohort reports null metrics, not 0% agreement or perfect quality.

Then show one row per example: opaque ID (source mapping available only in the
post-freeze analyst appendix), human score/verdict/reason reference, ordered judge
scores, mean/range, matching verdict count/denominator, crossing, numeric
differences and manual issue relation or unreviewed. Highlight threshold
disagreements for inspection without hiding score-only differences or errors.
Keep case order stable rather than sorting by favorable agreement.

Show equal-response MAE/bias/agreement, call-level confusion counts/rate and
secondary exact-score counts with denominators. Full ordered per-call reasons,
observations, hashes and errors remain in JSON and an analyst detail appendix.
Dimension/case-type breakdowns are descriptive and display small sample counts.
Neither renderer outputs credentials, raw envelopes, hidden prompts, absolute
local source paths or uncontrolled exception bodies. Escape Markdown/HTML from
untrusted response/reason text. Reports contain evaluation content and require
the same sharing controls as the source and annotation files.

Status remains `provisional_uncalibrated` regardless of agreement. A later status
change would require a separately approved protocol: an adequately sized,
representative held-out set, genuinely independent blind human judgments and a
documented adjudication process, prespecified rubric/threshold and acceptance
criteria, fixed judge/config versions, repeatability/error analysis, and review
of coverage/limitations. This milestone sets no numerical universal pass bar,
changes no release gate and cannot certify human labels or a judge from 18 items.

## Milestones and offline tests

1. **Models and identity.** Add strict versioned annotation/example/result types,
   manifest/schema validation, canonical identities and historical versus replay
   verification adapters. Establish data-only interfaces with no target/provider
   construction. Test mismatches before any scoring or report generation.
2. **Blind collection.** Add allowlisted packet rendering and blank templates,
   opaque source binding, exposure policy, immutable freeze receipts and explicit
   correction revisions. Test export/freeze without loading judge observations.
3. **Join and report.** Import selected saved observations after receipt validation,
   retain distributions/errors, compute explicit-weight metrics and render
   reports. Add optional separate manual issue-review records, never an LLM
   annotation generator. Keep status unchanged.
4. **Recipe and validation.** Finish generic/semantic offline end-to-end examples,
   operator docs and ADR; run all checks, record counts/results/deviations here.
   Prepare collection artifacts only when the user authorizes the selection and
   manual workflow. Do not run additional live judging automatically.

Required offline matrix:

- Annotation schema: bool/string/NaN/out-of-range/off-anchor scores, blank/oversized reason,
  invalid timestamp/version/annotator/dimension/exposure, unknown secret/raw fields,
  null draft fields and exact-threshold PASS. Derived verdict contradiction rejected.
- Manifest/response/evidence/prompt/rubric/threshold/dataset/config mismatch,
  case-ID collisions, changed source attempt, stale/corrupt fingerprint and same
  prose with different evidence. Strict validation recomputes, not trusts hashes.
- Blind packet contains all semantic evidence/rubric but none of judge scores,
  verdicts/reasons/model IDs, deterministic results, raw/hidden fields, source
  selectors, labels implying weakness or public hash links. Sentinel and adversarial
  text tests cover nested fields, prose rendering and no active remote content.
- Export/freeze have no JudgeObservationSet input or result-report access. Analyze
  fails on unfrozen/edited/incomplete annotations before opening a judge store;
  no prefilled human scores/reasons, no model-authored annotations. Known exposure
  cannot be downgraded; post-disclosure corrections remain non-blind.
- Unique annotation IDs, duplicate active records, valid superseding revision,
  correction cycles/wrong source, explicit active-version selection, preserved old
  frozen bytes and old reports. File/line diagnostics stay useful without logging
  source content or absolute paths in portable reports.
- Signed/absolute differences, cancellation trap, MAE, equal-response versus
  call-weighted agreement with unequal repeat counts, integer confusion counts,
  exact equality, threshold differences, single/all-error/empty cases, range
  inclusion and repeated crossing example. Never count ERROR as quality zero.
- Mixed successful/ERROR calls, missing judge record, missing human label, unrelated
  scorer error with valid selected semantic Score, no selected score and unknown
  historical error cause; explicit coverage and null empty denominators.
- Replay source/config/fingerprints verified; historical reconstruction distinctly
  labelled; no pooling differing judge/rubric/projection/threshold or duplicate
  judge attempts. No automatic mean verdict or automatic issue-recognition inference.
- JSONL/JSON round-trip, stable hashing, freeze receipt integrity, exclusive writes,
  partial writes/save failures, summary recomputation and unchanged SQLite sources.
- Generic non-Sales-Agent examples and recipe end-to-end tests use synthetic saved
  responses. Bomb target constructors/invoke/normal runner/judge clients during
  export/freeze/analyze; all tests remain under the existing network blocker.

Offline validation commands (implemented modules):

```sh
UV_OFFLINE=1 uv run --frozen --extra salesagent --extra judge-openai pytest -q tests/test_calibration.py tests/test_calibration_io.py tests/test_salesagent_human_calibration.py tests/test_replay.py tests/test_salesagent_judge_replay.py tests/test_rubric_judge.py tests/test_store.py tests/test_comparison.py
UV_OFFLINE=1 uv run --frozen --extra salesagent --extra judge-openai pytest -v
UV_OFFLINE=1 uv run --frozen --extra salesagent --extra judge-openai ruff check .
UV_OFFLINE=1 uv run --frozen --extra salesagent --extra judge-openai mypy src/ examples/
UV_OFFLINE=1 uv run --frozen --extra salesagent --extra judge-openai ruff format --check src/harness/core/calibration.py src/harness/core/calibration_io.py src/harness/reporting/calibration.py examples/salesagent_human_calibration.py tests/test_calibration.py tests/test_calibration_io.py tests/test_salesagent_human_calibration.py
git diff --check
git diff --exit-code -- datasets/salesagent/baseline.jsonl datasets/salesagent/semantic.jsonl
```

Extend scoped formatting to every file actually touched. Prior milestone has
three unchanged global format failures: targets/base.py, test_callable_target.py,
test_dataset.py. Report pre-existing failures separately; do not refactor them.
Verify byte/canonical dataset hashes and source/replay database checksums before
and after. No test may depend on ignored live artifacts or credentials.

## Manual acceptance after implementation approval

1. Approve/freeze the 18-item selection policy, rubric/threshold and evidence
   contract before human annotation. Resolve coverage gaps and prior-exposure
   expectations explicitly. Save source selectors privately and fingerprint every
   selected response. No target call, new output or expectation edits occur.
2. Export the blind review packet and blank JSONL template under a new set ID.
   Verify full evidence preservation and exclusion of judge results/identity hints.
   The intended annotator receives the review directory, not the private manifest,
   source databases or previously generated analyst summaries.
3. The user manually reads the unchanged semantic rubric, rates each fixed response
   and writes a concise reason, declaring prior exposure/recognition/ambiguity and
   optional dimensions. Do not display scores, give judge-based rating hints,
   auto-complete judgments or tune rubric/threshold during collection.
4. Validate/freeze the complete annotation set; record file hashes and receipt.
   Save before opening any joined judge report. This is the boundary after which
   results can be disclosed. If a draft is incomplete, return only validation
   diagnostics and keep judge results hidden.
5. Load the predeclared two replays and compatible historical semantic judgments
   read-only. Join using source plus response/evidence/prompt/config fingerprints.
   Report missing/ineligible items and historical request-verification limitations.
   Do not silently replace the previously selected distribution or count the
   original source Score again inside a replay distribution.
6. Produce the first JSON/Markdown report with separate exposure and verification
   cohorts, explicit denominators and all individual scores/errors. The primary
   blind/verified aggregate may be empty; exploratory comparisons remain labelled.
   Optionally add manual issue comparisons after ratings are immutable, including
   the known omission example without retroactively changing its human label.
7. If useful and separately invoked, replay selected fixed responses N times using
   the existing recipe after human freeze, with an explicit source/attempt/config
   and judge-call budget. Target calls remain zero. Produce a new analysis revision
   listing the added replay IDs; do not overwrite annotations or old results.
8. Record set/annotation/analysis IDs and hashes, actual cohort sizes, metrics,
   observed issues, gaps/exposure/verification limits and unchanged status here.
   An implementation plumbing check or a high agreement rate is not calibration.

Implemented command phases are `export --source-db <source> --output <export>
--annotator <pseudonym>`, `freeze --export <export> --annotations <human-draft>
--output <frozen>`, then `analyze --frozen <frozen> --source-db <source>
--replay-db <replays> --output <analysis>` on
`examples/salesagent_human_calibration.py`. The approved selection and two replay
IDs are fixed in the recipe and frozen privately during explicit export; there
is no --live path in this recipe. Plain JSONL editing is
the annotation interface. No automatic five-call replay is part of acceptance.

## Risks, limitations and approved decisions

| Risk or gap | Proposed treatment |
| --- | --- |
| Prior scores/reasons already disclosed | Track conservative exposure; never claim renamed packets restore blindness. Separate diagnostic and declared-blind cohorts; allow null primary evidence. |
| Desired weak/contradiction/coherence failures may be absent | Record objective coverage gaps; approve bounded pilot or obtain additional eligible persisted material before collection. No fabricated target evidence. |
| Historical prompt bytes absent | Label reconstruction, separate from replay verification; optional later fixed-input replay only after freeze. |
| More repeats or repeated scenario IDs inflate apparent sample size | Equal-response metrics, separate call matrix, scenario counts and correlated-example caveat; no significance/reliability estimates. |
| Same issue inferred from similar scores or keywords | Separate manual post-rating issue review, unreviewed default; no automatic recognition claims or judge-generated human labels. |
| Optional human dimensions mistaken for judge dimensions | Human-only descriptive breakdowns with counts; no invented sub-scores or systematic-difficulty claim. |
| Sensitive evaluation prose or local paths leak | Explicit packet/report allowlists, inert rendering and share-safe source locators; evaluation artifacts are not public merely because operational fields are excluded. |
| Frozen files edited or corrections cherry-picked | Exclusive writes, canonical manifests/receipts, immutable IDs, explicit supersedes/version selection; no hidden latest-record replacement. Local files are not a tamper-proof service. |
| Users overinterpret a small selected set | Keep provisional_uncalibrated, expose missingness/denominators/cohorts and avoid a single judge quality score. |

The user approved these choices on 2026-09-27:

1. Generic file-based models/export/freeze/join/report modules using existing
   replay preparation and stores; no new SQLite tables or alternative scoring
   framework. JSONL drafts and immutable local bundles, not live labels committed
   to Git by default.
2. The 18-response selection policy, with coverage gaps stated explicitly, and
   conservative handling of already exposed cases. A fully blind primary cohort
   is not guaranteed for this user; choose whether that bounded exploratory pilot
   is acceptable or provide additional unseen compatible saved material first.
3. Strict freeze-before-join and opaque blind packet bindings, with separate
   historical-reconstruction and frozen-request verification cohorts. Never
   present exposed/reconstructed comparisons as blind verified agreement.
4. One human score plus derived threshold verdict, concise reason and optional
   qualitative dimensions/ambiguity; immutable corrections and optional separate
   manual issue-recognition review after ratings are frozen.
5. Equal-response MAE/signed difference/verdict agreement, separate integer
   call-level confusion matrix, full replay distributions and unchanged
   provisional_uncalibrated status. No correlation/significance/reliability claim,
   tuning or automatic status promotion.

Non-goals remain dashboard/annotation website, crowdsourcing, additional human
raters, rubric/threshold tuning, model selection/ranking, ensembles/second judge
provider, RAG-specific evaluation, release gates, statistical significance and
Sales Agent changes. No target re-execution or mutation of any historical run,
replay, expectation or source response is authorized.

## Historical planning validation record

Only this plan was created. Read-only offline inspection validated 41 currently
compatible semantic source attempts, both existing ReplayResults and their exact
source/rebuilt input matches, and the 18-selector proposal's distinct evidence
and multi-turn counts. Source/replay/structured SQLite checksums were unchanged.
No human annotation, packet, calibration result or implementation was created;
no target/judge call, paid API, commit or merge occurred. No implementation suite
was run for this documentation-only task. Final checks passed: git diff --check,
explicit untracked-plan whitespace/code-fence/required-section validation,
unchanged dataset Git diff, and unchanged checksums for all three databases.
Git status confirms this plan is the sole changed file.

## Approved amendments (2026-09-27)

The Sales Agent human rating contract declares anchors `[0.0, 0.3, 0.6, 0.8, 1.0]`.
Generic validation reads the contract, with continuous scales available to other
evaluators. No rubric or judge parser changes are authorized. The unchanged 0.7
threshold is not an additional human score.

MAE, signed differences and related metrics are descriptive distances on the
rubric's numeric score scale. They are not statistically calibrated prediction
errors; score intervals have no assumed universal quantitative meaning.

The rating contract explicitly versions human rating instructions and binds the
full rubric/version, score scale/anchors, threshold, evidence/projection and prompt
versions/settings, instructions/version and human packet/schema version. Changed
guidance creates a different contract fingerprint.

Previously exposed examples do not delay this exploratory pilot. Conservative
exposure labels remain, exposed comparisons are never called blind calibration,
and the primary genuinely blind cohort may be empty. This study provides
exploratory human–judge agreement evidence with status `provisional_uncalibrated`.

## Implementation and offline acceptance record (2026-09-27)

Milestones 1–4 are complete on `feat/human-judge-calibration`. Manual acceptance
remains **ready, not executed**. No actual human rating, review packet, frozen
annotation set or agreement result was created. No target/live judge call,
dataset/rubric/threshold change, historical artifact mutation, tuning, commit or
merge was performed. Tests create explicitly synthetic labels in temporary
folders only. Status remains `provisional_uncalibrated`.

### Files and final architecture

| File | Implemented responsibility |
| --- | --- |
| `src/harness/core/calibration.py` | Strict frozen contracts, private examples/manifests, blind packet/draft models, immutable human revisions, saved-judge adapters, verified joins, issue reviews and pure descriptive result summaries. |
| `src/harness/core/calibration_io.py` | Safe JSON/JSONL diagnostics, exclusive export/freeze/report bundles, raw/canonical hashes, receipt-last completeness, freeze-before-loader ordering, immutable corrections and report reload/recomputation. |
| `src/harness/reporting/calibration.py` | Separate typed blind packet and post-freeze analyst Markdown renderers; escaped inert evaluation content. |
| `examples/salesagent_human_calibration.py` | Fixed 18-item recipe, contract anchors/instructions version, conservative exposure, read-only source preparation/import, explicit export/freeze/analyze commands. |
| `tests/test_calibration.py` | 78 synthetic schema/identity/math/exposure/join/issue tests. |
| `tests/test_calibration_io.py` | 28 export/blinding/freeze/immutable-revision/persistence/report tests. |
| `tests/test_salesagent_human_calibration.py` | 9 synthetic recipe/dataset/isolation checks, including the complete 18-item flow. |
| `docs/human-judge-calibration.md` | Final schema, commands, sharing controls, interpretation and manual acceptance instructions. |
| `docs/adr/0005-human-judge-agreement.md` | Accepted decisions 1–5 and three amendments. |
| `docs/plans/human-judge-calibration.md` | Approval, amendments, living progress and this validation record. |

No existing implementation, target, scorer, store or dataset file changed.
`ReplayResult` and `PreparedReplay` remain unchanged. Preparation is reused only
as an offline identity/evidence boundary. `CalibrationResult` pins the private
manifest, exact frozen human revision, selected observations and optional manual
issue reviews; its summary is derived, never accepted as an editable truth.
Persisted result loading recomputes metrics and rendered report content.

`RatingContract` binds full rubric/version, anchors/scale, threshold,
projection/prompt/judgment versions and evidence settings, instructions/version,
packet/annotation schemas and dimension keys. Drafts remain null-score/empty-reason
until human-authored. Freeze supplies IDs, UTC timestamps, contract binding and
derived verdict only. Generic continuous contracts support exact-threshold PASS;
the Sales Agent contract rejects 0.7 and all other non-anchor human scores.

### Manifest, blinding, exposure and joins

The selection remains 14 pre-fix canonical cases + the predefined three post-fix
promotion responses + the exact instability response. It selects neither by
agreement nor numeric score. Source snapshots pin all selected source document
hashes; source identities cannot repeat, case IDs may repeat for different fixed
responses, and evidence-duplicate groups remain inspectable. Presentation order
uses a once-per-export random permutation and per-example random salted binding.
Known coverage gaps remain explicit; no human quality labels are inferred.

All 18 are conservatively `prior_results_seen` for this intended annotator.
Unknown or recognized exposure cannot become `not_seen` through optimistic draft
flags. Primary requires genuinely declared-unexposed plus saved-request-verified
input and may be empty with null metrics. Exposed results remain exploratory
human–judge agreement evidence, never blind calibration.

The synthetic full-flow test asserts preservation of every projected turn/fact
and the complete rubric while excluding sentinel raw/provider/private/deterministic
fields, judge scores/reasons/models, all selected run/case/replay IDs, source paths,
selection labels and published response/replay hashes from the reviewer files.
Adversarial prose is rendered inside escaped inert blocks. These controls do not
guarantee arbitrary natural-language content is nonsensitive.

Export/freeze do not accept a judge source. Corrupt/missing/edited receipts stop
`analyze_bundle` before its observation loader is called; the recipe additionally
bomb-tests database construction before receipt validation. Target constructors,
invocation, normal runner, HTTP/judge constructors and scorer execution methods
are bombed throughout the recipe test, including fixture setup. The fixtures are
direct normalized saved responses, requiring no target construction at all.

Source preparation checks frozen dataset selection/full hashes and original
case/input/attempt, response availability and recorded evaluator configuration.
Joining rebuilds the exact prepared snapshot, compares full provenance/evidence/
prompt/input/configuration, verifies saved replay actual-call hashes and rejects
changed contracts, copied identity claims, same-prose/different-evidence records,
wrong source attempts, duplicate observations and mixed requested evaluator configs.
Historical selected semantic scores survive unrelated aggregate errors. Missing
scores retain an explicit unknown-cause error. Historical requests remain labelled
reconstructed, not proof of saved original request bytes.

The two fixed replay IDs supply their five calls each; the remaining 16 items
supply one historical call apiece. The synthetic acceptance flow produces exactly
26 observations, proving original source scores are not double counted when a
replay is selected. Exposure/input-verification summaries stay separate.

### Metrics, errors, revisions and persistence

Tests cover signed and absolute distances, cancellation, equal-response MAE and
verdict agreement versus call-weighted rates, integer confusion counts, exact
score matches, thresholds, mixed/empty/all-error calls, informational SKIP,
missing human/judge data, inclusive range membership, single observations and
repeated crossing. The synthetic h=0.6 / [0.8,0.6,0.6,0.8,0.8] fixture gives mean
0.72, population stddev approximately 0.09798, MAE/signed difference 0.12, verdict
agreement 2/5 and matrix FAIL/FAIL=2, FAIL/PASS=3. These are synthetic test labels,
not actual human judgments. No zero score substitutes for an infrastructure error.

Distances describe the rubric's numeric scale, not calibrated prediction error
or universally meaningful intervals. No mean-threshold/majority verdict,
automatic issue recognition, statistical reliability estimate or status promotion
is produced. Optional human dimensions have explicit counts; issue relationships
remain unreviewed unless a separate manual post-freeze record binds an exact pair.

Freeze preserves raw draft bytes and canonical annotations, snapshots, hashes and
an exclusive receipt written last. Tests reject malformed/edited/incomplete
bundles, write failures, existing destinations and symlink aliases. New correction
IDs explicitly supersede the active version, retain all historical annotations,
pin the preceding receipt and preserve old frozen bytes/reports. Cycles, forks,
wrong-example bindings, stale versions and duplicate active ratings fail. Every
revision addition is conservatively post-disclosure and excluded from blind-primary
analysis. Report reload rejects edited aggregates and rendering mismatches.

### Validation results

All commands used `UV_CACHE_DIR=/private/tmp/ai-test-harness-uv-cache`,
`UV_OFFLINE=1`, and `uv run --frozen --extra salesagent --extra judge-openai`.

| Check | Result |
| --- | --- |
| New calibration tests | 115 passing (78 core + 28 IO + 9 recipe) |
| Complete focused matrix listed above | 291 passed |
| Complete pytest `-v` | 572 passed |
| Ruff `check .` | Passed |
| Scoped Ruff format | All 7 new Python files formatted |
| Global Ruff format | Only the same 3 pre-existing failures: `src/harness/targets/base.py`, `tests/test_callable_target.py`, `tests/test_dataset.py`; unchanged |
| mypy `src/ examples/` | Passed, 32 source files |
| Frozen dataset byte and canonical hash tests | Passed for baseline and semantic datasets |
| SQLite byte SHA-256 before/after | All three unchanged; values equal the earlier table |
| Dataset Git diff | Empty |
| `git diff --check` | Passed; new/untracked files additionally checked explicitly |

Frozen dataset verification:

| Dataset | Byte SHA-256 | Canonical dataset hash |
| --- | --- | --- |
| baseline | `f24ffe05b08d75848860f71ef726cf96dccb78e457e5757fb7144cd30db4a747` | `c1a73ef207f2cabe3292d743504f7249f4729825d785adff5b6bf14ad6a7b12b` |
| semantic | `3200acd541c6db9f3bb3301186f4213746e177c0c3048b4ad99434da590791a9` | `33654c3f4870efc67edd8e30a6ae0a82c17eb58c8c30cb323add5d0efe414849` |

### Final refinements and manual readiness

No architectural or scope deviation. Concrete CLI flags replace the illustrative
planning flags: export directly freezes the approved policy rather than requiring
a separately authored private selector file; subsequent commands consume that
frozen manifest. The broader pre-implementation candidate inventory stays in this
ExecPlan; exported manifests pin the selected source snapshots rather than copying
all excluded historical documents. Corrections are always conservatively labelled
post-disclosure, including when disclosure cannot be established. Actual missing
selected artifacts fail closed in the recipe; the generic API can explicitly
represent missing observations. These details are documented in the operator guide.

Manual export/rating acceptance is ready and deliberately pending. A human must
explicitly run export, personally supply the 18 ratings/reasons, freeze them and
then invoke saved-judge analysis. No collection artifact or human score has been
created automatically. The full synthetic workflow is plumbing evidence, not a
completed human study or judge calibration.

## Approved reporting and issue-review refinement (2026-09-27)

The user authorized this refinement on `feat/human-judge-calibration` after the
manual pilot was collected. Existing artifacts now contain 18 frozen human
annotations and 26 saved judge observations across 14 cases. This work reads
those existing artifacts; it creates no human ratings or issue classifications.
The previous implementation/manual-readiness record above is historical.

Boundaries: preserve frozen annotations, historical RunResults/ReplayResults,
datasets, rubric, threshold, observations, agreement functions and status.
`result.json` remains the complete canonical source of truth, byte-for-byte
unchanged for the current pilot. No target/judge calls or merge.

- [x] Inspect renderer, persistence validation, taxonomy and current artifacts;
  capture checksums of all collection/analysis files, datasets and databases.
- [x] Implement compact report plus complete analyst appendix; collapse empty
  optional dimension matrices only in presentation.
- [x] Add manual `human_only_issue` / `judge_only_issue`; preserve unreviewed
  defaults, frozen labels and unchanged numeric agreement calculations.
- [x] Add exact legacy report validation and an explicit Markdown-only refresh
  command that stages derived documents and never rewrites canonical JSON.
- [x] Add focused presentation/taxonomy/integrity/escaping/regression tests.
- [x] Refresh only current pilot Markdown, verify protected artifacts unchanged.
- [x] Run complete offline validation and record final counts/results below.

The concise report contains title/status, interpretation limits, six collection
counts plus missingness, exposure/verification limitations, headline metrics and
compact confusion counts, cohort rows, filtered disagreement rows, short findings
and an appendix/JSON reference. Stable E01-style labels link to full opaque
identities in the appendix. Exact matches do not crowd the disagreement table;
threshold crossing, errors and missing observations remain visible. All numbers
come from the existing unchanged `CalibrationResult.summary`.

The appendix retains complete per-response metrics/distributions and original
payload: human/judge reasons, observations/errors, optional collected dimensions,
nonadditive case families, contract/manifest, versions, hashes and provenance.
Empty optional matrices are collapsed to a not-collected note without changing
JSON. Human-authored evaluation text stays escaped and inert.

Taxonomy definitions are now in the operator guide. Recognition disagreement
requires manually supplied labels; severity disagreement requires `same_issue`
plus differing scores. Neither score equality, a perfect score nor keyword
matching can supply a relation. Every issue record remains post-freeze,
unblinded and bound to an exact immutable annotation/observation pair.

The reporting split requires a small persistence refinement: new bundles validate
both Markdown files, while original one-report bundles validate through the
unchanged legacy layout. `render --analysis <existing-directory>` validates
before staging either derived file; each replacement is atomic, while interrupted
multi-file publication remains detectable. It never loads a source database or
rewrites `result.json`. No architecture or scope deviation is intended.

### Refinement validation and delivery

Changed code: `src/harness/reporting/calibration.py`,
`src/harness/core/calibration_io.py`, `src/harness/core/calibration.py` (only the
additive issue-relation enum), `examples/salesagent_human_calibration.py`.
Changed tests: new `tests/test_calibration_reporting.py` and the presentation
assertions in `tests/test_calibration_io.py`. Existing calibration math tests
remain unchanged. Updated this plan, `docs/human-judge-calibration.md` and
`docs/adr/0005-human-judge-agreement.md`.

The explicitly invoked presentation refresh updated only the existing
`runs/calibration/salesagent-human-v1-analysis/report.md` and created its sibling
`analyst_appendix.md`. The concise report is 562 words, with three notable rows;
the appendix retains full detail. No issue review was created or inferred.

All 16 protected files captured before this refinement remain byte-identical:
collection/private/review artifacts, every frozen bundle file, canonical
`result.json`, both datasets and all three source/replay databases. The only
changed pre-existing artifact is derived `report.md`. Canonical result SHA-256
remains `c54b510b6b67ab319af67ccd232cd79199a0bad254043bc0a91629f6fe0d6984`.
Database/dataset SHA-256 values remain those recorded above; dataset canonical
hash assertions also pass in the offline suite.

| Validation | Result |
| --- | --- |
| New reporting/taxonomy tests | 30 passed |
| All calibration tests | 145 passed within the focused/full suites |
| Complete focused matrix, including replay/scoring/store/comparison | 321 passed |
| Complete offline pytest `-v` | 602 passed |
| Ruff `check .` | Passed |
| mypy `src/ examples/` | Passed, 32 source files |
| Scoped Ruff format | All 6 touched Python files pass |
| Global format | Same 3 pre-existing failures only: targets/base.py, test_callable_target.py, test_dataset.py |
| Dataset Git diff | Empty |
| Source/replay/structured database checksums | All unchanged |
| Canonical result and frozen/collection artifact checksums | All unchanged |
| `git diff --check` plus explicit new-file whitespace checks | Passed |

Coverage includes concise/full presentation separation, complete unchanged JSON
serialization, exact-match filtering in mixed reports, threshold crossing,
errors/missing observations, cancellation display, large repeat-count summaries,
uncollected/collected optional dimensions, all seven manual taxonomy values,
no score/keyword inference, same-issue severity, inert Markdown/HTML and excluded
operational fields, deterministic generation, legacy bundle validation, repeated
presentation refresh without source access, and corrupt/missing summary/report/
appendix rejection. Existing math tests pass unchanged.

Agreement functions and `result.json` schema/completeness/semantics are unchanged.
Taxonomy changes are additive manual labels only. No deviations from the request;
legacy validation and the explicit `render` command are necessary compatibility
support for splitting presentation on the existing completed pilot. No targets,
live judges, annotation regeneration, source mutation or merge occurred.
