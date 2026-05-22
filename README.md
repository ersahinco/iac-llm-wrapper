# intent-engine

**Knowledge-driven infrastructure decision engine.**

Architects describe infrastructure intent in prose. This tool extracts structured decisions, validates them against architectural knowledge graphs, and produces traceable artifacts engineers can act on.

Not a code generator. Not a Terraform/CDK wrapper. A **decision capture and validation** layer that sits between design documents and provisioning pipelines.

## The Core Idea

Infrastructure design today means prose docs → misinterpretation → rework → compliance surprises.

This project replaces that with a **model-driven flow**:

```
Prose / Markdown
     │
     ▼
Extraction ──── LLM traverses a requirement graph, detects signals, suggests addons
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
Output ──────── Decision reports, deployment graphs, workload skeletons
```

**Every decision is recorded** with timestamp, rationale, compliance context, and tradeoffs. Architects get living documentation. Compliance gets an audit trail. Engineers get a validated decision set to map to their IaC of choice.

## Quick Start

```bash
pip install intent-engine
source .venv/bin/activate  # or use your venv of choice

# See available patterns
intent-engine discover -i fixtures/valid-payments.md

# Generate a design doc scaffold from a pattern
intent-engine template --pattern baseline --output design.md

# Compile a design doc into decision artifacts
intent-engine compile -i design.md -o out/
```

## Patterns

Patterns define which questions are asked, what defaults apply, and what knowledge context is shown. The framework ships with built-in patterns — each a complete requirement graph:

| Pattern | Description |
|---------|-------------|
| `baseline` | Full feature set with hub-spoke networking, security, CI/CD, hybrid |
| `minimal` | Bare minimum: region, topology, CIDR, audit retention |
| `workload` | Workload account deployment only |
| `hybrid-enterprise` | Baseline + Direct Connect, egress inspection, hybrid DNS |
| `financial-services` | Baseline + PCI-DSS, SOX, data residency, payment segmentation |
| `healthcare` | Baseline + HIPAA, PHI encryption, BAA coverage |
| `kubernetes-cluster` | K8s cluster provisioning with node pools and network policies |

### Addons

Addons layer additional requirements onto any base pattern:

```bash
intent-engine compile -i design.md --pattern baseline --addon pci-compliance --addon hipaa
```

Built-in addons: `pci-compliance`, `hipaa`, `self-hosted-cicd`, `hashicorp-vault`, `paloalto-fw`, `hybrid-challenges`.

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

### Create a new addon

```python
from intent_engine.core.patterns import ADDON_REGISTRY, Addon

ADDON_REGISTRY.register(
    Addon(
        name="my-addon",
        description="My custom addon",
        requirements=[...],
        field_map={...},
        section_map={...},
    )
)
```

See the [extension guide](EXTENSION.md) for the full contract.

## Architecture

```
src/intent_engine/
├── cli.py                 # Typer CLI
├── core/
│   ├── models.py          # Domain models (pattern-agnostic)
│   ├── requirements.py    # Requirement + RequirementGraph
│   ├── extractor.py       # LLM extraction (graph-driven prompts)
│   ├── interview.py       # Guided question engine
│   ├── normalizer.py      # Deterministic defaults
│   ├── validator.py       # Fail-closed validation
│   ├── discovery.py       # Gap/signal detection
│   ├── generator.py       # Output registry
│   ├── compiler.py        # Orchestrator
│   ├── catalog.py         # Known-good decision sets
│   ├── llm_caller.py      # OpenAI/Ollama/Anthropic backends
│   └── patterns.py        # Pattern registry + addon system
└── patterns/
    ├── lza/               # Landing Zone Accelerator patterns
    ├── kubernetes/        # K8s cluster pattern
    └── ...                # Add yours here
```

## Why Not Terraform/CDK/CloudFormation?

Those tools execute infrastructure. This tool **designs infrastructure** — it captures the architectural decisions that should be made *before* provisioning. It produces decision artifacts that engineers use alongside sample configurations and IaC modules. It does not generate deployable infrastructure.

## Project Status

Alpha. 382+ tests. Core architecture is stable. Pattern library is growing. Contributions welcome.

## License

Apache 2.0
