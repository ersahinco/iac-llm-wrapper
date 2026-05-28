"""CloudFormation parameter handoff intent model."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CloudFormationParametersIntent(BaseModel):
    """Parameters for an existing CloudFormation template handoff."""

    stack_name: str = "app-stack"
    template_url: str = ""
    region: str = "eu-central-1"
    parameter_overrides: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=lambda: ["CAPABILITY_NAMED_IAM"])
    execution_role_arn: str = ""
