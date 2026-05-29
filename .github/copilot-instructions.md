# GitHub Copilot Instructions

Follow the root `AGENTS.md` for architecture, naming, quality gates, and current
session state.

Project rules:

- Primary project and CLI name: `iac-llm-wrapper`.
- Core engine name: `intent-engine`.
- Keep core modules generic; target-specific behavior belongs in pattern packages.
- Do not generate deployable IaC from prose. Emit validated handoff artifacts unless
  a future target adapter has graph, contract, gate, evidence, and rollback checks.
- Update tests and docs for user-facing behavior changes.

Required local checks:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run --extra dev mypy
uv run python scripts/sync-sample-fixtures.py --check
uv run python scripts/evaluate-extraction.py
uv run python scripts/evaluate-usability.py
```
