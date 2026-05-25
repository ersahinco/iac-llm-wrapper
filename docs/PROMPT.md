# Session Prompt: OSS Hardening and Developer Experience

## Current Goal

Ship `iac-llm-wrapper` as a modern open source Python project with:

- `uv` as the default dependency workflow
- strong type safety expectations
- strict quality gates (lint, format, tests)
- practical security checks
- excellent CLI user and developer experience

## Constraints

- Keep architecture honest: this is a decision capture and validation engine, not an IaC generator.
- Preserve model-driven design: requirement graph changes should flow into extraction/interview/validation/generation automatically.
- Do not break existing patterns/addons or CLI behavior.

## Work Plan

### 1) uv-first contributor workflow

- [ ] Ensure all docs use `uv` commands for setup and development.
- [ ] Keep `pip install iac-llm-wrapper` for end-user install, but default contributor path to `uv venv` + `uv pip install -e ".[dev,llm]"`.
- [ ] Align CI and local command examples where practical.

### 2) Type safety baseline

- [ ] Document typed-domain expectations (Pydantic models over untyped dicts for domain objects).
- [ ] Add a dedicated type-checking plan (mypy or pyright) and phase it in without breaking velocity.
- [ ] Add CI hook for type checks once baseline noise is manageable.

### 3) Quality gates

- [ ] Keep Ruff lint + format + pytest as mandatory gates.
- [ ] Verify command snippets are copy/paste ready.
- [ ] Ensure CONTRIBUTING and README communicate the same quality contract.

### 4) Security checks

- [ ] Add dependency vulnerability scanning (`pip-audit` or equivalent) in CI.
- [ ] Add static security linting (`bandit` or equivalent) with pragmatic allowlist.
- [ ] Document threat model boundary: no cloud API calls, no direct deployment.

### 5) CLI UX hardening

- [ ] Review `--help` output for all primary commands (`compile`, `discover`, `interview`, `validate`, `catalog`, `template`, `review`).
- [ ] Ensure examples use realistic docs/fixtures and pattern/addon combinations.
- [ ] Improve error clarity for common failures (missing input file, invalid decisions JSON, unsupported pattern/addon).

## Suggested Command Set

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev,llm]"

uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## Success Criteria

1. README and CONTRIBUTING clearly promote `uv` for contributor workflows.
2. Quality gates are explicit, consistent, and CI-enforced.
3. Type-safety direction is documented with an actionable rollout path.
4. Security checks are integrated or scheduled with clear ownership.
5. CLI onboarding from `--help` to first successful `compile` is smooth.

## Honest Scope

The project outputs validated, traceable decision artifacts. Engineers use those artifacts with their chosen IaC modules and deployment systems. This repository does not directly deploy infrastructure.
