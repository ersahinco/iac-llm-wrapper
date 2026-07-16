"""Registered reference bundle metadata for Terraform VPC handoff."""

from intent_engine.core.sample_config import ModuleRef, SampleConfig

SAMPLES = [
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
            "az_count": 2,
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
                version="6.6.1",
                description="Community Terraform VPC module fed by intent-engine decisions.",
            )
        ],
    )
]
