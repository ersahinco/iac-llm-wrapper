# Extension Contract

This framework is a **general-purpose intent-driven decision system** for
registered target configuration. AWS LZA is one target pattern, not a special
core mode: accepted decisions become contract-checked LZA YAML/config files for the
downstream LZA deployment process. You can add new target patterns (for example
`kubernetes-cluster`, `gcp-org`, or `saas-tenant`) without modifying core
framework files.

## What Is the Core Framework?

These files are generic and must not contain use-case-specific logic:

- `extractor.py` — Builds prompts from any `RequirementGraph`
- `compiler.py` — Orchestrates extract, graph sync, validate, and emit
- `validator.py` — `validate_graph()` checks graph metadata; accepts extra validators
- `interview.py` — Topological question ordering
- `cli.py` — Generic CLI; `--pattern` selects the target pattern
- `generator.py` — Pluggable output generators (registry pattern)
- `patterns.py` — `PatternRegistry`
- `requirements.py` — `RequirementGraph` with dependencies, gates, cascade

## What Is the Pattern Layer?

Everything target-specific lives here:

- **Pydantic models** — Define the intent shape for one target pattern
- **Pattern graph factories** — Define decisions as `Requirement` nodes
- **Registered generators** — Emit deterministic target configuration files
- **Model and graph defaults** — Define deterministic defaults close to the fields they affect
- **Sample configs** — Define versioned, known-good decision sets
- **CLI `--pattern` flag** — Selects which target pattern to run

## Adding a New Target Pattern

Follow these steps. None should require touching core framework files.

### Built-In vs Private Patterns

Built-in patterns are enough when the target shape is reusable across teams and
safe to keep in this repository. Private patterns are useful when an organization
has internal accelerators, proprietary module variables, confidential sample
bundles, customer-specific control language, or review gates that should not
live in the public/core pattern library.

Keep private patterns on the same contract: they still own models, graphs,
contracts, validators, samples, and generators, and they should avoid core
changes. Do not add a generic external plugin loader until there is a real
consumer that needs packaged private pattern distribution; importing the private
package before CLI use is enough for local/internal runs.

### 1. Define Pydantic Models

Create a new pattern module (e.g., `src/intent_engine/patterns/my_pattern/models.py`):

```python
from pydantic import BaseModel

class K8sIntent(BaseModel):
    cluster_name: str = "k8s-cluster"
    cluster_version: str = "1.29"
    network_policy_enabled: bool = True
    pod_cidr: str = "10.244.0.0/16"
```

### 2. Define RequirementGraph Factory

Create a factory function that builds a `RequirementGraph`:

```python
from intent_engine.core.requirements import Requirement, RequirementGraph

def build_k8s_graph() -> RequirementGraph:
    g = RequirementGraph()
    g.add(Requirement(
        key="cluster_name",
        target_field="cluster_name",
        target_type="string",
        label="Cluster Name",
        question="What is the cluster name?",
        default="k8s-cluster",
        category="general",
    ))
    return g
```

Rules:
- `target_field` maps to your Pydantic model attribute (dotted paths supported)
- `target_type` controls type coercion: `string`, `int`, `bool`, `float`,
  `string_list`, `cidr_list`, or any enum name
- Use `depends_on` and `cascade` for ordering/default propagation.
- Use `applies_if`/`blocked_if` for simple key/value gates.
- Use `applies_when`/`blocked_when` expressions for richer gates such as
  `equals`, `contains`, `present`, `all`, `any`, and `not`.
- Use a pattern-owned semantic model when requirements depend on real
  relationships between entities such as accounts, OUs, permission sets,
  assignments, controls, artifacts, or target capabilities.

### 3. Register Generators

Register output generators that emit target configuration files:

```python
from io import StringIO
from pathlib import Path

import ruamel.yaml

from intent_engine.core.generator import register_generator
from intent_engine.patterns.my_pattern.models import K8sIntent

def _write_yaml(path: Path, data: dict) -> None:
    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    buffer = StringIO()
    yaml.dump(data, buffer)
    path.write_text(buffer.getvalue())

def gen_cluster_config(intent, output_dir: Path) -> None:
    model = getattr(intent, "intent", intent)
    if not isinstance(model, K8sIntent):
        return
    data = {"cluster": {"name": model.cluster_name}}
    _write_yaml(output_dir / "cluster-config.yaml", data)

register_generator(
    "k8s-cluster",
    gen_cluster_config,
    priority=10,
    applies_to={"kubernetes-cluster"},
)
```

