# AGENTS.md

## Project: intent-engine

**General-purpose intent-driven configuration framework.** Landing zone accelerator (LZA) is Pattern #1 — the first use case that proves the architecture. The framework captures architectural intent from design documents, validates it against requirements, and produces traceable decision artifacts that engineers map to their provisioning system of choice.

## Commands

```
source .venv/bin/activate
python -m pytest          # run all tests
ruff check .              # lint
ruff format --check .     # format check
```

## Architecture

- **Models** (`models.py`): Pydantic v2 data model for intent concepts. Use-case specific; LZA models include `CICDRunnerConfig`, `SecretManagementConfig`, `NetworkApplianceConfig`. The model drives extraction, graph sync, validation, and generation — like environment variables for a runtime.
- **Extract** (`extractor.py`): Single `Extractor` class driven by the requirement graph. Auto-generates LLM prompts from graph node `target_field`/`target_type`, parses JSON responses with type coercion. No regex, no rigid format — describe requirements in any structure. Falls back to graph defaults when no LLM available. Prompt is domain-agnostic; patterns optionally inject `prompt_context`.
- **Patterns** (`patterns.py`): Pluggable pattern registry (`baseline`, `minimal`, `workload`, `hybrid-enterprise`, `financial-services`, `healthcare`, `kubernetes-cluster`). Patterns carry their own graph factories, intent models, default catalogs, validators, generators, and template metadata. New patterns register without core code changes. **Addon system**: `Addon`/`AddonRegistry` for composable modules that layer requirements, field maps, and section maps onto any base pattern. Built-in addons include `pci-compliance`, `hipaa`, `self-hosted-cicd`, `hashicorp-vault`, `paloalto-fw`. `--addon` CLI flag enables composition.
- **Requirements** (`requirements.py`): Knowledge graph of decisions with `applies_if`, `blocked_if`, `depends_on`, and `cascade` rules. Each node carries architectural knowledge: WA pillars, compliance controls, migration signals, tradeoffs, alternatives, consequences, and confidence scores. Graphs are pattern-driven.
- **Interview** (`interview.py`): Knowledge-driven interview engine. Presents questions in topological order with full context: WA pillars, compliance controls, tradeoffs, consequences, and detected signals. `path_log()` shows every decision and why each path was taken or skipped. Every decision is recorded in an audit trail with timestamp and rationale.
- **Normalize** (`normalizer.py`): Applies deterministic defaults from `defaults.yaml` using duck-typing. No hardcoded fallbacks — use-case specifics live in config.
- **Validate** (`validator.py`): Fail-closed checks. `validate_graph()` derives violations from graph metadata. Accepts extra pattern-specific validators. Raises `CompileError` with violation codes on missing required decisions.
- **Generate** (`generator.py`): Produces decision reports, deployment graphs, and workload skeletons from normalized intent. Uses a registry pattern so new output modules can be added without modifying core generation logic. Built-in generators have `hasattr` guards so multiple patterns coexist safely.
- **Catalog** (`catalog.py`): Known-good reference configurations (`lza-minimal`, `lza-baseline`, `lza-hybrid-enterprise`, `lza-financial`, `lza-healthcare`). Architects can diff current decisions against proven configs. Engineers can apply catalog entries as starting points. CLI: `intent-engine catalog list/show/diff/apply`.
- **LLM** (`llm_caller.py`): Pluggable `LLMBackend` (OpenAI-compatible REST) with retry + exponential backoff. `create_backend("openai"|"ollama"|"anthropic")` factory. Evidenced via `LLMEvidenceStore` with token usage tracking.
- **CLI** (`cli.py`): Typer app with `compile`, `interview`, `validate`, `explain`, `catalog`, `discover`, `template`, `review` commands. Use `--pattern` to select scenario, `--addon` to layer addons, `--decisions` JSON for pre-fill, `--evidence-output` for LLM call audit.

## Key Design Decisions

