"""Validation and fail-closed checks.

Two layers of validation:
  1. Graph-driven: the requirement graph declares what is required when applicable.
     This makes validation data-driven — new requirements automatically enforce rules.
  2. Intent-driven: pattern validators handle cross-field and list-item checks that
     are hard to express in the graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

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

    Pattern-specific validation runs against the typed intent model.
    """
    violations: list[Violation] = []

    if isinstance(intent, BaseModel):
        try:
            type(intent).model_validate(intent.model_dump())
        except ValidationError as exc:
            for error in exc.errors():
                path = ".".join(str(part) for part in error["loc"]) or "<root>"
                code_path = "_".join(str(part).upper() for part in error["loc"]) or "ROOT"
                violations.append(
                    Violation(
                        code=f"INTENT_MODEL_{code_path}_INVALID",
                        message=f"Intent field '{path}' is invalid: {error['msg']}",
                    )
                )
            return violations

    # Layer 1: graph-driven validation (data model is truth)
    if graph is not None:
        violations.extend(validate_graph(graph))

    # Layer 2: pattern-specific validators
    if extra_validators:
        for validator in extra_validators:
            violations.extend(validator(intent))

    return violations
