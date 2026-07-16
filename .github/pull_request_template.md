## What changed

- Describe the problem and the fix (or the feature and why it matters).
- Link any related issues.

## Quality gates

- [ ] `uv run --locked --extra dev pytest` passes
- [ ] `uv run --locked --extra dev ruff check .` is clean
- [ ] `uv run --locked --extra dev ruff format --check .` is clean
- [ ] `uv run --locked --extra dev mypy` is clean
- [ ] `uv run --locked --extra dev pyright .` is clean
- [ ] `uv run --locked --extra dev python scripts/sync-sample-fixtures.py --check` is clean
- [ ] `uv run --locked --extra dev python scripts/evaluate-extraction.py` is clean
- [ ] `uv run --locked --extra dev python scripts/evaluate-usability.py` is clean
- [ ] `uv run --locked --extra dev python scripts/evaluate-golden-journey.py` is clean
- [ ] `uv run --locked --extra dev prek run --all-files` passes
- [ ] `uv run --locked --extra dev pytest --cov=src/intent_engine --cov-fail-under=80` passes

## Risk

- **Low**: tests pass, follows existing patterns
- **Medium**: novel approach or unclear requirements
- **High**: significant architectural change

## Stakeholder value

What does this give the architect / engineer / compliance reviewer?
