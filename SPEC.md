# Specification

## Goal

`iac-llm-wrapper` is an intent-to-IaC orchestration framework. It turns design
prose or structured Markdown into validated decision records and handoff
artifacts for existing IaC accelerators, modules, and provisioning toolchains.

The core engine is `intent-engine`. It owns extraction orchestration,
requirement graphs, target contracts, validation, lineage, and artifact
emission.

## Scope

- Extract architecture intent with an LLM when available.
- Preserve explicit structured Markdown decisions ahead of LLM guesses.
- Apply deterministic defaults only through graph/model rules.
- Validate decisions fail-closed through requirement graphs, pattern validators,
  and target contracts.
- Emit traceable handoff artifacts for engineers.
- Persist sample recommendations and LLM trace summaries as artifacts.
- Support multiple target patterns without provider-specific core branches.

## Non-Goals

- No cloud API calls from current built-ins.
- No direct deployment.
- No arbitrary Terraform, CloudFormation, CDK, or Kubernetes generation from prose.
- No provider-specific branches in core CLI, compiler, extractor, generator,
  validator, or normalizer modules.
- No dashboards or long-running orchestration service in the current CLI path.

## Current Patterns

| Pattern | Purpose | Boundary |
|---|---|---|
| `aws-lza` | AWS Landing Zone Accelerator handoff | Emits official-style LZA YAML, lineage, runbook, samples, and readiness artifacts. Does not emit a parallel landing-zone stack. |
| `cloudformation-parameters` | BYOM CloudFormation parameter handoff | Emits parameter handoff for an approved existing template. Does not generate a stack. |
| `kubernetes-cluster` | Kubernetes cluster handoff | Emits cluster/namespace handoff with optional Terraform EKS module input references. |
| `terraform-vpc` | BYOM Terraform VPC module input capture | Emits module variables/tfvars handoff for an existing module. |

## Interfaces

- CLI: `iac-llm-wrapper compile|interview|validate|discover|template|sample|contract|explain|review`
- Optional CLI alias: `intent-engine`
- Pattern registry: `PatternRegistry.register/get/list`
- Requirement graph: `RequirementGraph.add/decide/apply_decisions/apply_to_intent`
- Contracts: `TargetContract` plus artifact, decision, lineage, and value assertions
- LLM backend: `LLMCaller.call(prompt) -> (response, LLMEvidence)`
- Fixtures: versioned sample bundles under `fixtures/*-v1`

## Invariants

- Every accepted decision is recorded in the graph audit trail.
- Compile output is blocked when applicable required decisions are missing or contradictory.
- LLM-reported gaps and contradictions only block when they target known applicable graph nodes.
- Explicit structured Markdown decisions take precedence over direct LLM decisions.
- Direct LLM decisions take precedence over signal decisions.
- Defaults fill only remaining applicable gaps.
- Contract-backed patterns emit `handoff-plan.yaml`.
- Blocked compile output emits only safe assessment artifacts.
- New target patterns register through pattern packages and must not require core provider branches.
- Sample fixture drift is checked by `scripts/sync-sample-fixtures.py --check`.

## Quality Gates

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

Run LLM-backed evals locally when changing extraction, prompts, graph wording, or
pattern behavior:

```bash
uv run python scripts/evaluate-extraction.py --llm --provider ollama --model qwen2.5:7b
uv run python scripts/evaluate-usability.py --llm --provider ollama --model qwen2.5:7b
```

## High-Value Next Work

1. Run local LLM usability with evidence output when Ollama is available.
2. Tune prompts only from trace/eval findings that deterministic checks cannot classify.
3. Add AWS LZA schema depth only for real customer identity/network/security inputs.
4. Keep packaging names aligned if publishing changes: `iac-llm-wrapper` is the
   distribution and CLI; `intent-engine` is the core and optional alias.
