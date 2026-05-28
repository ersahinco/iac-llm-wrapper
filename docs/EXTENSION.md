# Extension Contract

This framework is a **general-purpose intent-driven configuration system**. Landing zone accelerator (LZA) is simply the first use case — Pattern #1. You can add new use cases (e.g., `kubernetes-cluster`, `gcp-org`, `saas-tenant`) without modifying any core framework file.

## What Is the Core Framework?

These files are generic and must not contain use-case-specific logic:

- `extractor.py` — Builds prompts from any `RequirementGraph`
- `compiler.py` — Orchestrates extract → normalize → validate → generate
- `validator.py` — `validate_graph()` checks graph metadata; accepts extra validators
- `normalizer.py` — Applies defaults from `defaults.yaml` using duck-typing
- `interview.py` — Topological question ordering
- `cli.py` — Generic CLI; `--pattern` selects the use case
- `generator.py` — Pluggable output generators (registry pattern)
- `patterns.py` — `PatternRegistry`
- `requirements.py` — `RequirementGraph` with dependencies, gates, cascade

## What Is the Pattern Layer?

Everything use-case specific lives here:

- **Pydantic models** — Define the intent shape for one use case
- **Pattern graph factories** — Define decisions as `Requirement` nodes
- **Registered generators** — Define output artifacts
- **`defaults.yaml`** — Define defaults and guardrails
- **Sample configs** — Define versioned, known-good decision sets
- **CLI `--pattern` flag** — Selects which use case to run

## Adding a New Use Case

Follow these steps. None of them require touching core framework files.

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
- `target_type` controls type coercion: `string`, `int`, `bool`, or any enum name
- Use `applies_if`, `blocked_if`, `depends_on`, and `cascade` for logic gates

### 3. Register Generators

Register output generators that write your artifacts:

```python
from intent_engine.core.generator import register_generator
from pathlib import Path
from intent_engine.patterns.my_pattern.models import K8sIntent

def gen_cluster_config(intent, output_dir: Path) -> None:
    model = getattr(intent, "intent", intent)
    if not isinstance(model, K8sIntent):
        return
    data = {"cluster": {"name": model.cluster_name}}
    (output_dir / "cluster-config.yaml").write_text(yaml_dump(data))

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
    description="Kubernetes cluster provisioning",
    graph_factory=build_k8s_graph,
    intent_factory=K8sIntent,
    section_map={"cluster_name": ("Cluster", "name")},
    section_order=["Cluster"],
    prompt_context="This pattern designs Kubernetes clusters.",
    contracts=[contract],
))
```

Pattern metadata fields:
- `intent_factory` — The Pydantic model class for this use case
- `prompt_context` — Domain context injected into LLM prompts
- `section_order` — Template section ordering
- `section_map` — Maps requirement keys to template sections
- `free_form_examples` — Free-form Markdown examples for templates
- `validators` — List of extra validator functions `intent -> list[Violation]`
- `normalizer` — Optional normalizer override function
- `contracts` — Target contracts for required files, required paths, value assertions,
  decisions, and lineage
- `sample-recommendations.yaml` — Generic artifact emitted automatically when sample configs
  exist for the pattern
- `required_artifacts` — Simple file checks when no target contract exists
- `artifact_validators` — Custom cross-file validators only when contracts cannot express the rule

### 5. Add Defaults to `defaults.yaml`

Add a section for your use case:

```yaml
k8s_defaults:
  cluster_name: k8s-cluster
  cluster_version: "1.29"
  network_policy_enabled: true
```

The normalizer reads `defaults.yaml` and applies values duck-typed against your intent model.

### 6. CLI Usage

Built-in patterns are available after `load_builtin_patterns()` imports them. If you add a
new built-in pattern, add its package import there; external patterns can import/register
their package before CLI use.

```bash
intent-engine template --pattern kubernetes-cluster --output k8s-design.md
intent-engine interview --pattern kubernetes-cluster --output ./k8s-out
intent-engine validate --input ./k8s-out --pattern kubernetes-cluster
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

1. **The requirement graph is the product** — Adding one `Requirement` node automatically updates LLM prompts, interview questions, validation rules, and template sections.
2. **Generators are defensive** — Use `hasattr` guards so multiple patterns coexist in the same registry.
3. **Normalizers are duck-typed** — Only touch fields that exist on the intent model.
4. **Validators are layered** — Graph-driven rules come from `Requirement` metadata; pattern-specific rules come from `Pattern.validators`.
5. **No core code changes for new use cases** — If you find yourself editing `extractor.py`, `compiler.py`, `validator.py`, `normalizer.py`, `interview.py`, or `cli.py`, the framework is leaking domain assumptions. Move them to the pattern layer.
