# Glossary

Shared language for `iac-llm-wrapper`.

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

## Handoff Artifact

A file emitted for humans or downstream IaC toolchains. Current handoff artifacts
are not deployments and do not make cloud changes.

## Handoff Readiness

The status that says whether a handoff is ready, blocked, or missing required
input. Readiness is graph- and contract-owned, not model-owned.

Artifacts may still expose the legacy YAML key `deploymentReadiness` for
backward compatibility. Treat it as an alias for handoff readiness, not as
permission to deploy from prose.

## Handoff Allowed

The `handoffAllowed` readiness field: whether the reviewed artifact bundle can
move to the existing downstream toolchain after manual gates. Older artifacts may
also expose `deploymentAllowed` as a compatibility alias. Neither field means
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
