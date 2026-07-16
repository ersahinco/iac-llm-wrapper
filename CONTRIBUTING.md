# Contributing

Thanks for considering contributing to `iac-llm-wrapper`, the registered target
configuration handoff framework. `intent-engine` is the core that owns requirement
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
- Related-work inspired features must map to owner evidence, decision
  validation, sample alignment, review clarity, or registered-target contract
  depth. Do not add synth/deploy runners, dashboards, plugin loaders, or broad
  schema expansion without repeated evidence.

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
| Docs only | `README.md`, `docs/`, product-language tests | `uv run --locked --extra dev pytest tests/core/test_product_language.py`, `uv run --locked --extra dev ruff format --check .`, `uv run --locked --extra dev ruff check .` |
| AWS LZA field or validation | `src/intent_engine/patterns/aws_lza/` | Pattern tests, golden journey, fixture drift |
| Generic graph or validation behavior | `src/intent_engine/core/requirements.py`, `validator.py`, `compiler.py` | Core tests, pattern tests, extraction/usability evals |
| Artifact shape | `contracts.py`, `generator.py`, pattern generators | Contract tests, fixture drift, golden journey |
| Prompt/model behavior | Pattern `prompt_context`, extractor, eval fixtures | Deterministic evals plus LLM-backed evals from `docs/LLM_SETUP.md` |
| New pattern | `docs/PATTERN_AUTHORING.md`, `docs/EXTENSION.md` | Pattern check, compile test, fixture/eval coverage |

## Local Setup

Install the uv version required by `pyproject.toml`; CI reads the same setting.

```bash
uv sync --locked --extra dev
uv run --locked --extra dev pytest
```

## Full Gate

```bash
uv run --locked --extra dev pytest
uv run --locked --extra dev ruff check .
uv run --locked --extra dev ruff format --check .
uv run --locked --extra dev mypy
uv run --locked --extra dev pyright .
uv run --locked --extra dev python scripts/sync-sample-fixtures.py --check
uv run --locked --extra dev python scripts/evaluate-golden-journey.py
uv run --locked --extra dev python scripts/evaluate-extraction.py
uv run --locked --extra dev python scripts/evaluate-usability.py
uv run --locked --extra dev prek run --all-files
uv build --build-constraint build-constraints.txt --require-hashes
```

For small changes, run the smallest relevant subset from the change matrix.
Extraction, pattern, or prompt changes should also use the LLM-backed workflows
in [docs/LLM_SETUP.md](docs/LLM_SETUP.md) when model behavior matters.

## Shift-left checks

`prek` runs checks that this repository installs and enforces: Ruff,
YAML/TOML hygiene, mypy, Pyright, and fixture drift. It does not register
external tools that silently pass when their executable is missing.

Use `iac-llm-wrapper shift-left checkov` when an owner-provided IaC path needs
recorded Checkov evidence. Other scanners belong in the owner pipeline that
installs, configures, and enforces them.

## Evidence discipline

- Tie new behavior to a real packet, target contract, review failure, or measured gap.
- Keep provider decisions in the owning pattern; do not add provider branches to core.
- Prefer one authoritative representation over parallel reports, aliases, and adapters.
- Make checks fail when evidence is missing; never turn an unavailable tool into a green check.
- Test observable behavior and artifact contracts, not the presence of feature-shaped text.
- Delete unused paths and compatibility layers once their caller or migration window is gone.

## Code conventions

- **Type safety**: Use Pydantic v2 models at domain and untrusted-input boundaries.
  Use dataclasses or typed mappings for cohesive internal state, and plain mappings
  for serialized artifact payloads where the target contract owns the shape.
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
