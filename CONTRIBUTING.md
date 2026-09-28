# Contributing

Start with the [quickstart](README.md#quickstart). For a change, describe an observed
problem, keep the patch focused, and explain how you verified it. Use sanitised
examples in issues and tests; keep client packets, credentials and generated
bundles out of contributions. Contributions use the [Apache 2.0 license](LICENSE).

## Local checks

Use Python 3.11+ and [uv](https://docs.astral.sh/uv/). From the repository root:

```bash
uv sync --locked --extra dev --extra graphrag
env -u NEO4J_PASSWORD uv run --locked --extra dev --extra graphrag pytest
uv run --locked --extra dev --extra graphrag ruff check .
uv run --locked --extra dev --extra graphrag mypy
```

This skips database tests. GraphRAG model calls in automated tests are controlled;
passing tests do not establish live model answer quality.

## Full suite with Neo4j and OPA

Graph tests erase the database they connect to. Use a dedicated test project,
separate from saved client cases, and choose unused ports. Install OPA on the host
(`brew install opa` on macOS); CI pins its version in
[ci.yml](.github/workflows/ci.yml).

```bash
export COMPOSE_PROJECT_NAME=iac-tests
export NEO4J_BROWSER_PORT=28474 NEO4J_BOLT_PORT=28687
docker compose up -d --wait neo4j
export NEO4J_URI="bolt://127.0.0.1:${NEO4J_BOLT_PORT}"
export NEO4J_USER=neo4j NEO4J_PASSWORD=localdevpassword NEO4J_DATABASE=neo4j
opa check --strict src/intent_engine/policy samples/organisation/policy.rego
opa fmt --fail --list src/intent_engine/policy samples/organisation/policy.rego
uv run --locked --extra dev --extra graphrag pytest
docker compose stop
unset NEO4J_URI NEO4J_USER NEO4J_PASSWORD NEO4J_DATABASE
unset COMPOSE_PROJECT_NAME NEO4J_BROWSER_PORT NEO4J_BOLT_PORT
```

The full suite should finish without skips. Stopping retains the test volume.
No model downloads, cloud credentials or deployment are required.

## Change boundaries

Add a regression check when behavior changes. Reuse Neo4j/Cypher, GraphRAG, OPA
and JSON Schema before introducing custom code or dependencies. New questions,
checks and output mappings need a concrete case and explicit coverage limits.
Preserve source evidence, human confirmation and export gates. Keep deployment
and approvals in the consuming team's pipeline.

The code map and invariants are in [AGENTS.md](AGENTS.md). CI runs lint, types,
Python 3.11–3.13 tests, real Neo4j checks and an LZA export journey. Include the
checks you ran and any skipped coverage in your pull request.
