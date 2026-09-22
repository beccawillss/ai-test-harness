# Structured assertions v1

`StructuredAssertionsScorer` reads `reference.assertions`. Each entry has a
unique `id`, `path`, `op`, and (except unary operators) exactly one of `expected`
or `expected_path`. Paths are arrays of string keys/nonnegative integer indices
rooted at a normalized response field. `raw` is deliberately unavailable.
A `*` projects list members and requires `quantifier: "any"` or `"all"`.
Both quantifiers fail on an empty projection; neither proves evidence vacuously.

Operators: `equals` (typed deep equality), `decimal_equals`, `decimal_lte`,
`is_null`, `not_null`, `exists` (boolean expectation), `nonempty` (list),
`contains`/`excludes` (list membership using object-subset matching), `matches`
(object subset), `matches_any` (one of a list of allowed object subsets/values),
and `subset` (every actual list item matches an allowed expected item).
Decimal comparisons accept finite decimal strings/numbers, never booleans.

Missing telemetry is ERROR, not null. Only `exists` intentionally tests missing
paths. Traversing a known null optional object retains null, so a required
promotion's null value fails normally. Malformed paths/operators/configuration
raise errors. List type errors are configuration/evidence errors. Expected
references and actual values are not copied into diagnostic Score extras.

`gated` defaults true. `critical` defaults false and requires gated=true.
Score.value is a descriptive fraction; Score.passed is the conjunction of gates.
No gated assertions yields an informational Score. Independent scorer errors
retain other Scores but make the attempt ERROR under existing runner semantics.
