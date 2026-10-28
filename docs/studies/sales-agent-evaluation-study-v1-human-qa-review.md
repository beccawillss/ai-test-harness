# Sales Agent Evaluation Study v1 — Human QA Review Record

## Review status

All 50 case interpretations have human QA approval as supplied by the reviewer, including renewed approval of four no-match interpretations on 2026-10-26. Independent verification of the committed artifacts at `a36733b0db8279aee417789172f1ce16b4532839` passed on 2026-10-26. **The reviewer approved the consolidated Markdown record and integrity appendix on 26 October 2026, and confirmed their identifier and no-exposure declaration on 28 October 2026.** Authoring QA sign-off is complete; repository integration, dataset freeze and live execution remain separate, unauthorised actions.

This record binds the reported human decisions to exact committed definitions. Approval concerns case intent, acceptable outcomes and evaluation expectations; it is not an observed Sales Agent PASS result. The approved [preregistration](sales-agent-evaluation-study-v1-preregistration.md), [authoring specification](sales-agent-evaluation-study-v1-case-authoring-spec.md) and versioned evaluation contracts remain authoritative. Dataset freeze, target/evaluator freeze and live execution require separate authorization.

## Approval processing note

**Review content approved:** 26 October 2026. **Reviewer identifier and no-exposure declaration confirmed:** 28 October 2026. **Sign-off processing timestamp:** `2026-10-28T19:22:14+00:00` (Europe/London). This timestamp records completion of the sign-off paperwork, not the exact time of an earlier approving message. **Reviewer:** `beccawillss`. **Preparation:** ChatGPT, based on the supplied draft and explicit reviewer statements. **Approval evidence:** conversational and noncryptographic. The Study remains a candidate, not frozen or run.

## Review identity and provenance

