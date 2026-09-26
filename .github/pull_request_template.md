## What changed

- Describe the problem and the fix (or the feature and why it matters).
- Link any related issues.

## Quality gates

- [ ] `uv run --locked --extra dev pytest` passes
- [ ] `uv run --locked --extra dev ruff check .` is clean
- [ ] `uv run --locked --extra dev mypy` is clean
- [ ] `NEO4J_PASSWORD=... uv run --locked --extra dev pytest tests/test_graph.py` passes (graph changes only; local development database)
- [ ] `opa check --strict src/intent_engine/policy` is clean (policy changes only)

## Risk

- **Low**: tests pass, follows existing structure
- **Medium**: novel approach or unclear requirements
- **High**: changes the emitted artifact shape or the graph model

## Value

What does this give the architect or the reviewer?
