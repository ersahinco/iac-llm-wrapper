"""Discovery engine: analyzes intent against requirement graph to find gaps.

This module is data-driven: it asks the graph what is missing rather than
hardcoding domain-specific checks. Works with any pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .requirements import RequirementGraph, RequirementStatus


@dataclass
class RequirementGap:
    key: str
    label: str
    reason: str
    suggestion: str
    priority: int
    depends_on: list[str] = field(default_factory=list)


@dataclass
class Ambiguity:
    key: str
    label: str
    reason: str
    clarification: str


@dataclass
class Inconsistency:
    key_a: str
    key_b: str
    reason: str


@dataclass
class DetectedSignal:
    signal: str
    triggered_requirements: list[str]
    context: str


@dataclass
class DiscoveryResult:
    missing: list[RequirementGap] = field(default_factory=list)
    ambiguous: list[Ambiguity] = field(default_factory=list)
    inconsistent: list[Inconsistency] = field(default_factory=list)
    signals: list[DetectedSignal] = field(default_factory=list)
    synced: list[str] = field(default_factory=list)

    def is_complete(self) -> bool:
        return len(self.missing) == 0 and len(self.ambiguous) == 0 and len(self.inconsistent) == 0

    def total_gaps(self) -> int:
        return len(self.missing) + len(self.ambiguous) + len(self.inconsistent)

    def summarize(self) -> dict[str, Any]:
        missing_by_priority: dict[int, list[str]] = {}
        for gap in self.missing:
            missing_by_priority.setdefault(gap.priority, []).append(gap.label)

        return {
            "complete": self.is_complete(),
            "total_gaps": self.total_gaps(),
            "missing_count": len(self.missing),
            "ambiguous_count": len(self.ambiguous),
            "inconsistent_count": len(self.inconsistent),
            "missing_by_priority": missing_by_priority,
            "top_priority_gaps": [
                {"key": g.key, "label": g.label, "reason": g.reason, "suggestion": g.suggestion}
                for g in self.missing
                if g.priority == 1
            ],
        }


class DiscoveryEngine:
    """Analyzes intent against a requirement graph to find gaps and inconsistencies.

    All checks are data-driven from the graph metadata. No hardcoded field names.

    Requirement graph metadata drives gaps, consistency checks, and signals.
    """

    def __init__(self, graph: RequirementGraph) -> None:
        self.graph = graph

    def sync_intent_to_graph(self, intent: Any) -> list[str]:
        """Feed extracted intent values into the requirement graph as decisions.

        Derives field mappings from the graph's requirement nodes (target_field),
        making this data-driven rather than hardcoded.
        """
        synced = []
        import warnings as _warnings

        default_intent = self._create_default_intent(intent)

        def _read_nested(obj: Any, dotted_path: str) -> Any:
            parts = dotted_path.split(".")
            for part in parts:
                obj = getattr(obj, part)
            return obj

        def _val_to_str(val: Any) -> str | None:
            if val is None:
                return None
            from enum import StrEnum as _StrEnum

            if isinstance(val, _StrEnum):
                return val.value
            if isinstance(val, bool):
                return "true" if val else "false"
            if isinstance(val, list):
                return ",".join(str(x) for x in val) if val else None
            return str(val)

        field_map: dict[str, str | None] = {}
        default_map: dict[str, str | None] = {}

        for key, req in self.graph._requirements.items():
            intent_path = req.target_field
            if intent_path is None:
                continue
            try:
                val = _read_nested(intent, intent_path)
                field_map[key] = _val_to_str(val)
            except AttributeError:
                field_map[key] = None
            try:
                val = _read_nested(default_intent, intent_path)
                default_map[key] = _val_to_str(val)
            except AttributeError:
                default_map[key] = None

        for key, val in field_map.items():
            if val is not None:
                if key in self.graph._requirements:
                    if val != default_map.get(key):
                        self.graph.decide(key, val)
                    else:
                        req = self.graph._requirements[key]
                        if req.default is None or str(req.default).strip() == "":
                            # Graph has no default; model default is not evidence
                            # that the design doc supplied this requirement.
                            continue
                        self.graph.apply_default(key)
                    synced.append(key)
                elif val != default_map.get(key):
                    _warnings.warn(
                        f"Field '{key}' is set to '{val}' but this pattern's graph "
                        f"has no corresponding requirement. Add a Requirement node "
                        f"or use a different pattern."
                    )
        return synced

    def _create_default_intent(self, intent: Any) -> Any:
        """Create a fresh default intent for comparison."""
        if isinstance(intent, type):
            return intent()
        model = type(intent)
        try:
            return model()
        except Exception:
            return intent

    def discover(self, intent: Any, text: str = "") -> DiscoveryResult:
        """Run all discovery checks against the current intent."""
        result = DiscoveryResult()

        result.synced = self.sync_intent_to_graph(intent)
        self._check_graph_gaps(result)
        self._check_cross_field_consistency(intent, result)
        self._detect_signals(intent, text, result)

        result.missing.sort(key=lambda x: x.priority)
        return result

    def _check_graph_gaps(self, result: DiscoveryResult) -> None:
        """Find gaps using only graph metadata (no hardcoded domain logic)."""
        for key, req in self.graph._requirements.items():
            if not req.required_when_applicable:
                continue
            if not self.graph.is_applicable(key):
                continue
            if self.graph.is_blocked(key):
                continue
            st = self.graph.status(key)
            if st in (RequirementStatus.DECIDED, RequirementStatus.DEFAULTED):
                continue

            priority = 1 if req.violation_code else 2
            result.missing.append(
                RequirementGap(
                    key=key,
                    label=req.label or key,
                    reason=req.violation_message or f"{req.label} is required but not set.",
                    suggestion=req.hint or f"Add '{key}' to your design document.",
                    priority=priority,
                    depends_on=list(req.depends_on),
                )
            )

    def _check_cross_field_consistency(self, intent: Any, result: DiscoveryResult) -> None:
        """Check for inconsistencies between intent fields.

        Checks graph relationships that are violated by intent values.
        """
        for key, req in self.graph._requirements.items():
            for condition_key, blocking_values in req.blocked_if.items():
                cond_val = self.graph.get(condition_key)
                if cond_val is not None and cond_val in blocking_values:
                    result.inconsistent.append(
                        Inconsistency(
                            key_a=condition_key,
                            key_b=key,
                            reason=f"{condition_key}={cond_val} blocks {key}.",
                        )
                    )
            if req.blocked_when and self.graph.is_blocked(key):
                result.inconsistent.append(
                    Inconsistency(
                        key_a="expression",
                        key_b=key,
                        reason=self.graph.is_blocked_reason(key)
                        or f"Expression gate blocks {key}.",
                    )
                )

        # Check applicable-gate requirements that were EXPLICITLY DECIDED but
        # their condition is not met. Skip defaulted values because defaults may
        # not satisfy applies_if/applies_when gates.
        for key, req in self.graph._requirements.items():
            st = self.graph.status(key)
            if st != RequirementStatus.DECIDED:
                continue
            val = self.graph.get(key)
            if val is None:
                continue
            for condition_key, required_values in req.applies_if.items():
                cond_val = self.graph.get(condition_key)
                if cond_val is not None and cond_val not in required_values:
                    result.inconsistent.append(
                        Inconsistency(
                            key_a=condition_key,
                            key_b=key,
                            reason=(
                                f"{key} is explicitly set but "
                                f"{condition_key}={cond_val} does not satisfy applies_if."
                            ),
                        )
                    )
            if req.applies_when and not self.graph.is_applicable(key):
                result.inconsistent.append(
                    Inconsistency(
                        key_a="expression",
                        key_b=key,
                        reason=self.graph.is_applicable_reason(key)
                        or f"{key} is explicitly set but applies_when is not satisfied.",
                    )
                )

    def _detect_signals(self, intent: Any, text: str, result: DiscoveryResult) -> None:
        """Detect migration/compliance signals in design doc text.

        Uses graph metadata (signals field on requirements) to auto-detect
        relevant keywords instead of hardcoding domain knowledge.
        """
        text_lower = text.lower()

        # Build signal keyword map from graph metadata
        signal_keywords: dict[str, list[str]] = {}
        req_by_signal: dict[str, list[str]] = {}

        for key, req in self.graph._requirements.items():
            for sig in req.signals:
                req_by_signal.setdefault(sig, []).append(key)
                keywords = sig.replace("-", " ").replace("_", " ").split()
                signal_keywords.setdefault(sig, []).extend(keywords)
                if sig == "on-prem-ad":
                    signal_keywords[sig].extend(["active directory", "ad domain"])
                elif sig == "mpls":
                    signal_keywords[sig].extend(["mpls", "direct connect"])
                elif sig == "pci-scope":
                    signal_keywords[sig].extend(["pci", "compliance scope", "regulated"])
                elif sig == "regulated-industry":
                    signal_keywords[sig].extend(["regulated", "compliance", "pci", "sox", "hipaa"])
                elif sig == "sap-workload":
                    signal_keywords[sig].extend(["sap", "s/4hana", "sap hana", "sap ecc"])
                elif sig == "oracle-workload":
                    signal_keywords[sig].extend(["oracle", "oracle database", "oracle ebs"])
                elif sig == "mainframe-integration":
                    signal_keywords[sig].extend(["mainframe", "z/os", "zos", "cobol", "cics"])
                elif sig == "multi-cloud":
                    signal_keywords[sig].extend(["multi-cloud", "multicloud", "gcp", "azure"])

        for sig, keywords in signal_keywords.items():
            if any(kw in text_lower for kw in keywords):
                triggered = req_by_signal.get(sig, [])
                if not triggered:
                    continue

                # Suppress the entire signal if any triggered requirement is
                # explicitly decided — the user has already addressed this area.
                any_decided = any(
                    self.graph.status(t) == RequirementStatus.DECIDED for t in triggered
                )
                if any_decided:
                    continue

                # Report triggered requirements that are either undecided OR
                # have a default value that may not match the signal intent.
                to_report = []
                for t in triggered:
                    val = self.graph.get(t)
                    st = self.graph.status(t)
                    if val is None or st in (
                        RequirementStatus.PENDING,
                        RequirementStatus.DEFAULTED,
                    ):
                        to_report.append(t)
                if to_report:
                    result.signals.append(
                        DetectedSignal(
                            signal=sig,
                            triggered_requirements=to_report,
                            context=(
                                f"Signal '{sig}' detected in text. "
                                f"Consider requirements: {', '.join(to_report)}."
                            ),
                        )
                    )


def generate_clarifying_questions(
    result: DiscoveryResult,
    intent: Any,
    graph: RequirementGraph | None = None,
) -> list[dict[str, Any]]:
    """Convert discovery result into structured clarifying questions for LLM or UI.

    Enriches questions with options, hints, and context from graph metadata.
    """
    questions = []

    for gap in result.missing:
        question: dict[str, Any] = {
            "key": gap.key,
            "label": gap.label,
            "question": f"What is the {gap.label.lower()}?",
            "reason": gap.reason,
            "suggestion": gap.suggestion,
            "priority": gap.priority,
            "depends_on": gap.depends_on,
        }

        # Enrich from graph metadata if available
        if graph is not None and gap.key in graph._requirements:
            req = graph._requirements[gap.key]
            if req.question:
                question["question"] = req.question
            if req.options:
                question["options"] = req.options
                question["type"] = "select"
            else:
                question["type"] = "text"
            if req.hint:
                question["context"] = req.hint
            if req.default:
                question["default"] = req.default
            if req.wa_pillars:
                question["wa_pillars"] = req.wa_pillars
            if req.compliance_controls:
                question["compliance_controls"] = req.compliance_controls

        questions.append(question)

    for amb in result.ambiguous:
        questions.append(
            {
                "key": amb.key,
                "label": amb.label,
                "question": f"Clarify: {amb.clarification}",
                "reason": amb.reason,
                "type": "clarify",
            }
        )

    return questions
