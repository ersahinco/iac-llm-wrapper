"""Requirement graph with dependencies, blocking rules, and pattern templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC
from enum import StrEnum
from typing import Any

import networkx as nx


class RequirementStatus(StrEnum):
    PENDING = "pending"
    DECIDED = "decided"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    DEFAULTED = "defaulted"


@dataclass
class Requirement:
    """A single architectural decision point with full contextual knowledge."""

    key: str
    label: str
    question: str
    options: list[str] | None = None
    default: str | None = None
    depends_on: list[str] = field(default_factory=list)
    blocked_if: dict[str, list[str]] = field(default_factory=dict)
    applies_if: dict[str, list[str]] = field(default_factory=dict)
    cascade: dict[str, str] = field(default_factory=dict)
    category: str = "general"
    hint: str | None = None
    why_applies: str | None = None
    why_blocked: str | None = None
    # Model-driven mapping: which RawIntent field this node maps to ----------
    target_field: str | None = None  # dotted path: "security.cidr", "cicd.mode"
    target_type: str = "string"  # "string" | "int" | "bool" | enum name
    # Well-Architected mapping ------------------------------------------------
    wa_pillars: list[str] = field(default_factory=list)
    # Knowledge fields ---------------------------------------------------------
    compliance_controls: list[str] = field(default_factory=list)
    enterprise_standards: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    tradeoffs: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    consequences: list[str] = field(default_factory=list)
    experience_notes: list[str] = field(default_factory=list)
    confidence: float = 1.0  # confidence in default (0-1)
    overridable: bool = True  # can experience override default
    # Validation metadata ------------------------------------------------------
    required_when_applicable: bool = True  # fail-closed if applicable but unset
    violation_code: str | None = None  # e.g. HUB_SPOKE_NETWORK_ACCOUNT_REQUIRED
    violation_message: str | None = None  # human-readable fail-closed message


class RequirementGraph:
    """Tracks requirements, their dependencies, and resolution status."""

    def __init__(self, intent_model: Any = None) -> None:
        self._graph = nx.DiGraph()
        self._requirements: dict[str, Requirement] = {}
        self._decisions: dict[str, str] = {}
        self._status: dict[str, RequirementStatus] = {}
        self._audit_log: list[dict[str, Any]] = []
        # Optional addon field_map overrides: key -> intent_field_path
        self._field_map: dict[str, str | None] = {}
        # Optional intent model for auto-deriving target_field/target_type
        self._intent_model = intent_model

    def add(self, req: Requirement) -> None:
        # Auto-derive target_field/target_type from model when not provided
        if self._intent_model is not None:
            self._auto_derive_requirement(req)
        self._requirements[req.key] = req
        self._graph.add_node(req.key)
        for dep in self._ordering_dependencies(req):
            self._graph.add_edge(dep, req.key)
        self._status[req.key] = RequirementStatus.PENDING

    def _ordering_dependencies(self, req: Requirement) -> list[str]:
        deps = list(req.depends_on)
        deps.extend(req.applies_if)
        deps.extend(req.blocked_if)
        return list(dict.fromkeys(dep for dep in deps if dep != req.key))

    def _auto_derive_requirement(self, req: Requirement) -> None:
        """Auto-populate target_field and target_type from the intent model."""
        from .model_introspection import derive_target_type, discover_model_fields

        model = self._intent_model
        if model is None or not isinstance(model, type):
            return

        # If target_field is not set, try to discover it from the model
        if req.target_field is None:
            discovered = discover_model_fields(model)
            if req.key in discovered:
                req.target_field = discovered[req.key][0]

        # If target_type is not set (or is generic "string"), derive from annotation
        if req.target_field and (not req.target_type or req.target_type == "string"):
            try:
                from .model_introspection import resolve_field_info

                _, annotation = resolve_field_info(model, req.target_field)
                req.target_type = derive_target_type(annotation)
            except Exception:
                pass

        # Auto-generate label/question from key if not provided
        if not req.label:
            req.label = req.key.replace("_", " ").title()
        if not req.question:
            req.question = f"What is the {req.label.lower()}?"

    def _audit(self, key: str, value: str, how: str, reason: str | None = None) -> None:
        from datetime import datetime

        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "key": key,
            "value": value,
            "how": how,
            "reason": reason,
        }
        self._audit_log.append(entry)

    def decide(self, key: str, value: str, reason: str | None = None) -> None:
        if key not in self._requirements:
            raise KeyError(f"Unknown requirement: {key}")
        self._decisions[key] = value
        self._status[key] = RequirementStatus.DECIDED
        self._audit(key, value, "decided", reason)
        self._apply_cascades(key, value)
        self._update_blocked()

    def apply_default(self, key: str) -> None:
        if key not in self._requirements:
            raise KeyError(f"Unknown requirement: {key}")
        req = self._requirements[key]
        if not req.default:
            raise ValueError(f"No default for requirement: {key}")
        self._decisions[key] = req.default
        self._status[key] = RequirementStatus.DEFAULTED
        self._audit(key, req.default, "defaulted", "default value")
        self._apply_cascades(key, req.default)
        self._update_blocked()

    def skip(self, key: str, reason: str | None = None) -> None:
        self._status[key] = RequirementStatus.SKIPPED
        self._audit(key, "(skipped)", "skipped", reason)

    def audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit_log)

    def get(self, key: str) -> str | None:
        return self._decisions.get(key)

    def status(self, key: str) -> RequirementStatus:
        return self._status.get(key, RequirementStatus.PENDING)

    def is_ready(self, key: str) -> bool:
        req = self._requirements.get(key)
        if not req:
            return False
        if self._status[key] != RequirementStatus.PENDING:
            return False
        for dep in self._ordering_dependencies(req):
            if dep not in self._requirements:
                continue
            if self._status.get(dep) not in (
                RequirementStatus.DECIDED,
                RequirementStatus.DEFAULTED,
                RequirementStatus.SKIPPED,
            ):
                return False
        return True

    def is_blocked(self, key: str) -> bool:
        req = self._requirements.get(key)
        if not req:
            return False
        for condition_key, blocking_values in req.blocked_if.items():
            if self._decisions.get(condition_key) in blocking_values:
                return True
        return False

    def is_applicable(self, key: str) -> bool:
        req = self._requirements.get(key)
        if not req:
            return False
        if not req.applies_if:
            return True
        for condition_key, triggering_values in req.applies_if.items():
            if self._decisions.get(condition_key) not in triggering_values:
                return False
        return True

    def is_blocked_reason(self, key: str) -> str | None:
        req = self._requirements.get(key)
        if not req:
            return None
        for condition_key, blocking_values in req.blocked_if.items():
            if self._decisions.get(condition_key) in blocking_values:
                cond_val = self._decisions.get(condition_key, "(undecided)")
                return req.why_blocked or f"Blocked when {condition_key}={cond_val}"
        return None

    def is_applicable_reason(self, key: str) -> str | None:
        req = self._requirements.get(key)
        if not req:
            return None
        if not req.applies_if:
            return None
        for condition_key, triggering_values in req.applies_if.items():
            actual = self._decisions.get(condition_key)
            if actual is None:
                return None
            if actual not in triggering_values:
                return req.why_applies or f"Not applicable when {condition_key}={actual}"
        return None

    def pending(self) -> list[str]:
        ready = []
        for key in self._requirements:
            if self._status[key] != RequirementStatus.PENDING:
                continue
            if self.is_blocked(key):
                self._status[key] = RequirementStatus.BLOCKED
            elif not self.is_ready(key):
                continue
            elif not self.is_applicable(key):
                self._status[key] = RequirementStatus.SKIPPED
            else:
                ready.append(key)
        return ready

    def all_decided(self) -> bool:
        for key, req in self._requirements.items():
            st = self._status[key]
            if st == RequirementStatus.PENDING:
                return False
            if st == RequirementStatus.BLOCKED:
                continue
            if st == RequirementStatus.SKIPPED:
                continue
        return True

    def decisions(self) -> dict[str, str]:
        return dict(self._decisions)

    def typed_decisions(self) -> dict[str, Any]:
        typed: dict[str, Any] = {}
        for key, value in self._decisions.items():
            if value is None:
                continue
            req = self._requirements.get(key)
            if req is not None:
                typed[key] = self._convert_value(
                    value,
                    req.target_type,
                    req.target_field or key,
                )
            else:
                typed[key] = value
        return typed

    def apply_defaults_for_remaining(self) -> None:
        while True:
            pending = self.pending()
            if not pending:
                break
            key = pending[0]
            req = self._requirements[key]
            if req.default:
                self.apply_default(key)
            else:
                self.skip(key)

    @staticmethod
    def stringify_decision_value(value: Any, target_type: str) -> str:
        """Serialize structured prefill values into graph-friendly strings."""
        if target_type == "bool" and isinstance(value, bool):
            return "true" if value else "false"
        if target_type in ("cidr_list", "string_list") and isinstance(value, list):
            return ",".join(str(item) for item in value)
        return str(value)

    def apply_decisions(self, decisions: dict[str, Any]) -> list[str]:
        """Apply a batch of decisions to the graph, respecting gates.

        Returns the list of keys that were successfully applied.
        """
        applied: list[str] = []
        ordered_keys = [key for key in nx.topological_sort(self._graph) if key in decisions]
        ordered_keys.extend(key for key in decisions if key not in self._requirements)
        for key in ordered_keys:
            value = decisions[key]
            if key not in self._requirements:
                continue
            # Skip if blocked or not applicable
            if self.is_blocked(key):
                self.skip(key, self.is_blocked_reason(key))
                continue
            if not self.is_applicable(key):
                self.skip(key, self.is_applicable_reason(key))
                continue
            req = self._requirements[key]
            self.decide(key, self.stringify_decision_value(value, req.target_type))
            applied.append(key)
        return applied

    def summary(self) -> dict[str, Any]:
        return {
            "decisions": dict(self._decisions),
            "status": {k: v.value for k, v in self._status.items()},
            "pending": self.pending(),
        }

    def _convert_value(self, value: str, target_type: str, target_field: str | None = None) -> Any:
        """Convert a string decision value to the target type.

        Uses the intent model's annotation when available for generic coercion.
        """
        # Try model-driven coercion first
        if self._intent_model is not None and target_field is not None:
            try:
                from .model_introspection import coerce_value, resolve_field_info

                _, annotation = resolve_field_info(self._intent_model, target_field)
                return coerce_value(value, annotation)
            except Exception:
                pass

        # Legacy string-based coercion
        if target_type == "string":
            return value
        if target_type == "int":
            return int(value)
        if target_type == "bool":
            return value.lower() in ("true", "yes", "1")
        if target_type in ("cidr_list", "string_list"):
            return [c.strip() for c in value.split(",") if c.strip()]
        # Enum types — resolve from intent model module if available
        if self._intent_model is not None:
            import importlib

            mod = importlib.import_module(self._intent_model.__module__)
            enum_cls = getattr(mod, target_type, None)
            if enum_cls is not None:
                return enum_cls(value)
        return value

    @staticmethod
    def _set_nested(obj: Any, dotted_path: str, value: Any) -> None:
        """Set an attribute on a nested object by dotted path.
        E.g., 'security.cidr' → obj.security.cidr = value
        """
        parts = dotted_path.split(".")
        for part in parts[:-1]:
            obj = getattr(obj, part)
        setattr(obj, parts[-1], value)

    def apply_to_intent(self, intent: Any) -> None:
        # Build set of cascade targets with their inferred types from parent
        cascade_types: dict[str, str] = {}
        for req in self._requirements.values():
            for target_key, cascade_value in req.cascade.items():
                if cascade_value == "{value}":
                    cascade_types[target_key] = req.target_type

        for key, value in self._decisions.items():
            if value is None:
                continue
            requirement = self._requirements.get(key)
            if requirement is not None and requirement.target_field is not None:
                parsed = self._convert_value(
                    value,
                    requirement.target_type,
                    requirement.target_field,
                )
                self._set_nested(intent, requirement.target_field, parsed)
            elif requirement is None and key in cascade_types:
                # Cascaded keys — use parent requirement's target_type
                parsed = self._convert_value(value, cascade_types[key], key)
                self._set_nested(intent, key, parsed)
            elif requirement is None:
                # Unknown cascaded key — set as raw string
                self._set_nested(intent, key, value)

    def _apply_cascades(self, key: str, value: str) -> None:
        req = self._requirements[key]
        for target_key, cascade_value in req.cascade.items():
            if cascade_value == "{value}":
                self._decisions[target_key] = value
            else:
                self._decisions[target_key] = cascade_value
            if target_key in self._status:
                self._status[target_key] = RequirementStatus.DEFAULTED

    def _update_blocked(self) -> None:
        for key in self._requirements:
            st = self._status[key]
            if st in (
                RequirementStatus.PENDING,
                RequirementStatus.BLOCKED,
                RequirementStatus.SKIPPED,
            ):
                if self.is_blocked(key):
                    self._status[key] = RequirementStatus.BLOCKED
                elif not self.is_applicable(key):
                    self._status[key] = RequirementStatus.SKIPPED
                else:
                    self._status[key] = RequirementStatus.PENDING
