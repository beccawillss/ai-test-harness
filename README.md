# AI Test Harness

Independent evaluation for agents, RAG systems, chatbots and LLM-backed APIs.
Project priorities and development standards are maintained in [AGENTS.md](AGENTS.md).

## Development

Use a permanent checkout (the primary workspace is
`~/Developer/ai-test-harness-dev`). From its root, provision dependencies with uv
and the Python version selected by `.python-version`:

```sh
uv sync --locked --no-install-project
```

This includes the development group from `uv.lock` without building/installing
the project. Dependency provisioning may need downloads; add `--offline` when all
required dependencies are cached. Routine checks use the existing local `.venv`
without synchronizing or changing dependencies. `PYTHONPATH=src` selects this
checkout's source without requiring an installed package:

```sh
PYTHONPATH=src .venv/bin/python -m pytest -q --ignore=tests/test_canary_controller.py
.venv/bin/ruff check src tests examples
.venv/bin/ruff format --check src tests examples
PYTHONPATH=src .venv/bin/mypy src
```

The regression command retains the historical exclusion of
`tests/test_canary_controller.py`, which starts a local listening server. Exercise
that module separately as integration testing in an environment that permits
loopback listening and has the required application dependencies. Other optional
application/SDK integration tests also require their explicit opt-ins and supported
environments. Report exclusions and skips; they are not passing results. These
integration tests use synthetic provider responses, not live AI calls.

Choose relevant test files/checks according to the change; see AGENTS.md for
verification and review requirements. Default tests are offline and deterministic.
Live integrations and Study execution require separate explicit approval and
their applicable controls.

See [test taxonomy, suites and reporting](docs/test-taxonomy-and-suites.md) for
descriptor authoring, validation, fingerprints, suite execution, grouped evidence
and qualified comparisons. The [offline example](examples/taxonomy_suites.py)
requires an explicit output directory and uses only deterministic fakes.
