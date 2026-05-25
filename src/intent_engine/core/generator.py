"""Generate intent artifacts from normalized intent.

Produces decision reports, deployment graphs, and workload skeletons
that engineers use alongside sample configurations and IaC modules.

The generator uses a registry pattern so new output modules can be added
without modifying core generation logic. Each registered generator is a
function(intent, output_dir) that writes its own files.

Use-case-specific strings (e.g. organization name, role prefix) are read
from defaults.yaml so the generator framework stays generic.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

import ruamel.yaml

_DEFAULTS_FILE = Path(__file__).parent / "defaults.yaml"


def _load_generator_config() -> dict:
    with open(_DEFAULTS_FILE) as f:
        return ruamel.yaml.YAML(typ="safe").load(f) or {}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

GeneratorFn = Callable[[Any, Path], None]


@dataclass
class RegisteredGenerator:
    name: str
    fn: GeneratorFn
    priority: int  # lower = earlier
    category: str  # e.g., "core", "security", "workload"


class GeneratorRegistry:
    """Registry of output generators."""

    def __init__(self) -> None:
        self._generators: list[RegisteredGenerator] = []

    def register(
        self,
        name: str,
        fn: GeneratorFn,
        priority: int = 50,
        category: str = "general",
    ) -> None:
        self._generators.append(RegisteredGenerator(name, fn, priority, category))
        self._generators.sort(key=lambda g: g.priority)

    def generate(self, intent: Any, output_dir: Path) -> None:
        for gen in self._generators:
            gen.fn(intent, output_dir)

    def list(self) -> list[str]:
        return [g.name for g in self._generators]


# Global registry instance
GLOBAL_REGISTRY = GeneratorRegistry()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _yaml_dump(data: Any) -> str:
    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    buf = StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()


def _write(output_dir: Path, name: str, data: Any) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / name).write_text(_yaml_dump(data))


def register_generator(
    name: str,
    fn: GeneratorFn,
    priority: int = 50,
    category: str = "custom",
) -> None:
    """Register a custom generator without modifying core code."""
    GLOBAL_REGISTRY.register(name, fn, priority, category)


def generate_all(intent: Any, output_dir: Path) -> None:
    from .module_mapping import DesignDocument, IaCIntentPayload

    if isinstance(intent, IaCIntentPayload):
        payload = intent
    else:
        payload = IaCIntentPayload(
            design_doc=DesignDocument(),
            module_inputs=[],
            intent=intent,
        )
    GLOBAL_REGISTRY.generate(payload, output_dir)


def gen_design_doc(intent: Any, output_dir: Path) -> None:
    """Write design-doc.yaml when business context is present."""
    if not hasattr(intent, "design_doc"):
        return
    dd = intent.design_doc
    if not any(
        [
            dd.project_name,
            dd.business_justification,
            dd.estimated_tier,
            dd.compliance_tags,
        ]
    ):
        return
    data = {
        "projectName": dd.project_name,
        "businessJustification": dd.business_justification,
        "estimatedTier": dd.estimated_tier,
        "complianceTags": dd.compliance_tags,
    }
    _write(output_dir, "design-doc.yaml", data)


def gen_module_inputs(intent: Any, output_dir: Path) -> None:
    """Write module-inputs.yaml when module mappings exist."""
    if not hasattr(intent, "module_inputs"):
        return
    inputs = intent.module_inputs
    if not inputs:
        return
    data = {
        "moduleInputs": [{"moduleName": mi.module_name, "variables": mi.variables} for mi in inputs]
    }
    _write(output_dir, "module-inputs.yaml", data)


register_generator("design-doc", gen_design_doc, priority=4, category="meta")
register_generator("module-inputs", gen_module_inputs, priority=5, category="meta")
