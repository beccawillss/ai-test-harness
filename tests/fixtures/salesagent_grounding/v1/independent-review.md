# Independent review - Sales Agent numeric waterproof diagnostic corpus v1

## 1. Review identity and scope

| Field | Value |
|---|---|
| Corpus | Numeric waterproof diagnostic corpus v1 |
| Contract version | `salesagent-waterproof-diagnostic-v1` |
| Candidate revision | `candidate-1` |
| Corpus schema | `salesagent-waterproof-corpus-v1` |
| Review type | Independent human review of synthetic case inputs, expected labels, policies and limitations |
| Prepared on | 2026-10-11 (assisted review draft) |
| Human reviewer | Rebecca Williams |
| Human review date (UTC or local with timezone) | 11/10/2026 11:30 BST |
| Independence from fixture/detector author | I reviewed the expected outcomes against the agreed evaluation specification before detector implementation, with supporting analysis from ChatGPT. I was involved in defining the evaluation requirements and policy, so this review is independent of fixture authoring but not independent of overall project design. |
| Final human decision | APPROVED |

## 2. Immutable corpus identity / integrity

| File | SHA-256 of exact bytes | Verification |
|---|---|---|
| `cases.jsonl` | `1bfb96ec6a381ed313db86957e03843cdf7a020363793e9bb7bd04d75a19f5ce` | Matches candidate-1 manifest in supplied materials |
| `expected.jsonl` | `8682d235f38e90ab5ab78a79ba0d7c97c28a3ddc5d27e592dc52753dbc67e962` | Matches candidate-1 manifest in supplied materials |

## 3. Evaluation policy decisions

| Topic | Proposed decision for reviewer confirmation | Reason / boundary |
|---|---|---|
| Purpose | Approve | This diagnostic checks agreement with separately reviewed reference information. `agent_grounding=not_assessed`: agreement does not show the agent actually saw or used the numeric facts. |
| Narrow language scope | Approve for v1 | Detect explicit English numeric waterproof/hydrostatic-head assertions within a documented grammar. Unrecognized paraphrases may be missed without an abstention. |
| `unsupported` semantics | Approve | Use only when version-bound, reviewed complete reference evidence explicitly says `not_supplied`. This is lack of support *within that source scope*, not a proof of falsehood. Missing data or incomplete authority yields `indeterminate`. |
| Evidence and time | Approve | Compare the stated product, valid source revision, and evidence eligible at each turn. Later facts or corrections do not retroactively justify earlier claims. |
| Synthetic acceptance evidence | Approve for contract conformance only | 24 small visible text fixtures and 8 error fixtures demonstrate intended behaviour, not blind generalisation or production precision. |
| Error handling | Approve | Malformed response/source/version/pointer/completeness data is an execution error, not a quality failure. |
| Metric policy | Approve with scope statement | Exact-grammar recall denominator is 15: S01–S06 (6) + V01–V06 (6) + A01/A05/A06 (3). A03/A04 are affirmative *unsupported-syntax challenges* and reported separately; A02 is hedged. Exclusions/errors must also be separate. |

## 4. Individual record dispositions

