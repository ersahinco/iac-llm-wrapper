# iac-llm-wrapper

**LLM-powered infrastructure decision engine.**

Architects describe infrastructure intent in prose. The tool extracts structured decisions, validates them against architectural knowledge graphs, and produces traceable artifacts engineers can act on.

At its core is **intent-engine** — a knowledge-driven decision framework that powers extraction, validation, and generation. The `iac-llm-wrapper` package bundles this engine with off-the-shelf patterns for common infrastructure scenarios (landing zones, Kubernetes, compliance).

Not a code generator. Not a Terraform/CDK wrapper. A **decision capture and validation** layer that sits between design documents and provisioning pipelines.

## The Core Idea

Infrastructure design today means prose docs → misinterpretation → rework → compliance surprises.

This project replaces that with a **model-driven flow**:

```
Prose / Markdown
     │
     ▼
Extraction ──── LLM traverses a requirement graph and detects signals
     │
     ▼
Interview ───── Guided questions fill remaining gaps (via CLI or API)
     │
     ▼
Validation ──── Fail-closed checks against the graph. Catches missing decisions early.
     │
     ▼
Normalization ─ Defaults applied only when applicable. Duck-typed, pattern-aware.
     │
     ▼
Output ──────── Contract handoff artifacts, lineage, runbooks, module inputs
```

**Every decision is recorded** with timestamp, rationale, compliance context, and tradeoffs. Architects get living documentation. Compliance gets an audit trail. Engineers get a validated decision set to map to their IaC of choice.

The goal is not to reinvent infrastructure tooling. Existing accelerators and modules stay the delivery layer. LLMs help read human intent, surface missing decisions, and draft structured inputs; Pydantic models, requirement graphs, target contracts, validators, lineage, and runbooks keep the path safe and repeatable.

## Quick Start (Ollama + uv)

Run entirely locally with a 3B parameter model:

```bash
# 1. Install Ollama and pull a small model
ollama pull qwen2.5:3b
ollama serve

# 2. Set up the project
uv venv
source .venv/bin/activate
uv pip install -e ".[dev,llm]"

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

# Anthropic
export ANTHROPIC_API_KEY=sk-ant-...
iac-llm-wrapper compile -i design.md -o out/ --provider anthropic
```

### Without LLM (Bootstrap Only)

The deterministic fallback applies graph defaults, runs signal keyword matching, and can recover
structured Markdown entity sections for accounts, OUs, and workloads. It still cannot interpret
arbitrary free-form prose. Use only for unit tests or when you have no LLM access:

```bash
INTENT_ENGINE_DISABLE_LLM=1 iac-llm-wrapper compile -i design.md -o out/
```

### Evaluate Complex Docs

Run the checked-in eval corpus to test extraction quality against expected generated artifacts:

```bash
uv run python scripts/evaluate-extraction.py
uv run python scripts/evaluate-extraction.py --llm --provider ollama --model qwen2.5:7b
uv run python scripts/evaluate-usability.py
uv run python scripts/evaluate-usability.py --llm --provider ollama --model qwen2.5:7b
uv run python scripts/evaluate-usability.py --llm --provider ollama --model qwen2.5:7b --evidence-dir /tmp/iac-llm-evidence
```

The eval loop compiles docs in `fixtures/eval/`, compares `decision-report.yaml` values,
entity counts/names, and required handoff files, then exits non-zero on misses.
The usability loop checks role-based trials for architect gap discovery, engineer handoff,
and bring-your-own Terraform module input generation. Deterministic mode is the CI plumbing
gate; `--llm` is the product-quality check for local/provider models. In `--llm` mode,
the script verifies evidence files contain LLM calls; use `--evidence-dir` to keep the
prompt/response YAML for inspection or observability import.

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

The tool extracts decisions, detects signals (PCI scope, regulated industry, hybrid connectivity), and reports any gaps.

### 3. Inspect Contract and Samples

```bash
# See required AWS LZA handoff files, decisions, and lineage paths
iac-llm-wrapper contract show --pattern aws-lza

# See pinned reference bundles for engineer handoff
iac-llm-wrapper sample list --contract aws-lza-sample-configuration
```

This keeps the path explicit: graph decisions must satisfy a target contract,
then engineers receive generated handoff files plus matching sample bundles.

### 4. Compile to Decision Artifacts

```bash
iac-llm-wrapper compile -i design.md -o out/ --pattern aws-lza
```

