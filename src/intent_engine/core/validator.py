"""Validation and fail-closed checks.

Two layers of validation:
  1. Graph-driven: the requirement graph declares what is required when applicable.
     This makes validation data-driven — new requirements automatically enforce rules.
  2. Intent-driven: cross-field and list-item checks that are hard to express in the
     graph (e.g., workload target_account, ECS runtime + network mode).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .requirements import RequirementGraph, RequirementStatus


@dataclass
class Violation:
    code: str
    message: str


def validate_graph(graph: RequirementGraph) -> list[Violation]:
    """Validate using the requirement graph as the single source of truth.

    Any requirement that is applicable, not blocked, and has
    required_when_applicable=True must have a decision (decided or defaulted).
    """
    violations: list[Violation] = []
    for key, req in graph._requirements.items():
        if not req.required_when_applicable:
            continue
        if not graph.is_applicable(key):
            continue
        if graph.is_blocked(key):
            continue
        st = graph.status(key)
        if st in (RequirementStatus.DECIDED, RequirementStatus.DEFAULTED):
            value = graph.get(key)
            if value is not None and str(value).strip():
                continue
        # Not satisfied — emit violation using graph metadata
        code = req.violation_code or f"{key.upper()}_REQUIRED"
        message = req.violation_message or (
            f"'{req.label}' is required when applicable but not set. "
            f"Add '{key}' to your design document."
        )
        violations.append(Violation(code=code, message=message))
    return violations


def validate(
    intent: Any,
    graph: RequirementGraph | None = None,
    extra_validators: list[Any] | None = None,
) -> list[Violation]:
    """Validate intent, optionally augmented by graph-driven rules.

    If a graph is provided, graph-driven validation runs first. This makes
    the system data-model-driven: adding a Requirement node with
    required_when_applicable=True automatically creates a fail-closed rule.

    Pattern-specific validators can optionally accept a graph parameter
    to make graph-aware decisions.
    """
    violations: list[Violation] = []

    # Layer 1: graph-driven validation (data model is truth)
    if graph is not None:
        violations.extend(validate_graph(graph))

    # Layer 2: pattern-specific validators
    if extra_validators:
        for validator in extra_validators:
            try:
                violations.extend(validator(intent, graph=graph))
            except TypeError:
                # Fallback for validators that don't accept graph
                violations.extend(validator(intent))

    return violations