| ID | Exact expected outcome | Proposed per-record decision | Rationale |
|---|---|---|---|
| S01 | `supported` | Approve | Explicit SYN-001 20,000 mm assertion agrees with its reviewed synthetic numeric record. |
| S02 | `supported` | Approve | Comma-grouped 20,000 mm normalizes to the same authoritative value. |
| S03 | `supported` | Approve | 2,000.0 cm converts exactly to 20,000 mm. |
| S04 | `supported` | Approve | 20 m converts exactly to 20,000 mm; no categorical inference is involved. |
| S05 | `supported` | Approve| Unique case/whitespace-normalized product name resolves SYN-001; Unicode prefix is correctly outside the claim span. |
| S06 | `supported (turn 1)` | Approve | Turn 0 has no claim; turn 1 asserts 20,000 mm with authority valid through turn 1. Caveat: a new lookup occurs on turn 1, so this does not isolate earlier-only tool evidence. |
| V01 | `contradicted` | Approve | The claimed 25,000 mm conflicts with the reviewed SYN-001 value of 20,000 mm. |
| V02 | `contradicted` | Approve | 25 m is exactly 25,000 mm, which differs from 20,000 mm. |
| V03 | `contradicted` | Approve | Claim concerns SYN-002; its authority record is 10,000 mm, even though SYN-001 is 20,000 mm. Do not substitute the tool-retrieved product. |
| V04 | `unsupported` | Approve | SYN-001 has an explicitly complete, reviewed not_supplied numeric rating; this is absence of support under policy, not proof of falsity. |
| V05 | `unsupported` | Approve | Rain Shell A uniquely resolves SYN-001 and the complete reviewed source explicitly lacks a numeric rating. |
| V06 | `unsupported (turn 0)` | Approve | Later numeric fact and correction on turn 1 cannot justify/erase the unsupported claim made on turn 0; no new numeric assertion in correction. |
| A01 | `indeterminate` | Approve | The numeric assertion is recognizable, but pronoun It cannot be resolved under the deliberately narrow subject grammar. |
| A02 | `indeterminate` | Approve | Might have is hedged, not a decisive factual assertion; abstention is appropriate. |
| A03 | `indeterminate` | Approve | A range is an assertion but cannot normalize to one scalar under v1; preserve candidate as unsupported syntax. |
| A04 | `indeterminate` | Approve | 20k is explicitly outside the v1 supported grammar; keep the candidate visible and do not interpret it as exact scalar. |
| A05 | `indeterminate` | Approve | No numeric property record and incomplete reference scope; absence is not proof of unsupported claim. |
| A06 | `indeterminate` | Approve | Two simultaneously valid reviewed sources give 20,000 and 25,000 mm; without precedence the authority conflicts. |
| N01 | `excluded` | Approve | Question asks about a numeric rating but does not assert one. |
| N02 | `excluded` | Approve | Cannot confirm expresses lack of certainty, not a positive product-rating assertion. |
| N03 | `excluded` | Approve | Quoted shopper statement is attribution without assistant endorsement. |
| N04 | `excluded` | Approve | Conditional hypothetical does not assert that the product actually possesses the rating. |
| N05 | `excluded` | Approve | 20 mm concerns rainfall, not a garment waterproof/hydrostatic-head property; separate weather reliability risk remains out of scope. |
| N06 | `excluded` | Approve | 20 mm concerns a hem length, not a waterproof rating. |
| E01 | `error: missing_turn_output` | Approve | Only turn lacks required output; turn-local missing-output error with no completed findings is appropriate. |
| E02 | `error: invalid_turn_sequence` | Approve | Sole turn index begins at 1 instead of 0; invalid response-level sequence. |
| E03 | `error: final_output_mismatch` | Approve | Final response output differs from the last turn output; fail evidence validation before claims. |
| E04 | `error: unsupported_evidence_version` | Approve | Unsupported normalization schema requires evaluation error, not factual FAIL. |
| E05 | `error: invalid_authority_value` | Approve | NaN is not a finite numeric authority value; source hash is recomputed, isolating the semantic validation failure. |
| E06 | `error: source_hash_mismatch` | Approve | Source content hash is intentionally corrupt; source-hash error correctly takes precedence over secondary reviewer-hash inconsistency. |
| E07 | `error: invalid_evidence_reference` | Approve | fact_ref points to non-existent source 99; no factual comparison is permitted. |
| E08 | `error: invalid_completeness` | Approve | Boolean True is not a valid completeness enum; malformed authority must yield an error. |

### Focused review requirements

- **V03:** The statement is about SYN-002; its reviewed value is 10,000 mm. Do not compare the claimed 20,000 mm to SYN-001 merely because that product appears in tool evidence.
- **V04/V05 versus A05:** `complete + not_supplied` can justify `unsupported` under the declared policy; incomplete authority remains `indeterminate`.
- **V06:** Preserve the turn-0 unsupported finding even when a later fact and correction appear.
- **A01:** An unresolved pronoun stays unresolved; no nearest-product or single-product guessing.
- **N01–N06:** Question, denial, quotation, hypothetical, rainfall and garment dimensions must not be scored as affirmed waterproof claims.
- **E01–E08:** Verify error code, scope, precedence and absence of fabricated findings; E06 source-hash failure takes precedence over its secondary review-hash mismatch.

## 5. Integrity, label, and metric review evidence

