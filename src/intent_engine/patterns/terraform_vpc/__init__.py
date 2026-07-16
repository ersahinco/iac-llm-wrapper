"""Bring-your-own Terraform VPC module pattern registration."""

from intent_engine.core.generator import gen_tfvars
from intent_engine.core.patterns import GLOBAL_REGISTRY, Pattern, PatternGenerator

from .atmos import gen_atmos_handoff
from .contracts import ATMOS_CONTRACT, CONTRACT, POLICY_PACK
from .evidence import load_review_evidence
from .generators import gen_decision_report, map_terraform_vpc_modules, validate_intent
from .graph import build_graph
from .models import TerraformVpcIntent
from .samples import SAMPLES
from .target import (
    build_target_report,
    enrich_handoff_readiness,
    gen_plan_manifest,
    gen_requirement_graph,
    gen_target_capability_graph,
)

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
        description=(
            "Approved Terraform AWS VPC module input capture and requirement-to-plan conformance"
        ),
        graph_factory=build_graph,
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
        target_report_builder=build_target_report,
        generators=[
            PatternGenerator(
                "terraform-vpc-target-capability-graph",
                gen_target_capability_graph,
                priority=5,
            ),
            PatternGenerator(
                "terraform-vpc-requirement-graph",
                gen_requirement_graph,
                priority=5,
            ),
            PatternGenerator("terraform-tfvars", gen_tfvars, priority=5),
            PatternGenerator("terraform-vpc-decision-report", gen_decision_report, priority=10),
            PatternGenerator("terraform-vpc-atmos-handoff", gen_atmos_handoff, priority=20),
            PatternGenerator("terraform-vpc-plan-manifest", gen_plan_manifest, priority=29),
        ],
        validators=[validate_intent],
        contracts=[CONTRACT, ATMOS_CONTRACT],
        policy_packs=[POLICY_PACK],
        readiness_enricher=enrich_handoff_readiness,
        review_evidence_loader=load_review_evidence,
        artifact_review_owners={
            "module-inputs.yaml": "network-platform-owner",
            "plan-manifest.yaml": "network-platform-owner",
            "atmos/stacks/catalog/terraform-vpc-intent.yaml": "network-platform-owner",
            "atmos/components/terraform/terraform-vpc/main.tf": "network-platform-owner",
            "atmos/components/terraform/terraform-vpc/variables.tf": "network-platform-owner",
            "atmos/components/terraform/terraform-vpc/.terraform.lock.hcl": (
                "network-platform-owner"
            ),
        },
        reconfirmation_categories=("network",),
        samples=SAMPLES,
        plan_ready=True,
    )
)

__all__ = ["gen_decision_report", "map_terraform_vpc_modules"]
