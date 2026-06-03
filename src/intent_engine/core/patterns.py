"""Pattern registry: pluggable requirement graphs for different scenarios."""

from __future__ import annotations

import builtins
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from .contracts import ContractValidator, TargetContract
from .requirements import RequirementGraph
from .target_capabilities import TargetCapability


@dataclass
class Pattern:
    """A named pattern: requirement graph + metadata + optional custom behaviors."""

    name: str
    description: str
    graph_factory: Callable[[], RequirementGraph]
    # Intent model factory — the Pydantic model that this pattern produces
    intent_factory: Callable[[], BaseModel] = field(default_factory=lambda: lambda: BaseModel())
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
    # Target contracts that drive decisions, validation, and generated artifacts
    contracts: list[TargetContract] = field(default_factory=list)
    # Downstream target capability graph declarations.
    target_capabilities: list[TargetCapability] = field(default_factory=list)

    def create_graph(self) -> RequirementGraph:
        graph = self.graph_factory()
        model = self.intent_factory
        if isinstance(model, type) and issubclass(model, BaseModel):
            graph._intent_model = model
        return graph

    def expected_artifacts(self) -> list[str]:
        from .sample_config import GLOBAL_SAMPLE_REGISTRY

        artifacts: list[str] = []
        for contract in self.contracts:
            artifacts.extend(contract.required_artifacts)
        if self.contracts:
            artifacts.append("handoff-plan.yaml")
        if GLOBAL_SAMPLE_REGISTRY.find_by_pattern(self.name):
            artifacts.append("sample-recommendations.yaml")
        if self.target_capabilities:
            artifacts.append("target-capability-graph.yaml")
        return list(dict.fromkeys(artifacts))


class PatternRegistry:
    """Registry of named patterns."""

    def __init__(self) -> None:
        self._patterns: dict[str, Pattern] = {}
        self._builtins_load_attempted = False

    def _load_builtins_if_global(self) -> None:
        if self._builtins_load_attempted:
            return
        if globals().get("GLOBAL_REGISTRY") is not self:
            return
        self._builtins_load_attempted = True
        try:
            from intent_engine.patterns import load_builtin_patterns
        except ImportError:
            return
        load_builtin_patterns()

    def register(self, pattern: Pattern) -> None:
        # Schema alignment guard: validate requirements against intent model
        self._validate_pattern(pattern)
        self._patterns[pattern.name] = pattern

    def _validate_pattern(self, pattern: Pattern) -> None:
        """Validate that all requirements map to valid intent model fields.

        Skips validation if the graph factory depends on symbols not yet loaded
        during module import.
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
            # Graph factory depends on not-yet-loaded symbols during import.
            return

        errors: list[str] = []
        for req in graph._requirements.values():
            errors.extend(validate_requirement_against_model(req, model))
        for contract in pattern.contracts:
            validator = ContractValidator(contract)
            for violation in validator.validate_contract() + validator.validate_graph(graph):
                errors.append(f"Contract '{contract.name}': {violation.message}")
        if errors:
            msg = "Pattern '{}' schema validation failed:\n  - {}".format(
                pattern.name, "\n  - ".join(errors)
            )
            raise ValueError(msg)

    def get(self, name: str) -> Pattern:
        self._load_builtins_if_global()
        if name not in self._patterns:
            available = ", ".join(sorted(self._patterns.keys()))
            raise KeyError(f"Unknown pattern '{name}'. Available: {available}")
        return self._patterns[name]

    def list(self) -> builtins.list[str]:
        self._load_builtins_if_global()
        return sorted(self._patterns.keys())


# Global registries (populated by domain-specific modules) --------------------


GLOBAL_REGISTRY = PatternRegistry()
