# Offline numeric waterproof diagnostics

Run the existing diagnostic over one saved normalized response and an explicitly
supplied authority manifest. This example reads local JSON and prints a report;
it constructs no target or judge, uses no credentials or paid service, and has no
live mode. It does not open result stores or change saved inputs or Study v1.

Use Python 3.12 or newer with the project's installed dependency
`pydantic>=2.13.4`. Activate the existing project virtual environment so `python`
resolves to that interpreter; a bare system Python may lack the dependency.
No provider SDK or optional live-service dependency is needed for this CLI.

For this isolated worktree, reuse the original checkout's environment:

```sh
source /Users/rebeccawilliams/Developer/ai-test-harness/.venv/bin/activate
cd /private/tmp/ai-test-harness-grounding-m3
```

Run both examples below from the worktree root in that activated shell.
`PYTHONPATH=src` selects this worktree's code even if the environment has an
editable install pointing to another checkout. Alternatively, replace `python`
with the absolute path to that environment's `bin/python`.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python examples/salesagent_grounding.py \
  --response /path/to/response.json \
  --context /path/to/context.json \
  --authority /path/to/authority.json
```

## Inputs

All three paths are required. Each file contains one UTF-8 JSON value, with
unique object keys and finite numbers. JSONL, raw HTTP responses, complete saved
runs and corpus envelopes are not CLI inputs.

- **Response:** a serialized `TargetResponse`, such as a saved attempt's
  `response.model_dump(mode="json")`. It must include metadata evidence version
  `salesagent-evidence-v2`, ordered `structured.turns` and top-level `output`
  matching the last turn. The CLI validates the normalized envelope strictly;
  unknown envelope/tool-call fields are rejected rather than silently dropped.
- **Context:** `source_id` and nonnegative integer `attempt_index`, matching the
  manifest binding. `synthetic` defaults to false. Optional `harness_revision`
  records a caller-supplied implementation revision; it is not inferred.
  Optional `expected_response_sha256` verifies the canonical, model-normalized
  response hash (including model defaults), not the file's byte checksum.
- **Authority:** the evaluator-owned manifest described in
  [the specification](salesagent-grounding-diagnostics-v1.md#6-reviewed-authority-manifest).
  Supply a file containing JSON `null` to explicitly diagnose without authority.
  Missing authority is uncertainty, not proof of absence. Nothing is discovered,
  fetched, approved or rebound automatically. Real evidence needs human-reviewed
  source revisions, applicability and completeness; synthetic review is accepted
  only with `synthetic: true`.

Example context for a real saved response:

```json
{"source_id": "saved-response-001", "attempt_index": 0, "synthetic": false}
```

For an offline synthetic smoke run, extract copies from frozen fixture S01 into
a fresh temporary directory. This leaves the corpus unchanged and does not
create production authority or use expected labels:

```sh
demo_dir=$(mktemp -d)
python - "$demo_dir" <<'PY'
import json
import sys
from pathlib import Path

corpus = Path("tests/fixtures/salesagent_grounding/v1/cases.jsonl")
rows = [json.loads(line) for line in corpus.read_text(encoding="utf-8").splitlines()]
data = next(row["input"] for row in rows if row["id"] == "S01")
for name in ("response", "context", "authority"):
    (Path(sys.argv[1]) / f"{name}.json").write_text(
        json.dumps(data[name], ensure_ascii=False), encoding="utf-8"
    )
PY
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python examples/salesagent_grounding.py \
  --response "$demo_dir/response.json" \
  --context "$demo_dir/context.json" \
  --authority "$demo_dir/authority.json"
```

Expected S01 result: exit code **0**, `execution_status: "complete"`, one
candidate and one affirmative claim, `counts.supported: 1`, and
`counts.errors: 0` (all other finding/exclusion counts are zero). The candidate
has `finding: "supported"` and `agent_grounding: "not_assessed"`. This confirms
agreement with the synthetic reference, not physical product truth or evidence
that the agent used that reference.

## Output and execution status

Stdout contains one canonical `GroundingDiagnosticReport` JSON document plus a
newline. It includes execution status, candidates and reasons, Unicode spans,
original turn text, evidence references, counts, configuration and provenance
hashes. Identical inputs and configuration produce identical output. It can be
loaded with `GroundingDiagnosticReport.model_validate_json(...)`. The CLI writes
no files; if saving stdout, choose a new destination distinct from every input.
Reports retain evaluated text and should be handled as evaluation data.

| Exit code | Meaning |
| --- | --- |
| 0 | Diagnostic execution complete, regardless of findings or uncertainty |
| 1 | Report has execution status `partial` or `error`; report still goes to stdout |
| 2 | Invalid CLI arguments, unreadable/invalid JSON, response envelope or context; no report, safe error on stderr |

Malformed consumed evidence inside a valid response envelope or supplied manifest
produces report errors. Partial reports preserve unaffected turns. Execution
errors never become quality scores. Unexpected programming errors propagate.

## Findings, uncertainty and limits

| Finding | Interpretation within the supplied reference boundary |
| --- | --- |
| `supported` | Eligible reviewed numeric reference agrees |
| `contradicted` | Eligible reviewed numeric reference disagrees |
| `unsupported` | Explicitly reviewed complete reference set establishes absence of support |
| `indeterminate` | Extraction, subject, authority or applicability is unresolved |

Excluded questions, negations and other recognized non-claims have no finding.
No detected claim is no assurance. Findings and counts do not create a Score,
PASS/FAIL verdict, regression gate or measured agent-grounding rate;
`agent_grounding` remains `not_assessed`.

V1 recognizes a narrow English clause grammar, including “SUBJECT has a waterproof
rating of VALUE UNIT”, with exact mm/cm/m conversion. Unknown paraphrases may be
missed without an abstention. Pronouns, fuzzy/multiple-product attribution,
unsupported units and broader product truth remain outside scope. Hashes verify
integrity, not source authority or physical product performance. The frozen
synthetic acceptance set is small and visible, not a blind generalization test.
See the [contract](salesagent-grounding-diagnostics-v1.md),
[ADR](adr/0008-numeric-waterproof-diagnostics.md) and
[verification record](plans/salesagent-waterproof-grounding-diagnostics.md).
