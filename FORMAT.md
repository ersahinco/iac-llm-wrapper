# Formatting and Quality

This project uses standard Python tooling. There is no custom formatter or
project-specific style dialect.

## Python

- Format with Ruff.
- Lint with Ruff.
- Keep line length at 100 characters.
- Type check with mypy.
- Prefer Pydantic v2 models for domain data.
- Keep target-specific logic in `src/intent_engine/patterns/*`.

```bash
uv run ruff check .
uv run ruff format --check .
uv run --extra dev mypy
```

## Markdown

- Use clear headings and short sections.
- Keep root docs conventional: `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`,
  `RELEASING.md`, `SECURITY.md`, `SPEC.md`, `FORMAT.md`, `CODEOWNERS`.
- Use `AGENTS.md` for agent workflow and session state.
- Do not duplicate project rules across tool-specific agent files; point back to
  `AGENTS.md`.

## YAML

- Generated YAML artifacts include a schema comment and are checked through
  contract tests.
- Hand-authored workflow/config YAML must pass pre-commit `check-yaml`.
- Refresh generated sample fixtures with:

```bash
uv run python scripts/sync-sample-fixtures.py
```

Check fixture drift with:

```bash
uv run python scripts/sync-sample-fixtures.py --check
```

## Pre-Commit

Install hooks with:

```bash
uv run pre-commit install
```

Run all hooks with:

```bash
uv run pre-commit run --all-files
```