Important: register generators with `applies_to={"your-pattern"}`. Keep lightweight runtime
guards only as fallback safety.

### 4. Register the Pattern

Register a `Pattern` in `GLOBAL_REGISTRY`:

```python
from intent_engine.core.contracts import ArtifactContract, TargetContract
from intent_engine.core.patterns import GLOBAL_REGISTRY, Pattern
from intent_engine.patterns.my_pattern.models import K8sIntent

contract = TargetContract(
    name="kubernetes-cluster-config",
    kind="kubernetes-cluster-config",
    source_url="https://example.com/k8s-contract",
    artifacts=[
        ArtifactContract(
            name="cluster-config.yaml",
            required_paths=["cluster.name", "cluster.version"],
        ),
        ArtifactContract(
            name="decision-report.yaml",
            required_paths=["clusterName"],
        ),
    ],
    required_decisions=["cluster_name", "cluster_version"],
)

GLOBAL_REGISTRY.register(Pattern(
    name="kubernetes-cluster",
    description="Kubernetes cluster registered-target configuration",
    graph_factory=build_k8s_graph,
    intent_factory=K8sIntent,
    section_map={"cluster_name": ("Cluster", "name")},
    section_order=["Cluster"],
    prompt_context=(
        "This pattern captures approved Kubernetes cluster configuration inputs "
        "for an existing deployment mechanism only. Extract cluster, network, "
        "node pool, and namespace values for the registered target contract. "
        "Do not generate raw IaC or invoke deployment."
    ),
    contracts=[contract],
))
```

Pattern metadata fields:
- `intent_factory` — The Pydantic model class for this target pattern
- `prompt_context` — Domain context injected into LLM prompts
- `section_order` — Template section ordering
- `section_map` — Maps requirement keys to template sections
- `free_form_examples` — Free-form Markdown examples for templates
- `validators` — List of extra validator functions `intent -> list[Violation]`
- `contracts` — Deployment target contracts for required files, required paths,
  value assertions, decisions, and lineage
- `context-manifest.yaml` — Generic context-as-code inventory emitted automatically for
  pattern-backed successful handoffs
- `sample-recommendations.yaml` — Generic artifact emitted automatically when sample configs
  exist for the pattern

### 5. Keep Defaults Close to the Pattern

Prefer these locations, in order:

- Pydantic model defaults for simple field defaults
- `Requirement.default` for graph-visible defaults used by extraction, interview, and validation
- Pattern validators or generators for target-specific behavior that is not a default

### 6. CLI Usage

Built-in patterns are available after `load_builtin_patterns()` imports them. If you add a
new built-in pattern, add its package import there. Private/internal patterns can
import/register their package before CLI use.

```bash
iac-llm-wrapper template --pattern kubernetes-cluster --output k8s-design.md
iac-llm-wrapper interview --pattern kubernetes-cluster --output ./k8s-out
iac-llm-wrapper validate --input ./k8s-out --pattern kubernetes-cluster
```

## Acceptance Test

Write a test that compiles end-to-end without touching core files:

```python
import intent_engine.patterns.kubernetes  # triggers registration
from intent_engine.core.compiler import compile_from_interview

def test_k8s_compiles(tmp_path):
    decisions = {"cluster_name": "prod-k8s", "cluster_version": "1.30"}
    output = tmp_path / "out"
    compile_from_interview(decisions, output, pattern="kubernetes-cluster")
    assert (output / "cluster-config.yaml").exists()
```

## Core Design Principles

1. **The requirement graph is the product brain** — Adding one `Requirement` node updates LLM prompts, interview questions, validation rules, and template sections.
2. **Target contracts define handoff shape** — Required files, paths, value assertions, and lineage live in contracts.
3. **Generators are scoped** — Use `applies_to` so multiple patterns coexist in the same registry.
4. **Defaults are explicit** — Put defaults in the model or requirement graph so prompts, interviews, validation, and artifacts agree.
5. **Validators are layered** — Graph-driven rules come from `Requirement` metadata; pattern-specific rules come from `Pattern.validators`.
6. **No core code changes for new target patterns** — If you find yourself editing `extractor.py`, `compiler.py`, `validator.py`, `interview.py`, or `cli.py`, the framework is leaking domain assumptions. Move them to the pattern layer.
