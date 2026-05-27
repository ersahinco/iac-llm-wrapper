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
- The tool produces decision reports, intent artifacts, and reference variable files (e.g., `terraform.tfvars` for module input handoff). Engineers use these alongside sample configurations and IaC modules. It does not generate deployable CDK/Terraform root modules or provider configs.
- **Architecture debt**: Core files (`extractor.py`, `compiler.py`, `interview.py`) have LZA-specific conditionals despite generic naming. Fixing this requires moving prompt schemas to per-pattern `prompt_context` — a medium-refactor project. See `EXTENSION.md` for the extension contract.

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
T15: Lean contract-driven handoff maturity

### Status
- **Tests**: 515 passing, 1 skipped (LLM non-determinism)
- **Lint**: clean
- **Format**: clean
- **Repo**: `github.com/ersahinco/intent-engine` (private)
- **Last session**: Tightened AWS LZA global/network handoff shape, widened mypy to AWS LZA emitter, refreshed fixtures, kept full gate green

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
| Ollama auto-detect | `auto_detect_llm()` in `llm_caller.py` — tries Ollama when no API key, warns on fallback to defaults if not running |
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
| LZA fixture files | `fixtures/lza-baseline-v1/` full generated handoff bundle with sync/check coverage |
| K8s fixture files | `fixtures/kubernetes-v1/` full generated handoff bundle with sync/check coverage |
| Sample config registrations | `lza-baseline-v1`, `lza-minimal-v1`, `k8s-cluster-v1` with pinned module refs |
| **OSS release** | LICENSE (Apache 2.0), README.md, CONTRIBUTING.md, CI workflow, pre-commit, .gitignore, pyproject metadata |
| **Real-world examples** | `fixtures/kubernetes-enterprise.md`, `docs/CAPABILITY.md`, README Real-World Usage section |
| **LLM testing** | Local Ollama tests with qwen2.5:3b and llama3.2:3b on real design docs |
| **LLM docs** | `docs/LLM_SETUP.md`, `scripts/test-llm-extraction.sh`, Ollama-first README |
| **Prompt engineering** | Few-shot examples, section mapping, type coercion rules in extractor prompt; pattern prompt_context with section-to-field guidance |
| **JSON recovery** | `_safe_json_parse()` with multi-stage recovery: direct parse → brace matching → comma insertion → progressive truncation |
| **Extraction quality** | Payments: 5/5 accounts + 3/3 OUs; Enterprise: 8/8 accounts + 5/5 OUs + 4/4 workloads (7B model) — 3B models drop items on long docs |
| **7B model verified** | `qwen2.5:7b` extracts all accounts (8/8), all OUs (5/5), and workloads (2) from enterprise fixture — complete extraction. Default timeout bumped to 180s for local 7B+ models. |
| **Interview save/resume** | `InterviewEngine.save_state()` / `load_state()` with JSON state, `--save`/`--resume` CLI flags |
| **Interview transcript** | `to_markdown()` transcript with grouped categories, `<fill in>` for gaps |
| **Interactive interview** | Progress counter (N/M), bullet options, input validation, 3-attempt retry, `\back` undo, `\save` checkpoint |
| **Discover --resume** | `discover` command supports `--resume` to load saved state before gap analysis |
| **LLM flags on discover** | `--provider`, `--model`, `--base-url`, `--api-key`, `--evidence-output`, `--no-llm` on `discover` |
| **Catalog match after compile** | Auto-suggest closest catalog entry + diff after successful compilation |
| **LZA schema fixes** | Flat IAM config, `schemaVersion: lza-v1` header, `# yaml-language-server: $schema=none` suppression |
| **Cross-reference validators** | `validate_lza_artifacts()` checks workload/network/account OU cross-references |
| **Terraform tfvars generator** | `gen_tfvars()` from `module_inputs` with `_hcl_value()` type coercion |
| **LLM-unavailable warning** | `compile` prints warning to stderr when `auto_detect_llm` returns `None` |
| **Dead code removal** | Removed `extract_graph_result`, `extract_json`, `describe`, `validate_template_output`, `suggest_for_given`, unused Pattern fields |
| **Honest scope reframe** | AGENTS.md: reference tfvars not root modules, LZA coupling documented as debt, silent fallback now warns |
| **Cavekit install** | Skills (spec/build/check/caveman/backprop), commands (ck-spec/ck-build/ck-check), SPEC.md, FORMAT.md |
| **Deterministic entity extraction** | `extract_entities_from_markdown()` parses accounts/OUs/workloads from structured Markdown sections without LLM. Wired into compiler deterministic path. 17 unit + 2 integration tests. Verified: valid-payments.md → 5/5 accounts, 3/3 OUs, 1 workload |
| **AWS LZA thin path** | Added `aws-lza` pattern with `AwsLzaIntent`, `TargetContract`, `ContractValidator`, `ContractRegistry`, graph-driven questions, validators, LZA handoff YAML emitters, lineage manifest, deployment runbook, sample config registration, and tests. No core changes to existing flows. |
| **AWS LZA schema alignment** | `aws-lza` now emits official-style LZA top-level sections (`mandatoryAccounts`, `controlTower`, `defaultVpc`, `centralSecurityServices`, etc.) instead of custom placeholder shapes like `accounts[]` or `network.topology`. |
| **AWS LZA fixture variants** | Added `aws-lza-regulated-v1` and `aws-lza-healthcare-v1` generated fixture bundles plus per-fixture `README.md` docs, alongside refreshed `aws-lza-standard-v1`. |
| **AWS LZA subsection alignment** | `aws-lza` now emits upstream-backed subsections like `identityCenterPermissionSets`, VPC `routeTables`/`subnets`, GuardDuty export settings, and Security Hub org toggles. |
| **AWS LZA security schema depth** | `security-config.yaml` now carries richer upstream-backed shapes for GuardDuty, Security Hub standards, SCP revert notifications, Macie frequencies, SSM automation, and related empty-list/exclude-region fields, with contract assertions guarding key literals. |
| **AWS LZA global/network depth** | `global-config.yaml` now includes termination protection, CDK options, SNS/tag arrays, centralized logging region, and log-bucket lifecycle placeholders; `network-config.yaml` now includes home region, default VPC exclusions, VPC tenancy/NAT/tag placeholders, hub-spoke central network service placeholders, and TGW share targets. |
| **Sample config metadata** | `SampleConfig` now supports generic `description`, `source_contract`, `upstream_variant`, and `tags` metadata so contract-backed variants stay discoverable without AWS-specific core wiring. |
| **Sample config CLI** | Added `intent-engine sample list/show` for registry-backed sample inspection by name or pattern, including metadata, decisions, and module references. |
| **Sample matching** | Generic sample matching now ranks closest sample configs from typed graph decisions and prints recommendations after `compile`/`interview`. CLI list also filters by `--tag` and `--contract`. |
| **Persisted sample handoff** | Patterns with registered sample configs now emit `sample-recommendations.yaml` as output artifact so engineers retain baseline guidance after terminal session ends. |
| **Contract CLI** | `intent-engine contract list/show` exposes registered target contracts, required/optional artifacts, required paths, required decisions, source URL, and decision lineage. |
| **Contract schema checks** | `ArtifactContract.required_paths` lets target contracts validate generated YAML shape without pattern-specific artifact validators. |
| **Contract value assertions** | `ArtifactContract.value_assertions` now validates stable downstream literal values such as org-trail toggles, DNS flags, and GuardDuty export settings. |
| **Contract path semantics** | Plain contract paths now mean field presence, while `[]` means non-empty list. This makes schema checks closer to real JSON/YAML required-field behavior and reduces fake filler data pressure. |
| **Structured prefill coercion** | `RequirementGraph.apply_decisions()` / interview prefill now serialize list and bool values correctly, so registered sample decisions can compile without manual comma-string conversion. |
| **Lineage validation** | `ContractValidator.validate_artifacts()` verifies decision lineage paths exist in structured generated artifacts. |
| **K8s contract migration** | Removed Kubernetes custom artifact validator; `kubernetes-cluster` now uses `TargetContract` for required files, paths, decisions, and lineage. |
| **Generator scoping** | Registered generators support `applies_to`; LZA/K8s/AWS LZA generators are scoped at registry boundary with internal guards only as fallback safety. |
| **Pattern loader cleanup** | CLI now calls `load_builtin_patterns()`; built-in module side effects live in `patterns/__init__.py`, not generic CLI imports. |
| **Debt removal** | LZA required artifact names are centralized in `_LZA_REQUIRED_ARTIFACTS`; unused core generator defaults loader removed. |
| **Generator scoping tests** | Core tests now lock `applies_to` behavior so scoped generators do not run for other patterns. |
| **Fixture sync helper** | `scripts/sync-sample-fixtures.py` regenerates sample fixture bundles from registered sample decisions, prunes stale generated files, and supports `--check` drift detection. |
| **Fixture drift guard** | Sample fixture tests now compile each registered sample and compare checked-in bundles against fresh generated output, with timestamp normalization for `decision-audit.yaml`. |
| **Incremental mypy expansion** | `uv run --extra dev mypy` now covers core contracts, sample config registry, module payload mapping, AWS LZA emitter code, and AWS LZA contract metadata in addition to previous typed files. |
| **LLM-path deterministic backfill** | Compiler now merges deterministic Markdown accounts/OUs/workloads into LLM-produced intent, backfilling dropped or partial named entities from small models without duplicating explicit items. |

