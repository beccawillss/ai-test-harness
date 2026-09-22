# First Sales Agent baseline

Fourteen JSONL cases implement the approved scenario matrix. Target input is
only `input.turns`. References intentionally store evaluator assertions and
semantic expectations; `extra.provenance` identifies their source. Neither is
sent to the target. All normal recommendation checks use structured facts,
never exact assistant prose.

The original standalone golden dataset was unavailable. These cases adapt the
Sales Agent tests/plans recorded in each case. Expected product facts were
frozen from checkout `097a3774694e4eb8897102dda863b297a9ec9e5b`:

- products.json SHA256: `70960848556e1e63c1bd3337203ab057a9fae1e7f6d343fb383f85a838c541ab`
- discounts.json SHA256: `3147b6863b9458c928459cbb824d01b0e3b73aa2c5da2979debb78de4e1caf0c`

These are dataset provenance, not claims about a running deployment. Runtime
never reads/imports the Sales Agent repository. Verify deployed fixtures before
manual evaluation; revise expectations deliberately when catalogue intent
changes. Canonical hashing detects input, assertion, and provenance changes.

Main baseline: all 14 cases, one attempt each. Variance: replace, STAFF99
injection, fake price, previous-product follow-up, and conversation; three
attempts each, a distinct run and subset hash. Never treat the two as a direct
regression comparison.

Structured coverage checks every turn's accepted IDs against current-turn
product evidence and pinned catalogue price/URL facts, and checks chat/trace
agreement. Safety rejection may leave empty cards/promotion; normal shopping
and valid promotion cases require positive results. The off-topic case only
checks commerce safety without a judge; tone/usefulness remain unmeasured.
See `docs/structured-assertions.md` for the assertion language and the ExecPlan
for the full case intent table.
