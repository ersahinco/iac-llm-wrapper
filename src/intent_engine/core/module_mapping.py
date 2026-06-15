"""Module handoff models for validated intent.

This layer carries design context and module inputs:
- DesignDocument: business/architectural context for documentation/PRs
- ModuleInputs: literal variables for specific IaC modules
- IaCIntentPayload: combined output passed to generators
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


class DesignDocument(BaseModel):
    """Business and architectural context extracted from user prose."""

    project_name: str = Field(
        default="",
        description="Normalized project identifier (lowercase, hyphens).",
    )
    business_justification: str = Field(
        default="",
        description="Summary of why this infrastructure is needed.",
    )
    estimated_tier: str = Field(
        default="",
        description="Deduced tier based on criticality (e.g., Tier-1 Mission Critical).",
    )
    compliance_tags: list[str] = Field(
        default_factory=list,
        description="Inferred metadata tags like 'contains-pii' or 'public-facing'.",
    )


class ModuleInputs(BaseModel):
    """Literal, validated variables expected by a specific IaC module."""

    module_name: str = Field(
        default="",
        description="The primary target module (e.g., 'terraform-aws-vpc').",
    )
    variables: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Key-value pairs matching the exact input variable names of the underlying module."
        ),
    )


@dataclass(init=False)
class IaCIntentPayload:
    """Combined output: design context + module inputs + the original intent."""

    design_doc: DesignDocument
    module_inputs: list[ModuleInputs]
    intent: Any
    pattern: str = ""
    decisions: dict[str, Any] = field(default_factory=dict)
    extraction_summary: dict[str, Any] = field(default_factory=dict)
    target_capability_report: dict[str, Any] = field(default_factory=dict)
    source_context: dict[str, Any] = field(default_factory=dict)
    _handoff_readiness: dict[str, Any] = field(default_factory=dict, repr=False)

    def __init__(
        self,
        design_doc: DesignDocument,
        module_inputs: list[ModuleInputs],
        intent: Any,
        pattern: str = "",
        decisions: dict[str, Any] | None = None,
        extraction_summary: dict[str, Any] | None = None,
        target_capability_report: dict[str, Any] | None = None,
        source_context: dict[str, Any] | None = None,
        handoff_readiness: dict[str, Any] | None = None,
    ) -> None:
        self.design_doc = design_doc
        self.module_inputs = module_inputs
        self.intent = intent
        self.pattern = pattern
        self.decisions = decisions or {}
        self.extraction_summary = extraction_summary or {}
        self.target_capability_report = target_capability_report or {}
        self.source_context = source_context or {}
        self._handoff_readiness = handoff_readiness or {}

    @property
    def handoff_readiness(self) -> dict[str, Any]:
        """Preferred readiness name for graph- and contract-owned handoff status."""
        return self._handoff_readiness

    @handoff_readiness.setter
    def handoff_readiness(self, value: dict[str, Any]) -> None:
        self._handoff_readiness = value

    def __getattr__(self, name: str) -> Any:
        """Proxy attribute access to the underlying intent model.

        This allows existing generators to work unchanged when they receive
        an IaCIntentPayload instead of a raw intent object.
        """
        if name in (
            "design_doc",
            "module_inputs",
            "intent",
            "pattern",
            "decisions",
            "extraction_summary",
            "target_capability_report",
            "source_context",
            "handoff_readiness",
            "_handoff_readiness",
        ):
            return object.__getattribute__(self, name)
        return getattr(self.intent, name)
