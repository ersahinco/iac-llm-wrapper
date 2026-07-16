# Glossary

Shared language for `iac-llm-wrapper`.

## Requirements-to-target handoff compiler

The product identity for this repository: a stateless compiler that resolves
architecture requirements into contract-checked artifacts for an approved
downstream target. The package name `iac-llm-wrapper` is historical; an LLM is
optional and has no transition authority.

## Atmos abstract component

A non-deployable Atmos catalog component with `metadata.type: abstract`. The
`terraform-vpc/intent-defaults` component carries replay-bound variables and
points to the approved root. An owner must inherit it from a real component and
provide runtime configuration in the owner repository.

## Intent

Architect or engineer input, usually Markdown prose. Intent is source material,
not trusted truth. The tool extracts candidate decisions from it.

## Decision

A structured value accepted by the requirement graph. Decisions are the values
that validation, contracts, and handoff artifacts may rely on.

## Raw LLM Decision

A model-proposed value before graph acceptance. Raw LLM decisions are preserved
for audit and debugging, but they do not become authoritative unless they map to
known graph requirements.

## Requirement Graph

The source of truth for decision keys, ordering, applicability, dependencies,
defaults, blocking gaps, cascades, and contradiction handling.

## Target Contract

The contract for a target handoff shape: required artifacts, required paths,
required decisions, value assertions, and lineage checks.

## Registered Target

A downstream accelerator, module family, parameter surface, or configuration
schema that a pattern explicitly owns through a model, requirement graph,
deployment target contract, validators, and artifact emitters. Registered
targets can receive deterministic configuration artifacts. Unregistered targets
must not receive generated IaC from prose.

## Target Configuration Artifact

A deterministic file emitted for a registered target, such as AWS LZA YAML,
CloudFormation parameter values, Kubernetes cluster/namespace config, or
Terraform module input variables. These files are not executed by this tool.
The Terraform VPC plan adapter may copy verified values into its code-owned
temporary root solely to produce speculative-plan evidence.

## Deployment Target Contract

The contract that defines the required shape for target configuration artifacts:
files, paths, decisions, value assertions, and lineage. It gates whether a
bundle can move to an existing deployment mechanism.

## Existing Deployment Mechanism

The downstream system that applies reviewed target configuration artifacts, such
as AWS LZA, a provisioning pipeline, CloudFormation, Terraform, or a platform
workflow. Current built-ins do not invoke these mechanisms.
The Terraform VPC adapter invokes only a local speculative plan for one exact
approved module; the owner pipeline remains the deployment mechanism.

## Handoff Artifact

A file emitted for humans or downstream IaC toolchains. Current handoff artifacts
are not deployments and do not make cloud changes.

## Handoff Readiness

The status that says whether a handoff is ready, blocked, or missing required
input. Readiness is graph- and contract-owned, not model-owned.

Artifacts expose `handoffReadiness` as the canonical readiness object. It is
not permission to deploy from prose.

## Handoff Allowed

The `handoffAllowed` readiness field: whether the reviewed artifact bundle can
move to the existing downstream toolchain after manual gates. It does not mean
this tool deploys infrastructure.

## Allowed Next Action

The next safe action recorded in `handoff-plan.yaml`. It should tell an engineer
what can happen next without implying deployment when the bundle is blocked.

## Pattern

A product path plugin. A pattern owns its Pydantic model, requirement graph,
contracts, validators, sample configs, and artifact generators.

## Design Context And Module Inputs

The two generic objects carried through generation for patterns that need them:
design context describes the business and architectural reason for the handoff,
while module inputs are literal values for a known downstream module. Patterns
may use either, both, or neither.

## Battle Test

A repeatable local confidence run that writes an ignored bundle under
`tests/results/`. It emits `battle-summary.yaml` with verdict, confidence
categories, findings, and improvement items.

## Battle Summary

The verdict artifact for a battle test.

```yaml
verdict: pass | fail
confidence:
  extraction: pass | fail | improvement | expected-weakness
  handoff: pass | fail | improvement | expected-weakness
  safety: pass | fail | improvement | expected-weakness
  model: pass | fail | improvement | expected-weakness
  regression: pass | fail
findings: []
improvementItems: []
```

`fail` means a real regression or unsafe weakness was found. `improvement`
means the run passed but found something worth tightening. `expected-weakness`
means the run passed while preserving a known model or tool limitation.

## Evidence

Trace, benchmark, validation, and optional raw prompt/response data that
explains how the bundle was produced. Evidence is for audit and improvement; it
is not a separate source of authority. Raw prompt/response evidence is a local
development/debug artifact and can be disabled for service-style runs while
keeping trace and benchmark summaries.

## Plan Produced

The exact target adapter completed a non-errored Terraform plan and parsed its
JSON. This is an execution fact, not proof that requirements match or that apply
is authorized.

## Plan Conformant

Every applicable `terraform-vpc` requirement observable at plan time has a
passing terminal outcome, every managed resource has approved provenance, and
all other controls are predeclared as later gates. The normal v1 status is
`conformant-with-deferred-gates`; it is not global policy compliance, owner
approval, or runtime compliance.

## Deferred Gate

A code-declared control that cannot be observed in the local speculative plan
and names the later evidence phase. Pipeline control, organizational IPAM
approval, and downstream attachment correctness are deferred in v1. Missing
plan data cannot be relabeled as a deferred gate.

## Policy Pack

Pattern-owned metadata mapping controls to requirements, artifacts, module
variables, scanners, and owner references. A policy pack is not itself a policy
runtime, conformance evaluator, attestation, or deployment approval.
