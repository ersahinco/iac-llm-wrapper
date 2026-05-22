# Contributing

Thanks for considering contributing to intent-engine.

## How to contribute

1. **Fork the repo** and create a feature branch from `main`.
2. **Write tests** for your changes.
3. **Run quality gates** before committing:

```bash
source .venv/bin/activate
python -m pytest        # all tests pass
ruff check .            # lint clean
ruff format --check .   # format clean
```

4. **Open a pull request** describing the problem and solution.

## Extension guide

See [EXTENSION.md](EXTENSION.md) for the exact contract for adding new patterns, addons, and requirements.

## Code conventions

- **Type safety**: Pydantic v2 models for all data structures. No `dict` for domain objects.
- **Pattern-driven**: New use cases = new pattern, not modifications to core code.
- **Data-driven**: New requirement = new `Requirement` node. The LLM prompt, interview questions, defaults, validation, and generation all update automatically.
- **No IaC generation**: This tool produces decision artifacts, not deployable infrastructure.

## Getting started

```bash
# Clone
git clone https://github.com/ersahinco/intent-engine
cd intent-engine

# Set up virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Install with dev + LLM dependencies
pip install -e ".[dev,llm]"

# Run tests
python -m pytest

# Optional: install pre-commit hooks
pip install pre-commit
pre-commit install
```

## Code of conduct

Be respectful. Assume good faith. Disagreement is fine; personal attacks are not.
