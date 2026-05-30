# iac-llm-wrapper

**Intent-to-IaC orchestration framework.**

Architects write messy design docs. The tool extracts structured decisions,
checks them against requirement graphs and target contracts, and emits traceable
handoff artifacts for engineers.

The repository and package are named `iac-llm-wrapper`. The core is
**intent-engine**. Today it wraps LLM extraction with deterministic decision
validation and emits handoff artifacts. Generation, execution, dashboards, and
cloud changes stay downstream unless a registered target adapter explicitly owns
them and passes graph, contract, and gate checks.
The primary CLI is `iac-llm-wrapper`; `intent-engine` is kept as an optional
alias for the core engine.

LLMs help read intent. Human-owned models, requirement graphs, contracts,
validators, lineage, runbooks, and evals decide what is acceptable. Existing
accelerators, modules, and provisioning pipelines remain the delivery layer.

## The Core Idea

Infrastructure delivery often starts with prose, then loses decisions during
handoff. That creates rework, compliance gaps, and unsafe defaults.

This project replaces that with a **model-driven flow**:

```
Prose / Markdown
     │
     ▼
Extraction ──── LLM extracts graph decisions from prose
     │
     ▼
Interview ───── Guided questions fill remaining gaps (via CLI or API)
     │
     ▼
Validation ──── Fail-closed checks against graph, model, and target contracts
     │
     ▼
Output ──────── Target handoff artifacts for the downstream IaC toolchain
```

Every decision is recorded with provenance. Architects get a living decision
record. Compliance gets traceability. Engineers get a validated handoff bundle
for their IaC toolchain.

Goal: reduce ambiguity before provisioning and create a controlled path toward
IaC delivery. LLMs read human intent and surface missing or conflicting decisions.
Deterministic models, graphs, contracts, validators, lineage, runbooks, and evals
decide when handoff, generation, or execution is allowed.

## Quick Start (Ollama + uv)

Run entirely locally with a 3B parameter model:

```bash
# 1. Install Ollama and pull a small model
ollama pull qwen2.5:3b
ollama serve

# 2. Set up the project
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# 3. Compile a design doc with local LLM
iac-llm-wrapper compile -i fixtures/usability/engineer-handoff-lza.md -o out/ \
  --pattern aws-lza --provider ollama --model qwen2.5:3b
```

No API key required. A 3B model (2GB RAM) extracts region, topology, CIDR, accounts, and security settings from Markdown in 8-15 seconds on modern laptops.

### Alternative: Cloud LLM

```bash
# OpenAI
export OPENAI_API_KEY=sk-...
iac-llm-wrapper compile -i design.md -o out/ --provider openai
```

### Without LLM (Bootstrap Only)

The deterministic fallback applies graph defaults and can recover structured
Markdown entity sections for accounts, OUs, and workloads. It still cannot
interpret arbitrary free-form prose. Use only for unit tests or when you have no
LLM access:

```bash
INTENT_ENGINE_DISABLE_LLM=1 iac-llm-wrapper compile -i design.md -o out/
```

### Evaluate Complex Docs

Run the checked-in eval corpus to test extraction quality against expected
handoff artifacts:

```bash
uv run python scripts/evaluate-extraction.py
uv run python scripts/evaluate-extraction.py --llm --provider ollama --model qwen2.5:7b
uv run python scripts/evaluate-extraction.py --llm --provider ollama --model qwen2.5:7b --evidence-dir /tmp/iac-llm-evidence
uv run python scripts/evaluate-usability.py
uv run python scripts/evaluate-usability.py --llm --provider ollama --model qwen2.5:7b
uv run python scripts/evaluate-usability.py --llm --provider ollama --model qwen2.5:7b --evidence-dir /tmp/iac-llm-evidence
```

The eval loop compiles docs in `fixtures/eval/`, compares decision values,
entity names/counts, required files, trace shape, and contract checks, then exits non-zero
on misses. The usability loop checks role-based trials for architect gap
discovery, engineer handoff, and bring-your-own Terraform module input capture.
It also includes a CloudFormation parameter handoff trial to prove BYOM
orchestration beyond Terraform without generating a stack.
Deterministic mode is the CI harness gate; `--llm` is the model-quality gate.
Use `--evidence-dir` to keep prompt/response YAML for inspection.

Install from PyPI:

```bash
uv pip install iac-llm-wrapper
```

## Real-World Usage

### 1. Start with a Design Document

Write infrastructure intent in Markdown (see `fixtures/usability/engineer-handoff-lza.md`
for a thin AWS LZA example):

