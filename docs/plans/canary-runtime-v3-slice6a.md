# C3b Slice 6a: synthetic signed approval contract and offline verification

## Authorised scope and baseline

Independent human QA approved this bounded implementation on 2026-11-22.
GitHub main was freshly observed at `fc2d63dc4c96547b223044b137b90bc91bbed384`,
tree `cd7a7b1ff6b77f8019c01e41740b7981393275d2`. That exact commit was fetched
and one isolated worktree created at
`/private/tmp/ai-test-harness-canary-runtime-v3-slice6a`, branch
`feat/canary-runtime-v3-slice6a-approval`. No existing workspace was reset,
cleaned, pruned or overwritten. Existing development changes and worktree
registrations, including unavailable historical registrations, are preserved.

Only these additions are authorised:

- `src/harness/canary/approval_v3.py`
- `tests/test_canary_approval_v3.py`
- This plan.

No existing production/test file, dependency, lock, fixture, dataset, fingerprint
or historical evidence may change. No commit, push, PR or merge is authorised.
No real identity enrolment, credentials, provider/billing requests, judge, Study,
consumption store, journal creation or controller integration is authorised.

## Design and interfaces

The manifest is a strict immutable, versioned synthetic/offline contract. Its
proposed execution embeds the existing immutable SourceApprovalReceipt, whose
DefinitionBinding already covers roster, fixtures, inference, policies and limits.
An explicit source-receipt SHA-256 must match that receipt. The signed proposal
also includes its authorisation ID, audience, synthetic project/organisation and
optional nonsecret synthetic provisioning reference. The surrounding manifest
binds purpose, environment, namespace, issuer, canonical UTC times and explicit
false judge/Study/replacement/resume/live authority fields.

The independently supplied expected proposal prevents signed but unrelated
configurations or identifiers from being substituted. The separately supplied
synthetic trust policy fixes principal, one Ed25519 public key, roles, revocations
and maximum validity. The signed artifact cannot supply its own trust policy.

OpenSSH `ssh-keygen -Y verify` verifies exact supplied canonical JSON bytes in a
dedicated approval namespace, distinct from future review/sealing. Only public
verification material and detached signatures reach private temporary files.
No production signing helper exists. The verifier uses a fixed system executable,
explicit arguments, a stripped environment, a timeout and a checked success
protocol. Missing/incompatible verification fails closed, without installation.

All public parsing/verification errors use fixed privacy-safe categories. Exact
canonical round trips reject duplicate keys, unknown/default-omitted fields,
coercions, alternate decimal/time spellings and signed-byte normalisation.
Clock input is explicit. Validity is half-open: not-before <= now < expiry.
Created <= not-before < expiry; total validity is at most one hour and may be
tightened by trusted policy. Verification is repeatable and has no replay store.

Successful results distinguish structure, signature, synthetic signer/role,
expected proposal binding, time and supplied revocation policy. Source matching
is not performed. Real-human identity, provider authentication and live authority
remain false. A synthetic signature is never permission to execute a canary.

## Milestones

- [x] Verify remote baseline and preserve local state; create isolated worktree.
- [x] Inspect existing source contracts, policies and verification environment.
- [x] Implement only the approval module and synthetic tests.
- [x] Exercise actual system OpenSSH, malformed input, binding, time and privacy.
- [x] Run source/policy regressions and full locked offline suite, excluding the
  historical listening-server controller module.
- [x] Run Ruff, mypy, changed-file formatting and whitespace checks.
- [x] Verify all baseline bytes/modes and existing workspace statuses unchanged.
- [x] Record exact results, limitations and PR-preparation recommendation; stop
  for independent human QA without commit/publication.

## Verification strategy

Reuse the existing Slice 2 locked CPython 3.12 environment without syncing or
installing dependencies. Run with an empty environment plus system PATH,
PYTHONPATH=src and disabled bytecode/test caches. Confirm installed package
versions against the unchanged harness lock before using the environment.
System OpenSSH observed: OpenSSH_9.9p2 / LibreSSL 3.3.6. Signature tests generate
temporary synthetic keys only, exercise the real verifier without optional skips,
and remove key material on fixture teardown. Fake clocks make time checks stable.

Tests cover cryptographic tampering, unknown/principal/namespace/role/revocation
failures; every source/configuration binding; exact validity boundaries; strict
JSON/types/canonicalization; unavailable/misbehaving verifier; independent trust;
identifier substitution; immutable false authority flags; and no ambient SSH,
credential, network, provider or private diagnostic discovery.

Preservation compares every tracked baseline file's actual bytes and executable
mode with its Git object, recomputes historical C1 and approved v3 identities,
and checks unchanged locks/fixtures/datasets through that complete inventory.
Existing journal/fault/controller/policy tests retain their approved semantics.

## Results and limitations

Completed on the current uncommitted source:

| Check | Actual result |
| --- | --- |
| Focused final approval suite | 169 passed, no skips, 4.51 seconds |
| Runtime/source, execution-policy and selection regressions | 258 passed, 1 optional skip, 3.57 seconds |
| Full locked offline harness suite | 3,799 passed, 6 optional skips, 543.63 seconds |
| Ruff across src/tests | PASS |
| Mypy across src | PASS, 62 source files |
| Changed Python formatting | PASS, both files |
| Tracked and three-addition whitespace checks | PASS |
| Baseline tracked byte/mode inventory | All 215 files exact |
| Historical C1, v2.1 and v3 identities | Exact approved values |
| Installed harness dependencies | Match unchanged lock versions |

