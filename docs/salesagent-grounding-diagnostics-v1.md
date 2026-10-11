# Sales Agent numeric waterproof diagnostics v1

Status: Milestone 1 specification; architecture approved in principle. Corpus
candidate-1 independent human review approved; corpus frozen with user approval. No
detector, scorer, CLI, or live evaluation exists. The signed review is bound in
the corpus manifest; Milestone 2 remains unauthorized.
See the [ExecPlan](plans/salesagent-waterproof-grounding-diagnostics.md),
[ADR 0008](adr/0008-numeric-waterproof-diagnostics.md), and
[corpus review guide](../tests/fixtures/salesagent_grounding/v1/README.md).

## 1. Evaluated property and isolation

V1 evaluates agreement of explicit numeric waterproof/hydrostatic-head claims
with an explicitly reviewed, version-bound authoritative reference set valid
for the evaluated turn. `supported` means reference-supported, not demonstrated
physical product performance or universal factual truth. `unsupported` means
the declared complete reference set supplies no support, not false in the world.

This differs from grounding in information available to the agent when answering.
The current `salesagent-evidence-v2` product projection carries categorical
`waterproof_rating`, but drops unknown fields and exposes no numeric rating.
Consequently v1 sets `agent_grounding: not_assessed` on every candidate/finding.
An observed product lookup proves neither receipt of a numeric fact nor use of
that fact. An evaluator reference can support an answer even if the visible
agent trajectory contains no such fact. Conversely a reference contradiction
does not establish that the agent ignored evidence it received. Do not describe
these diagnostics as a measured agent-grounding rate.

No Score, pass/fail gate, quality aggregate, Study v1 annotation, or runner
integration is introduced. Core models, adapter projections, case fingerprints,
semantic rubrics/thresholds, historical results, and Study v1 files remain intact.
Inputs contain no golden case reference or expected outcome. No target/client,
judge, target-internal import, network source fetch, or LLM extraction is allowed.

## 2. Proportionate versioning

One `salesagent-waterproof-diagnostic-v1` contract covers projection, grammar,
normalization, reference policy, errors, and report representation. Record exact
safe configuration/content fingerprints and the implementing harness revision
when implementation exists. Do not create independently dispatched subcontracts.
A change to observable interpretation or representation requires a diagnostic
contract revision; documentation-only clarification does not.

`salesagent-waterproof-corpus-v1` versions the separate corpus envelope. Its
`revision: candidate-1`, file hashes, and explicit independent-review state track
authoring. This exact reviewed revision is now frozen with user approval. Any
input/label change requires a new revision, refreshed hashes and another review.
Approval binds the exact input and label hashes, not just the version string.

Canonical hashing reuses `harness.core.fingerprints.canonical_json/fingerprint`:
sorted keys, compact separators, UTF-8, preserved Unicode, finite JSON only.
File checksums are SHA-256 of exact UTF-8 file bytes, including final newlines.

## 3. Planned public interface and evidence projection

Future pack-only entry point (not implemented in Milestone 1):

```text
diagnose_numeric_waterproof_claims(
    response: TargetResponse,
    *,
    context: GroundingDiagnosticContext,
    authority: GroundingEvidenceManifest | None = None,
) -> GroundingDiagnosticReport
```

Context contains `source_id`, nonnegative `attempt_index`, and an explicit
`synthetic` flag, default false. It may include an expected source artifact hash
for verification. Labels are opaque identity bindings, never extraction hints.
No TestCase, study selector, target, judge, scorer or expected label is accepted.
Projection, detection, resolution, normalization, and comparison stay internal
pure functions in one Sales Agent pack module unless size justifies splitting.

Require metadata evidence version `salesagent-evidence-v2` and a nonempty ordered
`structured.turns` list. Turn `index` is a contiguous zero-based integer, never a
Boolean. Turn `output` is a string; an empty string is valid and has no candidate.
Top-level `output` must match the final turn text exactly. Project successful
`get_product` / `search_products` identities from each turn's trajectory and
record JSON-pointer provenance. Failed calls cannot supply authoritative facts.
Validate fields actually consumed, not unrelated recommendation/constraint fields.
Do not infer absent turn boundaries from the flattened trajectory.

Each turn is evaluated independently against references valid at that turn.
Earlier observations may supply identity in later turns of this same response;
never across attempts/responses. Later observations cannot resolve an earlier
subject. References carry inclusive `valid_turns.first/last`; only applicable
records may support or contradict a claim. A reviewed reference can be attached
after capture only if its immutable source revision and applicability to the
captured turn are explicitly established, not inferred from a current catalogue.
No automatic latest-wins rule resolves overlapping conflicting references.

