# Numeric waterproof diagnostic corpus v1: independent review guide

Status: candidate-1; independent human review approved; frozen. These are
authored expected outcomes, not measured detector outputs. No diagnostic
implementation exists. The user approved the freeze; Milestone 2 remains unauthorized.

[Signed review](independent-review.md): Rebecca Williams, 11 October 2026 at
11:30 BST. All 32 decisions, policies, the 15-claim recall denominator and S06
limitation are approved. The reviewer declares independence from fixture authoring,
with involvement in overall project design and supporting analysis from ChatGPT.

## Files and separation

- `cases.jsonl`: 32 unique records; id, group, split and input. Input contains
  context, synthetic TargetResponse JSON and evaluator-owned authority manifest.
- `expected.jsonl`: one matching record per input, bound by canonical input hash;
  exact candidates/spans, normalization, resolution, evidence pointers, findings,
  errors, counts and provenance hashes. These are semantic report expectations.
- `manifest.json`: versions, candidate revision, counts, byte hashes and completed
  independent-review fields. `approved_files` binds the exact input/label hashes;
  `candidate_revision`, `reviewer`, `reviewed_at` and `decision` record the approval.
  `review_file` and `review_sha256` bind the unchanged signed review. The timestamp
  is the signed 11/10/2026 11:30 BST expressed as ISO 8601 with offset +01:00.
  Status `frozen` records the separately approved corpus freeze. The reviewed
  revision remains `candidate-1`; its exact inputs, labels and review are unchanged.
- `independent-review.md`: the unchanged human review declaration, all per-ID
  decisions and rationales, approved policies and acknowledged limitations.

These are not TestCases, Study v1 cases, replay results, human ratings or target
outputs. Do not move them into `datasets/salesagent/study-v1`, send them to a
target, or use Study v1 live outputs to revise them. All product identities,
source records, shopper requests and review identities in inputs are invented.
Authority `review.kind=synthetic_simulation` with `status=reviewed` is a simulated
condition under test, NOT a claim of independent corpus review. A real-context
diagnostic must reject simulated authority review.

## Inventory and exact expectations

| ID | Scenario | Expected finding/disposition |
| --- | --- | --- |
| S01 | Explicit SYN-001, 20000 mm | supported, 20000 mm |
| S02 | Thousands separator, 20,000 mm | supported, 20000 mm |
| S03 | Equivalent decimal 2000.0 cm | supported, 20000 mm |
| S04 | Equivalent 20 m | supported, 20000 mm |
| S05 | Unicode prefix, case/whitespace name, millimetres | supported, unique_exact_name; prefix excluded from span |
| S06 | Two turns, reference valid across both, later claim | supported at turn 1 only |
| V01 | 25,000 mm against 20000 mm | contradicted |
| V02 | 25 m against 20000 mm | contradicted, 25000 mm |
| V03 | SYN-002 given SYN-001's number | contradicted against SYN-002's 10000 mm |
| V04 | Exact numeric claim, reviewed complete not_supplied | unsupported, not proven false |
| V05 | Same absence with exact product name | unsupported |
| V06 | Earlier unsupported claim; later reference and correction | unsupported at turn 0; future record excluded; no erasure |
| A01 | It has a numeric rating | indeterminate: unresolved_subject |
| A02 | Might have a numeric rating | indeterminate: hedged_assertion |
| A03 | 15,000–20,000 mm range | indeterminate: range_not_supported; no scalar |
| A04 | 20k mm | indeterminate: shorthand_not_supported; no scalar |
| A05 | No property records, incomplete authority | indeterminate: authority_incomplete |
| A06 | Conflicting reviewed values | indeterminate: conflicting_authority |
| N01 | Numeric question | excluded: question |
| N02 | Cannot confirm a rating | excluded: negation |
| N03 | Shopper quotation without endorsement | excluded: unendorsed_quotation |
| N04 | If a product had a rating | excluded: hypothetical |
| N05 | Rainfall amount | excluded: different_property |
| N06 | Garment dimension | excluded: different_property |
| E01 | Missing sole turn output | error: missing_turn_output, turn scope |
| E02 | Turn starts at index 1 | error: invalid_turn_sequence, response scope |
| E03 | Final output differs from final turn | error: final_output_mismatch, response scope |
| E04 | Unknown evidence version | error: unsupported_evidence_version, response scope |
| E05 | Authority numeric string NaN, hashes otherwise valid | error: invalid_authority_value, authority scope |
| E06 | Corrupt source checksum | error: source_hash_mismatch, authority scope |
| E07 | Unresolvable local evidence pointer | error: invalid_evidence_reference, authority scope |
| E08 | Boolean completeness instead of enum | error: invalid_completeness, authority scope |