The regression skip is `tests/test_canary_runtime_v3.py:452`: the optional
complete source fixture requires the separate pinned CPython 3.13 worker.
No signature-verifier test skips. The full suite excluded only historical
listening-server `tests/test_canary_controller.py`. Its six optional skips were:

- `tests/test_canary_controller_v3_application.py:26`: explicitly enabled pinned
  application integration suite; not enabled in this milestone.
- `tests/test_canary_instrumentation_v3_sdk.py:22`: optional pinned OpenAI 3.3.1
  runtime absent from the locked harness environment.
- `tests/test_canary_sdk.py:9`: optional OpenAI package absent.
- `tests/test_canary_selection_state.py:5`: optional pinned application runtime.
- `tests/test_canary_state.py:13`: optional pinned application runtime.
- `tests/test_canary_runtime_v3.py:452`: optional complete CPython 3.13 source check.

These skips are not represented as integration successes. No external application
or provider was launched. The full suite includes existing C1, journal/fault,
mock-only controller, instrumentation, driver and policy compatibility coverage.

Initial focused coverage passed 137 tests. Expanded coverage found a test helper
that reinserted a deliberately deleted receipt-digest field; that helper was
corrected without weakening parsing. The final 169-test run above includes the
correction, further contract boundaries and real OpenSSH revocation rejection.
Initial lint corrections removed unused imports and adopted Python 3.12 generic
syntax; final Ruff/mypy/format checks above all passed.

The harness lock SHA-256 remains
`a8a1997cb57cf88bad6d8b00e38efa0b62b77c2ad0057c667ab52933585b1dba`.
Dataset, fixtures, historical tracked evidence, journal/controller implementations
and all other existing files are covered by the complete byte/mode inventory.

Public interfaces:

- `serialize_manifest(manifest) -> bytes`: validates constructed/copied nested
  models, then returns canonical UTF-8 bytes. It neither signs nor saves.
- `parse_manifest(payload: bytes) -> ApprovalManifest`: accepts exact canonical
  bytes only; duplicate/unknown/missing fields and coercions fail privately.
- `verify_approval(payload, signature, *, expected, trust_policy, now)` returns
  `ApprovalVerification` only after actual authorised-signer verification.

Namespaces/roles are fixed to
`canary-approval-v3@ai-test-harness.invalid` and `synthetic-canary-approver`.
Manifest schema is `canary-synthetic-approval-v1`; trust schema is
`canary-synthetic-trust-v1`. Principals must use the `synthetic-...@canary.invalid`
format. Project/organisation/provisioning identifiers are explicitly synthetic.
Only source receipts with synthetic provenance and `offline-verification-v1`
are accepted; their v3 binding is validated against unchanged approved identities.

OpenSSH receives a fixed `/usr/bin/ssh-keygen -Y verify` invocation, private
temporary public-key/signature/revocation files, exact original payload bytes,
explicit principal/namespace and only PATH/LC_ALL/LANG environment variables.
It has a five-second timeout. Both zero exit status and the exact expected
OpenSSH success message/key fingerprint are required, with empty stderr. A
different success-output protocol is an explicit compatibility failure, not a
fallback. The synthetic key's actual OpenSSH revocation rejection is tested.

Clock input must be an aware UTC datetime at whole-second precision. Tests cover
start inclusion, expiry exclusion, one-hour maximum, tighter trusted-policy
boundaries, invalid dates/order/representations, and future/expired approvals.

Reproduction commands, from this worktree (no sync/install step):

```sh
env -i PATH=/usr/bin:/bin PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python -B -m pytest tests/test_canary_approval_v3.py -q --tb=short -rs -p no:cacheprovider
env -i PATH=/usr/bin:/bin PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python -B -m pytest tests/test_canary_runtime_v3.py tests/test_canary_execution_policy.py tests/test_canary_selection_v3.py -q --tb=short -rs -p no:cacheprovider
env -i PATH=/usr/bin:/bin PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python -B -m pytest -q --tb=short -rs -p no:cacheprovider --ignore=tests/test_canary_controller.py
env -i PATH=/usr/bin:/bin PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python -B -m ruff check --no-cache src tests
env -i PATH=/usr/bin:/bin PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python -B -m ruff format --check --no-cache src/harness/canary/approval_v3.py tests/test_canary_approval_v3.py
env -i PATH=/usr/bin:/bin PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python -B -m mypy --cache-dir=/private/tmp/canary-slice6a-mypy src
```

Whitespace checks include `git diff --check` for tracked files and
`git diff --no-index --check /dev/null <path>` for each of the three additions.
The latter returns 1 for a new-file difference, with empty output when there are
no whitespace findings. A first stripped-environment Python wrapper also saw a
benign Git/Darwin temporary-directory warning; direct Git checks had no findings.

No existing production files changed. The original development checkout retains
its original seven modified tracked files and two untracked entries. Available
Slice 2–5/controller, grounding and pinned Study harness worktrees were inspected
without changes; unavailable historical registrations were not repaired/pruned.

Trust policy and clock are supplied by a trusted caller. A software signature
does not establish a real person's identity, credential ownership, safe external
spending, single use, or a trustworthy Python process/host. Key revocation means
only the explicitly supplied synthetic policy; no online freshness is inferred.

## Independent-QA disposition

GO recommendation for preparing a PR after independent human QA of this exact
three-file slice. Feature HEAD remains the exact approved baseline, with only
the three authorised additions untracked/uncommitted. No commit, push, PR, merge,
authority consumption, admission/controller integration or later milestone was
performed. A verified synthetic approval still has source_authorised=false,
provider_evidence_authenticated=false, authorises_live_execution=false and
real_human_authorisation_authenticated=false. It grants no execution permission.
