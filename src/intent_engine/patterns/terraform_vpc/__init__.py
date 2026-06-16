"""Bring-your-own Terraform VPC module pattern.

This is intentionally small: a data model, graph, contract, mapper, and one
decision-report generator. It proves custom IaC modules can be driven by the
same intent-engine flow without core framework edits.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from intent_engine.core.contracts import (
    ArtifactContract,
    DecisionLineage,
    TargetContract,
)
from intent_engine.core.generator import gen_tfvars
from intent_engine.core.module_mapping import ModuleInputs
from intent_engine.core.patterns import GLOBAL_REGISTRY, Pattern, PatternGenerator
from intent_engine.core.policy import (
    PolicyCheckRef,
    PolicyControl,
    PolicyPack,
    PolicyRequirementMapping,
)
from intent_engine.core.requirements import Requirement, RequirementGraph
from intent_engine.core.sample_config import ModuleRef, SampleConfig
from intent_engine.core.validator import Violation
from intent_engine.core.yaml_utils import write_yaml_artifact

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
    graph.add(
        Requirement(
            key="target_account_id",
            target_field="target_account_id",
            target_type="string",
            label="Target Account ID",
            question="Which existing AWS account ID should receive this VPC handoff?",
            category="delivery",
            required_when_applicable=True,
            violation_code="TERRAFORM_VPC_TARGET_ACCOUNT_REQUIRED",
            violation_message=(
                "Terraform VPC handoff requires the existing target AWS account ID."
            ),
        )
    )
    graph.add(
        Requirement(
            key="deployment_pipeline_ref",
            target_field="deployment_pipeline_ref",
            target_type="string",
            label="Deployment Pipeline Reference",
            question="Which owner-controlled deployment pipeline will consume these inputs?",
            category="delivery",
            required_when_applicable=True,
            violation_code="TERRAFORM_VPC_PIPELINE_REQUIRED",
            violation_message=(
                "Terraform VPC handoff requires an owner-controlled deployment pipeline reference."
            ),
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
        "target_account_id",
        "deployment_pipeline_ref",
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
                "delivery.targetAccountId",
                "delivery.deploymentPipelineRef",
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
        DecisionLineage(
            decision="target_account_id",
            artifact="decision-report.yaml",
            path="delivery.targetAccountId",
        ),
        DecisionLineage(
            decision="deployment_pipeline_ref",
            artifact="decision-report.yaml",
            path="delivery.deploymentPipelineRef",
        ),
    ],
)

_REGULATED_VPC_POLICY_PACK = PolicyPack(
    name="regulated-vpc-baseline-v1",
    version="1.0.0",
    description=(
        "Baseline regulated-environment policy mappings for existing-account Terraform "
        "AWS VPC module handoff."
    ),
    frameworks=["SOC2", "PCI", "HIPAA", "NIST", "CUSTOM_CLIENT"],
    controls=[
        PolicyControl(
            id="VPC-DELIVERY-001",
            title="Owner-controlled account and pipeline routing is declared",
            description=(
                "The handoff must identify the existing target account and the owner "
                "pipeline that consumes reviewed module inputs."
            ),
            frameworks=["SOC2", "NIST", "CUSTOM_CLIENT"],
            mapping=PolicyRequirementMapping(
                requirement_keys=["target_account_id", "deployment_pipeline_ref"],
                target_contracts=["terraform-aws-vpc-module"],
                artifact_paths=[
                    "decision-report.yaml:delivery.targetAccountId",
                    "decision-report.yaml:delivery.deploymentPipelineRef",
                ],
                owner_policy_refs=["owner://pipeline-routing-required"],
            ),
        ),
        PolicyControl(
            id="VPC-NETWORK-001",
            title="VPC and subnet CIDR plan is explicit",
            description=(
                "Network ranges must be reviewable before the owner pipeline deploys "
                "the approved Terraform module."
            ),
            frameworks=["SOC2", "PCI", "HIPAA", "NIST"],
            mapping=PolicyRequirementMapping(
                requirement_keys=["cidr", "public_subnet_cidrs", "private_subnet_cidrs"],
                target_contracts=["terraform-aws-vpc-module"],
                artifact_paths=[
                    "decision-report.yaml:vpc.cidr",
                    "decision-report.yaml:vpc.publicSubnetCidrs",
                    "decision-report.yaml:vpc.privateSubnetCidrs",
                    "module-inputs.yaml:moduleInputs[].variables.cidr",
                    "module-inputs.yaml:moduleInputs[].variables.public_subnets",
                    "module-inputs.yaml:moduleInputs[].variables.private_subnets",
                ],
                module_variables=["cidr", "public_subnets", "private_subnets"],
                checkov_check_ids=["CKV_CUSTOM_VPC_001"],
                owner_policy_refs=["owner://network-cidr-allocation"],
            ),
            checks=[
                PolicyCheckRef(
                    check_id="CKV_CUSTOM_VPC_001",
                    name="Client VPC CIDR and subnet allocation policy",
                    source="owner-custom",
                    description=(
                        "Owner-provided Checkov custom policy for approved VPC and subnet ranges."
                    ),
                )
            ],
        ),
        PolicyControl(
            id="VPC-EGRESS-001",
            title="NAT mode is intentional and reviewable",
            frameworks=["PCI", "HIPAA", "NIST"],
            mapping=PolicyRequirementMapping(
                requirement_keys=["enable_nat_gateway", "single_nat_gateway"],
                target_contracts=["terraform-aws-vpc-module"],
                artifact_paths=[
                    "decision-report.yaml:vpc.enableNatGateway",
                    "decision-report.yaml:vpc.singleNatGateway",
                    "module-inputs.yaml:moduleInputs[].variables.enable_nat_gateway",
                    "module-inputs.yaml:moduleInputs[].variables.single_nat_gateway",
                ],
                module_variables=["enable_nat_gateway", "single_nat_gateway"],
                owner_policy_refs=["owner://egress-architecture-review"],
            ),
        ),
        PolicyControl(
            id="VPC-DNS-001",
            title="DNS hostname behavior is declared",
            frameworks=["SOC2", "HIPAA", "NIST"],
            mapping=PolicyRequirementMapping(
                requirement_keys=["enable_dns_hostnames"],
                target_contracts=["terraform-aws-vpc-module"],
                artifact_paths=[
                    "decision-report.yaml:vpc.enableDnsHostnames",
                    "module-inputs.yaml:moduleInputs[].variables.enable_dns_hostnames",
                ],
                module_variables=["enable_dns_hostnames"],
                owner_policy_refs=["owner://dns-platform-baseline"],
            ),
        ),
        PolicyControl(
            id="VPC-ATTACHMENT-001",
            title="Cross-resource VPC attachment checks remain owner-policy references",
            description=(
                "Cross-resource checks such as security-group-to-VPC attachment are "
                "represented as policy references unless the pattern owns the resource "
                "relationship model."
            ),
            frameworks=["PCI", "HIPAA", "NIST", "CUSTOM_CLIENT"],
            mapping=PolicyRequirementMapping(
                requirement_keys=["vpc_name", "cidr"],
                target_contracts=["terraform-aws-vpc-module"],
                artifact_paths=["decision-report.yaml:vpc.name", "decision-report.yaml:vpc.cidr"],
                module_variables=["name", "cidr"],
                checkov_check_ids=["CKV_CUSTOM_VPC_ATTACHMENT_001"],
                owner_policy_refs=["owner://vpc-attachment-cross-resource-check"],
            ),
            checks=[
                PolicyCheckRef(
                    check_id="CKV_CUSTOM_VPC_ATTACHMENT_001",
                    name="Client VPC attachment cross-resource policy",
                    source="owner-custom",
                    description=(
                        "Owner-provided custom Checkov policy for relationships such as "
                        "security group attachment to the intended VPC."
                    ),
                )
            ],
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
    readiness = getattr(intent, "handoff_readiness", {})
    model = _intent(intent)
    if model is None:
        return
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
    "target_account_id": ("Delivery", "target_account_id"),
    "deployment_pipeline_ref": ("Delivery", "deployment_pipeline_ref"),
}

GLOBAL_REGISTRY.register(
    Pattern(
        name="terraform-vpc",
        description="Bring-your-own Terraform AWS VPC module input capture",
        graph_factory=_graph_factory,
        intent_factory=TerraformVpcIntent,
        section_map=SECTION_MAP,
        section_order=["VPC Module", "Subnets", "Egress", "DNS", "Delivery"],
        prompt_context=(
            "This pattern gathers handoff inputs for an existing approved Terraform AWS "
            "VPC module. Extract exact module variables such as CIDR, subnets, NAT "
            "settings, and DNS flags, plus the existing target AWS account ID and "
            "owner-controlled deployment pipeline reference. Do not generate root "
            "Terraform scaffolding from prose."
        ),
        module_mapper=map_terraform_vpc_modules,
        generators=[
            PatternGenerator("terraform-tfvars", gen_tfvars, priority=5),
            PatternGenerator("terraform-vpc-decision-report", gen_decision_report, priority=10),
        ],
        validators=[_validate_intent],
        contracts=[_CONTRACT],
        policy_packs=[_REGULATED_VPC_POLICY_PACK],
        samples=[
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
                    "target_account_id": "111122223333",
                    "deployment_pipeline_ref": "github://platform-networking/vpc-deploy",
                },
                module_refs=[
                    ModuleRef(
                        module_name="terraform-aws-vpc",
                        source="terraform-aws-modules/vpc/aws",
                        version="~> 5.0",
                        description=(
                            "Community Terraform VPC module fed by intent-engine decisions."
                        ),
                    )
                ],
            )
        ],
    )
)
