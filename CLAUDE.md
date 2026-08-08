# ai-test-harness

Python eval orchestration harness. src layout, package name `harness`.

# Commands
- Run tests: `uv run pytest -v` (prefer single test files while iterating)
- Lint/format: `uv run ruff check .` and `uv run ruff format .`
- Type check: `uv run mypy src/`
- Always use `uv run` / `uv add` — never pip or plain python

# Architecture rules
- Core (`harness/core`) must stay dependency-free: no provider SDKs,
  no eval libraries. Those belong in packs as optional extras.
- New scorers implement the Scorer Protocol; new adapters implement the
  Target Protocol (see targets/base.py). Don't invent parallel interfaces.
- Scorer `name`s are public API — never rename existing ones.
- Quality failures return low Scores; only infrastructure problems raise.

# Workflow
- Branch per feature (feat/<name>), PR into main. Never commit to main.
- Every code change lands with tests. Run pytest and show output before
  claiming done.
- Significant design decisions get a one-page ADR in docs/adr/.