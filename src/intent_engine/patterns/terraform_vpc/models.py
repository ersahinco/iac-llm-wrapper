"""Intent model for a bring-your-own Terraform VPC module."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TerraformVpcIntent(BaseModel):
    """Inputs needed by a typical Terraform AWS VPC module."""

    vpc_name: str = "app-vpc"
    primary_region: str = "eu-central-1"
    cidr: str = "10.0.0.0/16"
    az_count: int = 2
    public_subnet_cidrs: list[str] = Field(default_factory=list)
    private_subnet_cidrs: list[str] = Field(default_factory=list)
    enable_nat_gateway: bool = True
    single_nat_gateway: bool = True
    enable_dns_hostnames: bool = True
    target_account_id: str = ""
    deployment_pipeline_ref: str = ""
