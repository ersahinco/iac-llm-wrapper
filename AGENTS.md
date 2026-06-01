# AGENTS.md

## Project: iac-llm-wrapper / intent-engine core

Core engine for `iac-llm-wrapper`, an intent-to-IaC orchestration framework. It
captures architecture intent from prose, validates decisions through requirement
graphs and target contracts, and emits traceable handoff artifacts that engineers
use with their IaC toolchain. Generation or controlled IaC execution stays
downstream unless a registered pattern owns it and passes graph, contract, and
gate checks.

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
uv run pre-commit run --all-files
```

## Architecture

- **Models** (`models.py`): Pydantic v2 intent data models. Pattern-specific models drive extraction, graph sync, validation, and artifact emission.
- **Extract** (`extractor.py`): Single graph-driven `Extractor`. Prompts come from requirement nodes, not regex or fixed document layout. Without LLM, deterministic fallback applies graph defaults and structured Markdown entity recovery.
- **Patterns** (`patterns.py`): Lean registry for pluggable product paths. Current built-ins: `aws-lza`, `cloudformation-parameters`, `kubernetes-cluster`, `terraform-vpc`.
- **Requirements** (`requirements.py`): Decision graph with `applies_if`, `blocked_if`, `depends_on`, cascade rules, tradeoffs, compliance controls, signals, and audit trail.
- **Interview** (`interview.py`): Graph-ordered requirement capture. Shows context, asks only applicable gaps, supports save/resume, and records rationale.
- **Validate** (`validator.py`): Fail-closed graph and pattern validation. Missing required applicable decisions become compile errors.
- **Generate** (`generator.py`): Registry-driven emitter for decision report, generic handoff plan, contract handoff files, lineage, runbook, module inputs when pattern owns module mapping, sample recommendations, and static review artifacts.
- **Contracts** (`contracts.py`): Target artifact contracts define required files, paths, decisions, lineage, and stable value assertions.
- **Samples** (`sample_config.py`): Registered reference bundles with pinned source metadata, module refs, tags, fixture dirs, and match recommendations.
- **LLM** (`llm_caller.py`): Pluggable OpenAI-compatible and Ollama backends with retry/backoff and evidence capture.
- **CLI** (`cli.py`): `compile`, `interview`, `validate`, `explain`, `sample`, `contract`, `graph`, `discover`, `template`, `review`. Default pattern is `aws-lza`.

## Current Pattern Surface

- `aws-lza`: Contract-backed AWS LZA handoff path. Emits official-style LZA YAML artifacts, decision report, lineage manifest, deployment runbook, and sample recommendations. Does not emit deployable Terraform/Terragrunt landing-zone stacks.
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
6. Validate and emit handoff artifacts for engineers.

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

T18: Clarify handoff boundary, evidence hygiene, and private pattern guidance

### Status

- **Tests**: 308 passing, 1 skipped
- **Lint**: clean
- **Format**: clean
- **Type check**: clean
- **Repo**: `github.com/ersahinco/iac-llm-wrapper` (private)
- **Last session**: Added `handoffReadiness` alongside the legacy `deploymentReadiness` key, switched human-facing wording to handoff readiness, defaulted LLM CLI compiles to preserve `raw-evidence.yaml`, documented raw evidence hygiene/private patterns, refreshed eval expectations, compacted session memory; full gate green

### Done

- Core: graph-driven extraction/discovery/interview/validation, pattern registry, contracts, handoff generation, static review, contract validation, benchmark/battle artifacts, sample matching, and CLI commands are implemented and covered.
- Built-ins: `aws-lza`, `cloudformation-parameters`, `kubernetes-cluster`, and `terraform-vpc` are contract-backed handoff paths. Current built-ins make no cloud API calls and do not deploy from prose.
- Evaluation: deterministic extraction corpus, role usability trials, forbidden-artifact checks, fixture drift guard, contract validation tests, battle-summary tests, static review tests, and full repo gate are green.
- Cleanup: removed stale LZA research/extension/diff/apply/default-normalizer surfaces, no-contract artifact fallback, pattern `extra_artifacts`, duplicate fixture normalization, and stale duplicate LLM docs.
- Language: user-facing docs now prefer handoff readiness; `deploymentReadiness` remains a legacy compatibility alias in artifacts.

### Next

1. Run local LLM usability with evidence output when new models are available; deterministic usability remains green.
2. Use `scripts/battle-test.py`, `battle-summary.yaml`, `model-benchmark.yaml`, and `scripts/compare-model-benchmarks.py` to tune prompts only when deterministic harness cannot classify the issue.
3. Continue AWS LZA schema depth only where real customer inputs justify it.
4. Keep private pattern work package-local until a real consumer needs packaged external distribution; do not add a generic loader speculatively.

### Durable Decisions

- Core stays domain-agnostic; pattern packages own models, graphs, contracts, validators, samples, and generators.
- Graph and contracts own readiness. LLM output is evidence until accepted by graph requirements and artifact contracts.
- Handoff artifacts are not deployments. `handoffReadiness` is the clearer term; legacy `deploymentReadiness` stays for backward compatibility.
- Raw LLM evidence is important and should be preserved for observability, but treated as customer design material and kept out of accidental commits.
- Built-ins are enough until a team has proprietary modules, controls, sample bundles, or gates that justify private patterns.