- The framework is **domain-agnostic**. LZA-specific logic lives in the LZA pattern, models, and generators — not in core files.
- Topology is parsed into `intent.topology` then synced to `intent.network.topology` during normalization (LZA-specific normalizer behavior, duck-typed).
- Workload Markdown format: `- name: key=value, key=value` (comma-separated KV after first colon).
- Private CI/CD auto-adds 10 VPC endpoints: s3, sts, kms, logs, ecr.api, ecr.dkr, secretsmanager, ssm, ec2messages, ssmmessages.
- Default region: eu-central-1. Default audit retention: 2555 days.
- No AWS API calls. No deployment. No arbitrary Terraform from prose.
- The tool produces decision reports and intent artifacts — engineers use these alongside sample configurations and IaC modules. It does not generate deployable CDK/Terraform.

## Pattern Registry and Catalog

- **Patterns**: The `PatternRegistry` (`patterns.py`) decouples scenario definition from core logic. Each pattern has a name, description, graph factory, intent model factory, and optional catalog reference.
  - `baseline`: full LZA with hub-spoke, security, CI/CD, hybrid
  - `minimal`: bare minimum (4 decisions)
  - `workload`: workload account deployment only
  - `hybrid-enterprise`: baseline + hybrid connectivity + enhanced security
  - `financial-services`: baseline + PCI-DSS, SOX, data residency, payment segmentation (via `pci-compliance` addon)
  - `healthcare`: baseline + HIPAA, PHI encryption, BAA coverage (via `hipaa` addon)
  - `kubernetes-cluster`: K8s cluster provisioning with node pools and network policies (proof of generic framework)
- **Addons**: The `AddonRegistry` supports composable modules that layer onto any base pattern. `--addon pci-compliance --addon hipaa` stacks multiple addons. Each addon carries requirements, field maps for extraction sync, and section maps for template generation. Built-in addons: `pci-compliance` (3 decisions), `hipaa` (3 decisions).
- **ConfigCatalog**: Pre-built decision sets that represent proven, validated deployments.
  - `lza-minimal`: starter config for 1-2 accounts
  - `lza-baseline`: standard enterprise (hub-spoke, no hybrid)
  - `lza-hybrid-enterprise`: with Direct Connect, egress inspection, hybrid DNS
  - `lza-financial`: PCI-DSS scope isolation, SOX audit trails, HSM-backed KMS
  - `lza-healthcare`: HIPAA compliance, PHI access logging, BAA-covered vendors
  - `catalog diff`: compare current decisions against a reference
  - `catalog apply`: merge catalog entry as defaults, keeping current overrides

## Schema-Driven LLM Extraction

- `SchemaDrivenExtractor` introspects the requirement graph to build LLM prompts dynamically.
- `--pattern minimal` → LLM asked about 4 fields. `--pattern baseline` → LLM asked about 16.
- `--pattern baseline --addon pci-compliance` → LLM asked about 19 (baseline + pci addon).
- `--pattern kubernetes-cluster` → LLM asked about 10 K8s-specific fields.
- New decisions added to a pattern automatically appear in LLM prompts without code changes.
- Partial JSON recovery from malformed LLM responses via brace matching.
- Retry + exponential backoff on 5xx/429/timeout/connection errors.

## Requirement Graph and Interview Mode

- Requirements are modeled as a directed graph with explicit dependencies.
- `applies_if` gates: e.g., `central_network_account` only applies when `topology == hub-spoke`. Each question shows `why_applies` context.
- `blocked_if` gates: prevents decisions that contradict prior choices. Shows `why_blocked` reason when displayed.
- `cascade` rules: e.g., deciding `topology` auto-sets `network.topology`.
- `hint` field on every requirement gives the architect context for answering.
- Interview presents questions in topological order — dependencies resolved first. Same decisions = same question sequence every time.
- Three CLI modes: `--decisions` (JSON pre-fill), `--interactive` (prompted), or defaults-only.
- Path log tracks every skip and blocked reason with dependency context.
- Patterns determine which decisions exist in the graph. `--pattern minimal` asks 4 questions; `--pattern baseline` asks 16; `--pattern financial-services` asks 19; `--pattern kubernetes-cluster` asks 10.

