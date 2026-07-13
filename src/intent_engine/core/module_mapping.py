"""Module handoff models for validated intent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


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


@dataclass
class IaCIntentPayload:
    """Validated intent plus generation context."""

    module_inputs: list[ModuleInputs]
    intent: Any
    pattern: str = ""
    decisions: dict[str, Any] = field(default_factory=dict)
    extraction_summary: dict[str, Any] = field(default_factory=dict)
    target_capability_report: dict[str, Any] = field(default_factory=dict)
    source_context: dict[str, Any] = field(default_factory=dict)
    decision_audit: list[dict[str, Any]] = field(default_factory=list)
    handoff_readiness: dict[str, Any] = field(default_factory=dict)
