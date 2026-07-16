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
     - terraform-vpc emits an abstract Atmos catalog and byte-identical approved root
       as an optional Git/contract handoff, without owner runtime configuration
  -> optional target conformance
     - terraform-vpc alone verifies replay, root, module-tree, provider, and tool identities
     - runs a temporary account-bound speculative plan with no apply or retained state
     - gives every applicable requirement/control a plan, input, or deferred-gate outcome
     - fails on contradictions, unknowns, incomplete plans, or untraceable resources
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
  owner-approved AWS credentials for caller identity and a temporary speculative
  plan against one exact approved module; it observes the account, not credential
  scope, and cannot apply or retain state. The AWS LZA validation-only
  adapter may run the official local validator, which can require read-only
  account lookup through the provided AWS/LZA context.
- Atmos owns no state here. The `terraform-vpc` pattern emits an abstract catalog
  component and the already-approved root. Owner repositories supply real stack
  names, backend, authentication, workspace, approvals, and execution. The bridge
  adds no core callback, service API, or Python dependency.

## Boundary

The model can suggest. The requirement graph and target contracts decide.
Artifacts can be consumed by another UI or tool, but this repo remains
CLI-first, artifact-first, and handoff-first.

The integration protocol is generated files plus target contracts and replay
digests. Backstage may invoke the CLI, and Atlantis may execute an owner's Atmos
workflow. Terramate and Terragrunt are alternative Terraform orchestrators.
Score and Crossplane require independent target demand. None is a runtime
dependency, and no MCP facade exists in this slice.

LLM providers remain supported for compatibility, but provider expansion is
frozen. Model output may propose decisions; it may not select target versions,
weaken contracts, construct the Atmos root, or authorize a state transition.

For `terraform-vpc`, the pattern-local conformance specification owns plan JSON
interpretation and resource provenance. `policy-graph.yaml` remains control
mapping metadata, not an evaluator. State, locking, drift, approval, signed
attestation, and any fresh downstream plan remain owner-platform concerns.

AWS Landing Zone Accelerator is the reference target: accepted decisions produce
contract-checked LZA YAML/config files, and the downstream LZA process remains
responsible for validating and applying them.