## Knowledge Graph and Signal Detection

- Each `Requirement` node carries architectural knowledge:
  - `wa_pillars`: e.g., `["Security", "Operational Excellence"]` — Well-Architected pillars this decision affects
  - `compliance_controls`: e.g., `["PCI-DSS-10.7", "SOC2-CC7.2"]`
  - `signals`: e.g., `["on-prem-ad", "mpls", "5+-accounts"]` — migration signals that trigger this decision
  - `tradeoffs`: structured pros/cons for each option
  - `alternatives`: options considered and rejected
  - `consequences`: downstream effects of this decision
  - `confidence`: certainty in the default value (0-1)
- `DiscoveryEngine._detect_signals()`: scans design doc text for keywords and proactively suggests related requirements even before they're explicitly set.
- Interview displays WA pillars, compliance controls, tradeoffs, consequences, and signals alongside each question.

## Decision Traceability and Audit Trail

- Every decision (decided, defaulted, skipped) is recorded in the graph's audit log with timestamp, value, method, and optional rationale.
- The decision report includes a `wellArchitectedCoverage` section showing which WA pillars are covered by each decision.
- A separate `decision-audit.yaml` artifact provides the full audit trail for compliance and governance.
- This enables: "Why did we choose hub-spoke?" → "On 2024-05-22, architect decided hub-spoke because 8+ accounts with transitive routing needs. Alternative single-VPC rejected: blast radius too large for compliance boundary."

## Fail-Closed Violation Codes

| Code | Trigger |
|------|---------|
| `HUB_SPOKE_NETWORK_ACCOUNT_REQUIRED` | hub-spoke topology without central Network account |
| `PRIVATE_CICD_PLACEMENT_REQUIRED` | private CI/CD without placement config |
| `WORKLOAD_TARGET_ACCOUNT_REQUIRED` | workload without target_account |
| `PRIVATE_ECS_REQUIRES_PRIVATE_NETWORKING` | ECS workload with public networking |
| `EGRESS_INSPECTION_INCOMPLETE` | egress inspection required but no pattern/vendor |
| `HYBRID_CONFIG_INCOMPLETE` | hybrid required but missing dns_model/ip_model/on_prem_cidrs |

## What Each Stakeholder Gets

| Stakeholder | Pain Today | What This Tool Gives Them |
|-------------|-----------|---------------------------|
| **Architect** | Writes 20-page prose docs that engineers misinterpret; forgets critical questions until deployment; no structured way to capture "why I chose X over Y" | Guided interview surfaces gaps they'd miss; every decision shows tradeoffs, consequences, and compliance context; decision report is living documentation |
| **Client / Compliance** | Auditors ask "why is this configured this way?" and nobody knows; compliance reviews happen after deployment, causing rework; no evidence decisions were intentional | Decision audit trail with timestamps and rationale; compliance controls mapped to each decision; WA pillar coverage shows due diligence was performed |
| **Platform Team** | Every landing zone is a snowflake; architects make incompatible decisions across teams; no way to enforce "we always do hub-spoke" or "we never use public CI/CD" | Pattern registry enforces standard starting points; catalog diff shows deviation from approved patterns; can define mandatory decisions and forbidden choices |
| **Engineer** | Receives vague prose docs, has to reverse-engineer intent; "architect said hub-spoke but didn't mention the Network account"; no way to validate LZA config matches original intent | Clear, validated decision list with all dependencies resolved; decision report maps directly to config sections; knows which sample config to start from |
| **Business** | Landing zone projects take 3-6 months due to rework; compliance failures discovered late, blocking go-live; architects leave, taking all rationale with them | Faster time to validated design (days not weeks); compliance validation before engineering work starts; knowledge persists in machine-readable format |
| **Industry** | Each new project reinvents the wheel; industry-specific compliance (PCI, HIPAA, SOX) requires custom research; no shared repository of "what good looks like" | Pattern library with industry-specific knowledge baked in; community can contribute patterns (healthcare, gov, retail, kubernetes, etc.) |

