## What changed

- Describe the problem and the fix (or the feature and why it matters).
- Link any related issues.

## Quality gates

- [ ] `uv run pytest` passes
- [ ] `uv run ruff check .` is clean
- [ ] `uv run ruff format --check .` is clean
- [ ] `uv run mypy` is clean
- [ ] `uv run python scripts/sync-sample-fixtures.py --check` is clean
- [ ] `uv run pytest --cov=src/intent_engine --cov-fail-under=80` passes

## Risk

- **Low**: tests pass, follows existing patterns
- **Medium**: novel approach or unclear requirements
- **High**: significant architectural change

## Stakeholder value

What does this give the architect / engineer / compliance reviewer?
