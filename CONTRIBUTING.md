# Contributing

Thanks for considering contributing to `iac-llm-wrapper`, the intent-to-IaC
orchestration framework. `intent-engine` is the core that owns requirement
graphs, target contracts, validation, and handoff artifacts.

## How to contribute

1. **Fork the repo** and create a feature branch from `main`.
2. **Write tests** for your changes.
3. **Run quality gates** before committing:

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev,llm]"
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run --extra dev mypy
uv run python scripts/sync-sample-fixtures.py --check
uv run python scripts/evaluate-extraction.py
uv run python scripts/evaluate-usability.py
uv run pre-commit run --all-files
```

CI also runs coverage, dependency audit, static security scan, and SBOM generation:

```bash
uv run pytest --cov=src/intent_engine --cov-fail-under=80
uv run pip-audit --skip-editable
uv run bandit -c bandit.yaml -r src -q -ll
```

4. **Test extraction quality** (mandatory for extraction changes):

This project is **LLM-assisted and deterministic-first for acceptance**. The LLM
extracts candidate decisions from prose. The deterministic harness decides what
is acceptable. The fallback path (graph defaults plus structured Markdown
recovery) is not sufficient for real narrative design documents. Every change
that affects extraction, patterns, or prompts must be validated with an LLM:

Use deterministic evals for fixture drift and LLM-backed evals when validating
prompt/model behavior:

```bash
uv run python scripts/evaluate-extraction.py
uv run python scripts/evaluate-usability.py
uv run python scripts/evaluate-extraction.py --llm --provider ollama --model qwen2.5:7b
uv run python scripts/evaluate-usability.py --llm --provider ollama --model qwen2.5:7b
```

The deterministic fallback (`INTENT_ENGINE_DISABLE_LLM=1`) exists for unit tests and CI bootstrapping only. It applies defaults and does keyword matching — it cannot parse free-form prose. Do not treat it as a production extraction path.

5. **Open a pull request** describing the problem and solution.

## Extension guide

Use [docs/GLOSSARY.md](docs/GLOSSARY.md) for shared project language. Use
[docs/PATTERN_AUTHORING.md](docs/PATTERN_AUTHORING.md) as the checklist for
adding or changing a pattern. See [docs/EXTENSION.md](docs/EXTENSION.md) for the
exact API contract for new target patterns and requirements.

## Code conventions

- **Type safety**: Pydantic v2 models for all data structures. No `dict` for domain objects.
- **Pattern-driven**: New target path = new pattern, not modifications to core code.
- **Data-driven**: New requirement = new `Requirement` node. The LLM prompt, interview questions, defaults, validation, and artifact emission all update automatically.
- **No arbitrary IaC generation**: Current paths emit validated handoff artifacts, not deployable infrastructure from prose. Future target adapters must run behind graph, contract, gate, evidence, and rollback checks.

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
