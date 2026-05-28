# AGENTS.md

## Project: intent-engine

Pre-provisioning infrastructure decision engine. It captures architecture intent
from prose, validates decisions through requirement graphs and target contracts,
and emits traceable handoff artifacts that engineers use with their IaC toolchain.

AWS Landing Zone Accelerator is the first product path, but the core must stay generic: patterns own domain models, contracts, validators, samples, and generators.

## Commands

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run --extra dev mypy
uv run python scripts/sync-sample-fixtures.py --check
uv run python scripts/evaluate-extraction.py
uv run python scripts/evaluate-usability.py
```

## Architecture

- **Models** (`models.py`): Pydantic v2 intent data models. Pattern-specific models drive extraction, graph sync, validation, and artifact emission.
- **Extract** (`extractor.py`): Single graph-driven `Extractor`. Prompts come from requirement nodes, not regex or fixed document layout. Without LLM, deterministic fallback applies graph defaults and structured Markdown entity recovery.
- **Patterns** (`patterns.py`): Lean registry for pluggable product paths. Current built-ins: `aws-lza`, `kubernetes-cluster`, `terraform-vpc`.
- **Requirements** (`requirements.py`): Decision graph with `applies_if`, `blocked_if`, `depends_on`, cascade rules, tradeoffs, compliance controls, signals, and audit trail.
- **Interview** (`interview.py`): Graph-ordered requirement capture. Shows context, asks only applicable gaps, supports save/resume, and records rationale.
- **Normalize** (`normalizer.py`): Deterministic defaults from config/model data. No hidden provider calls.
- **Validate** (`validator.py`): Fail-closed graph and pattern validation. Missing required applicable decisions become compile errors.
- **Generate** (`generator.py`): Registry-driven emitter for decision report, contract handoff files, lineage, runbook, module inputs when pattern owns module mapping, and sample recommendations.
- **Contracts** (`contracts.py`): Target artifact contracts define required files, paths, decisions, lineage, and stable value assertions.
- **Samples** (`sample_config.py`): Registered reference bundles with pinned source metadata, module refs, tags, fixture dirs, and match recommendations.
- **LLM** (`llm_caller.py`): Pluggable OpenAI-compatible, Ollama, or Anthropic backends with retry/backoff and evidence capture.
- **CLI** (`cli.py`): `compile`, `interview`, `validate`, `explain`, `sample`, `contract`, `discover`, `template`, `review`. Default pattern is `aws-lza`.

## Current Pattern Surface

- `aws-lza`: Thin AWS LZA handoff path. Emits official-style LZA YAML artifacts, decision report, lineage manifest, deployment runbook, and sample recommendations. Does not emit deployable Terraform/Terragrunt landing-zone stacks.
- `kubernetes-cluster`: Contract-backed K8s handoff for cluster, namespace, module input, and sample fixture behavior.
- `terraform-vpc`: BYOM Terraform AWS VPC module input capture. Emits module variables/tfvars handoff for an existing module, not root deployment scaffolding.

## Key Decisions

- Core stays domain-agnostic. Use-case logic lives in pattern packages.
- Graph owns decision order, branching, blocked paths, cascades, gaps, provenance, and deployment sequencing.
- Existing accelerators/modules are contracts/data models, not custom stacks to generate.
- No AWS API calls. No deployment. No arbitrary Terraform from prose.
- Sample recommendations must persist as artifacts, not terminal-only hints.
- `src/intent_engine/patterns/aws_lza` is the only AWS LZA path. Old research path was removed to avoid two-source confusion.

## Fixtures

- `fixtures/aws-lza-standard-v1/`, `fixtures/aws-lza-regulated-v1/`, `fixtures/aws-lza-healthcare-v1/`: emitted AWS LZA sample handoff bundles.
- `fixtures/k8s-cluster-v1/`: emitted K8s sample handoff bundle.
- `fixtures/usability/`: role trials for architect gap capture, engineer handoff, and BYOM module flow.
- `fixtures/eval/`: extraction gold corpus with expected handoff artifact checks.
- Version suffixes (`-v1`) are fixture contract versions. They protect emitted artifact shape from silent drift.

## Model-Driven Flow

1. Architect writes Markdown or runs interview.
2. Extractor asks LLM for graph decisions, or deterministic fallback applies explicit structured inputs plus defaults.
3. Graph applies decisions in dependency order and records provenance.
4. Discovery reports applicable gaps and detected signals.
5. Interview fills only missing applicable decisions.
6. Normalize, validate, and emit handoff artifacts for engineers.

## Extension Contract

Add new target path by registering a pattern with:

- Pydantic intent model.
- Requirement graph.
- Optional target contract.
- Optional sample configs.
- Optional validators/generators/module mapping.

Do not add provider-specific branches to core CLI/compiler/extractor/generator.

## Stack

Python 3.11+, Pydantic v2, Typer, ruamel.yaml, networkx, pytest, ruff, mypy.

## Session State

<!-- UPDATE THIS SECTION AT END OF EVERY SESSION -->

### Current Goal

T16: Keep product path lean and current

### Status

- **Tests**: 263 passing, 1 skipped
- **Lint**: clean
- **Format**: clean
- **Type check**: clean
- **Repo**: `github.com/ersahinco/iac-llm-wrapper` (private)
- **Last session**: Cleaned product language: `iac-llm-wrapper` is package/CLI, `intent-engine` is pre-provisioning decision engine; full gate green

### Done

| Area | Item |
|------|------|
| Core | models, extractor, requirements, patterns, interview, discovery, normalizer, validator, generator, contracts, samples, module mapping, CLI |
| Patterns | `aws-lza`, `kubernetes-cluster`, `terraform-vpc` |
| AWS LZA | Thin LZA handoff YAML, decision report/readiness, lineage manifest, deployment runbook, sample recommendations |
| Contracts | Required artifacts, required paths, required decisions, lineage checks, value assertions, blocked assessment artifacts |
| Samples | Registry-backed `sample list/show`, match recommendations, fixture sync/drift guard |
| LLM | Ollama/OpenAI-compatible/Anthropic backend factory, evidence store, local LLM integration tests |
| Evaluation | Deterministic extraction gold corpus with pass/fail/contract cases and role-based usability trials |
| Fixtures | AWS LZA emitted bundles, K8s emitted bundle, usability docs, eval corpus |
| Cleanup | Removed old LZA research path, old diff/apply surfaces, extension registry, old fixtures/tests/helpers |
| Product docs | README defines repo/package name vs product role: `iac-llm-wrapper` ships `intent-engine`; not an IaC wrapper |
| Observability | Lean `llm-trace-summary.yaml` for provider/model, calls, decisions, gaps, contradictions, and raw evidence path |
| Language | Docs now use consistent terms: requirement graph, target contract, decision record, handoff artifact, provisioning toolchain |

### Next

1. Add one non-Terraform BYOM trial (CDK or CloudFormation) if `terraform-vpc` trial stays clean.
2. Continue AWS LZA schema depth where real customer identity inputs exist, especially IAM Identity Center permission sets and assignments.
3. Run local LLM usability/eval periodically with evidence output to validate actual architect/engineer experience beyond deterministic harness checks.
4. Use local LLM trace quality findings to tune prompts only when deterministic harness cannot classify the issue.
5. If public packaging changes, decide whether to keep `iac-llm-wrapper` as distribution name or rename to `intent-engine` before GA.

### Key Decisions This Session

- Repo/package name can remain `iac-llm-wrapper`, but product language must say it is not an IaC wrapper.
- Use "pre-provisioning decision engine" and "handoff artifacts" instead of vague wrapper/generator language.
- Order of documented flow must match code: extraction/interview, normalization, validation, artifact emission.
