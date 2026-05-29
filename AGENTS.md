# AGENTS.md

## Project: iac-llm-wrapper / intent-engine core

Core engine for `iac-llm-wrapper`, an intent-to-IaC orchestration framework. It
captures architecture intent from prose, validates decisions through requirement
graphs and target contracts, and emits traceable handoff artifacts that engineers
use with their IaC toolchain. Future target adapters may wrap module generation
or controlled IaC execution only after graph, contract, and gate checks pass.

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
- **Patterns** (`patterns.py`): Lean registry for pluggable product paths. Current built-ins: `aws-lza`, `cloudformation-parameters`, `kubernetes-cluster`, `terraform-vpc`.
- **Requirements** (`requirements.py`): Decision graph with `applies_if`, `blocked_if`, `depends_on`, cascade rules, tradeoffs, compliance controls, signals, and audit trail.
- **Interview** (`interview.py`): Graph-ordered requirement capture. Shows context, asks only applicable gaps, supports save/resume, and records rationale.
- **Normalize** (`normalizer.py`): Deterministic defaults from config/model data. No hidden provider calls.
- **Validate** (`validator.py`): Fail-closed graph and pattern validation. Missing required applicable decisions become compile errors.
- **Generate** (`generator.py`): Registry-driven emitter for decision report, generic handoff plan, contract handoff files, lineage, runbook, module inputs when pattern owns module mapping, and sample recommendations.
- **Contracts** (`contracts.py`): Target artifact contracts define required files, paths, decisions, lineage, and stable value assertions.
- **Samples** (`sample_config.py`): Registered reference bundles with pinned source metadata, module refs, tags, fixture dirs, and match recommendations.
- **LLM** (`llm_caller.py`): Pluggable OpenAI-compatible, Ollama, or Anthropic backends with retry/backoff and evidence capture.
- **CLI** (`cli.py`): `compile`, `interview`, `validate`, `explain`, `sample`, `contract`, `discover`, `template`, `review`. Default pattern is `aws-lza`.

## Current Pattern Surface

- `aws-lza`: Thin AWS LZA handoff path. Emits official-style LZA YAML artifacts, decision report, lineage manifest, deployment runbook, and sample recommendations. Does not emit deployable Terraform/Terragrunt landing-zone stacks.
- `cloudformation-parameters`: BYOM CloudFormation parameter handoff for an approved existing template. Emits parameters and decision report, not a stack.
- `kubernetes-cluster`: Contract-backed K8s handoff for cluster/namespace config with optional Terraform EKS module input references.
- `terraform-vpc`: BYOM Terraform AWS VPC module input capture. Emits module variables/tfvars handoff for an existing module, not root deployment scaffolding.

## Key Decisions

- Core stays domain-agnostic. Use-case logic lives in pattern packages.
- Graph owns decision order, branching, blocked paths, cascades, gaps, provenance, and deployment sequencing.
- Existing accelerators/modules are contracts/data models before they are generation or execution targets.
- Current built-ins make no AWS API calls and do not deploy. No arbitrary Terraform from prose.
- "Wrapper" means intent-to-IaC workflow orchestration, not bypassing IaC tools or gates.
- Sample recommendations must persist as artifacts, not terminal-only hints.
- `src/intent_engine/patterns/aws_lza` is the only AWS LZA path. Old research path was removed to avoid two-source confusion.

## Fixtures

- `fixtures/aws-lza-standard-v1/`, `fixtures/aws-lza-regulated-v1/`, `fixtures/aws-lza-healthcare-v1/`: emitted AWS LZA sample handoff bundles.
- `fixtures/k8s-cluster-v1/`: emitted K8s sample handoff bundle.
- `fixtures/usability/`: role trials for architect gap capture, engineer handoff, BYOM Terraform, and BYOM CloudFormation parameter flow.
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

T17: Harden lean intent-to-IaC orchestration surface

### Status

- **Tests**: 272 passing, 1 skipped
- **Lint**: clean
- **Format**: clean
- **Type check**: clean
- **Repo**: `github.com/ersahinco/iac-llm-wrapper` (private)
- **Last session**: Aligned root DevOps docs and agent guidance; OpenCode/Copilot now share `AGENTS.md`; release build and packaging metadata verified; full gate green