```markdown
# Payments Landing Zone

## LZA Baseline
- baseline: standard

## Organization
- org_mode: control-tower
- organization_name: ExampleCorp
- organizational_units: Security, Infrastructure, Workloads

## Regions
- home_region: eu-central-1
- enabled_regions: eu-central-1

## Accounts
- workload_accounts: AppProd
- audit_account: Audit
- log_archive_account: LogArchive
- security_tooling_account: SecurityTooling
- network_account: Network

## Identity
- identity_center_delegated_admin_account: SecurityTooling
- identity_center_permission_sets: ReadOnlyAccess, PowerUserAccess
- identity_center_assignments: PlatformAdmins:PowerUserAccess:Management, AppTeam:ReadOnlyAccess:AppProd

## Network
- topology: hub-spoke
- network_cidr: 10.50.0.0/16

## Security
- centralized_logging: true
- security_hub_enabled: true
- guardduty_enabled: true
```

### 2. Discover Signals and Gaps

```bash
iac-llm-wrapper discover -i design.md --pattern aws-lza
```

The tool extracts graph decisions and reports applicable gaps for the selected
pattern.

### 3. Inspect Contract and Samples

```bash
# Export the requirement graph for review or UI consumption
iac-llm-wrapper graph export --pattern aws-lza --format mermaid
iac-llm-wrapper graph export --pattern aws-lza --format json

# See required AWS LZA handoff files, decisions, and lineage paths
iac-llm-wrapper contract show --pattern aws-lza

# See pinned reference bundles for engineer handoff
iac-llm-wrapper sample list --contract aws-lza-sample-configuration
```

This keeps the path explicit: graph decisions must satisfy a target contract
before engineers receive handoff files and matching sample bundles.

### 4. Compile to Handoff Artifacts

```bash
iac-llm-wrapper compile -i design.md -o out/ --pattern aws-lza
```

For `aws-lza`, successful output includes:
- `decision-report.yaml` — decisions, deployment readiness, blockers, and safe handoff path
- `accounts-config.yaml`, `global-config.yaml`, `iam-config.yaml`, `network-config.yaml`, `organization-config.yaml`, `security-config.yaml` — AWS LZA handoff config files
- `lineage-manifest.yaml` — decision-to-artifact path map
- `handoff-plan.yaml` — ordered owners, dependencies, gates, rollback, boundary, and allowed next action
- `deployment-runbook.md` — prerequisites and handoff sequence
- `sample-recommendations.yaml` — closest pinned reference bundles for handoff
- `llm-trace-summary.yaml` — provider/model, calls, raw and accepted decisions,
  resolved/blocking gaps, blocking contradictions, and raw evidence status

When compile is blocked, only safe assessment artifacts are written:
`decision-report.yaml` and `llm-trace-summary.yaml`. They must satisfy the
built-in `blocked-assessment-artifacts` contract.

Generate a portable static review page when humans need one file to inspect:

```bash
iac-llm-wrapper review html --input out/ --output out/handoff-review.html
```

The page summarizes readiness, allowed next action, blockers, decisions,
artifacts, handoff-plan steps, and LLM trace summary without running a server.

### 5. Engineer Handoff

Engineers use the handoff artifacts alongside sample configurations:

```bash
# List available sample configs
iac-llm-wrapper sample list

# Narrow by contract or metadata tag
iac-llm-wrapper sample list --contract aws-lza-sample-configuration
iac-llm-wrapper sample list --tag regulated

# Show sample config with contract metadata and decisions
iac-llm-wrapper sample show --name aws-lza-standard-v1
```

For BYOM module patterns such as `terraform-vpc`, `module-inputs.yaml` provides
ready-to-use module references:

```yaml
moduleInputs:
  - moduleName: terraform-aws-vpc
    variables:
      name: orders-vpc
      cidr: 10.0.0.0/16
      azs:
        - eu-central-1a
        - eu-central-1b
```

For `cloudformation-parameters`, `cloudformation-parameters.yaml` captures
parameters for an existing approved template without emitting a stack:

```yaml
cloudFormationParameters:
  stackName: orders-network
  templateUrl: s3://approved-templates/network.yaml
  parameters:
    EnvironmentName: orders
    VpcCidr: 10.60.0.0/16
```

Engineers apply BYOM inputs to their Terraform, CDK, or CloudFormation modules.
For `aws-lza`, engineers review the emitted LZA config files and runbook instead.
`sample-recommendations.yaml` preserves best matching reference bundles in output
directory so engineers can recover proven starting points later without re-running
interview session.
After `compile` or `interview`, the CLI also prints closest sample matches for the
selected pattern to speed architect baseline selection and engineer handoff.
Checked-in sample fixture bundles can be refreshed with
`uv run python scripts/sync-sample-fixtures.py` and drift-checked with
`uv run python scripts/sync-sample-fixtures.py --check`. CI runs the same check so
emitted fixture bundles cannot drift silently.

