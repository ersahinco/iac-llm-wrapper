"""Bring-your-own Terraform VPC module pattern.

This is intentionally small: a data model, graph, contract, mapper, and one
decision-report generator. It proves custom IaC modules can be driven by the
same intent-engine flow without core framework edits.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import ruamel.yaml

from intent_engine.core.contracts import (
    GLOBAL_CONTRACT_REGISTRY,
    ArtifactContract,
    DecisionLineage,
    TargetContract,
)
from intent_engine.core.generator import register_generator
from intent_engine.core.module_mapping import ModuleInputs, register_module_mapper
from intent_engine.core.patterns import GLOBAL_REGISTRY, Pattern
from intent_engine.core.requirements import Requirement, RequirementGraph
from intent_engine.core.sample_config import GLOBAL_SAMPLE_REGISTRY, ModuleRef, SampleConfig
from intent_engine.core.validator import Violation

from .models import TerraformVpcIntent


def _intent(payload: Any) -> TerraformVpcIntent | None:
    intent = getattr(payload, "intent", payload)
    if isinstance(intent, TerraformVpcIntent):
        return intent
    return None


def _graph_factory() -> RequirementGraph:
    graph = RequirementGraph()
    graph.add(
        Requirement(
            key="vpc_name",
            target_field="vpc_name",
            target_type="string",
            label="VPC Name",
            question="What should the VPC be named?",
            default="app-vpc",
            category="network",
            required_when_applicable=True,
        )
    )
    graph.add(
        Requirement(
            key="primary_region",
            target_field="primary_region",
            target_type="string",
            label="Primary Region",
            question="Which AWS region should host the VPC?",
            default="eu-central-1",
            category="network",
        )
    )
    graph.add(
        Requirement(
            key="cidr",
            target_field="cidr",
            target_type="string",
            label="VPC CIDR",
            question="What CIDR block should the VPC use?",
            default="10.0.0.0/16",
            category="network",
            required_when_applicable=True,
        )
    )
    graph.add(
        Requirement(
            key="az_count",
            target_field="az_count",
            target_type="int",
            label="Availability Zone Count",
            question="How many availability zones should the VPC span?",
            default="2",
            category="network",
        )
    )
    graph.add(
        Requirement(
            key="public_subnet_cidrs",
            target_field="public_subnet_cidrs",
            target_type="cidr_list",
            label="Public Subnet CIDRs",
            question="Which public subnet CIDRs should be passed to the module?",
            default="10.0.0.0/24,10.0.1.0/24",
            category="network",
            required_when_applicable=True,
        )
    )
    graph.add(
        Requirement(
            key="private_subnet_cidrs",
            target_field="private_subnet_cidrs",
            target_type="cidr_list",
            label="Private Subnet CIDRs",
            question="Which private subnet CIDRs should be passed to the module?",
            default="10.0.10.0/24,10.0.11.0/24",
            category="network",
            required_when_applicable=True,
        )
    )
    graph.add(
        Requirement(
            key="enable_nat_gateway",
            target_field="enable_nat_gateway",
            target_type="bool",
            label="NAT Gateway",
            question="Should private subnets have NAT gateway egress?",
            options=["true", "false"],
            default="true",
            category="network",
        )
    )
    graph.add(
        Requirement(
            key="single_nat_gateway",
            target_field="single_nat_gateway",
            target_type="bool",
            label="Single NAT Gateway",
            question="Use one NAT gateway instead of one per AZ?",
            options=["true", "false"],
            default="true",
            depends_on=["enable_nat_gateway"],
            applies_if={"enable_nat_gateway": ["true"]},
            category="network",
        )
    )
    graph.add(
        Requirement(
            key="enable_dns_hostnames",
            target_field="enable_dns_hostnames",
            target_type="bool",
            label="DNS Hostnames",
            question="Enable DNS hostnames in the VPC?",
            options=["true", "false"],
            default="true",
            category="network",
        )
    )
    return graph


_CONTRACT = TargetContract(
    name="terraform-aws-vpc-module",
    kind="terraform-module",
    source_url="https://registry.terraform.io/modules/terraform-aws-modules/vpc/aws",
    required_decisions=[
        "vpc_name",
        "cidr",
        "public_subnet_cidrs",
        "private_subnet_cidrs",
    ],
    artifacts=[
        ArtifactContract(
            name="decision-report.yaml",
            required_paths=[
                "vpc.name",
                "vpc.region",
                "vpc.cidr",
                "vpc.publicSubnetCidrs[]",
                "vpc.privateSubnetCidrs[]",
            ],
        ),
        ArtifactContract(
            name="module-inputs.yaml",
            required_paths=[
                "moduleInputs[]",
                "moduleInputs[].moduleName",
                "moduleInputs[].variables.name",
                "moduleInputs[].variables.cidr",
                "moduleInputs[].variables.public_subnets[]",
                "moduleInputs[].variables.private_subnets[]",
            ],
        ),
        ArtifactContract(
            name="terraform.tfvars",
            required=False,
            description="Reference Terraform variable file generated from module inputs.",
        ),
    ],
    lineage=[
        DecisionLineage(
            decision="vpc_name",
            artifact="decision-report.yaml",
            path="vpc.name",
        ),
        DecisionLineage(
            decision="cidr",
            artifact="decision-report.yaml",
            path="vpc.cidr",
        ),
        DecisionLineage(
            decision="public_subnet_cidrs",
            artifact="decision-report.yaml",
            path="vpc.publicSubnetCidrs",
        ),
        DecisionLineage(
            decision="private_subnet_cidrs",
            artifact="decision-report.yaml",
            path="vpc.privateSubnetCidrs",
        ),
    ],
)


def _validate_intent(intent: Any) -> list[Violation]:
    model = _intent(intent)
    if model is None:
        return []
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
    if model is None:
        return []
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
    readiness = getattr(intent, "handoff_readiness", None)
    if readiness is None:
        readiness = getattr(intent, "deployment_readiness", {})
    model = _intent(intent)
    if model is None:
        return
    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
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
    }
    if readiness:
        data["handoffReadiness"] = readiness
        # Backward-compatible alias for existing artifact consumers.
        data["deploymentReadiness"] = readiness
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "decision-report.yaml", "w") as file:
        yaml.dump(data, file)


SECTION_MAP: dict[str, tuple[str, str | None]] = {
    "vpc_name": ("VPC Module", "vpc_name"),
    "primary_region": ("VPC Module", "primary_region"),
    "cidr": ("VPC Module", "cidr"),
    "az_count": ("VPC Module", "az_count"),
    "public_subnet_cidrs": ("Subnets", "public_subnet_cidrs"),
    "private_subnet_cidrs": ("Subnets", "private_subnet_cidrs"),
    "enable_nat_gateway": ("Egress", "enable_nat_gateway"),
    "single_nat_gateway": ("Egress", "single_nat_gateway"),
    "enable_dns_hostnames": ("DNS", "enable_dns_hostnames"),
}

GLOBAL_CONTRACT_REGISTRY.register(_CONTRACT)
register_module_mapper("terraform-vpc", map_terraform_vpc_modules)
register_generator(
    "terraform-vpc-decision-report",
    gen_decision_report,
    priority=10,
    category="network",
    applies_to={"terraform-vpc"},
)
GLOBAL_REGISTRY.register(
    Pattern(
        name="terraform-vpc",
        description="Bring-your-own Terraform AWS VPC module input capture",
        graph_factory=_graph_factory,
        intent_factory=TerraformVpcIntent,
        section_map=SECTION_MAP,
        section_order=["VPC Module", "Subnets", "Egress", "DNS"],
        prompt_context=(
            "This pattern gathers handoff inputs for an existing approved Terraform AWS "
            "VPC module. Extract exact module variables such as CIDR, subnets, NAT "
            "settings, and DNS flags only. Do not generate root Terraform scaffolding "
            "from prose."
        ),
        validators=[_validate_intent],
        contracts=[_CONTRACT],
    )
)

GLOBAL_SAMPLE_REGISTRY.register(
    SampleConfig(
        name="terraform-vpc-basic-v1",
        pattern="terraform-vpc",
        description="Two-AZ private/public subnet VPC for Terraform AWS VPC module handoff",
        version="1.0.0",
        release_date="2026-05-28",
        source_url="https://registry.terraform.io/modules/terraform-aws-modules/vpc/aws",
        source_contract="terraform-aws-vpc-module",
        upstream_variant="two-az-public-private",
        tags=["byom", "terraform", "vpc"],
        decisions={
            "vpc_name": "orders-vpc",
            "primary_region": "eu-central-1",
            "cidr": "10.30.0.0/16",
            "az_count": "2",
            "public_subnet_cidrs": "10.30.0.0/24,10.30.1.0/24",
            "private_subnet_cidrs": "10.30.10.0/24,10.30.11.0/24",
            "enable_nat_gateway": "true",
            "single_nat_gateway": "false",
            "enable_dns_hostnames": "true",
        },
        module_refs=[
            ModuleRef(
                module_name="terraform-aws-vpc",
                source="terraform-aws-modules/vpc/aws",
                version="~> 5.0",
                description="Community Terraform VPC module fed by intent-engine decisions.",
            )
        ],
    )
)
