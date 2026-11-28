# ai-test-harness

Python eval orchestration harness. src layout, package name `harness`.

Follow [AGENTS.md](AGENTS.md), the primary development instructions, including
planning, testing, independent QA, human approval, security and scientific rules.

# Commands

Use the checkout's local `.venv` from the repository root. See
[development setup and checks](README.md#development) for locked provisioning,
`PYTHONPATH=src` and test/lint/type-check commands. Prefer focused test files while
iterating; format only files relevant to the change.

# Architecture rules
- Core (`harness/core`) must stay dependency-free: no provider SDKs,
  no eval libraries. Those belong in packs as optional extras.
- New scorers implement the Scorer Protocol; new adapters implement the
  Target Protocol (see targets/base.py). Don't invent parallel interfaces.
- Scorer `name`s are public API — never rename existing ones.
- Quality failures return low Scores; only infrastructure problems raise.

# Workflow

Use ordinary feature branches and the review process in AGENTS.md. Record
significant design decisions concisely in the existing `docs/adr/` when useful.
