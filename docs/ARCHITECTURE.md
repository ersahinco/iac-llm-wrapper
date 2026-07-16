# Architecture Map

`iac-llm-wrapper` turns architecture intent into validated registered-target
configuration artifacts. It does not deploy infrastructure.

```text
Architect packet / Markdown / Interview
  -> extraction
     - LLM proposes raw decisions
     - structured Markdown can provide deterministic decisions
  -> requirement graph
     - accepts known decisions
     - orders dependencies
     - applies defaults, cascades, applies_if/applies_when gates
     - identifies gaps, asks for missing inputs, and records blockers
  -> semantic model
     - derives typed entities such as accounts, OUs, permission sets, assignments,
       controls, artifacts, and target capabilities where a pattern owns them
     - evaluates predicate constraints over real relationships
  -> target contracts
     - define required artifacts, paths, decisions, assertions, and lineage
     - fail closed when required target configuration shape is missing
  -> target capability facts
     - extract explicit unsupported asks with evidence spans
     - route downstream target coverage from semantic facts and accepted decisions
  -> artifact generators
     - emit decision reports, handoff plans, trace summaries, benchmark files,
       review files, and pattern-specific target configuration files
  -> optional target proof
     - terraform-vpc alone verifies replay identities and the code-owned root
     - runs a temporary account-bound speculative plan with no apply or retained state
  -> confidence loop
     - evals compare expected decisions and artifacts
     - battle tests produce verdicts and improvement items
     - static review pages help humans inspect readiness and blockers
```

## Ownership

- Core owns extraction orchestration, graph sync, validation, contracts, generic
  semantic graph primitives, artifacts, review pages, and evaluation harnesses.
- Patterns own domain models, requirement graphs, validators, deployment target
  contracts, sample configs, semantic model derivation, predicate constraints,
  and pattern-specific target configuration emitters.
- Existing deployment mechanisms own deployment. Compile/generation paths do not
  call cloud APIs or invoke pipelines. The Terraform VPC plan adapter may use
  standard AWS credentials for caller identity and a temporary speculative plan
  against one exact approved module; it cannot apply or retain state. The AWS LZA validation-only
  adapter may run the official local validator, which can require read-only
  account lookup through the provided AWS/LZA context.

## Boundary

The model can suggest. The requirement graph and target contracts decide.
Artifacts can be consumed by another UI or tool, but this repo remains
CLI-first, artifact-first, and handoff-first.

AWS Landing Zone Accelerator is the reference target: accepted decisions produce
contract-checked LZA YAML/config files, and the downstream LZA process remains
responsible for validating and applying them.
