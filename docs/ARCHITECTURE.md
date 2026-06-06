# Architecture Map

`iac-llm-wrapper` turns architecture intent into validated handoff artifacts. It
does not deploy infrastructure.

```text
Prose / Markdown / Interview
  -> extraction
     - LLM proposes raw decisions
     - structured Markdown can provide deterministic decisions
  -> requirement graph
     - accepts known decisions
     - orders dependencies
     - applies defaults, cascades, applies_if/applies_when gates
     - identifies gaps, blockers, and contradictions
  -> semantic model
     - derives typed entities such as accounts, OUs, permission sets, assignments,
       controls, artifacts, and target capabilities where a pattern owns them
     - evaluates predicate constraints over real relationships
  -> target contracts
     - define required artifacts, paths, decisions, assertions, and lineage
     - fail closed when required handoff shape is missing
  -> target capability facts
     - extract explicit unsupported asks with evidence spans
     - route downstream target coverage from semantic facts and accepted decisions
  -> artifact generators
     - emit decision reports, handoff plans, trace summaries, benchmark files,
       review files, and pattern-specific handoff files
  -> confidence loop
     - evals compare expected decisions and artifacts
     - battle tests produce verdicts and improvement items
     - static review pages help humans inspect readiness and blockers
```

## Ownership

- Core owns extraction orchestration, graph sync, validation, contracts, generic
  semantic graph primitives, artifacts, review pages, and evaluation harnesses.
- Patterns own domain models, requirement graphs, validators, contracts, sample
  configs, semantic model derivation, predicate constraints, and pattern-specific
  handoff files.
- External IaC tools own deployment. Current built-ins do not call cloud APIs.

## Boundary

The model can suggest. The requirement graph and target contracts decide.
Artifacts can be consumed by another UI or tool, but this repo remains
CLI-first, artifact-first, and handoff-first.