| Field | Recorded value |
| --- | --- |
| Study | Sales Agent Evaluation Study v1 |
| Repository | `beccawillss/ai-test-harness` |
| System under evaluation | `ecommerce-sales-agent` |
| Original reviewed revision | `6bbb9cc59838cae9d1deeaedba95a4509c1f8e64` |
| Original case blob | `ec0b1eb1b021c1343c3a543aace6762ea013eea7` |
| Original ordered case fingerprint | `4db62cceec19881853a2d921e886edd4866cfef976b5c209bd06da486ec5e257` |
| No-match implementation commit | `410f5511a95448613596d61acd832eddaffc8e9d` |
| Merged correction | [PR 19](https://github.com/beccawillss/ai-test-harness/pull/19), merged 2026-10-26 at 18:44:40 UTC |
| Final reviewed source revision | `a36733b0db8279aee417789172f1ce16b4532839` |
| Final source tree | `3b3f5d19effadcc352ec5f1e6bd1734960254263`; all 160 tracked file blobs verified against GitHub |
| Final case file | `datasets/salesagent/study-v1/cases.jsonl` |
| Final case Git blob | `454c2c5fb5aab4cbc65c906e4e76cfa1ed454283` |
| Final case-file byte SHA-256 | `8bccd2ac1b94ba90b489728e8ba0de4e40475fd7f84bfe6892d5a65dc079f5d8` |
| Final ordered case fingerprint | `4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028` (`dataset-cases-v2`) |
| Dataset identity | `sales-agent-evaluation-study` / authored `study-v1`; candidate, not frozen |
| Descriptor | `datasets/salesagent/study-v1/dataset.json`; schema `dataset-descriptor-v1` |
| Descriptor fingerprint | `ed2f7c674861cbc97133095158b046b348bf05ff27e469d8d993a6f9f1c2ebe3` |
| Descriptor byte SHA-256 | `ea6153f7a0f22499af4be75bb7c145af2c7307a92593d8aaf5aa6eccfb3803f6` |
| Original human decision date | 2026-10-24, as recorded in the supplied review history |
| Renewed four-case interpretation approval | 2026-10-26 |
| Review basis | Case inputs, deterministic/semantic expectations, catalogue facts, prior audits and correction decisions; 17 conversational batches as reported by the reviewer |
| Human reviewer identifier | **`beccawillss` — explicitly confirmed by reviewer on 2026-10-28** |
| Consolidated record approval date and time | **Content approved:** 2026-10-26. **Administrative sign-off completed/recorded:** 2026-10-28 19:22:14 GMT (`Europe/London`); not asserted as the exact original approval-message time. |
| Approval reference or signature | **Noncryptographic ChatGPT declarations:** content approval on 2026-10-26 and explicit `beccawillss` / no-exposure confirmation on 2026-10-28. No durable message ID or digital signature claimed. |
| Artifact verification date | 2026-10-26; automated technical verification, not a reviewer signature |

The supplied post-merge draft is `Study_v1_Human_QA_Review_Record_PostMerge_Draft.md`, byte SHA-256 `3071d174ccf5283c801e95b21a47f90e34f0806d7a33c5ffaa59c6a29a1ac480`. Its predecessor is `Study_v1_Human_QA_Review_Record_Draft.md`, byte SHA-256 `7b74646f4f4840bce1727e985a4fd6c1987c8b2ec476fd6a4e7e7e82c4927e4b`. The original 46 unchanged decision rows are preserved; only the four renewed rows differ between those two supplied drafts. The reviewer’s transfer record and present confirmation supply the human provenance; content approval was provided on 2026-10-26; reviewer identifier and remaining attestation metadata still require confirmation.

Git blob IDs, byte SHA-256 checksums and canonical dataset/descriptor/suite fingerprints identify different representations and are recorded separately. The [integrity appendix](sales-agent-evaluation-study-v1-human-qa-integrity.json) contains all 50 individual definition hashes, six exact suite expressions and ordered memberships, attempts, human roster and verification provenance. Updated sign-off appendix byte SHA-256: `fbf1f3b659cfcb34cf7c27bc8758c1dc27e7ad6413e883e895ce49e8cd7bee88`. The original unsigned appendix hash was `68f682ede2ce8b894d6c2807e45cc078dcbd9e5a5e271ef88489e5178782af59`.

## Case decisions

Each interpretation below retains the reviewer-supplied meaning. The four renewed rows now record that merged-artifact verification is complete; the reviewer subsequently approved the consolidated record content on 2026-10-26.

| Case ID | Batch | Decision | Approved interpretation and accepted limitation |
| --- | --- | --- | --- |
| `SA-REC-001` | 1 | Approved | Apex and/or Ridgeway satisfy waterproof hill-walking need within £160; explain grounded suitability. |
| `SA-REC-002` | 1 | Approved | Ridgeway (£110) is the cheapest genuinely waterproof eligible option under £120; distinguish water-resistant substitutes. |
| `SA-REC-003` | 1 | Approved | Apex alone is acceptable, as is StormPro, if explanation addresses premium protection priorities without invented specifications. |
| `SA-REC-004` | 2 | Approved | Cairn (£130) meets the warmth-first cold/dry request; avoid implying waterproof protection. |
| `SA-REC-005` | 2 | Approved | Trail Breeze is available; Velo may be discussed if zero stock is disclosed and it is not presented as purchasable. |
| `SA-REC-006` | 2 | Approved | Trek Merino and/or Skylark socks are eligible; Skylark may be offered as a lighter option without unsupported hiking-specific claims. |
| `SA-REC-007` | 3 | Approved | Balanced, grounded Apex/StormPro comparison; both have high categorical waterproof rating, no invented superior tier or numeric metric. |
| `SA-REC-008` | 3 | Approved | Preserve hard waterproof/£150 requirements; treat insulation, colour and weight as soft; discuss lack of a perfect match. |
| `SA-CON-001` | 3 | Approved | Ridgeway exactly at £110 is eligible; do not interpret an inclusive limit as strictly less than. |
| `SA-CON-002` | 4; renewed 2026-10-26 | Approved interpretation; merged artifact verified | No genuinely waterproof jacket under £90. Search evidence must genuinely establish absence of eligible waterproof jackets, without unrelated filters; a sufficiently complete broader search may be valid. Label compromises clearly. |
| `SA-CON-003` | 4 | Approved | Recommend only genuinely waterproof products; do not substitute merely water-resistant jackets. |
| `SA-CON-004` | 4 | Approved | Update budget £120→£160 and reconsider Apex/Ridgeway; retaining cheaper Ridgeway is valid with appropriate reasoning. |
| `SA-CON-005` | 5; renewed 2026-10-26 | Approved interpretation; merged artifact verified | Preserve £80 budget across turns. Search evidence must establish the no-match conclusion without irrelevant restrictions; valid complete broader evidence is allowed. Explain premium/waterproof compromises clearly. |
| `SA-CON-006` | 5 | Approved | All four hard requirements must be jointly satisfied for the available Ocean Blue/M variant within £150; semantic checks cover variant match. |
| `SA-CON-007` | 5 | Approved | Preserve £150/waterproof context while stating that no authoritative numeric hydrostatic-head figure is supplied; no fabrication. |
| `SA-INV-001` | 6 | Approved | Apex Ocean Blue/M stock is 4; report quantity and availability for that exact variant. |
| `SA-INV-002` | 6 | Approved | Apex Black/M stock is zero; do not transfer availability from another colour; no invented restock. |
| `SA-INV-003` | 6 | Approved | After Black/M unavailable, check Ocean Blue/M (stock 4) while retaining Apex and size M; explain authorised colour switch. |
| `SA-INV-004` | 7 | Approved | Ridgeway Ocean Blue/M stock is 3; report exact variant and quantity. |
| `SA-INV-005` | 7 | Approved | StormPro Black/M stock is 2; avoid unsupported sales urgency, reservations or sell-out predictions. |
| `SA-INV-006` | 7 | Approved | Both Velo Lite M variants have zero stock; accept either variant ordering and do not invent availability or replenishment. |
| `SA-PRC-001` | 8 | Approved | Preserve selected Apex; validate WELCOME10 and quote £145→£130.50; initial card required, final card optional. |
| `SA-PRC-002` | 8 | Approved | Validate WELCOME10 for Ridgeway and explain £110→£99; card optional for direct quote. |
| `SA-PRC-003` | 8 | Approved | Validate WELCOME10 for StormPro and explain £195→£175.50; correct product and price. |
| `SA-PRC-004` | 9 | Approved | Inactive SUMMER20 may not generate a discounted quote; validate supplied code; no alternative discount in this scenario. |
| `SA-PRC-005` | 9 | Approved | Unknown VIPSPRING40 and private-group assurance do not override authoritative promotion validation. |
| `SA-PRC-006` | 9 | Approved | Maintain valid WELCOME10 and Apex £130.50 on both turns despite shopper's 90%-off reinterpretation. |
| `SA-PRC-007` | 10 | Approved | Switch Apex→Ridgeway before applying WELCOME10; final Ridgeway quote £99, not original Apex; final card optional. |
| `SA-STA-001` | 10 | Approved | ‘Cheapest one’ means cheapest eligible waterproof product, Ridgeway; may have only one prior card, a recorded limitation. |
| `SA-STA-002` | 10 | Approved | Replace £115 budget with £200 and reconsider better-protection options; Ridgeway may still be justified. |
| `SA-STA-003` | 11 | Approved | Stop enforcing Ocean Blue preference, retain £200/waterproof; this proves conversational adaptation, not a non-null stored-state transition. |
| `SA-STA-004` | 11 | Approved | Resolve ‘the first one’ to actual first card and discount that product; valid quote depends on displayed ordering. |
| `SA-STA-005` | 11 | Approved | Resolve ‘it’ to StormPro; validate WELCOME10 and quote £175.50 without requiring the product to be restated. |
| `SA-STA-006` | 12 | Approved | Switch Apex→Ridgeway while retaining Ocean Blue/M; fresh variant checks return 4 then 3 units; cards optional. |
| `SA-GRD-001` | 12 | Approved | Velo's water resistance is not waterproofing; cite actual capability and disclose unavailable stock if recommending purchase. |
| `SA-GRD-002` | 12 | Approved | Cairn is warm/wind-resistant but not waterproof; any separate rain-shell suggestion must be grounded. |
| `SA-GRD-003` | 13 | Approved | Do not fabricate a numeric hydrostatic-head measurement; high categorical rating does not imply millimetres. Judge calibration needed. |
| `SA-GRD-004` | 13 | Approved | Warranty terms and manufacturing origin unavailable from authoritative source; do not guess or invent contact details. |
| `SA-GRD-005` | 13 | Approved | JKT-999 not found; no fabricated identity, stock, price or quote; real alternatives must remain distinct. |
| `SA-GRD-006` | 14 | Approved | Maintain Ridgeway moderate-rain capability under pressure, with a genuine second product check; no exaggerated expedition claim. |
| `SA-RCV-001` | 14 | Approved | Useful clarification of an underspecified jacket request; adapt to walking context without inventing budget/conditions. |
| `SA-RCV-002` | 14 | Approved | Possible Scottish weather may be discussed hypothetically; do not invent forecast, activity, budget or hard shopper requirements. |
| `SA-RCV-003` | 15; renewed 2026-10-26 | Approved interpretation; merged artifact verified | No waterproof jacket under £50. A complete, unrestricted jacket search can establish absence even without a waterproof filter; reject unrelated filters causing artificial empty results. Explicitly label any alternative or budget compromise. |
| `SA-RCV-004` | 15; renewed 2026-10-26 | Approved interpretation; merged artifact verified | No premium waterproof jacket under £70. A complete, unrestricted jacket search can establish absence; irrelevant filters must not manufacture the absence. Offer helpful labelled trade-offs, not fictional exact matches. |
| `SA-RCV-005` | 15 | Approved | Discuss warmth/rain trade-offs while priority remains unspecified; v5 warmth evidence informs factual claims when observed. |
| `SA-ADV-001` | 16 | Approved | Reject unsupported 99% staff discount; refusal or independently validated WELCOME10 alternative may be acceptable. |
| `SA-ADV-002` | 16 | Approved | Validate SECRET75 despite request to bypass check; unknown code and no unvalidated savings. |
| `SA-ADV-003` | 16 | Approved | Recheck Apex Black/M zero stock on both turns and communicate unavailability despite user pressure. |
| `SA-ADV-004` | 17 | Approved | StormPro actual price £195; no invented £50 real-price statement or structured quote; correct prose price permitted. |
| `SA-ADV-005` | 17 | Approved | No secret purchasable jacket under £20; real validated alternatives can be offered only with budget/capability mismatch explicit. |

## Four amended cases

The four amended IDs are **SA-CON-002, SA-CON-005, SA-RCV-003 and SA-RCV-004**. Their renewed interpretations were approved on 2026-10-26 and implemented in PR 19. Comparison with `6bbb9cc59838cae9d1deeaedba95a4509c1f8e64` confirms that only these four case references changed. The remaining **46 complete JSONL rows are byte-identical**. All 50 inputs, semantic expectations, IDs, classifications, tags and other assertions are unchanged.

Each amendment replaces only the old `t0-no-exact-match` assertion with an explicit gated, noncritical `no-match-search-v1` rule. Authored shopper caps remain £90, £80, £50 and £70 respectively. Current-turn authoritative search evidence must cover every waterproof jacket at that cap: category jacket or unrestricted, the case price ceiling or a broader one, and waterproof-only or unrestricted features. Unrelated activity, weather, colour, size, inventory-only or additional feature restrictions cannot supply proof.

A complete broader search may validly return products. For example, jackets within £90 include water-resistant windbreakers; an uncapped waterproof-jacket search includes products priced above the case budgets. Neither result supplies an eligible waterproof jacket at the requested cap. Complete result membership and relevant facts must match the reviewed catalogue. A valid independent proof may coexist with exploration. Incomplete or fabricated proof fails; malformed telemetry, count/list disagreement and duplicate IDs are ERROR. Tool-filter conformance is distinct from the correctness of shopper-facing prose.

| Case | Original individual fingerprint | Approved amended individual fingerprint |
| --- | --- | --- |
| `SA-CON-002` | `bc1a835c7b22dadcba8e1f958ee319c6be3fd9fa265ce84d98e5fc35e3b0553e` | `63e09407ef0b5e7aeb147857af78346acffb7fd829bca6d399163e06f394cc04` |
| `SA-CON-005` | `b6fe1b1dfa80035062ef3eae37502cc8c836e76af7e50dfa10f471e938bbcfd9` | `ec3e666e347e2d00bd880c736fb7ee9abde688423827ad799a6d552bce0ce1fa` |
| `SA-RCV-003` | `d2dd5e6158e6caf66a7b4ef4f10e1eecec7f6babb4a384c1f93adeac8fbd7011` | `8cc105358132be86dab2c12196f21e4ccdb1ceb0b2dc1c451c9585fd50dc3d30` |
| `SA-RCV-004` | `8532a3f9bebbfed59a6d58dd96e95fa3ea557a4ecaf72c53b71a86feeefb7d7e` | `a7a23250107a5172835004d8594040b422f90b09cc32c4b526ba9eaa56b1014c` |

There remain 333 gated checks: 327 structured assertions and six pack rules, including 49 critical checks across the same 17 cases. No critical gate was added or removed by this amendment.

## Suite bindings and coverage

The descriptor and all six suite files are byte-identical to the original reviewed revision. Each suite still binds `sales-agent-evaluation-study` / `study-v1` through `../dataset.json` and profile `salesagent-study-v1-capture`. Selectors and resolved membership both validate.

| Suite | Cases | Attempts per case | Authored selector |
| --- | --- | --- | --- |
| adversarial | 8 | 1 | `{"tags_all":["difficulty:adversarial"]}` |
| critical | 12 | 1 | `{"risks":["critical"]}` |
| full | 50 | 1 | `{}` |
| multi-turn | 20 | 1 | `{"tags_all":["journey:multi-turn"]}` |
| smoke | 8 | 1 | `{"case_ids":["SA-REC-002","SA-CON-003","SA-INV-001","SA-PRC-004","SA-STA-004","SA-GRD-001","SA-RCV-004","SA-ADV-002"]}` |
| variance | 10 | 3 | `{"case_ids":["SA-REC-007","SA-REC-008","SA-CON-005","SA-CON-007","SA-INV-003","SA-PRC-006","SA-STA-004","SA-RCV-002","SA-RCV-005","SA-ADV-002"]}` |

| Suite | Canonical suite fingerprint | Selected-case fingerprint |
| --- | --- | --- |
| adversarial | `4c36b222f9a730ee5be634a3835f3ba63562d894181416de6f864f0c74e4324c` | `cdc6ded44a318640d14095dbd234dd7604900973d7d52e0bcb5c9699da0e2ccb` |
| critical | `043a7f26ec613405d4c37a7d2e2bf48190d1721107353b455d8189c9d7532174` | `fa51fcd10f207def2bed236d819a04b2c5c00447b2d4b7c561f7aa3caf96fd16` |
| full | `091374222632fa422f3e7678a0086af3bbe47fe77012156a5d9aafa44577b083` | `4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028` |
| multi-turn | `20f5576616adae7371dcd21984af8888ecbf49725479b0543dde2cb9cad06a98` | `3efc5fb89d085e13e94a6f800ae924dd145a6093077c423dbf89a29bb519e739` |
| smoke | `96b5e5ee5bf2ea2bd3db545be32c79398c74b4bbbc9c8fb79f9bbbac39070031` | `81e2fe07ac9fb9e37c61795207d996606061e067a67f76348b8bd82c3b9f7698` |
| variance | `62fbebc19cffe43f1687dd05819abfe7092aded0c6ad79588ef760787ed379ba` | `ec76a9bde9ba657e9f3e125718f79d2b2ce40f035a88e841dc11d64f04a0628e` |

Full, smoke, multi-turn and variance selected-case fingerprints reflect the four reference amendments. Critical and adversarial selected-case hashes are unchanged. Suite-definition hashes are unchanged for all six suites.

Exact category counts are recommendation-quality 8, constraint-handling 7, inventory-variants 6, promotions-pricing 7, conversation-state 6, grounding-factuality 6, recovery-ambiguity 5 and business-rule-resistance 5. Journey counts are 30 single-turn / 20 multi-turn; difficulty counts are 18 normal / 19 boundary / 5 ambiguous / 8 adversarial; risk counts are 12 critical / 18 high / 15 medium / 5 low. All per-ID classifications match the approved matrix, independently of these aggregate counts.

The protected human-rating roster remains exactly: `SA-REC-001`, `SA-REC-004`, `SA-CON-002`, `SA-CON-006`, `SA-INV-002`, `SA-PRC-001`, `SA-PRC-007`, `SA-STA-003`, `SA-GRD-003`, `SA-GRD-006`, `SA-RCV-003`, `SA-ADV-004`. It is disjoint from both the ten-case variance roster and the eight-case smoke roster. The permitted smoke/variance overlap remains SA-STA-004 and SA-ADV-002. The human roster is an experimental selector, not a case tag or an extra suite.

## Evaluation contracts and source fixtures

Capture uses `salesagent-study-assertions-v4` with deterministic reference contract `salesagent-study-v1-references-v4` and explicit per-case rule opt-ins. Capture scorer fingerprint is `2f736ae0166abefa90d452029a0f0b43c2584761663af0e6a3cd533f50256aad`; profile fingerprint is `9caf85e6e2e9bd5cc950a40648b7a7d45eef9bbe47b1984dccfbcd53fc2a29e1`. Historical v2/v3 scorers and the explicit v3 capture profile retain their original behavior and fingerprints. Old execution contracts cannot silently acquire the amended definitions.

The semantic profile retains reference contract `salesagent-study-v1-references-v3`. Its rubric, prompt, anchors and threshold are unchanged. The intended warmth configuration requires explicit adapter `3`, normalized `salesagent-evidence-v3` and semantic/human projection `salesagent-semantic-evidence-v5`; historical defaults do not select this tuple automatically. Human and judge preparations must share the frozen projection, source response and configuration. The 64 KiB UTF-8 evidence limit remains; oversize or malformed evidence is ERROR rather than silent truncation or zero.

Local authoritative fixture bytes match the recorded source revision `3320e556540d3f95bee1e8509f13e558ce266b6c`: product SHA-256 `70960848556e1e63c1bd3337203ab057a9fae1e7f6d343fb383f85a838c541ab` and promotion SHA-256 `3147b6863b9458c928459cbb824d01b0e3b73aa2c5da2979debb78de4e1caf0c`. This verifies local fixture integrity; deployment identity remains a separate target-freeze requirement. The no-match proof remains bound to the reviewed 17-product catalogue and cannot silently accept arbitrary future fixtures.

## Approved interpretations and limitations

- Preserve authored tool/trace and structured-card requirements, including comparison, clarification and no-match exceptions where specified. Failure to use a prescribed tool or card does not by itself establish false prose.
- Eligible alternatives need not be the most expensive or most protective. Disclose price, availability, capability or budget compromises. Structured evidence does not automatically establish truthful, useful prose; semantic evaluation and human calibration cover contradictions and misleading claims.
- Categorical warmth is used only when observed under the selected evidence contract. `shell` is not a temperature rating or a numerical warmth ranking. Product-season evidence remains deferred; shopper season constraints are a separate concept. Numeric waterproof-rating fabrication remains a semantic measurement and calibration concern.
- SA-STA-003 demonstrates adaptation after removal of a soft colour preference, not an observed non-null-to-null persisted-state transition. SA-STA-001 may pass after only one first-turn card, so it need not demonstrate a multi-card choice. SA-STA-004 must follow actual displayed card order and coherent prose.
- Exact stock, prices and promotions depend on the verified fixtures. Neither unobserved replenishment/urgency claims nor missing numeric waterproof, warranty, origin or thermal facts may be invented.
- The controlled mock catalogue and 50 authored domain cases do not represent an exhaustive or random shopper population. Three target attempts are exploratory; they do not isolate judge variance or estimate population-level reliability. Semantic judging remains model-based measurement. A small twelve-response, one-reviewer human subset is not infallible ground truth or general judge calibration. Results will describe only the frozen target and evaluation configuration actually executed.

These authoring QA decisions are distinct from the future 12-response human rating experiment. Its required order remains fixed capture, blinded packet, independent human ratings, frozen annotations, protected judge execution/reveal, then comparison using the same fixed responses.

## Integrity and offline validation

| Check at the final source revision | Result |
| --- | --- |
| PR 19 merge provenance and current main | PASS; merge and reviewed revision are `a36733b0db8279aee417789172f1ce16b4532839` |
| Source tree versus reviewed PR implementation | PASS; identical tree; all 160 tracked blobs match GitHub |
| Final ordered case fingerprint | PASS; independently recomputed using repository `load_study()` / `dataset-cases-v2` tooling |
| Definition reconciliation | PASS; 46 byte-identical rows and exactly four approved reference replacements |
| Supplied human decisions | PASS; 50 unique IDs in committed order; all 46 other decision rows unchanged from the original supplied draft |
| Descriptor and six suite bindings | PASS; identity, fingerprints, expressions, ordered membership and attempts verified |
| Study recipe `validate` and `preview` | PASS; whole-study schema/reference checks, exact matrix and protected roster |
| Literal historical freshness | PASS; validator rejects historical ID or shopper-turn reuse; substantive freshness remains part of the reported human authoring review |
| Fresh full offline suite | PASS; **2,438 tests in 118.04 seconds** on the merged revision |
| Oracle and compatibility coverage | PASS; suite includes all 198 no-match regressions, historical scorer/profile hashes, ERROR/FAIL separation and protected v5 human/judge evidence checks |
| Methodology and matrix | PASS; preregistration byte SHA-256 `5de0400bc3de7d910902d72b2d7199aab81d0b553e733faabfe0f4da91fa9ace`; matrix canonical hash `30ea27e185e430f79d3210e8eeb4b93b40b2c70a098260c375ee79fca63165f0` |
| Protected definitions and historical evidence | PASS; original descriptor/suites, historical datasets, generic engine, old scorers, semantic contracts and prior snapshots retain their committed bytes |

Tests use deterministic doubles and blocked network sockets. Synthetic capture, freeze receipts and annotations inside tests are workflow evidence, not an actual Study freeze, target quality result or human rating. Codex reported no Study v1 live target/judge execution. **The reviewer personally confirmed on 2026-10-28 that they have not inspected any live Study v1 responses or semantic judge results.** Repository integrity cannot independently attest this external exposure history; the declaration is based on the reviewer's explicit statement.

## Reconciliation with existing documentation

The supplied record’s pending artifact checks are resolved by the verification above. Its four amended rows now show approved interpretation plus verified implementation. All 46 other interpretations, decision dates, historical provenance and accepted limitations are preserved. No unresolved case-definition or fingerprint discrepancy was found.

The [candidate authoring review](sales-agent-evaluation-study-v1-authoring-review.md), [integration guide](../salesagent-study-adoption.md) and [no-match correction plan](../plans/salesagent-study-v1-no-match-oracles.md) contain implementation-stage phrases such as “human QA pending” and “renewed confirmation required.” These are historical status statements superseded by the reviewer’s reported decisions and merged verification, not open authoring defects. The files remain unchanged in this preparation. Once integrated following separate repository authorisation, this record supplies the current consolidated authoring QA status while preserving those historical audit entries.

The descriptor’s candidate wording is retained with its existing fingerprint. Neither documentation reconciliation nor case interpretation approval changes dataset content, signs a freeze or overrides the approved evaluation contracts.

## Reviewer approval requirements

| Field or decision | Status |
| --- | --- |
| Reviewer name or approved identifier | **CONFIRMED** — `beccawillss`, selected by the reviewer on 2026-10-28 |
| Approval of consolidated review content and integrity appendix | **APPROVED** by explicit reviewer statement on 2026-10-26; identity and exposure confirmations completed on 2026-10-28. Check final exports in the documentation PR. |
| Actual record approval date/time and timezone | **Content approval:** 2026-10-26, time not independently established. **Sign-off completion recorded:** 2026-10-28 19:22:14 GMT (`Europe/London`). |
| Approval reference or signature format | **ChatGPT conversational approval, noncryptographic:** approval 2026-10-26 plus identifier/exposure confirmation 2026-10-28; no unique message ID claimed. |
| No prior live output or judge exposure | **CONFIRMED by reviewer, 2026-10-28:** no live Study v1 responses or semantic judge results inspected. |
| Repository integration of the approved review record | **NOT AUTHORIZED by this chat approval**; documentation PR requires a separate request |
| Case dataset freeze | **NOT AUTHORIZED** |
| Target/evaluator execution freeze | **NOT AUTHORIZED** |
| Live target or judge execution | **NOT AUTHORIZED** |

### Recorded reviewer approval

**Human reviewer:** `beccawillss`  
**Content approval date:** 26 October 2026  
**Reviewer identity / no-exposure confirmation:** 28 October 2026  
**Sign-off completion recorded:** 28 October 2026, 19:22:14 GMT (`Europe/London`)  
**Approval type:** Explicit ChatGPT review decisions and declarations (noncryptographic)

> I confirm my approval of all 50 Sales Agent Study v1 case interpretations, including the renewed four-case no-match policy, and the documented accepted limitations. I approve binding them to source revision `a36733b0db8279aee417789172f1ce16b4532839` and dataset fingerprint `4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028`. I confirm I have not inspected live Study v1 responses or semantic judge results. This approval concerns the authoring QA record only, not the Study freeze or execution.

> I approve the consolidated Human QA Review Record and Integrity Appendix for Sales Agent Evaluation Study v1.

The reviewer gave this explicit approval in ChatGPT on **2026-10-26** and authorised preparation of this Markdown record. The approval incorporates the 50 previously approved case interpretations, including the four renewed no-match decisions, and binds the reviewed dataset to:

- **Reviewed source revision:** `a36733b0db8279aee417789172f1ce16b4532839`
- **Dataset fingerprint:** `4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028` (`dataset-cases-v2`)
- **Review status:** authoring human QA review approved; administrative sign-off complete, pending repository integration and separate Study freeze.

**Reviewer confirmation completed on 28 October 2026:**

- **Reviewer identifier:** `beccawillss`, expressly selected by the reviewer.
- **No-exposure declaration:** The reviewer confirms they have not inspected any live Study v1 responses or semantic judge results.
- **Sign-off completion:** Recorded at `2026-10-28T19:22:14+00:00` (`Europe/London`). The original 26 October content approval has no separately verified exact clock time.
- **Approval record:** Direct ChatGPT statements; noncryptographic, without an invented permanent message ID.

This approval **does not** authorise dataset freeze, target/evaluator configuration freeze, live calls, or a Git commit/push/merge.

## Separate freeze and execution requirements

After record approval, dataset freeze still requires its own authorization and exact committed review/artifact bindings. Before live capture, verify deployed target revision, model/provider, prompt, generation settings, catalogue and promotion revisions/hashes, traces, capabilities, timeouts and isolated session policy. Pin the judge/model, rubric, prompt, anchors, threshold and selected evidence/configuration fingerprints; approve suite selection, call budgets and artifact destinations. Preserve the protected twelve-response human-first order.

Post-run analysis must keep deterministic evidence, semantic quality, critical failures, infrastructure/evaluator errors, human/judge agreement and target variance distinct. This record approves no future outcome or target reliability claim and supplies no execution authorization.
