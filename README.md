# iac-llm-wrapper

**Architect exchange to registered target configuration.**

Architects write messy design docs. The tool extracts structured decisions,
checks them against requirement graphs and target contracts, and emits traceable
target configuration artifacts for engineers and existing deployment mechanisms.

The repository and package are named `iac-llm-wrapper`. The core is
**intent-engine**. Today it wraps LLM extraction with deterministic decision
validation and emits registered-target configuration artifacts. Direct
deployment, dashboards, and cloud changes stay downstream; the tool can say when
a bundle is ready for an existing deployment mechanism, but it does not invoke
that mechanism.
The primary CLI is `iac-llm-wrapper`; `intent-engine` is kept as an optional
alias for the core engine.

LLMs help read intent. Human-owned models, requirement graphs, contracts,
validators, lineage, runbooks, and evals decide what is acceptable. Existing
accelerators, modules, and provisioning pipelines remain the delivery layer.
AWS Landing Zone Accelerator is the reference path: collected and validated
inputs become LZA YAML/config files consumed by the downstream LZA deployment
process.

## The Core Idea

Infrastructure delivery often starts with prose, then loses decisions during
handoff. That creates rework, compliance gaps, and unsafe defaults.

This project replaces that with a **registered-target flow**:

```
Architect packet / Markdown / Interview
     │
     ▼
Extraction ──── LLM extracts graph decisions from prose
     │
     ▼
Requirement graph ─ Accept known decisions, find gaps, ask for missing inputs
     │
     ▼
Target contracts ─ Fail-closed validation of required files, paths, and lineage
     │
     ▼
Output ──────── Deterministic target configuration artifacts and handoff plan
```

Every decision is recorded with provenance. Architects get a living decision
record. Compliance gets traceability. Engineers get a validated configuration
bundle for an existing deployment mechanism.

Goal: reduce ambiguity before provisioning and create a controlled path toward
IaC delivery. LLMs read human intent and surface missing or conflicting decisions.
Deterministic models, graphs, contracts, validators, lineage, runbooks, and evals
decide when a registered-target configuration bundle is ready to hand off.

Use [docs/GLOSSARY.md](docs/GLOSSARY.md) for the shared project language:
intent, decision, requirement graph, registered target, target configuration
artifact, deployment target contract, existing deployment mechanism, readiness,
allowed next action, pattern, battle test, and evidence.

## Where To Look

