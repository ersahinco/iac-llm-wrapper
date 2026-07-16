# Pattern Authoring

Use this checklist when adding or changing a registered target pattern. A pattern
turns accepted decisions into deterministic target configuration artifacts for
an existing deployment mechanism. The detailed API contract lives in
[EXTENSION.md](EXTENSION.md).

## Checklist

1. Define the Pydantic intent model.
2. Define the requirement graph.
3. Define deployment target contracts for required files, paths, decisions, and
   lineage.
4. Add a pattern-owned semantic model when customer requirements depend on
   real-world relationships such as account placement, assignments, controls, or
   artifact ownership.
5. Define bounded `Pattern.prompt_context` using
   [context-as-code rules](CONTEXT_AS_CODE.md).
6. Attach target configuration emitters to `Pattern.generators`.
7. Add sample configs only when they represent a reusable reference bundle.
8. Add extraction fixtures for ready and blocked cases.
9. Add usability or battle tests when the change affects handoff quality.
10. Run `iac-llm-wrapper pattern check --pattern your-pattern` to validate graph
   shape, contracts, expected artifacts, and sample fixtures.
11. Run the full repo gate from `AGENTS.md`.

## Boundaries

- Do not add provider-specific logic to core CLI, compiler, extractor,
  validator, interview, or generator modules.
- Keep private/customer-specific pattern code in the pattern package that owns
  those contracts, controls, samples, and generators.
- Do not emit deployable scaffolding or raw IaC unless the registered target
  explicitly owns that artifact type through a deployment target contract.
- Do not invoke cloud APIs, Terraform, CloudFormation, AWS LZA, apply commands,
  or deployment pipelines from compile-time pattern generators. Emit reviewed
  configuration and plan metadata first. A target-specific plan adapter may be
  added only for an immutable registered target with replay verification,
  contract-backed evidence, temporary state, and a hard no-apply boundary; do
  not extract a generic executor before a second real target proves the same
  protocol.
- A plan-capable target must keep observation rules, strict outcome models,
  resource provenance, applicability, and aggregation inside the owning pattern.
  Every applicable requirement/control must have exactly one terminal outcome;
  unknown, sensitive, contradictory, missing, or unsupported evidence fails
  closed. `not-observable` must be declared in code with a later evidence phase.
- Keep policy-pack mappings distinct from evaluation. Do not add OPA, CUE, KCL,
  or another policy runtime for one target-specific Python/Pydantic consumer.
- Do not make LLM output authoritative. Raw model output must pass through the
  requirement graph and target contracts.
- Do not leave target boundaries only in prose prompts. Pattern context must be
  short, reviewable, and backed by graph and contract checks.
- Do not add dashboards, servers, workflow builders, or graph databases to make a
  pattern work. Emit portable artifacts first.
- Treat Git plus contract-backed artifacts as the default integration protocol.
  A pattern-local bridge may emit target-shaped configuration when it reuses an
  existing approved root and keeps backend, credentials, state, workspace,
  approval, and apply downstream. Do not add a core integration registry for one
  consumer.
- A second orchestration bridge, portal integration, MCP facade, or new semantic
  plan evaluator requires repeated owner demand. If each target needs another
  thousand-line evaluator, keep it configuration-only or stop.

## Acceptance Signals

A healthy pattern has:

- graph-backed required decisions
- `applies_when` / `blocked_when` expressions when simple key/value gates are not
  expressive enough
- typed entities and predicate constraints for important relationship rules
- clear blocked reasons for missing enterprise values
- required artifacts checked by contracts
- target configuration artifacts that match the registered deployment target
- `context-manifest.yaml` with graph, prompt context, contract, sample, target,
  runtime, and expected-artifact context
- optional `Pattern.policy_packs` when regulated controls should map to graph
  requirements, target contracts, artifact paths, module variables, Checkov IDs,
  and owner custom-policy references
- `handoff-plan.yaml` with an allowed next action
- `llm-trace-summary.yaml`, `model-benchmark.yaml`, and `battle-summary.yaml`
  when battle-tested
- fixture or eval coverage for wrong, missing, and invented model output

## Common Shape

```text
src/intent_engine/patterns/my_pattern/
  __init__.py       # registration
  models.py         # intent model
  graph.py          # requirement graph, if large enough to split
  semantic.py       # typed entities/edges/predicate constraints, when needed
  contracts.py      # target contracts, if large enough to split
  generators.py     # artifact emitters, if large enough to split
  validators.py     # pattern-specific validators, only when graph rules are not enough
  samples.py        # reusable sample configs
  conformance.py    # target-local plan observations/outcomes, only when earned
```

Keep small patterns in one module until splitting reduces noise.
