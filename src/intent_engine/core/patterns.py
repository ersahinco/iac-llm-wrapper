"""Pattern registry: pluggable requirement graphs for different scenarios."""

from __future__ import annotations

import builtins
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .contracts import CORE_CONTRACTS, TargetContract
from .module_mapping import IaCIntentPayload, ModuleInputs
from .policy import PolicyPack
from .requirements import RequirementGraph
from .sample_config import SampleConfig, SampleMatch, find_best_sample_matches, find_samples

GeneratorFn = Callable[[IaCIntentPayload, Path], None]
TargetReportBuilder = Callable[[dict[str, Any], str], dict[str, Any]]
ReadinessEnricher = Callable[[Any, dict[str, Any]], dict[str, Any]]
MarkdownEntityExtractor = Callable[[str], dict[str, list[dict[str, Any]]]]
EntityApplier = Callable[[dict[str, Any], Any], None]
ReviewEvidenceLoader = Callable[[Path], dict[str, Any]]


@dataclass
class PatternGenerator:
    """Pattern-owned artifact generator."""

    name: str
    fn: GeneratorFn
    priority: int = 50
    outputs: tuple[str, ...] = ()


@dataclass
class Pattern:
    """A named pattern: requirement graph + metadata + optional custom behaviors."""

    name: str
    description: str
    graph_factory: Callable[[], RequirementGraph]
    intent_factory: type[BaseModel]
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
    # Optional module handoff mapper owned by the pattern.
    module_mapper: Callable[[Any], list[ModuleInputs]] | None = None
    # Pattern-owned target artifact generators.
    generators: list[PatternGenerator] = field(default_factory=list)
    # Target contracts that drive decisions, validation, and generated artifacts
    contracts: list[TargetContract] = field(default_factory=list)
    # Version-pinned reference bundles owned by the pattern.
    samples: list[SampleConfig] = field(default_factory=list)
    # Optional regulated policy graph metadata owned by the pattern.
    policy_packs: list[PolicyPack] = field(default_factory=list)
    # Optional pattern-owned target routing/report builder.
    target_report_builder: TargetReportBuilder | None = None
    # Optional pattern-owned readiness details such as plan maturity.
    readiness_enricher: ReadinessEnricher | None = None
    # Optional pattern-owned structured entity recovery.
    markdown_entity_extractor: MarkdownEntityExtractor | None = None
    markdown_entity_applier: EntityApplier | None = None
    review_evidence_loader: ReviewEvidenceLoader | None = None
    violation_requirement_map: dict[str, str] = field(default_factory=dict)
    artifact_review_owners: dict[str, str] = field(default_factory=dict)
    reconfirmation_categories: tuple[str, ...] = ()
    reconfirmation_keys: tuple[str, ...] = ()
    forbidden_artifacts: tuple[str, ...] = ()
    # Whether this pattern emits a registered target plan-ready metadata bundle.
    plan_ready: bool = False

    def create_graph(self) -> RequirementGraph:
        graph = self.graph_factory()
        graph._intent_model = self.intent_factory
        return graph

    def expected_artifacts(self) -> list[str]:
        artifacts: list[str] = ["context-manifest.yaml", "decision-audit.yaml"]
        for contract in self.contracts:
            artifacts.extend(contract.required_artifacts)
        if self.contracts:
            artifacts.append("handoff-plan.yaml")
        if self.samples:
            artifacts.append("sample-recommendations.yaml")
        if self.target_report_builder:
            artifacts.append("target-capability-graph.yaml")
        if self.plan_ready:
            artifacts.extend(["plan-manifest.yaml", "replay-manifest.yaml"])
        if self.policy_packs:
            artifacts.append("policy-graph.yaml")
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
        from intent_engine.patterns import load_builtin_patterns

        load_builtin_patterns()

    def register(self, pattern: Pattern) -> None:
        # Schema alignment guard: validate requirements against intent model
        self._validate_pattern(pattern)
        self._patterns[pattern.name] = pattern

    def _validate_pattern(self, pattern: Pattern) -> None:
        """Validate that requirements, contracts, and metadata agree."""
        from .pattern_check import validate_pattern_references

        graph = pattern.create_graph()
        errors = [item.registration_message for item in validate_pattern_references(pattern, graph)]
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

    def contracts(self, *, include_core: bool = True) -> builtins.list[TargetContract]:
        self._load_builtins_if_global()
        contracts = [*CORE_CONTRACTS] if include_core else []
        for pattern in sorted(self._patterns.values(), key=lambda item: item.name):
            contracts.extend(pattern.contracts)
        by_name: dict[str, TargetContract] = {}
        for contract in contracts:
            by_name.setdefault(contract.name, contract)
        return list(by_name.values())

    def contract(self, name: str, *, include_core: bool = True) -> TargetContract:
        contracts_by_name = {
            contract.name: contract for contract in self.contracts(include_core=include_core)
        }
        if name not in contracts_by_name:
            available = ", ".join(sorted(contracts_by_name))
            raise KeyError(f"Unknown contract '{name}'. Available: {available}")
        return contracts_by_name[name]

    def samples(self) -> builtins.list[SampleConfig]:
        self._load_builtins_if_global()
        items: list[SampleConfig] = []
        for pattern in sorted(self._patterns.values(), key=lambda item: item.name):
            items.extend(pattern.samples)
        return sorted(items, key=lambda sample: sample.name)

    def sample(self, name: str) -> SampleConfig:
        samples_by_name = {sample.name: sample for sample in self.samples()}
        if name not in samples_by_name:
            available = ", ".join(sorted(samples_by_name))
            raise KeyError(f"Unknown sample config '{name}'. Available: {available}")
        return samples_by_name[name]

    def find_samples(
        self,
        *,
        pattern: str | None = None,
        contract: str | None = None,
        tag: str | None = None,
    ) -> builtins.list[SampleConfig]:
        return find_samples(self.samples(), pattern=pattern, contract=contract, tag=tag)

    def find_sample_matches(
        self,
        current_decisions: dict[str, Any],
        *,
        pattern: str | None = None,
        contract: str | None = None,
        tag: str | None = None,
        limit: int = 3,
    ) -> builtins.list[SampleMatch]:
        return find_best_sample_matches(
            self.samples(),
            current_decisions,
            pattern=pattern,
            contract=contract,
            tag=tag,
            limit=limit,
        )


# Global registries (populated by domain-specific modules) --------------------


GLOBAL_REGISTRY = PatternRegistry()
