# Session Prompt: Intent-Driven IaC Configuration Framework

## Core Realization

This project is not a landing-zone tool. It is a **general-purpose intent-driven IaC configuration framework** where the data model is the contract between an LLM and a deterministic harness. Landing zone accelerator (LZA) is simply **Pattern #1** — the first use case that proves the architecture.

The framework's job: an architect describes intent in prose; the LLM traverses a requirement graph to understand it; the harness enforces that understanding deterministically. The output is not deployed infrastructure — it is validated decision artifacts that engineers map to their provisioning system of choice.

## Architecture Review Goal

Audit every core file. Any assumption that "this is for AWS LZA" must move into the pattern/config layer. The framework must be provably generic by adding a **second non-LZA pattern** that compiles end-to-end without touching core code.

## What Must Stay Generic (The Framework)

| Component | Must Be Generic | Current Status |
|---|---|---|
| `Extractor` | Builds prompts from any `RequirementGraph` | ✅ Graph-driven |
| `LLMContextProvider` | Runs any graph against prose | ✅ Generic |
| `RequirementGraph` | Dependencies, gates, cascade, audit | ✅ Generic |
| `InterviewEngine` | Topological question ordering | ✅ Generic |
| `Normalizer` | Applies defaults from `defaults.yaml` | ✅ Generic |
| `Validator` | `validate_graph()` checks graph metadata | ✅ Generic |
| `GeneratorRegistry` | Pluggable output generators | ✅ Generic |
| `PatternRegistry` | Named graph factories | ✅ Generic |
| `AddonRegistry` | Composable requirement layers | ✅ Generic |
| `Catalog` | Known-good decision sets | ✅ Generic |

## What Is Use-Case Specific (The Pattern Layer)

Everything LZA-specific must live here:
- **Pydantic models** (`models.py`): defines the intent shape for one use case
- **Pattern graph factories** (`requirements.py`, `patterns.py`): defines decisions
- **Registered generators** (`generator.py`): defines output artifacts
- **`defaults.yaml`**: defines defaults and guardrails
- **Catalog entries**: defines known-good decision sets
- **CLI `--pattern` flag**: selects which use case to run

## Audit Checklist

### 1. Extractor Prompt Must Not Hardcode Domain

`Extractor.build_prompt()` currently says:
> "You are an architecture intent extractor for AWS Landing Zone Accelerator."

This must become generic. The pattern should optionally inject domain context.

**Refactor:**
- Default prompt: "You are an architecture intent extractor."
- Pattern can provide `domain_context` metadata that appends to the prompt
- Or the prompt is fully generic and the graph context provides all domain knowledge

### 2. Template Generation Must Not Hardcode "LZA"

`generate_template()` currently outputs:
> "# LZA Design Document — {pattern} pattern"

**Refactor:**
- Header comes from pattern metadata: `pattern.document_title` or generic default
- Pattern object should carry `display_name` or `template_header`

### 3. CLI Help Text Must Not Claim "Landing Zone"

`cli.py` app description: "Knowledge-driven landing zone decision system"

**Refactor:**
- Generic description: "Knowledge-driven infrastructure decision system"
- Pattern list in help shows available use cases

### 4. Add a Non-LZA Pattern to Prove Generic Nature

Create `pattern="kubernetes-cluster"` that demonstrates:
- Different Pydantic models (cluster config, namespace policy, node pools)
- Different requirement graph (cluster version, network policy, node pool sizing)
- Different defaults file (or same file with k8s section)
- Different generators (cluster-config.yaml, namespace-config.yaml)
- Compiles end-to-end with `compile_design()` without modifying core code

This is the **acceptance test for generic architecture**. If we can't do this without touching `extractor.py`, `compiler.py`, or `validator.py`, the framework is not generic.

### 5. Document the Extension Contract

Add `EXTENSION.md` that defines exactly what a new use case needs:

```
To add a new use case (e.g., "gcp-org", "kubernetes-cluster", "saas-tenant"):

1. Define Pydantic models in src/intent_engine/models.py (or a new module)
2. Define RequirementGraph factory in a new module
3. Register a Pattern in GLOBAL_REGISTRY with:
   - name, description, graph_factory
   - section_map for templates
   - optional catalog_name
4. Register generators in GeneratorRegistry (or reuse existing)
5. Add defaults to defaults.yaml (or a separate file)
6. Add catalog entries to ConfigCatalog
7. CLI: --pattern <name> selects your use case

No changes needed to: extractor, compiler, validator, normalizer, interview, CLI core.
```

## Concrete Refactoring Tasks

### Task 1: Make extractor prompt domain-agnostic
- [ ] Remove "AWS Landing Zone Accelerator" from default prompt
- [ ] Add optional `domain_name` to `Pattern` metadata
- [ ] Inject domain context into prompt if pattern provides it
- [ ] Verify all existing tests still pass

### Task 2: Make template generation domain-agnostic
- [ ] Remove "LZA" from template header
- [ ] Use pattern name + generic title
- [ ] Verify all template tests still pass

### Task 3: Make CLI domain-agnostic
- [ ] Update app description to generic text
- [ ] Update command help strings
- [ ] Ensure `--pattern` help lists available patterns dynamically

### Task 4: Add `kubernetes-cluster` pattern (acceptance test)
- [ ] Define minimal k8s models: `ClusterConfig`, `NodePool`, `NetworkPolicy`
- [ ] Define requirement graph: `cluster_version`, `node_pool_count`, `network_policy_enabled`
- [ ] Register pattern in `GLOBAL_REGISTRY`
- [ ] Add generators: `cluster-config.yaml`, `namespace-config.yaml`
- [ ] Add `defaults.yaml` entries for k8s defaults
- [ ] Write test: `test_kubernetes_pattern_compiles()` that:
  - Creates a design doc with k8s intent
  - Calls `compile_design()` with `pattern="kubernetes-cluster"`
  - Asserts output files exist and contain expected values
  - Does NOT modify any core framework file

### Task 5: Write `EXTENSION.md`
- [ ] Document the data-model-driven extension contract
- [ ] Show example: adding a new pattern from scratch
- [ ] Explain: models → graph → pattern → defaults → generators → catalog

## Commands

```
source .venv/bin/activate
python -m pytest          # run all tests
ruff check .              # lint
ruff format --check .     # format check
```

## Files to Read First

- `src/intent_engine/extractor.py` — check for LZA-specific prompt text
- `src/intent_engine/compiler.py` — check for LZA-specific template text
- `src/intent_engine/cli.py` — check for LZA-specific help text
- `src/intent_engine/patterns.py` — understand pattern registration; add `domain_context` field
- `src/intent_engine/generator.py` — understand generator registry; verify no hardcoded LZA logic in core
- `src/intent_engine/validator.py` — verify `validate_graph()` is generic
- `src/intent_engine/normalizer.py` — verify only reads from `defaults.yaml`
- `AGENTS.md` — review for LZA-centric language, update to generic framing

## Success Criteria

1. No occurrence of "landing zone", "LZA", or "AWS" in core framework files (extractor, compiler, validator, normalizer, interview, discovery, CLI app definition)
2. `kubernetes-cluster` pattern compiles end-to-end without touching any core file
3. All 271+ tests pass
4. Lint and format clean
5. `EXTENSION.md` exists and documents the generic extension contract

## Honest Scope

The project does not generate deployable Terraform or CDK. It generates **decision artifacts** — validated, traceable intent that engineers map to their provisioning system. The framework's value is structure and determinism, not deployment automation. This is true regardless of whether the use case is AWS LZA, GCP organization, Kubernetes cluster, or SaaS tenant onboarding.
