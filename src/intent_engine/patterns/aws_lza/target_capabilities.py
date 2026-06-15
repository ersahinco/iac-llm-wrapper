"""AWS LZA target capability graph for downstream handoff routing.

The requirement graph answers "what decisions are accepted?". This layer answers
"what downstream target can safely satisfy those decisions?".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


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
    "no ",
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
class UnsupportedAskFact:
    """Extracted semantic fact for a request the current pattern does not own."""

    kind: str
    label: str
    evidence_span: str
    recommended_target: TargetCapabilityType
    owned_by_pattern: bool
    detected_by: str
    reason: str
    source: str = "deterministic-text"

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "kind": self.kind,
            "label": self.label,
            "evidenceSpan": self.evidence_span,
            "recommendedTarget": self.recommended_target.value,
            "ownedByPattern": self.owned_by_pattern,
            "detectedBy": self.detected_by,
            "reason": self.reason,
            "source": self.source,
        }


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
        self._edges = list(
            dict.fromkeys(
                (dep, capability.key)
                for capability in capabilities
                for dep in capability.depends_on
            )
        )

    def evaluate(
        self,
        decisions: dict[str, Any],
        unsupported_ask_facts: list[UnsupportedAskFact] | None = None,
    ) -> dict[str, Any]:
        unsupported_ask_facts = unsupported_ask_facts or []
        nodes = []
        coverage: dict[str, str] = {}
        manual_gates: list[str] = []
        unsupported_gaps: list[dict[str, str | bool]] = []
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

        for fact in unsupported_ask_facts:
            selected_types.add(fact.recommended_target)
            selected_capability_keys.update(
                item.key
                for item in self.capabilities
                if item.capability_type == fact.recommended_target
            )
            unsupported_gaps.append(
                {
                    "key": fact.kind,
                    "label": fact.label,
                    "detectedBy": fact.detected_by,
                    "recommendedTarget": fact.recommended_target.value,
                    "reason": fact.reason,
                    "evidenceSpan": fact.evidence_span,
                    "ownedByPattern": fact.owned_by_pattern,
                    "source": fact.source,
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
            "semanticFacts": {
                "unsupportedAsks": [fact.to_dict() for fact in unsupported_ask_facts],
            },
            "manualGates": list(dict.fromkeys(manual_gates)),
            "edges": [{"from": source, "to": target} for source, target in self._edges],
        }


def extract_unsupported_ask_facts(
    capabilities: list[TargetCapability],
    source_text: str,
) -> list[UnsupportedAskFact]:
    """Extract unsupported target asks as semantic facts before routing."""

    if not source_text:
        return []

    text_lower = source_text.lower()
    facts: list[UnsupportedAskFact] = []
    seen: set[str] = set()
    for capability in capabilities:
        for unsupported in capability.unsupported_requests:
            for keyword in unsupported.keywords:
                index = _affirmative_keyword_match_index(text_lower, keyword)
                if index is None:
                    continue
                fact_key = f"{capability.key}:{unsupported.key}"
                if fact_key in seen:
                    break
                seen.add(fact_key)
                facts.append(
                    UnsupportedAskFact(
                        kind=unsupported.key,
                        label=unsupported.label,
                        evidence_span=_evidence_span(source_text, index, len(keyword)),
                        recommended_target=unsupported.recommended_target,
                        owned_by_pattern=False,
                        detected_by=capability.key,
                        reason=unsupported.reason,
                    )
                )
                break
    return facts


def _affirmative_keyword_match_index(text: str, keyword: str) -> int | None:
    keyword = keyword.lower()
    start = 0
    while True:
        index = text.find(keyword, start)
        if index == -1:
            return None
        if _is_keyword_boundary(text, index, len(keyword)) and not _is_negated_keyword_match(
            text, index, len(keyword)
        ):
            return index
        start = index + len(keyword)


def _evidence_span(text: str, index: int, keyword_length: int) -> str:
    line_start = text.rfind("\n", 0, index) + 1
    line_end = text.find("\n", index + keyword_length)
    if line_end == -1:
        line_end = len(text)
    return " ".join(text[line_start:line_end].strip().split())


def build_target_capability_report(
    capabilities: list[TargetCapability],
    decisions: dict[str, Any],
    source_text: str = "",
    unsupported_ask_facts: list[UnsupportedAskFact] | None = None,
) -> dict[str, Any]:
    if not capabilities:
        return {}
    facts = (
        unsupported_ask_facts
        if unsupported_ask_facts is not None
        else extract_unsupported_ask_facts(capabilities, source_text)
    )
    return TargetCapabilityGraph(capabilities).evaluate(decisions, facts)