For `aws-lza`, output includes:
- `decision-report.yaml` — decisions, deployment readiness, blockers, and safe handoff path
- `accounts-config.yaml`, `global-config.yaml`, `iam-config.yaml`, `network-config.yaml`, `organization-config.yaml`, `security-config.yaml` — AWS LZA handoff config files
- `lineage-manifest.yaml` — decision-to-artifact path map
- `deployment-runbook.md` — prerequisites and handoff sequence
- `sample-recommendations.yaml` — closest pinned reference bundles for handoff
- `llm-trace-summary.yaml` — provider/model, calls, extracted decisions, gaps,
  contradictions, and raw evidence path when compile used extraction evidence

When compile is blocked, `decision-report.yaml` and `llm-trace-summary.yaml`
must satisfy the built-in `blocked-assessment-artifacts` contract.

### 5. Engineer Handoff

Engineers use the decision artifacts alongside sample configurations:

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

Engineers apply BYOM inputs to their Terraform/CDK/CloudFormation modules.
For `aws-lza`, engineers review the generated LZA config files and runbook instead.
`sample-recommendations.yaml` preserves best matching reference bundles in output
directory so engineers can recover proven starting points later without re-running
interview session.
After `compile` or `interview`, the CLI also prints closest sample matches for the
selected pattern to speed architect baseline selection and engineer handoff.
Checked-in sample fixture bundles can be refreshed with
`uv run python scripts/sync-sample-fixtures.py` and drift-checked with
`uv run python scripts/sync-sample-fixtures.py --check`. CI runs the same check so
generated fixture bundles cannot drift silently.

## Patterns

Patterns define questions, defaults, contracts, and output artifacts. Recommended product paths stay thin and contract-backed:

| Pattern | Description |
|---------|-------------|
| `aws-lza` | Thin AWS Landing Zone Accelerator handoff path using official-style LZA config artifacts |
| `kubernetes-cluster` | K8s cluster provisioning with node pools and network policies |
| `terraform-vpc` | BYOM Terraform AWS VPC module input capture |

## Developer Experience

- **CLI-first workflow**: Typer-based CLI with discover/compile/interview/validate/sample/contract/template/review commands for both architects and platform engineers.
- **uv for dependency management**: Fast, reproducible local setup and CI parity.
- **Model-driven type safety**: Pydantic v2 models are the contract for extraction, normalization, validation, and generation.
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

- No cloud API calls and no direct infrastructure deployment from prose.
- Decision artifacts are auditable (timestamps, rationale, compliance context).
- CI runs lint, format, and tests across supported Python versions.
- Dependency and static security checks are part of the roadmap for hardening before broader GA.

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

New requirements automatically appear in LLM prompts, interview questions, default application, validation, and generation — no core code changes needed.

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

See the [extension guide](EXTENSION.md) for the full contract.

## Architecture

```
iac-llm-wrapper/
└── src/
    └── intent_engine/     # Core decision engine
        ├── cli.py         # Typer CLI
        ├── core/          # Framework: models, graph, extraction, etc.
        └── patterns/      # Pluggable patterns (LZA, K8s, ...)
```

## Why Not Terraform/CDK/CloudFormation?

Those tools execute infrastructure. This tool **designs infrastructure** — it captures the architectural decisions that should be made *before* provisioning. It produces decision artifacts that engineers use alongside sample configurations and IaC modules. It does not generate deployable infrastructure.

## LLM Testing

Tested with local Ollama models on real design documents:

| Model | Size | Payments LZA | K8s Platform | Enterprise Hybrid |
|-------|------|-------------|-------------|-------------------|
| qwen2.5:3b | 3B | ✓ | ✓ | ✓ |
| llama3.2:3b | 3B | ✓ | — | — |

**What a 3B model can extract:**
- Region, topology, CIDR blocks
- Security settings (audit retention, logging, encryption)
- CI/CD mode and placement
- Network appliance configuration
- Kubernetes cluster name, version, node pools

**What it struggles with:**
- Complex account/OU lists (use `--decisions` JSON)
- Multi-workload parsing (structured format helps)
- Implicit requirements (signal detection covers these)

Run deterministic and LLM-backed eval loops:

```bash
uv run python scripts/evaluate-extraction.py
uv run python scripts/evaluate-extraction.py --llm --provider ollama --model qwen2.5:7b
uv run python scripts/evaluate-usability.py --llm --provider ollama --model qwen2.5:7b
```

See [docs/LLM_SETUP.md](docs/LLM_SETUP.md) for detailed model setup and troubleshooting.

## Project Status

Alpha. 522+ tests. Core architecture is stable. Pattern library is growing. Contributions welcome.

## License

Apache 2.0