## Honest Scope

The system brings **structure and traceability** to infrastructure design. It does not guarantee identical output from identical input — the LLM extraction layer has temperature, and architects can change their minds. What it guarantees:

- **Every applicable decision is surfaced** in dependency order with full context
- **Every decision is recorded** with timestamp, value, and rationale
- **Gaps are caught early** before engineering work starts
- **Tradeoffs are explicit** so architects make informed choices
- **Compliance controls are mapped** to each decision for audit readiness

## Extension Contract

See `EXTENSION.md` for the exact contract for adding new use cases. The litmus test: adding a `kubernetes-cluster` pattern required zero changes to `extractor.py`, `compiler.py`, `validator.py`, `normalizer.py`, `interview.py`, or `cli.py`.

## Fixtures

- `fixtures/valid-payments.md` — complete payments landing zone (compiles successfully)
- `fixtures/invalid-design.md` — hub-spoke without Network account (fails with violations)
- `fixtures/enterprise-full.md` — complex enterprise with hybrid, compliance, multi-account
- `fixtures/enterprise-partial.md` — partial enterprise with gaps and signals

## How It Works (Model-Driven Flow)

1. **Architect writes Markdown** — prose with structured sections (Region, Topology, Network, Security, etc.)
2. **Extraction** — LLM traverses the requirement graph guided by auto-generated prompts. Optional deterministic fallback uses graph defaults.
3. **Sync to Graph** — extracted values are fed into the requirement graph as decisions. The graph's `applies_if`/`blocked_if` rules propagate statuses automatically.
4. **Discovery** — the system finds genuine gaps (not all unasked questions, only those that are applicable but unset). It also detects signals from the prose.
5. **Interview** — if gaps exist, the architect is asked only the remaining questions. Each question includes WA pillar context, compliance controls, tradeoffs, consequences, and migration signals.
6. **Normalize + Validate + Generate** — decisions are normalized (defaults applied), validated (fail-closed), and translated into structured intent artifacts. Engineers use these alongside sample configurations and IaC modules.

## Why Model-Driven Matters

The requirement graph IS the product. It defines:
- What questions to ask (interview)
- What fields to extract (LLM prompt schema)
- What defaults to apply (normalization)
- What to validate (validation rules)
- What to generate (deployment graph)
- How to explain decisions (tradeoffs, consequences, WA pillars)

Adding a new feature means adding one `Requirement` node. The LLM prompt, interview questions, catalog defaults, WA coverage, and gap detection all update automatically. No code changes needed in extraction, interview, or generation logic.

## Stack

Python 3.11+, Pydantic v2, Typer, ruamel.yaml, networkx, pytest, ruff.

## Session State

<!-- UPDATE THIS SECTION AT END OF EVERY SESSION -->

### Current Goal
LLM-first product capability: real design documents, catalog module mapping, LLM-guided extraction, and engineer handoff documentation. LLM is the key accelerator — deterministic fallback exists but is secondary. Local LLM testing is each developer's responsibility.

### Status
- **Tests**: 382 passing, 1 skipped (LLM non-determinism)
- **Lint**: clean
- **Format**: clean
- **Repo**: `github.com/ersahinco/intent-engine` (private)
- **Last session**: Improved LLM extraction for 3B models:
  - Rewrote extractor prompt with few-shot JSON examples, type coercion rules (booleans→strings, integers→strings), and explicit accounts/OU/workload format guidance
  - Enhanced pattern `prompt_context` for baseline and kubernetes with section-to-field mapping (e.g., "Region section → primary_region")
  - Refactored JSON recovery into `_safe_json_parse()` with multi-stage recovery: direct parse → brace matching → comma insertion → progressive truncation
  - Made `_parse_ous` handle both `ous` and `ou` keys
  - Verified: payments fixture extracts 5/5 accounts and 2-3/3 OUs consistently (was 0); enterprise fixture extracts 8/8 accounts consistently (was 0)
  - Known: workloads and OUs from long documents can be dropped by 3B model (capacity limitation, model non-determinism)

