# Context As Code

`iac-llm-wrapper` treats LLM context as a reviewed project artifact, not as hidden
prompt prose. The model may propose decisions, but code-owned context decides
what can be accepted, what must be asked, and what may be handed off.

## Project Rules

- Put domain shape in pattern-owned Pydantic models.
- Put decision order, gaps, defaults, and blockers in requirement graphs.
- Put richer decision gates in `applies_when` / `blocked_when` expressions when
  `applies_if` / `blocked_if` is too shallow.
- Put important real-world relationships in pattern-owned semantic models with
  typed entities, typed relationships, and predicate constraints.
- Put downstream target configuration shape, required decisions, and lineage in
  deployment target contracts.
- Put LLM extraction boundaries in `Pattern.prompt_context`.
- Put reusable examples in sample configs and fixtures, not only in prompts.
- Put confidence checks in tests, fixture drift checks, golden journeys, and
  usability trials.
- Emit `context-manifest.yaml` so each successful handoff bundle records the
  code-owned context that shaped it.

## Prompt Context Rules

`Pattern.prompt_context` is intentionally small. It should:

- say what the LLM extracts or captures
- name the registered target or handoff boundary
- forbid generation outside the registered target
- stay short enough to review in code review

Avoid context like "make a good architecture plan" or "infer the best setup".
That asks the model to become the product. Instead, encode the product contract:

```text
This pattern captures configuration inputs for an existing approved Terraform AWS
VPC module. Extract exact module variables such as CIDR, subnets, NAT settings,
and DNS flags only. Do not generate root Terraform scaffolding or invoke
deployment from prose.
```

## Guardrail

Run this before merging pattern changes:

```bash
uv run iac-llm-wrapper pattern check --pattern aws-lza
```

The check validates graph shape, contract alignment, sample fixtures, expected
artifacts, and bounded prompt context. It is deliberately lightweight: it keeps
context close to the code that consumes it, without requiring a graph database or
separate policy engine.

Every successful pattern-backed compile also writes `context-manifest.yaml`. Use
that file to review the exact pattern, prompt context, requirement graph,
contracts, samples, target capabilities, runtime extraction summary, expected
artifacts, and guardrails that were active for the bundle.

Target capability routing uses accepted decisions plus semantic facts. For
unsupported downstream asks, deterministic text extraction creates explicit
`unsupportedAsk` facts with evidence spans before the capability graph selects
module-composition, generator, manual, or blocked paths. This keeps keyword
matching out of the routing decision itself.

AWS LZA also derives a lightweight semantic model from accepted handoff intent.
That model represents entities such as `Account`, `OU`, `PermissionSet`,
`Assignment`, `Control`, and `Artifact`, then evaluates predicate constraints
such as `references_known`, `contains`, and `cidr_valid`. This is the current
middle path: richer than flat strings and simple keyword routing, but still just
Pydantic, dataclasses, NetworkX, and YAML artifacts rather than RDF/OWL or a
Datalog engine.
