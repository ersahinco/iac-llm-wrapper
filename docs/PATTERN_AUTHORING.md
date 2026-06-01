# Pattern Authoring

Use this checklist when adding or changing a target pattern. The detailed API
contract lives in [EXTENSION.md](EXTENSION.md).

## Checklist

1. Define the Pydantic intent model.
2. Define the requirement graph.
3. Define target contracts for required files, paths, decisions, and lineage.
4. Register scoped artifact generators with `applies_to={"your-pattern"}`.
5. Add sample configs only when they represent a reusable reference bundle.
6. Add extraction fixtures for ready and blocked cases.
7. Add usability or battle tests when the change affects handoff quality.
8. Run `iac-llm-wrapper pattern check --pattern your-pattern` to validate graph
   shape, contracts, expected artifacts, and sample fixtures.
9. Run the full repo gate from `AGENTS.md`.

## Boundaries

- Do not add provider-specific logic to core CLI, compiler, extractor,
  validator, interview, or generator modules.
- Keep private/customer-specific pattern code in the pattern package that owns
  those contracts, controls, samples, and generators.
- Do not emit deployable scaffolding unless a target contract explicitly owns
  that artifact type.
- Do not make LLM output authoritative. Raw model output must pass through the
  requirement graph and target contracts.
- Do not add dashboards, servers, workflow builders, or graph databases to make a
  pattern work. Emit portable artifacts first.

## Acceptance Signals

A healthy pattern has:

- graph-backed required decisions
- clear blocked reasons for missing enterprise values
- required artifacts checked by contracts
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
  contracts.py      # target contracts, if large enough to split
  generators.py     # artifact emitters, if large enough to split
  validators.py     # pattern-specific validators, only when graph rules are not enough
  samples.py        # reusable sample configs
```

Keep small patterns in one module until splitting reduces noise.
