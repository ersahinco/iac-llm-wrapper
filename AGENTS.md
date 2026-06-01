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

T17: Harden lean intent-to-IaC orchestration surface

### Status

- **Tests**: 305 passing, 1 skipped
- **Lint**: clean
- **Format**: clean
- **Type check**: clean
- **Repo**: `github.com/ersahinco/iac-llm-wrapper` (private)
- **Last session**: Added the compact architecture map, optional extraction `eval-results.yaml` artifact, handoff-plan semantic tests, and deterministic ready/blocked battle-test verification; full gate green

### Done

| Area | Item |
|------|------|
| Core | models, extractor, requirements, lazy built-in pattern registry, patterns, pattern check, interview, discovery, validator, generator, graph export, static review, review renderer, contracts, contract validation, battle summary, samples, module mapping, CLI |
| Patterns | `aws-lza`, `cloudformation-parameters`, `kubernetes-cluster`, `terraform-vpc` |
| AWS LZA | Contract-backed LZA handoff YAML, IAM Identity Center permission sets/assignments, decision report/readiness, lineage manifest, deployment runbook, sample recommendations, focused pattern modules |
| Contracts | Required artifacts, required paths, required decisions, lineage checks, value assertions, blocked assessment artifacts, contract-backed generic handoff plan |
| Samples | Registry-backed `sample list/show`, match recommendations, fixture sync/drift guard |
| LLM | Ollama/OpenAI-compatible backend factory, evidence store, provider token usage capture, local LLM integration tests, graph-scoped prompts and blocking findings |
| Evaluation | Deterministic extraction gold corpus with AWS LZA standard/complex/blocked cases and CloudFormation pass/fail cases, trace quality assertions, optional `eval-results.yaml` output, handoff-plan semantic tests, battle-summary verdict unit tests for artifact, safety, model, and review failures, pattern-check unit tests, static review context unit tests, benchmark comparison script tests, contract-validation unit tests, sample fixture sync tests, optional LLM evidence capture, and role-based usability trials including CloudFormation BYOM |
| Fixtures | AWS LZA emitted bundles, K8s emitted bundle, usability docs, eval corpus |
| Cleanup | Removed old LZA research path, old diff/apply surfaces, extension registry, old fixtures/tests/helpers, global normalizer/defaults no-op surface, unused discovery hook fields, no-contract artifact fallback, overlapping capability doc |
| Product docs | Standard root docs (`README`, `CONTRIBUTING`, `CHANGELOG`, `RELEASING`, `SECURITY`) plus lean architecture map, glossary, artifact reference, and pattern authoring docs define current DevOps workflow, product boundary, artifacts, and shared language |
| Observability | Lean `llm-trace-summary.yaml`, `model-benchmark.yaml`, `contract-validation.yaml`, `battle-summary.yaml`, static review page, graph export links, raw evidence links, benchmark comparison, and contract validation details for provider/model, rounded latency, token availability, cost-estimation status, raw and accepted decisions, applied decisions, resolved/blocking gaps, blocking contradictions, raw evidence status, and battle verdicts; old flat aliases removed |
| Language | Docs now use consistent terms: intent, decision, raw LLM decision, requirement graph, target contract, handoff artifact, readiness, allowed next action, pattern, battle test, evidence, provisioning toolchain; use pattern-owned paths instead of target adapters |

### Next

