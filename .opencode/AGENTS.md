# OpenCode Instructions

Use the root [AGENTS.md](../AGENTS.md) as the source of truth for project
architecture, naming, quality gates, session state, and current priorities.

OpenCode and Codex contributors should follow the same development workflow:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run --extra dev mypy
uv run python scripts/sync-sample-fixtures.py --check
uv run python scripts/evaluate-extraction.py
uv run python scripts/evaluate-usability.py
uv run pre-commit run --all-files
```

Keep changes lean:

- `iac-llm-wrapper` is the primary CLI/package name.
- `intent-engine` is the core engine and optional alias.
- Patterns own domain models, graphs, contracts, validators, samples, and generators.
- Core stays generic; do not add provider-specific branches to core modules.
- Current built-ins emit validated handoff artifacts and do not deploy.
- Future target adapters require graph, contract, manual gate, evidence, and rollback checks.

When in doubt, read `README.md`, `SPEC.md`, and `CONTRIBUTING.md`, then prefer
the smallest change that keeps those documents true.
