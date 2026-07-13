"""Requirement graph with dependencies, blocking rules, and pattern templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC
from enum import StrEnum
from typing import Any

RequirementExpression = dict[str, Any]
_EXPRESSION_OPERATORS = {"all", "any", "not", "equals", "contains", "present"}


def expression_dependencies(expression: RequirementExpression | None) -> list[str]:
    """Return decision keys referenced by a small requirement expression."""

    if not expression:
        return []
    deps: list[str] = []
    for key in ("all", "any"):
        items = expression.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    deps.extend(expression_dependencies(item))
    negated = expression.get("not")
    if isinstance(negated, dict):
        deps.extend(expression_dependencies(negated))
    for key in ("equals", "contains", "present"):
        predicate = expression.get(key)
        if isinstance(predicate, dict):
            decision = predicate.get("decision")
            if isinstance(decision, str) and decision:
                deps.append(decision)
    return list(dict.fromkeys(deps))


def validate_expression(
    expression: RequirementExpression | None,
    *,
    path: str = "expression",
) -> list[str]:
    """Return shape errors for a lightweight requirement expression."""

    if expression is None:
        return []
    if not isinstance(expression, dict) or not expression:
        return [f"{path}: expression must be a non-empty mapping"]

    operators = [key for key in expression if key in _EXPRESSION_OPERATORS]
    unknown = [key for key in expression if key not in _EXPRESSION_OPERATORS]
    errors = [f"{path}: unsupported operator {key}" for key in unknown]
    if len(operators) != 1:
        errors.append(f"{path}: expression must define exactly one operator")
        return errors

    operator = operators[0]
    value = expression[operator]
    if operator in {"all", "any"}:
        if not isinstance(value, list) or not value:
            return errors + [f"{path}.{operator}: must be a non-empty list"]
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                errors.append(f"{path}.{operator}[{index}]: item must be an expression mapping")
                continue
            errors.extend(validate_expression(item, path=f"{path}.{operator}[{index}]"))
        return errors
    if operator == "not":
        if not isinstance(value, dict):
            return errors + [f"{path}.not: must be an expression mapping"]
        return errors + validate_expression(value, path=f"{path}.not")
    if operator in {"equals", "contains"}:
        if not isinstance(value, dict):
            return errors + [f"{path}.{operator}: must be a predicate mapping"]
        if not isinstance(value.get("decision"), str) or not value.get("decision"):
            errors.append(f"{path}.{operator}: decision is required")
        if "value" not in value:
            errors.append(f"{path}.{operator}: value is required")
        return errors
    if operator == "present":
        if not isinstance(value, dict):
            return errors + [f"{path}.present: must be a predicate mapping"]
        if not isinstance(value.get("decision"), str) or not value.get("decision"):
            errors.append(f"{path}.present: decision is required")
        return errors
    return errors


def evaluate_expression(
    expression: RequirementExpression | None,
    decisions: dict[str, str],
) -> bool:
    """Evaluate a lightweight decision expression against graph decisions."""

    if not expression:
        return True
    if validate_expression(expression):
        return False
    if "all" in expression:
        items = expression.get("all")
        return (
            isinstance(items, list)
            and bool(items)
            and all(
                isinstance(item, dict) and evaluate_expression(item, decisions) for item in items
            )
        )
    if "any" in expression:
        items = expression.get("any")
        return (
            isinstance(items, list)
            and bool(items)
            and any(
                isinstance(item, dict) and evaluate_expression(item, decisions) for item in items
            )
        )
    if "not" in expression:
        item = expression.get("not")
        return isinstance(item, dict) and not evaluate_expression(item, decisions)
    if "equals" in expression:
        predicate = expression.get("equals")
        if not isinstance(predicate, dict):
            return False
        decision = predicate.get("decision")
        expected = predicate.get("value")
        return str(decisions.get(str(decision), "")) == str(expected)
    if "contains" in expression:
        predicate = expression.get("contains")
        if not isinstance(predicate, dict):
            return False
        decision = str(predicate.get("decision", ""))
        expected = str(predicate.get("value", ""))
        values = _decision_values(decisions.get(decision, ""))
        return expected in values
    if "present" in expression:
        predicate = expression.get("present")
        if not isinstance(predicate, dict):
            return False
        decision = str(predicate.get("decision", ""))
        return bool(str(decisions.get(decision, "")).strip())
    return False


def describe_expression(expression: RequirementExpression | None) -> str:
    """Render a small expression in reviewer-friendly text."""

    if not expression:
        return ""
    if "all" in expression:
        items = expression.get("all")
        if not isinstance(items, list):
            return "all(<invalid>)"
        return " and ".join(part for part in (describe_expression(item) for item in items) if part)
    if "any" in expression:
        items = expression.get("any")
        if not isinstance(items, list):
            return "any(<invalid>)"
        return " or ".join(part for part in (describe_expression(item) for item in items) if part)
    if "not" in expression:
        item = expression.get("not")
        return f"not ({describe_expression(item)})" if isinstance(item, dict) else "not <invalid>"
    if "equals" in expression:
        predicate = expression.get("equals")
        if isinstance(predicate, dict):
            return f"{predicate.get('decision')} == {predicate.get('value')}"
    if "contains" in expression:
        predicate = expression.get("contains")
        if isinstance(predicate, dict):
            return f"{predicate.get('decision')} contains {predicate.get('value')}"
    if "present" in expression:
        predicate = expression.get("present")
        if isinstance(predicate, dict):
            return f"{predicate.get('decision')} is present"
    return "<unsupported expression>"


def _decision_values(value: str) -> list[str]:
    return [part.strip() for part in str(value).split(",") if part.strip()]


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
    applies_when: RequirementExpression | None = None
    blocked_when: RequirementExpression | None = None
    cascade: dict[str, str] = field(default_factory=dict)
    category: str = "general"
    hint: str | None = None
    # Model-driven mapping: which intent model field this node maps to -------
    target_field: str | None = None  # dotted path: "network.cidr", "security.enabled"
    target_type: str = "string"  # string, int, bool, float, *_list, or enum name
    compliance_controls: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    tradeoffs: list[str] = field(default_factory=list)
    # Validation metadata ------------------------------------------------------
    required_when_applicable: bool = True  # fail-closed if applicable but unset
    violation_code: str | None = None  # e.g. HUB_SPOKE_NETWORK_ACCOUNT_REQUIRED
    violation_message: str | None = None  # human-readable fail-closed message


class RequirementGraph:
    """Tracks requirements, their dependencies, and resolution status."""

    def __init__(self) -> None:
        self._edges: list[tuple[str, str]] = []
        self._edge_set: set[tuple[str, str]] = set()
        self._requirements: dict[str, Requirement] = {}
        self._decisions: dict[str, str] = {}
        self._status: dict[str, RequirementStatus] = {}
        self._audit_log: list[dict[str, Any]] = []
        self._intent_model: Any = None

    def add(self, req: Requirement) -> None:
        self._requirements[req.key] = req
        for dep in self._ordering_dependencies(req):
            self._add_edge(dep, req.key)
        self._status[req.key] = RequirementStatus.PENDING

    def _add_edge(self, source: str, target: str) -> None:
        edge = (source, target)
        if edge in self._edge_set:
            return
        self._edge_set.add(edge)
        self._edges.append(edge)

    def edges(self) -> list[tuple[str, str]]:
        return sorted(self._edges)

    def edge_count(self) -> int:
        return len(self._edges)

    def topological_order(self) -> list[str]:
        nodes = self._ordered_nodes()
        outgoing: dict[str, list[str]] = {node: [] for node in nodes}
        indegree: dict[str, int] = {node: 0 for node in nodes}
        for source, target in self._edges:
            outgoing.setdefault(source, []).append(target)
            indegree.setdefault(source, 0)
            indegree[target] = indegree.get(target, 0) + 1

        ready = [node for node in nodes if indegree.get(node, 0) == 0]
        ordered: list[str] = []
        while ready:
            node = ready.pop(0)
            ordered.append(node)
            for target in outgoing.get(node, []):
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)

        if len(ordered) != len(nodes):
            raise ValueError(f"requirement graph has a cycle: {self.cycle_edges()}")
        return ordered

    def cycle_edges(self) -> list[tuple[str, str]]:
        nodes = self._ordered_nodes()
        outgoing: dict[str, list[str]] = {node: [] for node in nodes}
        for source, target in self._edges:
            outgoing.setdefault(source, []).append(target)

        state: dict[str, str] = {}
        stack: list[str] = []

        def visit(node: str) -> list[tuple[str, str]]:
            state[node] = "visiting"
            stack.append(node)
            for target in outgoing.get(node, []):
                if state.get(target) == "visiting":
                    cycle_nodes = stack[stack.index(target) :] + [target]
                    return list(zip(cycle_nodes, cycle_nodes[1:]))
                if state.get(target) != "visited":
                    cycle = visit(target)
                    if cycle:
                        return cycle
            stack.pop()
            state[node] = "visited"
            return []

        for node in nodes:
            if state.get(node) is None:
                cycle = visit(node)
                if cycle:
                    return cycle
        return []

    def _ordered_nodes(self) -> list[str]:
        nodes = dict.fromkeys(self._requirements)
        for source, target in self._edges:
            nodes.setdefault(source, None)
            nodes.setdefault(target, None)
        return list(nodes)

    def _ordering_dependencies(self, req: Requirement) -> list[str]:
        deps = list(req.depends_on)
        deps.extend(req.applies_if)
        deps.extend(req.blocked_if)
        deps.extend(expression_dependencies(req.applies_when))
        deps.extend(expression_dependencies(req.blocked_when))
        return list(dict.fromkeys(dep for dep in deps if dep != req.key))

    def _audit(self, key: str, value: str, how: str, reason: str | None = None) -> None:
        from datetime import datetime

        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "key": key,
            "value": value,
            "how": how,
        }
        if reason is not None:
            entry["reason"] = reason
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
        if req.default is None:
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

    def has_requirement(self, key: str) -> bool:
        return key in self._requirements

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
        if req.blocked_when is not None:
            return evaluate_expression(req.blocked_when, self._decisions)
        return False

    def is_applicable(self, key: str) -> bool:
        req = self._requirements.get(key)
        if not req:
            return False
        if not req.applies_if and req.applies_when is None:
            return True
        for condition_key, triggering_values in req.applies_if.items():
            if self._decisions.get(condition_key) not in triggering_values:
                return False
        if req.applies_when is not None:
            return evaluate_expression(req.applies_when, self._decisions)
        return True

    def is_blocked_reason(self, key: str) -> str | None:
        req = self._requirements.get(key)
        if not req:
            return None
        for condition_key, blocking_values in req.blocked_if.items():
            if self._decisions.get(condition_key) in blocking_values:
                cond_val = self._decisions.get(condition_key, "(undecided)")
                return f"Blocked when {condition_key}={cond_val}"
        if req.blocked_when is not None and evaluate_expression(req.blocked_when, self._decisions):
            return f"Blocked when {describe_expression(req.blocked_when)}"
        return None

    def is_applicable_reason(self, key: str) -> str | None:
        req = self._requirements.get(key)
        if not req:
            return None
        if not req.applies_if and req.applies_when is None:
            return None
        for condition_key, triggering_values in req.applies_if.items():
            actual = self._decisions.get(condition_key)
            if actual is None:
                return None
            if actual not in triggering_values:
                return f"Not applicable when {condition_key}={actual}"
        if req.applies_when is not None and not evaluate_expression(
            req.applies_when,
            self._decisions,
        ):
            return f"Not applicable unless {describe_expression(req.applies_when)}"
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
        ordered_keys = [key for key in self.topological_order() if key in decisions]
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

        # Fallback for string-based target_type metadata.
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