The JSON labels, not this summary table, contain the exact offsets, values,
references and error paths. All error fixtures have no candidate findings.
S06 includes a fresh turn-1 `get_product`; it does not isolate earlier-only
tool evidence reuse. Its supported turn-1 label remains unchanged.
E01 has no valid remaining turn, hence error rather than partial. E05 recomputes
the content checksum to isolate numeric semantics from hash validation. E06 has
an inconsistent review hash as a secondary consequence; source hash failure has
precedence. V06 deliberately includes a later fact that cannot repair turn 0.

S/V/A/N 01–04 are development; 05–06 acceptance: 16/8 text fixtures. E01–E08 are
acceptance: eight error fixtures. Both text splits and labels are visible to the
implementer. Never call this a blinded holdout. Counts are fixture inventory,
not observed precision or accuracy.

## How the independent reviewer should assess each record

Read input and expected label together, using the
[contract](../../../../docs/salesagent-grounding-diagnostics-v1.md). Do not run a
detector and then adjust labels to its output. A reviewer should be independent
of the fixture/detector author; author self-checks are structural verification only.

For every fixture, record agreement/disagreement and rationale for:

1. The original assistant text, intended claim or exclusion, and supported grammar.
2. Every slot and full span: Unicode code-point slicing must reproduce exact text.
3. Subject ID/method and subject evidence references, without nearest-product or
   pronoun guessing. V03 must compare against SYN-002, not SYN-001.
4. Decimal conversion and its limits. `high` provides no numeric information.
5. Source set/revisions/hashes, simulated review, completeness and applicability.
6. Every comparison pointer and finding. Distinguish absent normalized fields,
   incomplete references, complete not_supplied, and conflicting actual values.
7. Time: no future observation/reference may support an earlier claim; later
   correction does not delete an earlier finding.
8. Error code, path, scope, precedence and suppression of unsupported findings.
9. `agent_grounding=not_assessed`: authoritative agreement cannot establish agent
   receipt/use of a numeric fact.

Maintain a review record with reviewer identity/date, contract version, candidate
revision, cases/labels hashes, per-ID decisions and unresolved objections. All
32 IDs need explicit disposition. Approval must bind both files' exact hashes.
If any label is disputed, resolve it against the contract or make an explicitly
reviewed contract/corpus revision. Preserve the previous review record; never
silently change labels to make an implementation pass. Do not fill review fields
with invented identities or mark review complete after automated checks.

## Metrics and limits

The 15 exact affirmative claims eligible for detection recall are S01–S06,
V01–V06, A01, A05, A06. Count A01 as a detected numeric assertion even though its
subject cannot be resolved. A02 is uncertain; A03/A04 test recognized exclusions
from scalar grammar. Six N fixtures test false positives. Publish separate raw
counts for supported grammar, challenges, exclusions and errors.

One-to-one detection matching uses turn/family/numeric anchor span; duplicate
detections are false positives. Report precision, recall, FP/FN, exact extraction
agreement, indeterminate rate among exact affirmative claims, candidate abstention
and comparator correctness under gold extraction separately. All denominators and
N/A cases must be visible. Report acceptance and development separately and state
their tiny sizes. Detailed definitions are in the contract.

All expected outcomes must pass before release, but perfect fixture conformance
would not establish broad natural-language detection accuracy, independence of
templates, statistical generalization, or real-world grounding. Unknown phrasing
may be missed with no abstention. Real authority review is not tested by a
simulated reviewer field. A future independent language challenge set would need
separate approval and must not be sourced from future Study v1 outputs.

## Gate before implementation

Independent human review is recorded for candidate-1 and its exact file hashes.
The signed review approves the narrow grammar, complete-reference absence policy
and visible acceptance set for bounded contract conformance. Explicit Milestone 2
authorization is still required. Corpus freeze and the commit of these reviewed
artifacts are approved; push and merge remain unauthorized.
Any change must retain reference agreement versus agent grounding as separate
concepts; changes to corpus inputs or labels require a new revision and review.