| Need | Start here |
| --- | --- |
| Run a local handoff | [Quick Start](#quick-start-ollama--uv) |
| Understand the core flow | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Understand emitted files | [docs/ARTIFACTS.md](docs/ARTIFACTS.md) |
| Visualize graphs and results | [docs/DEVELOPER_VISUALS.md](docs/DEVELOPER_VISUALS.md) |
| Add or change a pattern | [docs/PATTERN_AUTHORING.md](docs/PATTERN_AUTHORING.md) |
| Keep LLM context reviewable | [docs/CONTEXT_AS_CODE.md](docs/CONTEXT_AS_CODE.md) |
| Tune or compare LLMs | [docs/LLM_SETUP.md](docs/LLM_SETUP.md) |
| Contribute safely | [CONTRIBUTING.md](CONTRIBUTING.md) |

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

## First Successful Customer Packet Run

Use this path for messy real notes, meeting summaries, and architect
clarifications. Keep secret values out of the packet; write secret-store
references and expected parameter names instead.

```bash
# 1. Check what the packet already answers and what still needs an owner
iac-llm-wrapper discover -i customer-packet.md --pattern aws-lza \
  --provider ollama --model qwen2.5:7b

# 2. Compile service-style artifacts without storing raw prompts/responses
iac-llm-wrapper compile -i customer-packet.md -o out/customer-packet \
  --pattern aws-lza --provider ollama --model qwen2.5:7b --no-raw-evidence

# 3. Generate the one-file human review page
iac-llm-wrapper review html --input out/customer-packet \
  --output out/customer-packet/handoff-review.html
```

For Bedrock, keep the same command shape and swap only provider/model:

```bash
aws sts get-caller-identity
iac-llm-wrapper compile -i customer-packet.md -o out/customer-packet \
  --pattern aws-lza --provider bedrock \
  --model eu.amazon.nova-2-lite-v1:0 --no-raw-evidence
```

If compile is blocked, the CLI still writes safe assessment artifacts. Generate
the same review page, answer the blocker traceability questions in the source
Markdown, and re-run compile. If compile is ready, reviewers use
`handoff-review.html`, `context-manifest.yaml`, `handoff-plan.yaml`,
`deployment-runbook.md`, target configuration files, and
`sample-recommendations.yaml` before passing anything to the existing deployment
mechanism.

### Alternative: Cloud LLM

```bash
# OpenAI
export OPENAI_API_KEY=sk-...
iac-llm-wrapper compile -i design.md -o out/ --provider openai

# Amazon Bedrock through the local AWS CLI credentials/session
iac-llm-wrapper compile -i design.md -o out/ \
  --provider bedrock \
  --model eu.amazon.nova-2-lite-v1:0
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
uv run python scripts/evaluate-golden-journey.py --scenario ready
uv run python scripts/evaluate-golden-journey.py --scenario blocked
uv run python scripts/evaluate-golden-journey.py --scenario all --output tests/results/golden-journey.yaml
uv run python scripts/evaluate-golden-journey.py --llm --provider ollama --model qwen2.5:7b
uv run python scripts/evaluate-golden-journey.py --llm --provider ollama --model qwen2.5:7b --require-conformant
uv run python scripts/evaluate-golden-journey.py --llm --provider ollama --model qwen2.5:7b --keep-output tests/results/golden-qwen2.5-7b --benchmark-output tests/results/golden-qwen2.5-7b.yaml
uv run python scripts/evaluate-golden-journey.py --scenario all --llm --provider bedrock --model eu.amazon.nova-2-lite-v1:0 --keep-output tests/results/golden-bedrock-nova-2-lite --output tests/results/golden-journey-bedrock-nova-2-lite.yaml
uv run python scripts/evaluate-usability.py
uv run python scripts/evaluate-usability.py --llm --provider ollama --model qwen2.5:7b
uv run python scripts/evaluate-usability.py --llm --provider ollama --model qwen2.5:7b --evidence-dir /tmp/iac-llm-evidence
uv run python scripts/battle-test.py --fixture aws-lza-complex-enterprise-handoff --llm --provider ollama --model qwen2.5:7b
uv run python scripts/compare-model-benchmarks.py tests/results/*/model-benchmark.yaml
uv run python scripts/compare-model-benchmarks.py --require-conformant tests/results/*/model-benchmark.yaml
```

The eval loop compiles docs in `fixtures/eval/`, compares decision values,
entity names/counts, required files, trace shape, and contract checks, then exits non-zero
on misses. The golden journey loop is the quickest product-confidence check.
`--scenario ready` compiles the customer-style AWS LZA fixture with
`--no-raw-evidence`, writes `handoff-review.html`, and verifies readiness,
allowed next action, contracts, manual gates, target artifacts, trace summary,
model benchmark conformance, and raw evidence omission. `--scenario blocked`
proves messy blocked input stays safe: compile fails closed, only assessment and
review artifacts are emitted, blocker ownership/questions are visible, and no
deployable or target configuration artifacts appear. Use `--require-conformant` when
an LLM run must prove `conformance=pass`; use `--benchmark-output` to keep the
compact model summary without opening the full artifact bundle. Use `--output`
to write a compact ready/blocked result artifact for CI archives or model-run
comparison. The usability loop checks role-based trials for architect gap
discovery, engineer handoff, and bring-your-own Terraform module input capture.
It also includes a CloudFormation parameter handoff trial to prove BYOM
orchestration beyond Terraform without generating a stack, plus static review
page trials that check ready and blocked `handoff-review.html` signals for
architects, platform engineers, security reviewers, model developers, and
non-developer stakeholders who need to know what is ready, what is blocked, and
what can move to the provisioning toolchain.
Deterministic mode is the CI harness gate; `--llm` is the model-quality gate.
LLM-backed `compile` keeps prompt/response YAML at
`<output>/raw-evidence.yaml` by default. Use `--evidence-output` to choose a
different path, `--no-raw-evidence` for service-style runs that keep only trace
and benchmark summaries, or `--evidence-dir` in eval scripts to keep per-case
evidence. Treat raw evidence as local development/debug material that may
contain customer design content; it is not needed as a service artifact. Keep
secret values out of design docs and handoff artifacts; use secret-store
references plus expected parameter names so downstream IaC tooling resolves
values under its own access controls.
Use `battle-test.py` for repeatable local artifact bundles under ignored
`tests/results/`; each run writes `battle-summary.yaml` with a verdict,
confidence categories, findings, and improvement items.

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

# Check graph, contracts, bounded context, samples, and expected artifact surface
iac-llm-wrapper pattern check --pattern aws-lza

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
- `decision-report.yaml` — decisions, handoff readiness, blockers, safe handoff path,
  and pattern-owned semantic model details when available
- `accounts-config.yaml`, `global-config.yaml`, `iam-config.yaml`, `network-config.yaml`, `organization-config.yaml`, `security-config.yaml` — AWS LZA target configuration artifacts
- `lineage-manifest.yaml` — decision-to-artifact path map
- `context-manifest.yaml` — code-owned context inventory: pattern, prompt
  context, requirement graph, contracts, samples, target capabilities, and
  expected artifacts
- `handoff-plan.yaml` — ordered owners, dependencies, gates, rollback, boundary, and allowed next action
- `deployment-runbook.md` — prerequisites and handoff sequence
- `sample-recommendations.yaml` — closest pinned reference bundles for handoff
- `llm-trace-summary.yaml` — provider/model, calls, raw and accepted decisions,
  resolved/blocking gaps, blocking contradictions, and raw evidence status
- `model-benchmark.yaml` — latency, token, raw LLM coverage, conformance,
  quality, readiness, and cost-status rollups for LLM evaluation without
  embedding an observability platform

When compile is blocked, only safe assessment artifacts are written:
`decision-report.yaml`, `llm-trace-summary.yaml`, and `model-benchmark.yaml`.
They must satisfy the built-in `blocked-assessment-artifacts` contract.

Generate a portable static review page when humans need one file to inspect.
The page starts with readiness, contract status, allowed next action, reviewer
next actions, raw LLM coverage, missing raw decision keys, expected model
weaknesses, and blocker traceability to requirement keys/questions so reviewers
do not have to open YAML first:

```bash
iac-llm-wrapper review html --input out/ --output out/handoff-review.html
```

The page summarizes readiness, allowed next action, blockers, decisions,
requirement graph exports, contract validation, artifacts, handoff-plan steps,
raw evidence links or omission status, LLM trace summary, and model benchmark
without running a server. It writes `requirement-graph.json` and
`requirement-graph.mmd` beside the handoff artifacts for external viewers, and
writes `contract-validation.yaml` for tools that should not scrape HTML.

For incremental packet or sample updates, compare two generated handoff bundles
instead of re-reviewing everything from scratch or asking the model to reinterpret
the full document again:

```bash
iac-llm-wrapper compile --baseline-bundle out/before \
  --baseline-doc design-before.md \
  --changed-doc design-after.md \
  --output out/after --pattern aws-lza --no-raw-evidence

iac-llm-wrapper review compare --before out/before --after out/after \
  --output out/handoff-comparison.yaml \
  --html-output out/handoff-comparison.html
```

The incremental compile seeds the graph from the previous accepted bundle, gives
the LLM only changed hunks plus nearby document context when a model is used, and
then re-runs full graph validation, pattern validators, and artifact contracts on
the full resulting decision state. The comparison report summarizes readiness,
requirement completeness, accepted decision deltas, changed artifact files,
blocker changes, model quality changes, input-diff context, impacted
requirements, and sample recommendation rank/score changes.

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
stackName: orders-service-prod
templateUrl: s3://approved-templates/orders-service.yaml
region: eu-central-1
parameters:
  - ParameterKey: Environment
    ParameterValue: prod
  - ParameterKey: ServiceName
    ParameterValue: orders
capabilities:
  - CAPABILITY_NAMED_IAM
executionRoleArn: arn:aws:iam::123456789012:role/cfn-execution-orders
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
| `aws-lza` | Contract-backed AWS Landing Zone Accelerator registered-target configuration using official-style LZA YAML artifacts |
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
uv run python scripts/evaluate-golden-journey.py
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
- Ready bundles are inputs to an existing deployment mechanism, not an execution request from this tool.
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
Use [docs/PATTERN_AUTHORING.md](docs/PATTERN_AUTHORING.md) as the checklist for
adding or changing a pattern.

Private/internal patterns are useful only when a team has proprietary modules,
control language, sample bundles, or review gates that should stay outside this
repo. Built-ins are enough when the handoff target fits the shared pattern
library.

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
decisions that must be made before provisioning. Today it emits deterministic
target configuration artifacts engineers use with existing accelerators, sample
configurations, and IaC modules. AWS LZA YAML is the canonical example: the tool
can assemble validated config files for the registered target, but the LZA
deployment process remains downstream. It does not generate whole IaC from
scratch or arbitrary deployable infrastructure from prose.

## LLM Testing

Use [docs/LLM_SETUP.md](docs/LLM_SETUP.md) for model recommendations,
LLM-backed eval commands, benchmark comparison, and troubleshooting. The README
keeps only the quick-start path; the model-quality workflow lives there.

## Project Status

Alpha. Core architecture is stable. Pattern library is growing. Contributions welcome.

## License

Apache 2.0