### Next (prioritized)
1. [ ] Continue narrowing remaining `aws-lza` field gaps against official LZA sample config schemas, especially IAM permission set/assignment detail when real customer identity inputs exist.
2. [ ] Evaluate adding remaining source files to mypy scope when they change (ongoing incremental policy).
3. [ ] Decide whether fixture drift `--check` belongs in CI for faster, more explicit failure mode.
4. [ ] Decide whether sample recommendations should feed deployment runbooks or decision reports directly, not only standalone artifact.
5. [ ] Decide whether small-model extraction still needs separate workload-only LLM pass after deterministic backfill results settle.

### Key Decisions This Session
- **Global/network LZA shape deepened without deploy ownership**: Added upstream-style CDK/logging/network placeholders and contract checks, but still emits handoff YAML only.
- **Branch-specific contract pressure avoided**: Hub-spoke-only central network services and TGW details are emitted and tested, but not unconditional contract requirements, so `single-vpc` handoff still validates.
- **Mypy follows touched stable code**: Added `patterns/aws_lza/__init__.py` to typed scope after tightening emitter behavior.
- **Deterministic entities now reinforce LLM path**: Accounts, OUs, and workloads parsed from structured Markdown are merged into compiled intent even when an LLM response exists, so small models dropping whole entities no longer erase engineer handoff artifacts.
- **Named-entity merge beats duplicate append**: Added generic list-item merge by `name`, filling only fields that were missing or default-derived on existing items while preserving explicitly extracted values.
- **Mypy scope widened again, not blindly**: Added contracts/sample/module-mapping/AWS LZA contract files to configured mypy scope and fixed `Any` leaks before expanding further.
- **Mypy expansion stays incremental**: Added high-value newly-stable files to typed scope (`core/contracts.py`, `core/sample_config.py`, `core/module_mapping.py`, `patterns/aws_lza/contracts.py`) instead of forcing whole-repo typing churn.
- **Type seams fixed before scope growth**: Typed `_get_pattern_or_exit()` and removed `list` shadowing in sample registry so new mypy coverage catches signal, not avoidable noise.
- **Contracts assert values, not only presence**: Added generic `ArtifactContract.value_assertions` so downstream handoff validation can enforce stable literal values without new pattern-specific validators.
- **AWS invariants belong in contract metadata**: AWS LZA now encodes fixed booleans/strings like org-trail enablement, default VPC deletion, DNS flags, and GuardDuty export settings inside target contract metadata.
- **Fixture bundles must match real compiler output**: Added `scripts/sync-sample-fixtures.py` to regenerate sample bundles from registered sample decisions and prune stale generated files. No more manual copy drift.
- **Fixture naming is data, not hidden convention**: `SampleConfig.fixture_dir` / `fixture_name` makes fixture location explicit so new modules can ship sample bundles without CLI/test special cases.
- **Drift tests normalize only volatile timestamps**: Fixture comparison keeps full content equality for generated bundles while scrubbing `decision-audit.yaml` timestamps, avoiding false failures without hiding real drift.
- **Artifact over terminal-only hint**: Sample recommendations now persist in `sample-recommendations.yaml` instead of living only in CLI stdout. This keeps architect baseline guidance attached to engineer handoff bundles.
- **Generic recommendation artifact**: Sample handoff artifact is emitted by core generator logic using payload pattern + typed decisions, not by AWS LZA/Kubernetes custom generators. New patterns inherit behavior by registering sample configs.
- **Validation keeps handoff bundle honest**: `Pattern.expected_artifacts()` now includes `sample-recommendations.yaml` whenever sample configs exist for that pattern, so validate catches drift or accidental omission.
- **Typed decision reuse**: Added `RequirementGraph.typed_decisions()` so downstream recommendation and handoff code can consume normalized booleans/lists without reimplementing graph parsing logic.
- **Generic sample recommender over pattern-specific hints**: Sample matching lives in `SampleConfig`/`SampleConfigRegistry`, not in AWS LZA or LZA pattern code. This keeps new modules/data models expandable without new CLI branches.
- **Architect-to-engineer continuity**: `compile` and `interview` now print closest sample configs immediately after successful generation. Architects get baseline guidance at decision time; engineers get direct jump-off path to pinned reference bundles.
- **Delegated-admin drift removal**: `security_tooling_account` now feeds `security-config.yaml:centralSecurityServices.delegatedAdminAccount`. Previous `audit_account` mapping contradicted requirement intent and hid security-tooling lineage.
- **Schema-backed subsection depth**: AWS LZA handoff now includes official empty or boolean subsections that engineers must later fill, such as Identity Center permission-set arrays, VPC route-table/subnet arrays, GuardDuty export config, and Security Hub org toggles.
- **Runbook drift cleanup**: Removed stale guidance about placeholder `policies/` and `ssm/` file paths because default thin-path output does not emit them. Runbook now points at real completion work: emails, Identity Center assignments, VPC structures, security exports.
- **Generic sample CLI over AWS one-off UI**: Added `sample list/show` at CLI layer instead of leaving sample variants discoverable only through tests or overloading catalog commands. This resolves stale docs and keeps sample registry first-class.
- **Doc drift removal**: Updated README and capability/example docs to use `sample` commands for sample configs and left catalog commands focused on catalog entries. Sample-config guidance no longer points at wrong CLI surface.
- **Generic sample metadata**: Added contract-aware metadata to `SampleConfig` instead of inventing AWS-only fields. This keeps sample variants data-model-driven and reusable for future contract-backed patterns.
- **Fixture variants as review assets**: Added generated `aws-lza-standard-v1`, `aws-lza-regulated-v1`, and `aws-lza-healthcare-v1` fixture bundles with README docs so variant drift is visible in-repo, not hidden in tests.
- **Structured decision prefill support**: Sample-config `decisions` may contain lists/bools; core prefill paths now serialize them based on requirement target type before graph application. This removes silent mismatch between registry data and compile path.
- **Schema-presence semantics**: `ContractValidator` now treats plain dotted paths as required field presence and reserves `[]` for non-empty list enforcement. This prevents contract checks from forcing meaningless stub items when official schemas allow empty arrays or empty objects.
- **Official LZA shape over custom shape**: `aws-lza` handoff artifacts now target official LZA-required top-level sections (`mandatoryAccounts`, `logging`, `identityCenter`, `defaultVpc`, `organizationalUnits`, `centralSecurityServices`) instead of internal convenience structures.
- **Thin-path placeholder policy**: AWS LZA generator emits minimal official-shape placeholders such as derived account emails, empty policy lists, and empty handoff subsections, then runbook explicitly tells engineers what customer-specific data must be filled before deployment.
- **Thin AWS path**: `aws-lza` emits LZA handoff artifacts and runbook context, not a parallel Terraform/Terragrunt landing-zone stack.
- **Contract-driven core**: AWS LZA sample configurations are treated as source contracts/data models. Provider-specific orchestration stays in the pattern layer.
- **Target contract extraction**: `AWS_LZA_SAMPLE_CONFIG_CONTRACT` now centralizes mandatory/optional LZA artifacts and decision lineage so pattern metadata, validation, runbook, and manifest do not duplicate contract knowledge.
- **ContractValidator**: Added reusable core validator for target contracts: validates required decisions, required artifacts, and lineage references. This is the generic bridge for LZA sample configs, Terraform module schemas, org catalogs, and future custom workloads.
- **Contract graph drift guard**: `ContractValidator.validate_graph()` ensures contract-required and lineage decisions have matching graph nodes. `aws-lza` fails fast if contract and graph diverge.
- **Contract registry**: `GLOBAL_CONTRACT_REGISTRY` lets future targets register discoverable contracts such as `terraform-aws-vpc`, `terraform-aws-eks`, org catalogs, or custom workload contracts.
- **Pattern contract metadata**: `Pattern.contracts` makes target contracts first-class pattern metadata. Pattern registration validates contract definition + graph alignment, and generated artifact validation runs contract checks automatically.
- **Debt cleanup**: Added `Pattern.expected_artifacts()` and `extra_artifacts` so contract artifacts stay single-source. Added `string_list` target type and moved AWS region/OU/account list decisions off misleading `cidr_list`.
- **Generator scoping**: Added `applies_to` metadata to registered generators and compiler now passes the selected pattern to generation. LZA, K8s, and AWS LZA generators are pattern-scoped, reducing reliance on broad global guard behavior.
- **Contract CLI**: Added `intent-engine contract list/show` so target contracts are discoverable from CLI. `show --pattern aws-lza` reveals mandatory/optional LZA artifacts, required decisions, source URL, and decision-to-artifact lineage.
- **Contract required paths**: Added reusable `ArtifactContract.required_paths`; generated artifact validation now catches malformed YAML and missing nested/list paths from contract metadata. `lineage-manifest.yaml` now includes artifact contracts with `requiredPaths`.
- **Lineage path validation**: Generated artifact validation now checks contract lineage paths for structured artifacts, skips non-YAML/unschematized artifacts, and avoids duplicate noise when schema validation already failed.
- **K8s contract migration**: Removed `_k8s_artifact_validator`; Kubernetes now uses contract-driven artifact validation. `validate_generated_violations()` uses `pattern.expected_artifacts()` as the single required-file source and dedupes user-facing messages.
- **Extension contract docs**: `EXTENSION.md` now recommends `TargetContract` + `applies_to` first, with `required_artifacts`/`artifact_validators` reserved for legacy/simple or cross-file rules.
- **Pattern registration cleanup**: Added `load_builtin_patterns()` so CLI no longer imports individual pattern modules directly. Pattern-specific registration side effects stay in the pattern package.
- **K8s generator guard cleanup**: K8s generators now unwrap `IaCIntentPayload` and guard on concrete `K8sIntent`, matching AWS LZA style instead of loose `hasattr` checks.
- **Duplication removal**: Replaced repeated LZA required artifact lists with `_LZA_REQUIRED_ARTIFACTS`. Removed unused `_load_generator_config()` from core generator.
- **Contract CLI coverage**: Added CLI coverage for `contract show --pattern kubernetes-cluster` so K8s contract migration remains visible.
- **LZA artifact validator simplification**: Removed duplicate top-level key checks from `validate_lza_artifacts`; it now focuses on cross-file consistency while file/path validation lives in core/contract flow.
- **Generator scoping guardrail**: Added core tests for `applies_to` matching and non-matching behavior. Updated stale LZA generator docstring to point to registry-level scoping.
- **Contract validation simplification**: `ContractValidator.validate_artifacts()` now loads each YAML artifact once and reuses parsed data for required-path and lineage checks. Generated validation no longer checks contract files separately before contract validation; pattern file checks cover only legacy/simple and extra artifacts.
- **Artifact validation cleanup**: Internal generated-artifact validation now uses `Violation`; `validate_generated()` remains a backwards-compatible message wrapper.
- **AWS LZA golden fixture**: Added `fixtures/aws-lza-standard-v1/` and a golden test so default AWS LZA handoff artifacts are reviewable and drift-protected.
- **Borrowed from rxt-code-accelerator**: Kept Pydantic spec discipline, graph validation, lineage manifest, preflight/runbook mindset, and golden-test direction. Did not import Azure generator shape or wrapper parity.
- **Generator isolation**: AWS generators now guard on concrete `AwsLzaIntent`, not loose `hasattr`, because the global generator registry runs every generator for every pattern.

Respond terse like smart caveman. All technical substance stay. Only fluff die.

Rules:
- Drop: articles (a/an/the), filler (just/really/basically), pleasantries, hedging
- Fragments OK. Short synonyms. Technical terms exact. Code unchanged.
- Pattern: [thing] [action] [reason]. [next step].
- Not: "Sure! I'd be happy to help you with that."
- Yes: "Bug in auth middleware. Fix:"

Switch level: /caveman lite|full|ultra|wenyan
Stop: "stop caveman" or "normal mode"

Auto-Clarity: drop caveman for security warnings, irreversible actions, user confused. Resume after.

Boundaries: code/commits/PRs written normal.
