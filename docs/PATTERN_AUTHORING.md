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
  or deployment pipelines from the pattern. Emit reviewed configuration and
  plan-only metadata for the existing deployment mechanism instead. A future
  plan invocation must be registered, plan-only, contract-backed, and separate
  from apply.
- Do not make LLM output authoritative. Raw model output must pass through the
  requirement graph and target contracts.
- Do not leave target boundaries only in prose prompts. Pattern context must be
  short, reviewable, and backed by graph and contract checks.
- Do not add dashboards, servers, workflow builders, or graph databases to make a
  pattern work. Emit portable artifacts first.

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
```

Keep small patterns in one module until splitting reduces noise.
