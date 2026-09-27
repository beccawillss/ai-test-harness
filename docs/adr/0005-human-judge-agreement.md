# ADR 0005: Frozen human–judge agreement evidence

Status: accepted for Milestones 1–4, 2026-09-27.

Saved judge replay can reveal score variation, but does not measure agreement
with independently recorded human judgments. Historical scores also lack saved
request bytes. We need an auditable offline collection boundary without changing
target execution, existing result models, historical databases or evaluator rules.

1. Use provider-neutral frozen models and immutable JSON/JSONL file bundles.
   Reuse `PreparedReplay`, canonical fingerprints, read-only stores and replay
   variance calculations. Keep Sales Agent selection/configuration in its recipe.
   Add no SQLite tables, target execution interface or alternative judge engine.
2. Accept the bounded 18-response exploratory policy in the ExecPlan. Preserve
   conservative prior exposure (all 18 prior-results-seen for the intended
   annotator); allow an empty genuinely blind primary cohort. Coverage gaps are
   disclosed, not filled with fabricated examples or judge-selected labels.
3. Project a reviewer-only packet with full evidence/rubric and opaque salted
   bindings. Freeze human-authored ratings before opening selected judge sources.
   Verify source/dataset/response/evidence/prompt/configuration identities. Keep
   actual saved replay request verification separate from historical reconstruction.
4. Bind rubric, score scale/anchors, threshold, projection/prompt/settings,
   human instructions/version and packet/schema versions into a rating contract.
   Sales Agent human scores use only 0.0/0.3/0.6/0.8/1.0; threshold stays 0.7.
   Generic contracts can declare continuous scales. Scores/reasons are never
   generated or prefilled. Corrections create fresh IDs/revisions and explicit
   supersedes chains; revisions are conservatively post-disclosure. Optional
   manual issue review is separate unblinded interpretation.
5. Use equal-response descriptive numeric distances and verdict agreement,
   separate call-weighted integer confusion counts, and complete ordered replay
   distributions/errors. MAE is not calibrated prediction error and rubric
   intervals have no assumed universal quantitative meaning. Status remains
   `provisional_uncalibrated`; there is no tuning or statistical reliability claim.

Consequences: file editing is sufficient for this small pilot, with exclusive
outputs and checksum validation rather than a new annotation service. The human
renderer cannot consume full stored results. Source loading for preparation can
inspect analyst metadata; selected judge import/reporting is behind receipt
validation. Existing allowlists cannot make arbitrary evaluation prose safe to
publish. Hashes do not establish human authorship, and anonymity does not erase
prior disclosure. No manual collection is run by implementation or pytest.

See [operator instructions](../human-judge-calibration.md) and the
[ExecPlan](../plans/human-judge-calibration.md) for the selection, validation matrix
and separately invoked acceptance steps.

## Reporting refinement (2026-09-27)

Keep the canonical result/schema and agreement calculations unchanged. Split the
human presentation into a concise `report.md` and full `analyst_appendix.md`;
collapse uncollected optional matrices only in Markdown. Verify both derived
files on reload and retain exact legacy-render validation for existing bundles.
An explicit presentation-only refresh replaces derived Markdown without rewriting
JSON, opening judge/target sources or freezing annotations again.

Extend the existing manual issue-review relation enum with `human_only_issue`
and `judge_only_issue`. This is an additive vocabulary extension, not automated
annotation or a new agreement metric. Existing records retain their meaning and
schema version. Only manual issue labels support recognition comparisons;
`same_issue` plus unequal scores can describe severity difference. Defaults stay
unreviewed and frozen human labels stay immutable.