The complete-turn HTTP contract orders tool results before the final assistant
message. V1 does not claim streaming/token timing. Later corrections remain
separate text: they never remove an earlier finding. Never treat recommendations,
resolved constraints, user assertions, or assistant prose as independent authority.

## 4. Candidate grammar and spans

Supported affirmative core: an isolated declarative clause with a subject and
`has a hydrostatic-head rating of VALUE UNIT` or
`has a waterproof rating of VALUE UNIT`. English case-insensitive matching and
whitespace separation are allowed. A leading decorative symbol is outside the
claim span. Corpus S05 specifies Unicode offsets and name whitespace handling.
This is a deliberately bounded grammar, not a promise to parse all English
claims expressing the same fact. Detection of an explicit numeric claim and
resolution of its subject are separate; `It` can yield an unresolved candidate.

Candidate discovery also retains recognizable numeric rating mentions in the
listed question, negation, unendorsed quotation, hypothetical, hedge, range and
shorthand challenge forms. Dimension/rainfall controls with a number and length
unit are retained as excluded candidates. The corpus specifies exact required
forms; unsupported syntax beyond it is a coverage limitation, not automatically
a successfully detected abstention. V1 makes no claim about implicit meanings.

`span` covers the complete candidate clause/sentence, including terminal
punctuation, excluding leading decorative symbols. Slot spans record exact
subject/property/value/unit substrings or null when absent. All offsets are
half-open Unicode code-point indices into original turn output, not UTF-8 bytes,
graphemes, or normalized text. `text[start:end]` must equal recorded span text.
Retain turn text SHA-256. Never edit source text to simplify matching.

Candidate fields are normative in `expected.jsonl`: id, turn_index, span,
property_span, subject_span, value_span, unit_span, family, disposition,
extraction, subject, normalized, finding, reason, evidence_refs, agent_grounding.
IDs are assigned in turn/span order. Disposition is `affirmative`, `uncertain`,
or `excluded`; extraction is `exact`, `uncertain`, or `unsupported_syntax`.
Excluded means no affirmative claim; it has no normalized claim/finding. An
uncertain hedge has no decisive assertion even if its numeric tokens normalize.
Recognition of a range/shorthand retains a candidate, not a fabricated scalar.

## 5. Subject and numeric normalization

Resolve explicit IDs present in eligible product identities or reviewed source
subject records. Resolve exact unique product names after case-folding and
collapsing whitespace. Record `explicit_id` or `unique_exact_name` and the ID.
All candidate identity provenance must be retained in the runtime report even
when the test oracle focuses on the comparison evidence reference.

Pronouns, unnamed groups, fuzzy names, unknown IDs, duplicate-name matches,
`the first one`, and complex multi-product attribution are unresolved. Never
resolve a pronoun solely because one recommendation is present. No resolution
can depend on case IDs or labels. Excluded candidates use `not_attempted`.

For exact affirmative syntax, accept positive base-10 integers/decimals and
unambiguous thousands grouping (`20,000`, `2,000.5`); reject Boolean/nonfinite
authority values. Use Decimal, never float or rounding. Decimal point is `.`;
grouped integer digits have groups of exactly three after the first group.
Canonical millimetre strings have no grouping, exponent, leading plus/zeros,
or unnecessary trailing fractional zeros. Units are case-insensitive:

| Unit vocabulary | Multiply by to obtain millimetres |
| --- | ---: |
| mm, millimetre(s), millimeter(s) | 1 |
| cm, centimetre(s), centimeter(s) | 10 |
| m, metre(s), meter(s) | 1000 |

Explicit numeric waterproof ratings in these length units normalize to property
`hydrostatic_head_mm`; this interpretation is scoped to the declared grammar.
Do not convert `high`, `moderate`, `water-resistant`, or any categorical rating.
Ranges, inequalities, approximations, `20k`, number words, pressure units,
rainfall rates, missing/ambiguous units and locale-dependent numerals are outside
scalar comparison. Known patterns become indeterminate; unseen paraphrases may
be missed. Zero/negative ratings in response prose are unsupported numeric syntax,
not automatically a response-schema error or proof of falsehood.

## 6. Reviewed authority manifest

The corpus's input manifests are exact examples of the planned JSON contract.
They are evaluator-owned; they never enter the application under test.

