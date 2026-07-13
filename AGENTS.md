# AGENTS.md

## Project: iac-llm-wrapper / intent-engine core

Core engine for `iac-llm-wrapper`, an architect-exchange-to-registered-target
configuration framework. It captures architecture intent from prose, validates
decisions through requirement graphs and target contracts, and emits traceable
target configuration artifacts that engineers use with existing deployment
mechanisms. Direct deployment and whole-IaC-from-scratch generation stay out of
runtime scope.

AWS Landing Zone Accelerator is the first product path: collected inputs become
contract-checked LZA YAML/config files for the downstream LZA deployment process.
The core must stay generic: patterns own domain models, contracts, validators,
samples, and target configuration emitters.

## Commands

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
uv run --extra dev prek run --all-files
```

## Architecture

- **Models** (`src/intent_engine/patterns/*/models.py`): Pydantic v2 intent data
  models. Pattern-specific models drive extraction, graph sync, validation,
  semantic model derivation, and artifact emission.
- **Extract** (`extractor.py`): Single graph-driven `Extractor`. Prompts come
  from requirement nodes, not regex or fixed document layout. Without LLM,
  deterministic fallback applies graph defaults and structured Markdown entity
  recovery.
- **Patterns** (`patterns.py`): Lean registry for pluggable product paths.
  Current built-ins: `aws-lza`, `cloudformation-parameters`,
  `kubernetes-cluster`, `terraform-vpc`.
- **Requirements** (`requirements.py`): Decision graph with `applies_if`,
  `blocked_if`, expression gates, dependencies, cascade rules, tradeoffs,
  compliance controls, signals, and audit trail.
- **Semantic model** (`semantic_model.py` + pattern `semantic.py`): Lightweight
  typed entities, relationships, and predicate constraint results for
  real-world dependencies without RDF/OWL, Datalog, or a graph database.
- **Interview** (`interview.py`): Graph-ordered requirement capture. Shows
  context, asks only applicable gaps, supports save/resume, and records
  rationale.
- **Validate** (`validator.py`): Fail-closed graph and pattern validation.
  Missing required applicable decisions become compile errors.
- **Generate** (`generator.py`): Registry-driven emitter for decision report,
  handoff plan, target configuration artifacts, lineage, runbook, module inputs
  when pattern-owned, sample recommendations, and static review artifacts.
- **Contracts** (`contracts.py`): Target artifact contracts define required
  files, paths, decisions, lineage, and stable value assertions.
- **Samples** (`sample_config.py`): Registered reference bundles with pinned
  source metadata, module refs, tags, fixture dirs, and match recommendations.
- **LLM** (`llm_caller.py`): Pluggable OpenAI-compatible, Bedrock-through-local
  AWS CLI, and Ollama backends with retry/backoff and evidence capture.
- **CLI** (`cli.py`): `compile`, `compile-git`, `interview`, `validate`,
  `explain`, `sample`, `contract`, `graph`, `discover`, `template`, `review`,
  `shift-left`, and AWS LZA validation helpers. Default pattern is `aws-lza`.

## Current Pattern Surface

- `aws-lza`: Contract-backed AWS LZA registered target path. Emits official-style
  LZA YAML target configuration artifacts, decision report, lineage manifest,
  deployment runbook, plan/replay metadata, target capability graph, and sample
  recommendations. It does not emit deployable Terraform/Terragrunt
  landing-zone stacks.
- `cloudformation-parameters`: BYOM CloudFormation parameter handoff for an
  approved existing template. Emits parameters and decision report, not a stack
  or deployment.
- `kubernetes-cluster`: Contract-backed Kubernetes handoff for
  cluster/namespace config with optional Terraform EKS module input references.
- `terraform-vpc`: BYOM Terraform AWS VPC module input capture. Emits module
  variables/tfvars handoff plus delivery metadata for an existing module,
  account, and owner pipeline; it does not emit root deployment scaffolding.

## Key Decisions

- Core stays domain-agnostic. Use-case logic lives in pattern packages.
- Graphs own decision order, branching, blocked paths, cascades, gaps,
  provenance, and handoff sequencing.
- Existing accelerators/modules are registered targets with contracts and data
  models before emitted configuration artifacts are trusted.
- Current compile/generation paths make no AWS API calls and do not deploy. The
  AWS LZA validation-only adapter may run the official local validator, which can
  perform read-only account lookup through the provided AWS/LZA context.
- "Wrapper" means architect exchange to registered target configuration, not
  bypassing IaC tools, accelerators, owner pipelines, or gates.
- Sample recommendations must persist as artifacts, not terminal-only hints.
- `src/intent_engine/patterns/aws_lza` is the only AWS LZA path.
- Handoff artifacts are not deployments. `handoffReadiness` and
  `handoffAllowed` are the canonical readiness fields.
- Secrets travel as secret-store references and expected parameter names, never
  raw values.
- Add data-modeling or graph depth only when real packets expose a missed
  relationship or repeated review failure.

## Fixtures

- `fixtures/aws-lza-standard-v1/`, `fixtures/aws-lza-regulated-v1/`,
  `fixtures/aws-lza-healthcare-v1/`: emitted AWS LZA sample handoff bundles.
- `fixtures/k8s-cluster-v1/`: emitted Kubernetes sample handoff bundle.
- `fixtures/usability/`: role trials for architect gap capture, engineer
  handoff, BYOM Terraform, and BYOM CloudFormation parameter flow.
- `fixtures/eval/`: extraction gold corpus with expected handoff artifact
  checks.
- Version suffixes (`-v1`) are fixture contract versions. They protect emitted
  artifact shape from silent drift.

## Model-Driven Flow

1. Architect writes Markdown or runs interview.
2. Extractor asks LLM for graph decisions, or deterministic fallback applies
   explicit structured inputs plus defaults.
3. Graph applies decisions in dependency order and records provenance.
4. Discovery reports applicable gaps and detected signals.
5. Interview fills only missing applicable decisions.
6. Validate and emit deterministic target configuration artifacts for engineers.

## Extension Contract

Add a new target path by registering a pattern with:

- Pydantic intent model.
- Requirement graph.
- Optional deployment target contract.
- Optional sample configs.
- Optional validators, target configuration emitters, policy packs, target
  capability report, or module mapping.

Do not add provider-specific branches to core CLI/compiler/extractor/generator.

## Stack

Python 3.11+, Pydantic v2, Typer, ruamel.yaml, pytest, ruff, mypy, pyright.

## Session State

<!-- UPDATE THIS SECTION AT END OF EVERY SESSION -->

### Current Goal

AWS LZA owner-validation readiness audit and lean repair.

### Status

- **Committed cleanup**: `606bd3e` removed redundant YAML helpers, unused hook
  metadata, a generic test docstring, and stale session memory.
- **Customer packet**: the banking AWS LZA packet compiles and reviews in
  ignored `tests/results/owner-readiness-banking-lza/`; handoff is allowed, but
  downstream plan readiness is blocked on owner account emails and explicit
  network/TGW plan inputs.
- **Fixes in progress**: static review links existing `contract-validation.yaml`;
  LZA diagnostics and review fallbacks prioritize placeholder account-email
  failures before AWS account lookup permission.
- **Evidence**: the base packet official LZA validation now reports
  `owner-account-email-required` (`Default email (audit@example.com) found.`).
  An ignored private plan-input variant with non-placeholder emails and
  network/TGW details reaches `aws-account-lookup-permission`, proving the repo
  side clears plan inputs before the owner AWS context gate.
- **Tests**: `uv run pytest` passed (452 passed, 1 skipped); focused review/LZA
  and review CLI tests passed.
- **Lint/format/type/hooks**: `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run --extra dev mypy`,
  `uv run --extra dev pyright .`, and
  `uv run --extra dev prek run --all-files` passed.
- **Remaining blocker**: downstream-clean AWS LZA evidence requires
  owner-approved account emails and an AWS/LZA validation context with read-only
  account lookup permission; no deploy/apply path was added.

### Durable Decisions

- Keep the product boundary narrow: registered target configuration handoff,
  contract checks, review evidence, and owner-controlled downstream execution.
- Prefer packet-driven fixes over imagined platform features.
- Prefer deletion and shared local helpers over new abstractions.
- Keep generated/ignored evidence out of committed source unless it is an
  intentional fixture or contract artifact.

### Next

1. Re-run official `iac-llm-wrapper lza validate` with owner-approved account
   emails and an AWS/LZA lookup-capable validation context.
2. If validation still fails, fix only packet-backed repo issues or record
   owner-side failures as downstream evidence.