### Done

| Area | Item |
|------|------|
| Core | models, extractor, requirements, lazy built-in pattern registry, patterns, interview, discovery, normalizer, validator, generator, contracts, samples, module mapping, CLI |
| Patterns | `aws-lza`, `cloudformation-parameters`, `kubernetes-cluster`, `terraform-vpc` |
| AWS LZA | Thin LZA handoff YAML, IAM Identity Center permission sets/assignments, decision report/readiness, lineage manifest, deployment runbook, sample recommendations |
| Contracts | Required artifacts, required paths, required decisions, lineage checks, value assertions, blocked assessment artifacts, contract-backed generic handoff plan |
| Samples | Registry-backed `sample list/show`, match recommendations, fixture sync/drift guard |
| LLM | Ollama/OpenAI-compatible/Anthropic backend factory, evidence store, local LLM integration tests, graph-scoped prompts and blocking findings |
| Evaluation | Deterministic extraction gold corpus with AWS LZA and CloudFormation pass/fail/contract cases, trace quality assertions, optional LLM evidence capture, and role-based usability trials including CloudFormation BYOM |
| Fixtures | AWS LZA emitted bundles, K8s emitted bundle, usability docs, eval corpus |
| Cleanup | Removed old LZA research path, old diff/apply surfaces, extension registry, old fixtures/tests/helpers |
| Product docs | Standard root docs (`README`, `CONTRIBUTING`, `CHANGELOG`, `RELEASING`, `SECURITY`, `SPEC`, `FORMAT`) define current lean DevOps workflow and product boundary |
| Observability | Lean `llm-trace-summary.yaml` for provider/model, rounded latency, raw and accepted decisions, applied decisions, resolved/blocking gaps, blocking contradictions, and raw evidence status; old flat aliases removed |
| Language | Docs now use consistent terms: requirement graph, target contract, decision record, handoff artifact, provisioning toolchain |

### Next

1. Run local LLM usability with evidence output when Ollama is available; deterministic usability remains green.
2. Use local LLM trace quality findings to tune prompts only when deterministic harness cannot classify the issue.
3. Continue AWS LZA schema depth only where real customer inputs justify it.
4. If public packaging changes, keep naming aligned: `iac-llm-wrapper` is primary CLI/package, `intent-engine` is core/optional alias.

### Key Decisions This Session

- Primary CLI/package name is `iac-llm-wrapper`; `intent-engine` remains the core engine and optional CLI alias.
- Generic `handoff-plan.yaml` is emitted from existing graph/contract/readiness metadata; it records owners, order, gates, rollback, boundary, and allowed next action without deployment.
- Generic `handoff-plan.yaml` is now shape-validated by the `generic-handoff-plan` contract for all contract-backed patterns.
- AWS LZA IAM Identity Center now requires approved permission sets and assignments before handoff.
- AWS LZA Identity Center missing-decision errors are graph-owned; pattern validators only keep cross-field/format checks.
- CloudFormation BYOM is parameter handoff for an existing approved template, not stack generation.
- Extraction eval trace expectations are mode-aware: deterministic expects no raw evidence request, LLM expects captured evidence.
- Kubernetes cluster pattern is handoff-first; Terraform EKS module inputs are optional references, not root deployment scaffolding.
- LLM-reported gaps and contradictions only block when they target known requirement graph nodes; model-invented non-contract findings stay raw trace evidence.
- Extractor prompts now tell models to use only schema keys for decisions, signal decisions, gaps, and contradictions.
- The global pattern registry lazily loads built-in patterns on first `get()`/`list()` so core API tests do not depend on CLI imports or suite order.
- Decision precedence is deterministic: structured Markdown beats direct LLM decisions, direct LLM decisions beat signal decisions, defaults fill only remaining gaps.
- OpenCode and GitHub Copilot guidance now point back to root `AGENTS.md`; bespoke cavekit/spec command files were removed to avoid competing workflows.
- `SPEC.md` is now a current product spec, and `FORMAT.md` is standard formatting/quality guidance.
- Release workflow uses `uv build`; `pyproject.toml` uses SPDX license metadata to avoid setuptools deprecation warnings.
