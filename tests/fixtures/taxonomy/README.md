# Pinned pre-taxonomy compatibility fixture

`legacy-v1.json` was generated before modifying any production model, at
`9198ad26d84576a319537909f146c5121412be99` on 2026-10-03. Its byte SHA-256 is
`5818ce99cec46d4ec82095b7a6e9eb11685a8537248cff8eae2419e95dd49e4b`.

All content is synthetic. The existing offline `test_replay.fixture_run`,
`scorer`, `prepare`, and `settings` helpers supplied the source contract.
Timestamps and identifiers were fixed; the first input/metadata was extended
with Unicode and nested JSON. Calibration contracts/examples, a synthetic
annotation, frozen annotation set, and a saved replay were constructed using
the pre-change models. No target or judge was called. Fixture generation used
a judge callable that raises if invoked and asserted exactly the five original
TestCase fields before writing.

The fixture pins original compact model JSON, parsed model documents, dataset
and document fingerprints, prepared prompt/evidence, calibration identity and
binding, and historical/replay observation joins. Blank/duplicate legacy tags
and a minimal case protect permissive construction and default serialization.
The JSON contains no private runs or actual human annotations.

Do not regenerate these expected values with newer models to fix compatibility
failures. Test against the original representation. The fixture is data, not a
new dataset format or descriptor.
