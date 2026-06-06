"""Lightweight typed semantic graph primitives.

This module is intentionally small: patterns can derive entity/relationship
facts and predicate constraint results without introducing a database, ontology
runtime, or policy engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class PredicateStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class SemanticEntity:
    kind: str
    key: str
    label: str
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "key": self.key,
            "label": self.label,
            "properties": self.properties,
        }


@dataclass(frozen=True)
class SemanticRelationship:
    source: str
    relationship: str
    target: str
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "relationship": self.relationship,
            "target": self.target,
            "properties": self.properties,
        }


@dataclass(frozen=True)
class PredicateConstraint:
    key: str
    label: str
    expression: dict[str, Any]
    status: PredicateStatus
    evidence: str
    violation_code: str
    violation_message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "expression": self.expression,
            "status": self.status.value,
            "evidence": self.evidence,
            "violationCode": self.violation_code,
            "violationMessage": self.violation_message,
        }


@dataclass(frozen=True)
class SemanticModel:
    schema_version: str
    entities: list[SemanticEntity]
    relationships: list[SemanticRelationship]
    constraints: list[PredicateConstraint]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "summary": {
                "entityCount": len(self.entities),
                "relationshipCount": len(self.relationships),
                "constraintCount": len(self.constraints),
                "failedConstraintCount": len(
                    [item for item in self.constraints if item.status == PredicateStatus.FAIL]
                ),
            },
            "entities": [item.to_dict() for item in self.entities],
            "relationships": [item.to_dict() for item in self.relationships],
            "constraints": [item.to_dict() for item in self.constraints],
        }

    def failed_constraints(self) -> list[PredicateConstraint]:
        return [item for item in self.constraints if item.status == PredicateStatus.FAIL]
