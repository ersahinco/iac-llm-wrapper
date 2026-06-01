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
     - applies defaults and cascades
     - identifies gaps, blockers, and contradictions
  -> target contracts
     - define required artifacts, paths, decisions, assertions, and lineage
     - fail closed when required handoff shape is missing
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
  artifacts, review pages, and evaluation harnesses.
- Patterns own domain models, requirement graphs, validators, contracts, sample
  configs, and pattern-specific handoff files.
- External IaC tools own deployment. Current built-ins do not call cloud APIs.

## Boundary

The model can suggest. The requirement graph and target contracts decide.
Artifacts can be consumed by another UI or tool, but this repo remains
CLI-first, artifact-first, and handoff-first.