1. Run local LLM usability with evidence output when new models are available; deterministic usability remains green.
2. Use `scripts/battle-test.py`, `battle-summary.yaml`, `model-benchmark.yaml`, and `scripts/compare-model-benchmarks.py` to tune prompts only when deterministic harness cannot classify the issue.
3. Continue AWS LZA schema depth only where real customer inputs justify it.
4. Keep repo-internal docs lean: product scope in `README.md`/`docs/`, workflow in `CONTRIBUTING.md`/`AGENTS.md`; avoid new docs unless they reduce repeated explanation.

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
- OpenCode and GitHub Copilot guidance now point back to root `AGENTS.md`; custom parallel command files were removed to avoid competing workflows.
- Release workflow uses `uv build`; `pyproject.toml` uses SPDX license metadata to avoid setuptools deprecation warnings.
- Product scope lives in `README.md`/`docs/`; contributor workflow lives in `CONTRIBUTING.md`/`AGENTS.md`.
- Defaults now live in Pydantic models and requirement graph nodes; there is no global `defaults.yaml` or no-op normalizer path.
- AWS LZA pattern code is split by responsibility: registration, graph, validators, generators, samples, and helpers.
- Discovery is graph-owned; unused pattern-specific consistency/signal hook fields were removed.
- Artifact validation is contract-owned; pattern-level no-contract artifact fields were removed.
- README and AWS LZA docs now describe only current graph-backed behavior; stale CI/CD, hybrid, network appliance, and normalization claims were removed.
- Template/suggestion category fallbacks now match current built-in pattern categories.
- `model-benchmark.yaml` is derived from existing trace data; it records run mode, provider/model, latency, token availability, readiness, decision/gap/contradiction counts, parse errors, cost-estimation status, and the boundary that external tools may visualize it but readiness stays graph/contract-owned.
- `scripts/compare-model-benchmarks.py` stays a simple table utility for local benchmark comparisons and has direct subprocess tests for useful output and missing inputs.
- OpenAI-compatible backends preserve provider token usage when the API reports it; local models that do not report usage remain explicit `not-reported` instead of guessed.
- Static review HTML now writes and links `requirement-graph.json` plus `requirement-graph.mmd`, links trace/benchmark/raw-evidence artifacts, renders contract validation pass/fail details, and has direct context tests without adding a server or JS app.
- `docs/ARTIFACTS.md` documents emitted artifacts, owners, consumers, emission conditions, and the non-deployment boundary.
- `contract-validation.yaml` behavior is directly tested for ready bundles, blocked bundles, unknown patterns, missing artifacts, and stable schema/header output.
- `scripts/sync-sample-fixtures.py` behavior is directly tested for drift messages, timestamp normalization, missing fixture dirs, and check-mode no-write behavior.
- `scripts/battle-test.py` writes repeatable local bundles under ignored `tests/results/` and emits `battle-summary.yaml` with a verdict, confidence categories, findings, and improvement items.
- Battle-summary scoring lives in `src/intent_engine/core/battle_summary.py`; `scripts/battle-test.py` stays a thin local harness runner.
- Battle-summary confidence states are `pass`, `fail`, `improvement`, and `expected-weakness`; the compact contract is documented in `docs/GLOSSARY.md`.
- Battle summaries treat expected blocked cases as pass when they remain blocked for clear graph/contract reasons and still emit review/validation artifacts.
- LLM battles can pass with `expected-weakness` findings when deterministic Markdown carried the value and the model added no accepted decisions; that limitation becomes an explicit improvement item instead of hidden optimism.
- The latest AWS LZA complex deterministic run was ready with 20 accepted decisions, and the local `llama3.2:3b` run was ready with 4437 tokens, 81410.2 ms latency, 20 accepted decisions, zero parse errors, contract validation pass, and model confidence marked as expected weakness.
- `iac-llm-wrapper pattern check --pattern aws-lza` is backed by `src/intent_engine/core/pattern_check.py`; it validates graph shape, contract graph alignment, expected artifact names, and sample fixture presence.
- `docs/GLOSSARY.md` owns ubiquitous language; `docs/PATTERN_AUTHORING.md` owns the contributor checklist, while `docs/EXTENSION.md` remains the detailed API contract.
- `docs/ARCHITECTURE.md` is the compact product flow map; avoid longer design essays unless they replace repeated explanation.
- `scripts/evaluate-extraction.py --output` writes artifact-first `eval-results.yaml` while preserving the existing console table.
- `handoff-plan.yaml` semantics are directly tested for ready and blocked paths so the artifact remains useful rather than merely present.
