"""Pattern registry: pluggable requirement graphs for different scenarios.

Addons are composable modules that extend a base pattern's graph with
additional requirements, field mappings, and template sections.
New addons can be registered without modifying core code.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from .requirements import Requirement, RequirementGraph


@dataclass
class Pattern:
    """A named pattern: requirement graph + metadata + optional custom behaviors."""

    name: str
    description: str
    graph_factory: Callable[[], RequirementGraph]
    # Intent model factory — the Pydantic model that this pattern produces
    intent_factory: Callable[[], BaseModel] = field(default_factory=lambda: lambda: BaseModel())
    # Optional: custom validator, generator, or default catalog
    validator_factory: Callable[[], Any] | None = None
    generator_factory: Callable[[], Any] | None = None
    catalog_name: str | None = None  # reference to a ConfigCatalog entry
    # Schema hints for LLM extraction — auto-derived from graph if None
    llm_schema: dict[str, Any] | None = None
    # Domain context injected into LLM prompts
    prompt_context: str = ""
    # Section mapping for template generation: key -> (section, field_name)
    section_map: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    # Template section order
    section_order: list[str] = field(default_factory=list)
    # Free-form examples for template sections
    free_form_examples: dict[str, list[str]] = field(default_factory=dict)
    # Extra validators: list of functions(intent) -> list[Violation]
    validators: list[Callable[[Any], list[Any]]] = field(default_factory=list)
    # Optional normalizer override: function(intent) -> intent
    normalizer: Callable[[Any], Any] | None = None
    # Artifact validators for CLI validate command: list of functions(Path) -> list[str]
    artifact_validators: list[Callable[[Any], list[str]]] = field(default_factory=list)
    # Required artifact file names for CLI validate command
    required_artifacts: list[str] = field(default_factory=list)
    # Pattern-specific discovery hooks
    extra_consistency_checks: list[Any] = field(default_factory=list)
    extra_signal_detectors: list[Any] = field(default_factory=list)

    def create_graph(self) -> RequirementGraph:
        graph = self.graph_factory()
        model = self.intent_factory
        if isinstance(model, type) and issubclass(model, BaseModel):
            graph._intent_model = model
        return graph


class PatternRegistry:
    """Registry of named patterns."""

    def __init__(self) -> None:
        self._patterns: dict[str, Pattern] = {}

    def register(self, pattern: Pattern) -> None:
        # Schema alignment guard: validate requirements against intent model
        self._validate_pattern(pattern)
        self._patterns[pattern.name] = pattern

    def _validate_pattern(self, pattern: Pattern) -> None:
        """Validate that all requirements map to valid intent model fields.

        Skips validation if the graph factory depends on symbols not yet
        loaded (e.g. ADDON_REGISTRY during module import).
        """
        from .model_introspection import validate_requirement_against_model

        model = pattern.intent_factory
        if not isinstance(model, type):
            return
        if not issubclass(model, BaseModel):
            return

        try:
            graph = pattern.create_graph()
        except NameError:
            # Graph factory depends on not-yet-loaded symbols (e.g. ADDON_REGISTRY)
            return

        errors: list[str] = []
        for req in graph._requirements.values():
            errors.extend(validate_requirement_against_model(req, model))
        if errors:
            msg = "Pattern '{}' schema validation failed:\n  - {}".format(
                pattern.name, "\n  - ".join(errors)
            )
            raise ValueError(msg)

    def get(self, name: str) -> Pattern:
        if name not in self._patterns:
            available = ", ".join(sorted(self._patterns.keys()))
            raise KeyError(f"Unknown pattern '{name}'. Available: {available}")
        return self._patterns[name]

    def list(self) -> builtins.list[str]:
        return sorted(self._patterns.keys())

    def describe(self, name: str) -> str:
        p = self.get(name)
        return f"{p.name}: {p.description}"


# Addon system ----------------------------------------------------------------
#
# Addons are composable modules that extend a base pattern's graph with
# additional requirements, field mappings for extract sync, and section
# mappings for template generation. Any number of addons can be composed
# onto any base pattern via CLI --addon flag.


@dataclass
class Addon:
    """A composable module that adds requirements and mappings to a base pattern."""

    name: str
    description: str
    requirements: list[Requirement] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    # Field mapping for sync_intent_to_graph: key -> str | callable
    field_map: dict[str, str | None] = field(default_factory=dict)
    # Section mapping for template generator: key -> (section, field_name)
    section_map: dict[str, tuple[str, str | None]] = field(default_factory=dict)


class AddonRegistry:
    """Registry of named composable addons."""

    def __init__(self) -> None:
        self._addons: dict[str, Addon] = {}

    def register(self, addon: Addon) -> None:
        self._addons[addon.name] = addon

    def get(self, name: str) -> Addon:
        if name not in self._addons:
            available = ", ".join(sorted(self._addons.keys()))
            raise KeyError(f"Unknown addon '{name}'. Available: {available}")
        return self._addons[name]

    def list(self) -> builtins.list[str]:
        return sorted(self._addons.keys())

    def resolve_order(self, addon_names: builtins.list[str]) -> builtins.list[str]:
        """Topological sort of addon names respecting depends_on."""
        graph: dict[str, set[str]] = {}
        for name in addon_names:
            addon = self.get(name)
            graph.setdefault(name, set())
            for dep in addon.depends_on:
                if dep in addon_names:
                    graph.setdefault(dep, set())
                    graph[name].add(dep)
        # Simple Kahn's algorithm
        in_degree = {n: 0 for n in graph}
        for n in graph:
            for dep in graph[n]:
                in_degree[dep] = in_degree.get(dep, 0) + 1
        queue = [n for n in graph if in_degree.get(n, 0) == 0]
        ordered = []
        while queue:
            node = queue.pop(0)
            ordered.append(node)
            for dep in graph[node]:
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)
        remaining = [n for n in addon_names if n not in ordered]
        return ordered + remaining

    def compose(self, base: RequirementGraph, addon_names: builtins.list[str]) -> RequirementGraph:
        """Apply addon requirements and field maps onto a base graph.

        Returns a new graph with addon requirements added and field_map merged.
        """
        import copy

        result = copy.deepcopy(base)
        for addon_name in self.resolve_order(addon_names):
            addon = self.get(addon_name)
            for req in addon.requirements:
                result.add(req)
            # Merge addon field_map into graph so sync_intent_to_graph can use it
            for key, field_path in addon.field_map.items():
                result._field_map[key] = field_path
        return result

    def get_field_map(self, addon_names: builtins.list[str]) -> dict[str, str | None]:
        """Merge field_map entries from multiple addons."""
        merged: dict[str, str | None] = {}
        for name in self.resolve_order(addon_names):
            merged.update(self.get(name).field_map)
        return merged

    def get_section_map(self, addon_names: builtins.list[str]) -> dict[str, tuple[str, str | None]]:
        """Merge section_map entries from multiple addons."""
        merged: dict[str, tuple[str, str | None]] = {}
        for name in self.resolve_order(addon_names):
            merged.update(self.get(name).section_map)
        return merged


# Global registries (populated by domain-specific modules) --------------------


GLOBAL_REGISTRY = PatternRegistry()
ADDON_REGISTRY = AddonRegistry()
