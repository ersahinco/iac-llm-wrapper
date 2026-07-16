"""Code-owned observation and provenance specification for Terraform VPC plans."""

from __future__ import annotations

import hashlib
import json

from intent_engine.core.replay import contract_digest

from .contracts import CONTRACT, POLICY_PACK
from .target import MODULE_SOURCE, MODULE_VARIABLES, PROVIDER_SOURCE

REQUIREMENT_SET_ID = "terraform-vpc/requirements/v1"
CONFORMANCE_SPEC_ID = "terraform-vpc/plan-conformance/v2"
LEGACY_CONFORMANCE_SPEC_ID = "terraform-vpc/plan-conformance/v1"
REQUIREMENT_KEYS = (
    "vpc_name",
    "primary_region",
    "cidr",
    "az_count",
    "public_subnet_cidrs",
    "private_subnet_cidrs",
    "enable_nat_gateway",
    "single_nat_gateway",
    "enable_dns_hostnames",
    "target_account_id",
    "deployment_pipeline_ref",
)
CONTROL_IDS = (
    "VPC-DELIVERY-001",
    "VPC-NETWORK-001",
    "VPC-EGRESS-001",
    "VPC-DNS-001",
    "VPC-ATTACHMENT-001",
)
REQUIREMENT_SPEC = {
    "vpc_name": ("name", "aws_vpc.tags.Name"),
    "primary_region": ("region", "provider reference", "VPC region", "subnet AZ set"),
    "cidr": ("cidr", "aws_vpc.cidr_block"),
    "az_count": ("azs", "public/private subnet counts"),
    "public_subnet_cidrs": ("public_subnets", "public subnet CIDR set"),
    "private_subnet_cidrs": ("private_subnets", "private subnet CIDR set"),
    "enable_nat_gateway": ("enable_nat_gateway", "NAT gateway count"),
    "single_nat_gateway": ("single_nat_gateway", "NAT gateway count"),
    "enable_dns_hostnames": ("enable_dns_hostnames", "aws_vpc.enable_dns_hostnames"),
    "target_account_id": ("delivery.targetAccountId", "aws_caller_identity output"),
    "deployment_pipeline_ref": ("delivery.deploymentPipelineRef", "immutable input"),
}
CONTROL_SPEC = {
    "VPC-DELIVERY-001": ("target_account_id", "deployment_pipeline_ref"),
    "VPC-NETWORK-001": ("cidr", "public_subnet_cidrs", "private_subnet_cidrs"),
    "VPC-EGRESS-001": ("enable_nat_gateway", "single_nat_gateway"),
    "VPC-DNS-001": ("enable_dns_hostnames",),
    "VPC-ATTACHMENT-001": ("vpc_name", "cidr"),
}
RESOURCE_FAMILIES = {
    "vpc": (
        ("vpc_name", "primary_region", "cidr", "enable_dns_hostnames"),
        ("VPC-NETWORK-001", "VPC-DNS-001", "VPC-ATTACHMENT-001"),
    ),
    "public-network": (
        ("cidr", "primary_region", "az_count", "public_subnet_cidrs"),
        ("VPC-NETWORK-001",),
    ),
    "private-network": (
        ("cidr", "primary_region", "az_count", "private_subnet_cidrs"),
        ("VPC-NETWORK-001",),
    ),
    "egress": (
        ("enable_nat_gateway", "single_nat_gateway"),
        ("VPC-EGRESS-001",),
    ),
    "attachment": (("vpc_name", "cidr"), ("VPC-ATTACHMENT-001",)),
}
RESOURCE_RULES = (
    ("module.vpc.aws_subnet.public[", "aws_subnet", "public-network"),
    ("module.vpc.aws_route_table.public[", "aws_route_table", "public-network"),
    ("module.vpc.aws_route.public_internet_gateway[", "aws_route", "public-network"),
    (
        "module.vpc.aws_route_table_association.public[",
        "aws_route_table_association",
        "public-network",
    ),
    ("module.vpc.aws_internet_gateway.this[", "aws_internet_gateway", "public-network"),
    ("module.vpc.aws_subnet.private[", "aws_subnet", "private-network"),
    ("module.vpc.aws_route_table.private[", "aws_route_table", "private-network"),
    (
        "module.vpc.aws_route_table_association.private[",
        "aws_route_table_association",
        "private-network",
    ),
    ("module.vpc.aws_eip.nat[", "aws_eip", "egress"),
    ("module.vpc.aws_nat_gateway.this[", "aws_nat_gateway", "egress"),
    ("module.vpc.aws_route.private_nat_gateway[", "aws_route", "egress"),
    ("module.vpc.aws_default_security_group.this[", "aws_default_security_group", "attachment"),
    ("module.vpc.aws_default_network_acl.this[", "aws_default_network_acl", "attachment"),
    ("module.vpc.aws_default_route_table.default[", "aws_default_route_table", "attachment"),
)
ROOT_VARIABLES = {"region", *MODULE_VARIABLES}
VARIABLE_REQUIREMENT = {
    "region": "primary_region",
    "name": "vpc_name",
    "cidr": "cidr",
    "public_subnets": "public_subnet_cidrs",
    "private_subnets": "private_subnet_cidrs",
    "enable_nat_gateway": "enable_nat_gateway",
    "single_nat_gateway": "single_nat_gateway",
    "enable_dns_hostnames": "enable_dns_hostnames",
}


def conformance_spec_digest() -> str:
    """Return the canonical identity of the code-owned observation specification."""
    payload = {
        "id": CONFORMANCE_SPEC_ID,
        "requirements": REQUIREMENT_SPEC,
        "controls": CONTROL_SPEC,
        "resourceFamilies": RESOURCE_FAMILIES,
        "resourceRules": RESOURCE_RULES,
        "rootDataSource": "data.aws_caller_identity.current",
        "resourceProvider": f"registry.terraform.io/{PROVIDER_SOURCE}",
        "module": MODULE_SOURCE,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def requirement_id(key: str) -> str:
    return f"{REQUIREMENT_SET_ID}/{key}"


def conformance_identities(identities: dict[str, str]) -> dict[str, str]:
    """Add code-owned contract and policy identities to artifact identities."""
    policy = json.dumps(
        POLICY_PACK.model_dump(by_alias=True), sort_keys=True, separators=(",", ":")
    )
    return {
        **identities,
        "targetContractSha256": contract_digest(CONTRACT),
        "policyPackSha256": hashlib.sha256(policy.encode()).hexdigest(),
    }
