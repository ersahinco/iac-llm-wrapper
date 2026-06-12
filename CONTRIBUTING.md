# Contributing

Thanks for considering contributing to `iac-llm-wrapper`, the intent-to-IaC
orchestration framework. `intent-engine` is the core that owns requirement
graphs, target contracts, validation, and handoff artifacts.

## First Principles

- Core code is generic and lives under `src/intent_engine/core/`.
- Target-specific behavior lives under `src/intent_engine/patterns/`.
- LLM output is evidence. Graphs, validators, contracts, and artifact checks
  decide acceptance.
- New docs need a distinct audience or durable workflow. Prefer improving or
  deleting existing docs over adding a new file.
- Readiness claims need tests, contracts, or real owner evidence. For AWS LZA
  downstream-readiness claims, use
  [docs/LZA_DOWNSTREAM_VALIDATION.md](docs/LZA_DOWNSTREAM_VALIDATION.md).

## Repo Map

```text
src/intent_engine/core/       # Generic graph, extraction, validation, contracts, artifacts
src/intent_engine/patterns/   # Pattern-owned models, graphs, validators, generators, samples
scripts/                      # Evals, fixture sync, benchmark comparison, dev views
fixtures/                     # Checked-in sample bundles and authored trial inputs
tests/                        # Unit, integration, pattern, CLI, and product-language tests
tests/results/                # Ignored local evidence; only .gitkeep is tracked
docs/                         # Reference docs and owner-facing checklists
```

`fixtures/` are checked-in product examples. `tests/results/` and `out/` are
local evidence. Do not cite local output as owner validation unless a real
downstream owner, command, pipeline, or schema result produced it.

## Change Matrix

| Change | Start here | Usual checks |
| --- | --- | --- |
| Docs only | `README.md`, `docs/`, product-language tests | `uv run pytest tests/core/test_product_language.py`, `uv run ruff format --check .`, `uv run ruff check .` |
| AWS LZA field or validation | `src/intent_engine/patterns/aws_lza/` | Pattern tests, golden journey, fixture drift |
| Generic graph or validation behavior | `src/intent_engine/core/requirements.py`, `validator.py`, `compiler.py` | Core tests, pattern tests, extraction/usability evals |
| Artifact shape | `contracts.py`, `generator.py`, pattern generators | Contract tests, fixture drift, golden journey |
| Prompt/model behavior | Pattern `prompt_context`, extractor, eval fixtures | Deterministic evals plus LLM-backed evals from `docs/LLM_SETUP.md` |
| New pattern | `docs/PATTERN_AUTHORING.md`, `docs/EXTENSION.md` | Pattern check, compile test, fixture/eval coverage |

## Local Setup

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev,llm]"
uv run pytest
```

## Full Gate

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run --extra dev mypy
uv run --extra dev pyright .
uv run python scripts/sync-sample-fixtures.py --check
uv run python scripts/evaluate-golden-journey.py
uv run python scripts/evaluate-extraction.py
uv run python scripts/evaluate-usability.py
uv run pre-commit run --all-files
```

For small changes, run the smallest relevant subset from the change matrix.
Extraction, pattern, or prompt changes should also use the LLM-backed workflows
in [docs/LLM_SETUP.md](docs/LLM_SETUP.md) when model behavior matters.

## Code conventions

- **Type safety**: Pydantic v2 models for all data structures. No `dict` for domain objects.
- **Pattern-driven**: New target path = new pattern, not modifications to core code.
- **Data-driven**: New requirement = new `Requirement` node. The LLM prompt, interview questions, defaults, validation, and artifact emission all update automatically.
- **No arbitrary IaC generation**: Current paths emit validated handoff artifacts,
  not deployable infrastructure from prose. Future pattern-owned execution paths
  must run behind graph, contract, gate, evidence, and rollback checks.

## PR Checklist

- State the user or reviewer problem first.
- Name the pattern or core subsystem touched.
- Explain whether artifact shape changed.
- Include the smallest relevant command output.
- Attach real AWS LZA owner evidence before claiming downstream validation.

## Code of conduct

Be respectful. Assume good faith. Disagreement is fine; personal attacks are not.