| Field | Contract |
| --- | --- |
| contract_version | The single diagnostic contract identifier |
| source_set_id | Reviewed authority boundary identifier |
| binding | Exact context source_id and attempt_index |
| sources | Unique id, nonblank revision, inclusive valid_turns, bounded content, content sha256 |
| source content | subjects (product_id/name), facts (product_id/property/status/value_mm) |
| records | Unique id, local fact_ref, coverage, inclusive valid_turns |
| review | status, kind, reviewer_id, reviewed_source_hashes, complete_source_set |

`fact_ref` is a local JSON pointer into this manifest, never a URL/path to fetch.
Only the documented subject/fact fields are accepted in source content; no raw
provider payload, hidden prompt, authorization data, or arbitrary diagnostics.
Each source checksum binds canonical `content`; review hashes must match sources
exactly. Source-set identity/revisions and review declarations bind completeness
and authority, not just a claim's numerical value. Hashes prove internal integrity,
not real authority or deployment identity. Real use requires human-reviewed
source identity/revision and applicability; never infer them from trace labels.

Facts have status `value` with a positive canonical numeric value_mm, or
`not_supplied` with null value_mm. No absent key is a fact of absence. Records
have coverage `complete` or `open`. Record validity must be contained in its source validity. Subject identity from
a source is eligible only within that source interval; future subject records
cannot resolve earlier claims. An explicit not_supplied record can justify
unsupported only when the reviewed source set is complete, all applicable
references agree on absence, and no applicable source has a value. Incompatible
values or value/absence disagreement yield conflicting_authority. Merely having
a product record does not establish property completeness.

Authority may be null or have missing property records: this is permissible
incompleteness. Open, unreviewed, temporally inapplicable, or unbound evidence
cannot justify unsupported; yield indeterminate with the relevant reason.
An explicitly supplied binding that mismatches context, corrupt content/hash,
unresolvable fact_ref, invalid types or unsupported manifest version is an
evaluation error, not honest incompleteness. Valid authority facts may support
or contradict without an exhaustive source set, provided no applicable reviewed
reference conflicts; completeness is specifically necessary to assert absence.

Synthetic fixtures set context.synthetic=true and review.kind=synthetic_simulation.
Their simulated reviewed status exercises comparison policy; it is NOT evidence
that a human reviewed the corpus. Real contexts must reject simulated reviews.
The corpus manifest's independent_review remains null/pending until real review.

## 7. Decision policy and evidence errors

Validate response-level structure and supplied manifest integrity before
comparison. Candidate uncertainty precedes factual comparison; a clear number
does not repair an unclear assertion or subject. Eligible evidence refers to
the same subject/property and applicable turn interval.

| Finding | Condition |
| --- | --- |
| supported | Exact affirmative claim, resolved subject, equal eligible numeric reference |
| contradicted | Same prerequisites, unequal numeric reference, no conflicting authority |
| unsupported | Same extraction/resolution prerequisites, explicitly reviewed complete absence |
| indeterminate | Extraction, subject, reference coverage/applicability or authority unresolved |

Non-assertions have no finding. `no_in_scope_claim_detected` is represented by
turn inventory/counts and is never a quality pass. The reason-code vocabulary
used by corpus labels is normative for the included examples. Further reviewed
boundary tests must add explicit reason labels, never silently collapse states.

Execution status is complete, partial, or error, separate from all findings.
Complete can include indeterminate/excluded candidates. Partial preserves
unaffected turns when one turn cannot be projected. Error means a fatal envelope
or manifest failure, or no processable turn. Empty valid assistant text is
complete, not an execution failure. A missing turn output suppresses secondary
final-output-mismatch diagnostics; response structure/version then manifest
integrity then field semantics then turn processing define error precedence.
Report independent turn errors in turn order. Do not catch programming errors
and fabricate successful empty reports.

| Corpus error | Scope | Required behavior |
| --- | --- | --- |
| missing_turn_output | turn | Skip affected turn; preserve others; sole turn gives error |
| invalid_turn_sequence | response | Error; no findings |
| final_output_mismatch | response | Error; no findings |
| unsupported_evidence_version | response | Error; no findings |
| invalid_authority_value | authority | Error; no findings |
| source_hash_mismatch | authority | Error; no findings |
| invalid_evidence_reference | authority | Error; no findings |
| invalid_completeness | authority | Error; no findings |

Errors contain safe code, JSON pointer, scope, and optional turn_index. Do not
persist exception messages containing raw evidence. Invalid caller configuration
raises a typed configuration error; valid diagnostic inputs containing malformed
evaluation evidence produce a report with errors. These are not runner ERRORs:
the diagnostic does not invoke or alter the runner or any saved run.

## 8. Report and persistence boundary

