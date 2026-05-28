# Contributing

Thanks for considering contributing to intent-engine.

## How to contribute

1. **Fork the repo** and create a feature branch from `main`.
2. **Write tests** for your changes.
3. **Run quality gates** before committing:

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev,llm]"
uv run pytest --cov=src/intent_engine --cov-fail-under=80
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python scripts/sync-sample-fixtures.py --check
uv run pip-audit --skip-editable
uv run bandit -c bandit.yaml -r src -q -ll
```

4. **Test extraction quality** (mandatory for extraction changes):

This project is **LLM-first**. The deterministic fallback (graph defaults + keyword matching) is not sufficient for real design documents. Every change that affects extraction, patterns, or prompts must be validated with an LLM:

Use `uv run python scripts/evaluate-extraction.py` for deterministic fixture drift and
`uv run python scripts/evaluate-extraction.py --llm` when validating prompt/model behavior.

The deterministic fallback (`INTENT_ENGINE_DISABLE_LLM=1`) exists for unit tests and CI bootstrapping only. It applies defaults and does keyword matching — it cannot parse free-form prose. Do not treat it as a production extraction path.

5. **Open a pull request** describing the problem and solution.

## Extension guide

See [EXTENSION.md](EXTENSION.md) for the exact contract for adding new patterns and requirements.

## Code conventions

- **Type safety**: Pydantic v2 models for all data structures. No `dict` for domain objects.
- **Pattern-driven**: New use cases = new pattern, not modifications to core code.
- **Data-driven**: New requirement = new `Requirement` node. The LLM prompt, interview questions, defaults, validation, and generation all update automatically.
- **No IaC generation**: This tool produces decision artifacts, not deployable infrastructure.

## Getting started

```bash
# Clone
git clone https://github.com/ersahinco/iac-llm-wrapper
cd iac-llm-wrapper

# Set up virtualenv
uv venv
source .venv/bin/activate

# Install with dev + LLM dependencies
uv pip install -e ".[dev,llm]"

# Run tests
uv run pytest

# Optional: install pre-commit hooks
uv run pre-commit install
```

## Required checks on `main`

PRs should pass all CI jobs:

- `lint` (ruff, format, type check, fixture drift check)
- `test` (multi-version tests with coverage threshold)
- `security` (`pip-audit`, `bandit`, SBOM generation)
- `pre-commit` (optional but recommended — lower friction for reviewers)

Branch protection should enforce:

- Required review from `CODEOWNERS` for core framework changes.
- No direct pushes to `main` — all changes through PR.
- Required status checks (`lint`, `test`, `security`) must pass before merge.

## Code of conduct

Be respectful. Assume good faith. Disagreement is fine; personal attacks are not.
