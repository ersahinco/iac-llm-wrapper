"""Target capability graph for downstream handoff routing.

The requirement graph answers "what decisions are accepted?". This layer answers
"what downstream target can safely satisfy those decisions?".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import networkx as nx


class TargetCapabilityType(StrEnum):
    ACCELERATOR = "accelerator"
    MODULE_COMPOSITION = "module-composition"
    GENERATOR = "generator"
    TEMPLATE_GENERATION = "template-generation"
    MANUAL = "manual"
    BLOCKED = "blocked"


_ROUTING_ORDER = {
    TargetCapabilityType.ACCELERATOR: 0,
    TargetCapabilityType.MODULE_COMPOSITION: 1,
    TargetCapabilityType.GENERATOR: 2,
    TargetCapabilityType.TEMPLATE_GENERATION: 3,
    TargetCapabilityType.MANUAL: 4,
    TargetCapabilityType.BLOCKED: 5,
}

_NEGATED_BEFORE_MARKERS = (
    "do not",
    "don't",
    "dont",
    "must not",
    "should not",
    "shall not",
    "cannot",
    "can't",
    "mustn't",
    "without",
    "out of scope",
)
_NEGATED_AFTER_MARKERS = (
    "must not",
    "should not",
    "shall not",
    "cannot",
    "can't",
    "mustn't",
    "not be generated",
    "out of scope",
)


def _is_negated_keyword_match(text: str, index: int, keyword_length: int) -> bool:
    before = text[max(0, index - 80) : index]
    after = text[index : index + keyword_length + 80]
    if any(marker in before for marker in _NEGATED_BEFORE_MARKERS):
        return True
    return any(marker in after for marker in _NEGATED_AFTER_MARKERS)


def _is_keyword_boundary(text: str, index: int, keyword_length: int) -> bool:
    before = text[index - 1] if index > 0 else ""
    after_index = index + keyword_length
    after = text[after_index] if after_index < len(text) else ""
    if before and (before.isalnum() or before == "_"):
        return False
    return not (after and (after.isalnum() or after == "_"))


def _has_affirmative_keyword_match(text: str, keyword: str) -> bool:
    keyword = keyword.lower()
    start = 0
    while True:
        index = text.find(keyword, start)
        if index == -1:
            return False
        if _is_keyword_boundary(text, index, len(keyword)) and not _is_negated_keyword_match(
            text, index, len(keyword)
        ):
            return True
        start = index + len(keyword)


@dataclass(frozen=True)
class UnsupportedRequest:
    """A source-text signal that this target path does not own."""

    key: str
    label: str
    keywords: tuple[str, ...]
    recommended_target: TargetCapabilityType
    reason: str


@dataclass(frozen=True)
class TargetCapability:
    """A capability exposed by a downstream target path."""

    key: str
    label: str
    capability_type: TargetCapabilityType
    description: str
    handled_decisions: tuple[str, ...] = ()
    produced_artifacts: tuple[str, ...] = ()
    required_decisions: tuple[str, ...] = ()
    manual_gates: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    unsupported_requests: tuple[UnsupportedRequest, ...] = ()


class TargetCapabilityGraph:
    """Graph wrapper for target capability relationships."""

    def __init__(self, capabilities: list[TargetCapability]) -> None:
        self.capabilities = capabilities
        self._graph = nx.DiGraph()
        for capability in capabilities:
            self._graph.add_node(capability.key, capability=capability)
            for dep in capability.depends_on:
                self._graph.add_edge(dep, capability.key)

    def evaluate(self, decisions: dict[str, Any], source_text: str = "") -> dict[str, Any]:
        text_lower = source_text.lower()
        nodes = []
        coverage: dict[str, str] = {}
        manual_gates: list[str] = []
        unsupported_gaps: list[dict[str, str]] = []
        selected_types: set[TargetCapabilityType] = set()
        selected_capability_keys: set[str] = set()

        for capability in sorted(
            self.capabilities,
            key=lambda item: (_ROUTING_ORDER[item.capability_type], item.key),
        ):
            available = capability.capability_type != TargetCapabilityType.BLOCKED and all(
                str(decisions.get(key, "")).strip() for key in capability.required_decisions
            )
            if capability.handled_decisions and any(
                key in decisions for key in capability.handled_decisions
            ):
                selected_types.add(capability.capability_type)
                selected_capability_keys.add(capability.key)
            for key in capability.handled_decisions:
                coverage[key] = capability.key
            for unsupported in capability.unsupported_requests:
                if any(
                    _has_affirmative_keyword_match(text_lower, keyword)
                    for keyword in unsupported.keywords
                ):
                    selected_types.add(unsupported.recommended_target)
                    selected_capability_keys.update(
                        item.key
                        for item in self.capabilities
                        if item.capability_type == unsupported.recommended_target
                    )
                    unsupported_gaps.append(
                        {
                            "key": unsupported.key,
                            "label": unsupported.label,
                            "detectedBy": capability.key,
                            "recommendedTarget": unsupported.recommended_target.value,
                            "reason": unsupported.reason,
                        }
                    )
            nodes.append(
                {
                    "key": capability.key,
                    "label": capability.label,
                    "type": capability.capability_type.value,
                    "available": available,
                    "description": capability.description,
                    "handledDecisions": list(capability.handled_decisions),
                    "producedArtifacts": list(capability.produced_artifacts),
                    "requiredDecisions": list(capability.required_decisions),
                    "manualGates": list(capability.manual_gates),
                    "dependsOn": list(capability.depends_on),
                }
            )

        for capability in self.capabilities:
            if capability.key in selected_capability_keys:
                manual_gates.extend(capability.manual_gates)

        selected_path = [
            item.value for item in sorted(selected_types, key=lambda item: _ROUTING_ORDER[item])
        ]
        return {
            "selectedTargetPath": selected_path,
            "routingOrder": [item.value for item in TargetCapabilityType],
            "capabilities": nodes,
            "coverage": {
                "handledDecisionCount": len(coverage),
                "handledDecisions": coverage,
                "unhandledAcceptedDecisions": sorted(
                    key for key in decisions if key not in coverage
                ),
            },
            "unsupportedGaps": unsupported_gaps,
            "manualGates": list(dict.fromkeys(manual_gates)),
            "edges": [{"from": source, "to": target} for source, target in self._graph.edges()],
        }


def build_target_capability_report(
    capabilities: list[TargetCapability],
    decisions: dict[str, Any],
    source_text: str = "",
) -> dict[str, Any]:
    if not capabilities:
        return {}
    return TargetCapabilityGraph(capabilities).evaluate(decisions, source_text)