**Assisted static review checks:** The 32 supplied input and expected records were parsed and paired by ID; both exact file hashes were recomputed; earlier review checks reported consistent input/provenance digests, text/slot spans, evidence pointers, numeric conversion and counts. Deliberate corruptions in E06–E08 are expected. These checks validate fixture consistency, not implemented-detector performance. The actual worktree needs a fresh verification before signing.

**Metric denominator:** 15 in-grammar affirmative numeric claims: `S01 S02 S03 S04 S05 S06 V01 V02 V03 V04 V05 V06 A01 A05 A06`.

- A01 is a detectable in-grammar numeric assertion with *unresolved subject*; it contributes to claim-detection recall, even though factual comparison is indeterminate.
- A02 is hedged language, not an unqualified affirmative assertion.
- A03 (`15,000–20,000 mm`) and A04 (`20k mm`) remain separately measured out-of-grammar challenges; both are affirmative candidates but have no exact scalar extraction under v1.
- N01–N06 are non-claims/exclusions, including controls for false positives; E01–E08 are evaluator errors, not quality labels.
- Report precision, recall, raw TP/FP/FN, exclusion/challenge counts, candidate abstention, comparator correctness and indeterminate rate with their denominators; use **N/A** for empty denominators, never an assumed 100%.
- Development and visible acceptance splits are not blinded. Do not claim statistically representative language accuracy.

## 6. Qualifications, known limits and follow-ups

1. **S06:** The supported outcome for turn 1 is consistent, but the fixture also performs a turn-1 `get_product`. It does not isolate *earlier-only tool evidence reuse*. Consider a separate future test without changing this label.
2. **Agent knowledge not assessed:** Even `supported` claims match the synthetic evaluator-owned authority manifest, not necessarily numeric facts surfaced to the agent. The normalized commerce tool shows categorical `waterproof_rating` values such as `high`; this must never be converted to a numeric hydrostatic-head value.
3. **Conservative subject grammar:** Pronouns, ambiguous references, fuzzy names and complex product groups remain out of scope or unresolved.
4. **Incomplete evidence:** Missing normalized product fields do not prove missing source facts. Authoritative completeness and revision/temporal validity must be explicit and reviewed.
5. **Coverage and generalisation:** A passing implementation on these visible fixtures establishes bounded conformance only. A later independent language challenge set and more varied real examples would be needed to estimate real-world accuracy.
6. **Evaluation policy isolation:** This diagnostic is separate from Study v1 capture/score/reporting and must not modify that study’s methodology, result semantics, baseline datasets or historical artifacts.
7. **No source implementation yet:** The present record reviews *authored expected outcomes*, not measured outputs from a detector. Do not present it as live evaluation evidence.

## 7. Final human reviewer declaration

**Reviewer to complete only after reviewing the exact 32 records, the specification, and the policy decisions above.** Do not invent a reviewer identity or date.

- [x] I have checked all 32 source examples and their expected labels and **personally confirm each Approve decision** in Section 4, with no undisclosed disputes.
- [x] I have read `docs/salesagent-grounding-diagnostics-v1.md` and confirm the policy and contract interpretation.
- [x] I approve the 15-claim exact-grammar recall denominator and separate reporting of challenges, exclusions and errors.
- [x] I acknowledge the S06 limitation and that synthetic reference agreement does not establish agent grounding.
- [x] I confirm that the hashes in Section 2 match the candidate files in the isolated worktree at sign-off time.
- [x] I confirm I am independent of the fixture/detector author for this review, or I have transparently recorded the limitation.

**Human reviewer:** `Rebecca Williams`  
**Review date/time and timezone:** `11/10/2026 11:30 BST`  
**Decision:** `APPROVED`  
**Unresolved objections:** `NONE`  
**Reviewed corpus revision:** `candidate-1`  
**Approved cases SHA-256:** `1bfb96ec6a381ed313db86957e03843cdf7a020363793e9bb7bd04d75a19f5ce`  
**Approved expected SHA-256:** `8682d235f38e90ab5ab78a79ba0d7c97c28a3ddc5d27e592dc52753dbc67e962`

### Consequence of approval

If the named reviewer completes the declaration and verifies the hashes, Codex may be instructed separately to update `manifest.json` to record the review and freeze, and prepare a review diff. **This file alone does not update the manifest, approve a commit, authorise Milestone 2, or authorise live evaluation.** Any disputed decision requires a reviewed contract/corpus revision and refreshed hashes before freezing.

---