Future report includes contract version, safe configuration fingerprint, harness
revision when supplied, context bindings, normalized response/projection/authority
fingerprints, execution status, candidates/findings, errors, and coverage counts.
Retain original source text/hash and slot spans, resolved subject/provenance,
normalized values, reason codes, and comparison evidence JSON pointers. Reference
source IDs/revisions/hashes are available through the bound authority manifest.
Use the term reference agreement, never factual accuracy or agent grounding.

Counts: candidates, affirmative_claims (including recognized unsupported syntax),
supported, contradicted, unsupported, indeterminate, excluded, errors. Distinguish
these inventory counts from the narrower metric denominators below. Non-detected
claims cannot be counted from unlabeled responses. Report declared grammar and
exclusions, not a guessed percentage of language understood. No single quality
number, Score, PASS/FAIL, or certification field exists.

Canonical report body excludes timestamps/random IDs. Identical validated inputs
and configuration produce identical body hashes; no source mutation or cross-call
state. Persist only by an explicitly invoked future consumer. Milestone 1 writes
no report generator or persistence integration. The fixture oracle is the exact
expected semantic projection of a future report, not an invented historical run.

## 9. Evaluation of the evaluator

The separate candidate corpus has 24 synthetic text fixtures (six supported,
six violations, six indeterminate, six non-claims) and eight isolated error
fixtures. Text splits are 16 development and eight acceptance (four/two per
group). All error fixtures are acceptance. Both splits and their labels are
visible; this is not a blinded holdout. No deployed or Study v1 output is used.
No performance result can be reported before a detector exists and is measured.

Gold labels are authored expected behavior, not detector outputs. Independent
review must approve exact text, spans, assertion form, subject method/ID,
normalization, temporal eligibility, evidence references, finding/reason and
error classification before implementation. Review disagreement remains pending,
not averaged or decided by implementation convenience.

One-to-one detection matching uses turn, property family and exact numeric anchor
span. Count duplicates as false positives. Subject/value/full-span correctness
are separate measurements so a correctly located but misinterpreted claim is
not hidden by detection recall. Publish raw numerators/denominators by split.

| Metric | Definition and denominator |
| --- | --- |
| Precision | Matched eligible exact affirmative claims / emitted exact affirmative claims; unmatched/duplicate detections are FP |
| Recall | Matched eligible exact affirmative claims / gold eligible exact affirmative claims; missed ones are FN |
| Challenge detection | Inventory of range/shorthand/hedge recognition and exclusions; separate from supported-grammar recall |
| Extraction correctness | Gold agreement on value/unit, subject and spans for matched claims; errors remain visible |
| Indeterminate rate | Indeterminate among exact affirmative claims / all exact affirmative claims |
| Candidate abstention | Uncertain or unsupported-syntax or unresolved candidates / all candidates (union, no double counting) |
| Comparison correctness | Exact gold finding/reason/reference agreement using gold extracted candidates, independent of detector errors |
| End-to-end agreement | Entire expected semantic projection matches for each fixture; report error fixtures separately |

Eligible exact affirmative gold cases are S01–S06, V01–V06, A01, A05, A06:
15 claims. A01's subject ambiguity does not remove its clearly detected numeric
assertion from detection recall. A02 is an uncertain hedge, A03–A04 unsupported
numeric syntax, N01–N06 non-claims. End-to-end acceptance still requires all of
these controls; exclusions must not conceal their failures. Grammar expansion
requires revised denominators/contracts, not retrospective relabeling to improve
metrics. Empty denominators are N/A. Do not infer broad accuracy or confidence
from this small, deliberately selected, partly templated corpus.

Before release, every independently approved fixture must match exactly. M2 must
also verify missing/null optional authority, open/unreviewed evidence, partial
turn errors, no-state leakage, source immutability, invalid caller configuration,
duplicate names, and serialization/version drift with offline tests. These are
engineering boundary tests, not extra evidence of natural-language coverage;
new language examples require reviewed corpus amendments before tuning.

## 10. Known limits and approval boundary

No warranty/origin, forecast, preference inference, general product factuality,
multilingual extraction, pressure conversion, pronoun resolution, streaming,
external source discovery, or scientific verification. Unknown paraphrases can
be false negatives without generating an abstention. Reviewed reference absence
is conditional on an explicitly justified authority boundary. Corpus manifests
simulate that justification; real-source operation remains a separate review.

Milestone 1 authoring completion alone did not establish independent approval.
The subsequent signed candidate-1 review is now recorded in the corpus manifest;
the user has approved the corpus freeze and reviewed artifact commit. Milestones
2/3, source implementation, further commits, publishing and live evaluation require
separate authorization. See the ExecPlan
for workspace protection, verification baseline, and review gates.
