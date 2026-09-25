# Sales Agent evidence v2

`SalesAgentTarget` calls only the V1 chat/trace HTTP routes. It imports no target
application code. Install with `uv sync --extra salesagent`.

Each invocation accepts `{"turns": ["shopper message", ...]}`. A local session
variable starts empty, then reuses only the backend-issued ID within that
invocation. Requests never contain references, IDs, tags, extra, or assertions.
Cookies and injected-client default authentication/headers are not forwarded.
There are no automatic retries or redirects. Owned clients are closed by the
runner; injected clients remain caller-owned.

`output` is the last assistant message. `structured` contains final
recommendations, promotion, pricing, and all completed `turns`. A turn contains
index, input, output, structured, trajectory, evidence, and metadata. Prices
are decimal strings (without rounding away incorrect precision); pricing's
`base_price` becomes `original_price`. Null differs from absent evidence.

The top-level trajectory concatenates per-turn tool calls in order. Results
contain only normalized successful commerce data, or null for a business error.
Successful `get_product` and `search_products` product records now retain the
authoritative `waterproof_rating`: `none`, `water-resistant`, `moderate`, or
`high`. The field is required; missing, null, or unsupported values are malformed
evidence, not an inferred rating. Recommendation cards are unchanged. Extra
product fields are still excluded; `lightweight` never implies `packable`.

This addition bumps normalized evidence to `salesagent-evidence-v2` (adapter
version `2`) and the semantic commerce-facts projection to
`salesagent-semantic-evidence-v2`. Older persisted responses still load without
rewriting or backfilling them, but v1 evidence cannot be rejudged with the v2
builder when the required rating is absent. Run comparison flags either evidence
version change as an evaluation-configuration difference, even with the same
dataset. The datasets, rubric, and threshold have not changed.

Each structured result also projects `recommendation_product_ids` from its chat
cards. Each turn's evidence projects `grounded_product_ids` from that turn's
successful search/get-product results. These preserve observed facts for generic
subset assertions; they do not declare a recommendation valid.
Tool status, sequence, ID and duration stay in turn metadata. Evidence contains
constraints, changes, recommendation validation flags/error count, accepted
product IDs, trace promotion/pricing, and safe error codes. Chat and trace
claims remain separate so disagreement is scoreable.

`metadata` preserves trace IDs, model/prompt versions, usage totals, adapter and
evidence versions, and the operator-supplied target revision. Identity is always
`salesagent`. `latency_ms` measures the complete HTTP invocation; turn metadata
latency is server latency. Cost is unknown, contexts are absent, raw is empty.
Unknown nested fields and diagnostic prose are discarded. This is a projection
of the public contract, never a raw trace or SDK payload.

Missing/malformed evidence, correlation failures, and infrastructure errors
abort the attempt as ERROR. The existing runner does not preserve partial
responses when a later turn errors. Normal invalid promotions, empty matches,
and rejected nominations remain quality evidence. Scorers decide their verdict.
