# Test taxonomy and dataset selection

Milestones 1–2 provide case classification, versioned fingerprints,
descriptor-aware loading, deterministic selection, and definition-only previews.
Suite models/execution, v2 runner support, result snapshots, grouped reports,
and UI are not implemented yet. Do not send classified v2 cases to the legacy
runner, which still computes a v1 hash after execution.

The harness owns the mechanism; dataset authors own opaque category, tag, and
risk values. Risk does not alter scoring, gates, or weights. Definitions never
contain latest execution status or PASS/FAIL results.

## Author a descriptor and JSONL cases

```json
{
  "schema_version": "dataset-descriptor-v1",
  "id": "example-evaluation",
  "version": "study-v1",
  "title": "Example evaluation",
  "description": "An authored collection.",
  "cases": "cases.jsonl",
  "extra": {"origin": {"revision": 1}},
  "fingerprint_scheme": "dataset-cases-v2"
}
```

The schema version, ID, authored version, case binding, and fingerprint scheme
are required. Title/description default to null and `extra` defaults to `{}`.
Only this schema and v2 case fingerprints are supported by the new loader.
There is no second metadata dictionary.

`cases` is a local relative file binding interpreted from the descriptor's
directory, independently of process cwd. URLs, absolute paths (including
Windows drive paths), backslash bindings, and parent traversal are rejected.
Nested paths within the descriptor directory are supported; resolved symlinks
must also stay inside it. The authored binding remains unchanged in the
descriptor; resolved absolute paths are I/O context, not fingerprint content.

Every nonblank JSONL line contains an ordinary TestCase, for example:

```json
{"id":"case-a","input":"alpha","reference":"alpha","title":"First example","category":"family-a","tags":["quick","cross-cutting"],"risk":"high","extra":{"origin":{"revision":1}}}
```

Input is a string or object; reference is a string, object, or null. Extra is
arbitrary finite JSON metadata. Title/description/category/risk are optional.
Category expresses primary classification, tags cross-cutting classification,
and risk declared criticality. These values are not registered in core.

`load_dataset()` validates the entire case file before returning anything for
selection. It rejects unknown top-level fields, duplicate JSON keys at any
depth, non-finite numbers (including overflow), blank/duplicate IDs, invalid
types, and blank/duplicate/non-string tags. ID, category, risk, tags, dataset
ID/version, and selector values reject leading/trailing whitespace. Internal
whitespace remains significant and allowed. Values/order are never trimmed,
lowercased, sorted, or deduplicated. Non-null title must be nonblank; description
may be empty or whitespace prose. Case errors report file and physical line;
duplicate-ID errors identify both lines. Diagnostics omit whole case bodies.

The legacy `load_cases(path)` is unchanged and continues its existing permissive
behavior. Strict checks live in the new authoring path, not in legacy callers.

## Load and preview without targets or scorers

```python
from harness.core.dataset import load_dataset
from harness.core.selection import CaseSelection, preview_selection, select_cases

dataset = load_dataset("tests/fixtures/taxonomy/organization/dataset.json")
selection = CaseSelection(categories=["family-a"], tags_any=["quick"])
selected = select_cases(dataset.cases, selection)
preview = preview_selection(dataset, selection)
print(preview.model_dump_json(indent=2))
```

`LoadedDataset` holds the descriptor, ordered TestCases, resolved descriptor/case
paths, full case fingerprint, and descriptor fingerprint. It supports model/JSON
round-tripping and verifies supplied fingerprints against its content. Nested
case/metadata objects remain mutable; preview revalidates all in-memory source
content, including unselected cases, and rejects stale fingerprints. Reload the
source file after edits. Preview does not automatically reread files from disk.

`select_cases()` accepts an already validated sequence, returns references to
matching TestCases in original order, and never mutates inputs. For descriptor-
bound inputs, load the complete dataset first or use `preview_selection()` to
also check its current content and fingerprints. Legacy duplicate tags do not
duplicate returned cases; duplicate source IDs are rejected as ambiguous.

| Selector behavior | Meaning |
| --- | --- |
| Omitted selection / `{}` | All cases |
| Multiple fields | AND across fields |
| `case_ids`, `categories`, `risks` | OR within each array |
| `tags_any` | At least one requested tag |
| `tags_all` | Every requested tag |
| Comparison | Exact, case-sensitive; missing category/risk does not match |
| Order | Original dataset order, never requested-ID order |
| Supplied empty/null arrays or duplicate values | Validation error |
| Unknown explicit ID | Error before applying taxonomy filters |
| ID selectors with taxonomy filters | Intersection |
| No matching cases | Valid preview, `executable: false` |

The fixture example selects `case-a` out of three cases. Preview returns dataset
ID/version, descriptor/full/selected fingerprints and scheme names, the authored
selector, ordered IDs, counts, `executable`, and an empty-selection reason.
It contains no case input/reference or arbitrary metadata bodies. Its
`executable: true` means only that membership is nonempty; no target/scorer
capability or execution preflight has occurred. There is no suite execution API.

## Fingerprints and compatibility

The descriptor hash is the existing canonical JSON fingerprint of its normalized
authored fields, including `schema_version: dataset-descriptor-v1`, explicit
default nulls/empty extra, relative binding, and all authored metadata. Derived
hashes and absolute I/O paths are not included. A descriptor-only description or
metadata edit changes this hash without changing the case-content fingerprint.

Full and selected case hashes use `dataset-cases-v2` as defined in
[ADR 0006](adr/0006-versioned-case-definitions-and-suites.md). They bind ordered
case definitions, including classification, expectations, and metadata. The
empty subset also has a deterministic hash. Authored version labels, descriptor
hashes, full case hashes, and selected case hashes are separate concepts.

The frozen legacy dataset hashes and synthetic replay/calibration compatibility
fixture remain unchanged. Suite fingerprint pins, execution-time payload policy,
and historical result snapshots are reserved for the next milestone; these
previews do not create or persist a RunResult.
