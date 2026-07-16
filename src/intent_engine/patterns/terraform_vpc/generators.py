"""Validators and artifact generators for Terraform VPC handoff."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from intent_engine.core.module_mapping import ModuleInputs
from intent_engine.core.validator import Violation
from intent_engine.core.yaml_utils import write_yaml_artifact

from .models import TerraformVpcIntent


def _intent(payload: Any) -> TerraformVpcIntent:
    intent = getattr(payload, "intent", payload)
    if not isinstance(intent, TerraformVpcIntent):
        raise TypeError(
            f"Terraform VPC generator requires TerraformVpcIntent, got {type(intent).__name__}."
        )
    return intent


def validate_intent(intent: Any) -> list[Violation]:
    model = _intent(intent)
    violations: list[Violation] = []
    if len(model.public_subnet_cidrs) != model.az_count:
        violations.append(
            Violation(
                code="PUBLIC_SUBNET_AZ_COUNT_MISMATCH",
                message="public_subnet_cidrs count must match az_count.",
            )
        )
    if len(model.private_subnet_cidrs) != model.az_count:
        violations.append(
            Violation(
                code="PRIVATE_SUBNET_AZ_COUNT_MISMATCH",
                message="private_subnet_cidrs count must match az_count.",
            )
        )
    return violations


def _az_names(region: str, az_count: int) -> list[str]:
    suffixes = ("a", "b", "c", "d", "e", "f")
    return [f"{region}{suffix}" for suffix in suffixes[:az_count]]


def map_terraform_vpc_modules(intent: Any) -> list[ModuleInputs]:
    model = _intent(intent)
    return [
        ModuleInputs(
            module_name="terraform-aws-vpc",
            variables={
                "name": model.vpc_name,
                "cidr": model.cidr,
                "azs": _az_names(model.primary_region, model.az_count),
                "public_subnets": model.public_subnet_cidrs,
                "private_subnets": model.private_subnet_cidrs,
                "enable_nat_gateway": model.enable_nat_gateway,
                "single_nat_gateway": model.single_nat_gateway,
                "enable_dns_hostnames": model.enable_dns_hostnames,
            },
        )
    ]


def gen_decision_report(intent: Any, output_dir: Path) -> None:
    readiness = getattr(intent, "handoff_readiness", {})
    model = _intent(intent)
    data = {
        "pattern": "terraform-vpc",
        "vpc": {
            "name": model.vpc_name,
            "region": model.primary_region,
            "cidr": model.cidr,
            "azCount": model.az_count,
            "publicSubnetCidrs": model.public_subnet_cidrs,
            "privateSubnetCidrs": model.private_subnet_cidrs,
            "enableNatGateway": model.enable_nat_gateway,
            "singleNatGateway": model.single_nat_gateway,
            "enableDnsHostnames": model.enable_dns_hostnames,
        },
        "targetModule": {
            "name": "terraform-aws-vpc",
            "source": "terraform-aws-modules/vpc/aws",
        },
        "delivery": {
            "targetAccountId": model.target_account_id,
            "deploymentPipelineRef": model.deployment_pipeline_ref,
            "boundary": (
                "Account and pipeline routing are handoff metadata for owner-controlled "
                "automation; generated module inputs do not invoke deployment."
            ),
        },
    }
    if readiness:
        data["handoffReadiness"] = readiness
    write_yaml_artifact(output_dir / "decision-report.yaml", data, header="")