### Done
| Area | Item |
|------|------|
| Core | Models, extractor, requirements, patterns, interview, discovery, normalizer, validator, generator, catalog, CLI, **sample_config** |
| Patterns | baseline, minimal, workload, hybrid-enterprise, financial-services, healthcare, kubernetes-cluster |
| Catalog | 5 entries with diff/apply |
| Reports | Decision report with WA pillar coverage + audit trail |
| Signals | Detection from prose text (auto-generated from graph metadata) |
| Addons | Composable AddonRegistry with pci-compliance, hipaa, self-hosted-cicd, hashicorp-vault, paloalto-fw, hybrid-challenges |
| Data-driven | apply_to_intent and sync_intent_to_graph iterate graph node target_field/target_type — no hardcoded field maps |
| CLI | compile uses Extractor (graph-driven LLM extraction); discover uses Extractor |
| Extraction | Domain-agnostic prompt; pattern `prompt_context` injects domain knowledge; signal rules auto-generated from graph |
| Ollama auto-detect | `auto_detect_llm()` in `llm_caller.py` — tries Ollama when no API key, silent fallback to defaults if not running |
| Two-layer architecture | Explicit `LLMContextProvider` (Layer 1) + deterministic harness (Layer 2) in `compiler.py` |
| Graph traversal prompt | LLM receives full graph context: `applies_if`, `depends_on`, `signals`, `tradeoffs`, `consequences` |
| Structured LLM result | `LLMGraphResult` with `decisions`, `signal_decisions`, `addons_suggested`, `gaps`, `contradictions` |
| Batch graph application | `RequirementGraph.apply_decisions()` applies decision dicts with gate enforcement |
| LLM integration tests | Real Ollama tests in `test_llm_integration.py` — skip gracefully when unavailable |
| Graph-driven validation | `validate_graph()` derives violations from graph nodes with `required_when_applicable=True` |
| Config-driven defaults | Normalizer and generator read from `defaults.yaml`; no hardcoded fallbacks |
| Pattern-driven templates | `Pattern.section_map` + `Addon.section_map` + `_CATEGORY_TO_SECTION` fallback |
| Addon field_map wiring | `RequirementGraph._field_map` merged during `AddonRegistry.compose`; used by `sync_intent_to_graph` |
| LZA test isolation | All LZA-specific tests live in `tests/patterns/lza/`; core tests have zero LZA imports |
| Sample config system | `SampleConfig` + `SampleConfigRegistry` with versioned pins, source URLs, module refs |
| LZA fixture files | `fixtures/lza-baseline-v1/` with 6 real config files (org, accounts, global, iam, security, network) |
| K8s fixture files | `fixtures/kubernetes-v1/` with cluster and namespace config |
| Sample config registrations | `lza-baseline-v1`, `lza-minimal-v1`, `k8s-cluster-v1` with pinned module refs |
| **OSS release** | LICENSE (Apache 2.0), README.md, CONTRIBUTING.md, CI workflow, pre-commit, .gitignore, pyproject metadata |
| **Real-world examples** | `fixtures/kubernetes-enterprise.md`, `docs/CAPABILITY.md`, README Real-World Usage section |
| **LLM testing** | Local Ollama tests with qwen2.5:3b and llama3.2:3b on real design docs |
| **LLM docs** | `docs/LLM_SETUP.md`, `scripts/test-llm-extraction.sh`, Ollama-first README |
| **Prompt engineering** | Few-shot examples, section mapping, type coercion rules in extractor prompt; pattern prompt_context with section-to-field guidance |
| **JSON recovery** | `_safe_json_parse()` with multi-stage recovery: direct parse → brace matching → comma insertion → progressive truncation |
| **Extraction quality** | Payments: 5/5 accounts + 2-3/3 OUs; Enterprise: 8/8 accounts + 2/5 OUs (3B model limitation on long docs) |

