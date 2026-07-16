"""Requirement graph for Terraform VPC module handoff."""

from intent_engine.core.requirements import Requirement, RequirementGraph


def build_graph() -> RequirementGraph:
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
