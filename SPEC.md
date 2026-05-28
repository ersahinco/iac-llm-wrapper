# SPEC

## §G GOAL
Model-driven intent-to-IaC orchestration framework. Design doc → extracted
decisions → normalized intent → validation/gates → target handoff artifacts.
Future target adapters may wrap module generation or controlled IaC execution
after graph, contract, and gate checks pass. LZA is first target pattern.

## §C CONSTRAINTS
- Python ≥3.11, Pydantic v2, Typer, ruff, pytest
- Domain-agnostic core. Target logic → pattern files, not core
- LLM extraction via Ollama/OpenAI/Anthropic. Deterministic fallback for CI
- Current built-ins make no AWS API calls and do not deploy
- No arbitrary root module generation from prose
- Future generation/execution adapters require graph, contract, gate, evidence, and rollback checks
- One SPEC.md at root. No split specs

## §I INTERFACES
- cli: `intent-engine compile|interview|validate|discover|template|sample|contract|explain|review`
- graph: `RequirementGraph` — add, decide, status, apply_decisions, cascade
- models: pattern-specific Pydantic intent models
- emit: `GeneratorRegistry` — `register(name, fn, priority, category, applies_to)`
- contracts: `TargetContract` — artifacts, required_paths, required_decisions, lineage
- llm: `LLMCaller` — `call(prompt)` → `(response, LLMEvidence)`
- patterns: `PatternRegistry` — register, get, list
- env: `OPENAI_API_KEY`, `INTENT_ENGINE_PROVIDER`, `INTENT_ENGINE_MODEL`
- file: `SPEC.md` — spec at repo root
- file: `FORMAT.md` — spec schema at repo root

## §V INVARIANTS
V1: ∀ decision → recorded in audit trail with timestamp + rationale
V2: ∄ compile without validate. Fail-closed on violations
V3: Adding requirement node → auto-updates LLM prompt + interview + sample matching
V4: Every new target pattern → zero core changes (verify: no `patterns/` imports in `core/`)
V5: Pattern generators scoped by `applies_to`; internal guards only fallback safety
V6: Test suite ! pass before push. Current full gate green, ruff clean

## §T TASKS
id|status|task|cites
T1|x|Interview save/resume+transcript|V1
T2|x|Discover --resume + LLM flags|V1
T3|x|Sample match after compile|V1
T4|x|LZA schema fixes (flat IAM, schemaVersion, cross-ref validators)|V1
T5|x|Terraform tfvars generator|V1
T6|x|Dead code removal (extract_json, describe, validate_template_output, suggest_for_given)|V3
T7|x|LLM-unavailable warning + honest scope reframe|V3
T8|x|Benchmark script for LLM extraction quality|V3
T9|x|Deterministic fallback for accounts/OUs/workloads (keyword-based)|V4
T10|.|Improve workloads extraction for small models (split extraction)|V3
T11|.|More pattern-specific sample configs|V4
T12|.|Decision-report → Terraform variables mapping|V5
T13|~|Mypy expansion (remaining src files)|V4
T14|~|AWS LZA thin path: model-driven contract, YAML emitter, lineage manifest|V4,V5

## §B BUGS
id|date|cause|fix