### Next (prioritized)
1. [ ] Add deterministic fallback for accounts/OUs/workloads parsing (keyword-based, no LLM)
2. [ ] Improve workloads extraction for small models (split extraction or separate LLM call)
3. [ ] Add more pattern-specific sample configs with real module variable schemas
4. [ ] Create decision-report → Terraform variables file generator
5. [ ] Evaluate adding remaining source files to mypy scope when they change (ongoing incremental policy).

### Key Decisions This Session
- **LLM-first prioritization**: Prompt engineering and JSON recovery improvements are the highest-leverage work for extraction quality
- **Comma-insertion recovery**: Missing commas between top-level JSON keys (common LLM error) handled via regex `([}\]])[\t\n ]+(?=")` → `\1, `
- **Progressive truncation as last resort**: Scan backwards from end for valid JSON; handles unclosed root objects and extra braces
- **OU parsing robust**: `_parse_ous` handles both `ous` and `ou` keys from LLM response
- **Small model capacity**: 3B models reliably extract accounts and OUs from short docs (5 items), but drop items from long docs (8+ items) — use 7B+ for complex documents
- **Extraction quality verified**: Tested with qwen2.5:3b across multiple runs on payments and enterprise fixtures
- **pip-audit policy**: Use `--skip-editable` for local editable installs while still failing on real dependency vulnerabilities.
- **Mypy expansion policy**: Expand in small verified slices (2-3 modules) and fix only real typing issues, no broad refactors.
- **Security policy**: No formal exception workflow needed for a design-time tool. B101 skip removed (no asserts in src). Guidance is fix in code, document only if confirmed false positive.
- **Release automation**: Tag-driven workflow with PyPI trusted publishing (OIDC) and auto-generated GitHub Release notes. No manual twine uploads.
- **Supply-chain hardening**: Committed `uv.lock` for reproducible resolution, CycloneDX SBOM generated in CI, SLSA provenance attestations on release artifacts.
- **LLM testing policy**: Local LLM testing is each developer's responsibility — whether via Ollama or API key. CI may run LLM tests if API keys are configured, but local validation is the gate. `./scripts/test-llm-extraction.sh` validates extraction quality before PRs.
- **Deterministic fallback scope**: Exists for unit tests and CI bootstrapping only. It applies graph defaults and does keyword matching — it cannot parse free-form prose. Not a production extraction path.
- **Operational controls**: `CODEOWNERS` for review ownership, branch protection guidance in CONTRIBUTING.md, pre-commit CI as optional but recommended check.
- **Pre-commit CI**: Separate workflow runs pre-commit on all files to catch issues without requiring local hook installation.
- **CI matrix**: Split `quality` into `lint` (single Python version) and `test` (matrix) to avoid redundant lint/format/type-check runs. Pre-commit runs on PR only since `main` is protected.
- **Apache 2.0**: Standard for infrastructure tooling, permissive, OSI-approved.
- **CI matrix**: 3.11/3.12/3.13 — covers all supported Python versions.
- **Pre-commit**: ruff lint+format run on every commit; lower friction than CI-only enforcement.
- **pyproject.toml metadata**: Setuptools.find with `where = ["src"]`, `namespaces = false` — matches existing src-layout.
- **README tone**: Focus on core capability (decision capture + validation), not LZA specifics. Quick Start → Play (without LLM) → Extend (new pattern, requirement, addon) → CLI reference → Project status.
- **CONTRIBUTING**: Links to EXTENSION.md as the canonical extension contract. Pre-commit install is optional but documented.
- **Venv recreation**: Old `.venv` had hardcoded shebang to `/intent-engine/` path; deleted and recreated from scratch. This may affect other developers — AGENTS.md now documents `.venv/bin/python` as the canonical runner.
- **No .venv in .gitignore for CI**: CI installs via `pip install -e ".[dev,llm]"`; .venv/ is in .gitignore for local dev but irrelevant in CI.