## Patterns

Patterns define questions, defaults, contracts, validators, and output files.
Recommended product paths stay thin and contract-backed:

| Pattern | Description |
|---------|-------------|
| `aws-lza` | Contract-backed AWS Landing Zone Accelerator handoff using official-style LZA config artifacts |
| `cloudformation-parameters` | BYOM CloudFormation parameter handoff for an existing template |
| `kubernetes-cluster` | K8s cluster handoff with optional Terraform EKS module input references |
| `terraform-vpc` | BYOM Terraform AWS VPC module input capture |

## Developer Experience

- **CLI-first workflow**: Typer-based CLI with discover/compile/interview/validate/sample/contract/graph/template/review commands for both architects and platform engineers.
- **uv for dependency management**: Fast, reproducible local setup and CI parity.
- **Model-driven type safety**: Pydantic v2 models are the contract for extraction, validation, and artifact emission.
- **Fail-closed validation**: Graph-driven violation codes prevent incomplete or contradictory decisions from reaching implementation.

## Quality and Security

Current quality gates:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run --extra dev mypy
uv run python scripts/evaluate-extraction.py
uv run python scripts/evaluate-usability.py
```

Recommended local hooks:

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

Security posture:

- Current built-in paths make no cloud API calls and do not deploy infrastructure from prose.
- Decision artifacts are auditable (timestamps, rationale, compliance context).
- CI runs lint, format, tests, dependency audit, Bandit, and SBOM generation across supported Python versions.

## Extending

### Add a requirement to a pattern

```python
from intent_engine.core.requirements import Requirement, RequirementGraph

g = RequirementGraph()
g.add(
    Requirement(
        key="my_custom_setting",
        target_field="my_custom_setting",
        target_type="string",
        label="Custom Setting",
        question="What value for this setting?",
        default="default-value",
        category="general",
        options=["option-a", "option-b"],
    )
)
```

New requirements automatically appear in LLM prompts, interview questions,
default application, validation, and artifact emission. No core code changes
needed.

### Create a new pattern

```python
from intent_engine.core.patterns import GLOBAL_REGISTRY, Pattern

def my_graph_factory() -> RequirementGraph:
    g = RequirementGraph()
    # Add your requirements...
    return g

GLOBAL_REGISTRY.register(
    Pattern(
        name="my-pattern",
        description="My custom pattern",
        graph_factory=my_graph_factory,
        intent_factory=MyIntentModel,
    )
)
```

See the [extension guide](docs/EXTENSION.md) for the full contract.

## Architecture

```
iac-llm-wrapper/
└── src/
    └── intent_engine/     # Core intent engine
        ├── cli.py         # Typer CLI
        ├── core/          # Framework: models, graph, extraction, etc.
        └── patterns/      # Pluggable patterns (LZA, K8s, ...)
```

## Why Not Terraform, CDK, or CloudFormation?

Those tools provision infrastructure. This tool captures and validates the
decisions that must be made before provisioning. Today it emits handoff artifacts
engineers use with existing accelerators, sample configurations, and IaC modules.
Generation or execution stays downstream unless a registered target adapter owns
that behavior and passes graph, contract, and gate checks. It does not generate
arbitrary deployable infrastructure from prose.

## LLM Testing

Tested with local Ollama models on real design documents:

| Model | Size | Payments LZA | K8s Platform | Enterprise Hybrid |
|-------|------|-------------|-------------|-------------------|
| qwen2.5:3b | 3B | ✓ | ✓ | ✓ |
| llama3.2:3b | 3B | ✓ | — | — |

**What a 3B model can extract in current fixtures:**
- Region, topology, CIDR blocks
- Security settings (audit retention, logging, encryption)
- IAM Identity Center permission sets and assignments
- Kubernetes cluster name, version, node pools

**What it struggles with:**
- Complex account/OU lists (use `--decisions` JSON)
- Multi-workload parsing (structured format helps)
- Implicit requirements (signal detection covers these)

Run deterministic and LLM-backed eval loops:

```bash
uv run python scripts/evaluate-extraction.py
uv run python scripts/evaluate-extraction.py --llm --provider ollama --model qwen2.5:7b
uv run python scripts/evaluate-extraction.py --llm --provider ollama --model qwen2.5:7b --evidence-dir /tmp/iac-llm-evidence
uv run python scripts/evaluate-usability.py --llm --provider ollama --model qwen2.5:7b
```

See [docs/LLM_SETUP.md](docs/LLM_SETUP.md) for detailed model setup and troubleshooting.

## Project Status

Alpha. Core architecture is stable. Pattern library is growing. Contributions welcome.

## License

Apache 2.0
