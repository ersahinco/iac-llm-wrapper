"""AWS LZA handoff pattern registration."""

from __future__ import annotations

from typing import Any

from intent_engine.core.patterns import GLOBAL_REGISTRY, Pattern, PatternGenerator

from .contracts import AWS_LZA_SAMPLE_CONFIG_CONTRACT
from .entities import apply_llm_entities, extract_markdown_entities, merge_markdown_entities
from .generators import (
    enrich_lza_handoff_readiness,
    gen_lza_accounts_config,
    gen_lza_decision_report,
    gen_lza_deployment_runbook,
    gen_lza_global_config,
    gen_lza_iam_config,
    gen_lza_lineage_manifest,
    gen_lza_network_config,
    gen_lza_organization_config,
    gen_lza_plan_manifest,
    gen_lza_security_config,
    gen_lza_target_capability_graph,
)
from .graph import build_aws_lza_graph
from .models import AwsLzaIntent
from .review import load_lza_review_evidence
from .samples import aws_lza_samples
from .target_capabilities import (
    TargetCapability,
    TargetCapabilityType,
    UnsupportedRequest,
    build_target_capability_report,
)
from .validators import validate_aws_lza_intent

_AWS_LZA_SECTION_MAP: dict[str, tuple[str, str | None]] = {
    "baseline": ("LZA Baseline", "baseline"),
    "org_mode": ("Organization", "org_mode"),
    "organization_name": ("Organization", "organization_name"),
    "home_region": ("Regions", "home_region"),
    "enabled_regions": ("Regions", "enabled_regions"),
    "organizational_units": ("Organization", "organizational_units"),
    "workload_accounts": ("Accounts", "workload_accounts"),
    "audit_account": ("Accounts", "audit_account"),
    "log_archive_account": ("Accounts", "log_archive_account"),
    "security_tooling_account": ("Accounts", "security_tooling_account"),
    "network_account": ("Accounts", "network_account"),
    "account_emails": ("Accounts", "account_emails"),
    "identity_center_delegated_admin_account": (
        "Identity",
        "identity_center_delegated_admin_account",
    ),
    "identity_center_permission_sets": ("Identity", "identity_center_permission_sets"),
    "identity_center_assignments": ("Identity", "identity_center_assignments"),
    "topology": ("Network", "topology"),
    "network_cidr": ("Network", "network_cidr"),
    "core_route_tables": ("Network", "core_route_tables"),
    "core_subnets": ("Network", "core_subnets"),
    "core_nat_gateways": ("Network", "core_nat_gateways"),
    "tgw_route_tables": ("Network", "tgw_route_tables"),
    "tgw_routes": ("Network", "tgw_routes"),
    "tgw_attachments": ("Network", "tgw_attachments"),
    "centralized_logging": ("Security", "centralized_logging"),
    "security_hub_enabled": ("Security", "security_hub_enabled"),
    "guardduty_enabled": ("Security", "guardduty_enabled"),
    "compliance_overlay": ("Security", "compliance_overlay"),
}

_AWS_LZA_SECTION_ORDER = [
    "LZA Baseline",
    "Organization",
    "Regions",
    "Accounts",
    "Identity",
    "Network",
    "Security",
]

_AWS_LZA_FREE_FORM_EXAMPLES = {
    "Regions": ["enabled_regions: eu-central-1, eu-west-1"],
    "Accounts": ["workload_accounts: Dev, Test, Prod"],
    "Identity": [
        "identity_center_delegated_admin_account: SecurityTooling",
        "identity_center_permission_sets: ReadOnlyAccess, PowerUserAccess",
        (
            "identity_center_assignments: PlatformAdmins:PowerUserAccess:Management, "
            "AppTeam:ReadOnlyAccess:Prod"
        ),
    ],
}

_AWS_LZA_TARGET_CAPABILITIES = [
    TargetCapability(
        key="aws-lza-sample-config",
        label="AWS LZA sample configuration",
        capability_type=TargetCapabilityType.ACCELERATOR,
        description=(
            "AWS Landing Zone Accelerator owns the downstream deployment engine; "
            "iac-llm-wrapper emits validated LZA YAML handoff artifacts only."
        ),
        handled_decisions=tuple(_AWS_LZA_SECTION_MAP.keys()),
        produced_artifacts=tuple(AWS_LZA_SAMPLE_CONFIG_CONTRACT.required_artifacts),
        required_decisions=(
            "baseline",
            "org_mode",
            "home_region",
            "enabled_regions",
            "identity_center_permission_sets",
            "identity_center_assignments",
        ),
        manual_gates=(
            "Review AWS LZA configuration against the selected upstream sample baseline.",
            "Validate generated YAML with the AWS LZA toolchain before pipeline execution.",
            "Approve account emails, IAM Identity Center assignments, and networking CIDRs.",
        ),
        unsupported_requests=(
            UnsupportedRequest(
                key="bespoke-workload-infrastructure",
                label="Bespoke workload infrastructure",
                keywords=(
                    "application stack",
                    "app stack",
                    "database",
                    "rds",
                    "dynamodb",
                    "eks",
                    "kubernetes",
                    "lambda",
                    "ec2",
                    "workload infrastructure",
                ),
                recommended_target=TargetCapabilityType.MODULE_COMPOSITION,
                reason=(
                    "AWS LZA establishes landing-zone foundations; workload resources need "
                    "an approved module-composition or generator target."
                ),
            ),
            UnsupportedRequest(
                key="custom-terraform-generation",
                label="Custom Terraform generation",
                keywords=(
                    "generate terraform",
                    "write terraform",
                    "create terraform",
                    "custom terraform",
                    "terragrunt",
                ),
                recommended_target=TargetCapabilityType.BLOCKED,
                reason=(
                    "The AWS LZA pattern does not allow arbitrary Terraform or Terragrunt "
                    "generation from prose."
                ),
            ),
        ),
    ),
    TargetCapability(
        key="approved-workload-modules",
        label="Approved workload modules",
        capability_type=TargetCapabilityType.MODULE_COMPOSITION,
        description=(
            "Separate approved modules can own workload-specific infrastructure after "
            "landing-zone readiness is reviewed."
        ),
        depends_on=("aws-lza-sample-config",),
        manual_gates=(
            "Select an approved workload module pattern before emitting module inputs.",
            "Keep workload module handoff separate from the AWS LZA baseline bundle.",
        ),
    ),
    TargetCapability(
        key="arbitrary-iac-generation",
        label="Arbitrary IaC generation",
        capability_type=TargetCapabilityType.BLOCKED,
        description=(
            "Free-form prose must not produce raw deployable IaC unless a registered "
            "target explicitly owns that generation path."
        ),
        depends_on=("aws-lza-sample-config",),
    ),
]

_AWS_LZA_GENERATORS = [
    PatternGenerator(
        "aws-lza-target-capability-graph",
        gen_lza_target_capability_graph,
        priority=5,
    ),
    PatternGenerator("aws-lza-organization", gen_lza_organization_config, priority=20),
    PatternGenerator("aws-lza-accounts", gen_lza_accounts_config, priority=21),
    PatternGenerator("aws-lza-global", gen_lza_global_config, priority=22),
    PatternGenerator("aws-lza-security", gen_lza_security_config, priority=23),
    PatternGenerator("aws-lza-iam", gen_lza_iam_config, priority=24),
    PatternGenerator("aws-lza-network", gen_lza_network_config, priority=25),
    PatternGenerator("aws-lza-decision-report", gen_lza_decision_report, priority=26),
    PatternGenerator("aws-lza-lineage", gen_lza_lineage_manifest, priority=27),
    PatternGenerator("aws-lza-runbook", gen_lza_deployment_runbook, priority=28),
    PatternGenerator("aws-lza-plan-manifest", gen_lza_plan_manifest, priority=29),
]


def _build_aws_lza_target_report(
    decisions: dict[str, Any],
    source_text: str,
) -> dict[str, Any]:
    return build_target_capability_report(
        list(_AWS_LZA_TARGET_CAPABILITIES),
        decisions,
        source_text,
    )


def _register_pattern() -> None:
    GLOBAL_REGISTRY.register(
        Pattern(
            name="aws-lza",
            description="Contract-backed AWS Landing Zone Accelerator handoff path",
            graph_factory=build_aws_lza_graph,
            intent_factory=AwsLzaIntent,
            validators=[validate_aws_lza_intent],
            section_map=dict(_AWS_LZA_SECTION_MAP),
            section_order=list(_AWS_LZA_SECTION_ORDER),
            free_form_examples=dict(_AWS_LZA_FREE_FORM_EXAMPLES),
            target_report_builder=_build_aws_lza_target_report,
            generators=list(_AWS_LZA_GENERATORS),
            prompt_context=(
                "This pattern gathers decisions for AWS Landing Zone Accelerator. "
                "Use AWS LZA sample configurations as the downstream deployment contract. "
                "Extract only decisions needed for LZA configuration and handoff; flag "
                "explicit custom Terraform requests as unsupported for this pattern. "
                "When the packet explicitly lists named entities, the JSON may also include "
                "top-level accounts as [{name, ou, description}] and ous as "
                "[{name, description}]. These are metadata, not requirement gaps."
            ),
            contracts=[AWS_LZA_SAMPLE_CONFIG_CONTRACT],
            samples=aws_lza_samples(),
            readiness_enricher=enrich_lza_handoff_readiness,
            markdown_entity_extractor=extract_markdown_entities,
            markdown_entity_applier=merge_markdown_entities,
            llm_entity_applier=apply_llm_entities,
            review_evidence_loader=load_lza_review_evidence,
            violation_requirement_map={
                "AWS_LZA_SECURITY_OU_REQUIRED": "organizational_units",
                "AWS_LZA_INFRASTRUCTURE_OU_REQUIRED": "organizational_units",
                "AWS_LZA_WORKLOADS_OU_REQUIRED": "organizational_units",
                "AWS_LZA_LOG_ARCHIVE_ACCOUNT_REQUIRED": "log_archive_account",
                "AWS_LZA_AUDIT_ACCOUNT_REQUIRED": "audit_account",
                "AWS_LZA_SECURITY_TOOLING_ACCOUNT_REQUIRED": "security_tooling_account",
                "AWS_LZA_IDENTITY_CENTER_ADMIN_UNKNOWN": (
                    "identity_center_delegated_admin_account"
                ),
                "AWS_LZA_IDENTITY_CENTER_ASSIGNMENT_FORMAT_INVALID": (
                    "identity_center_assignments"
                ),
                "AWS_LZA_IDENTITY_CENTER_ASSIGNMENT_PERMISSION_SET_UNKNOWN": (
                    "identity_center_assignments"
                ),
                "AWS_LZA_IDENTITY_CENTER_ASSIGNMENT_ACCOUNT_UNKNOWN": (
                    "identity_center_assignments"
                ),
                "AWS_LZA_HOME_REGION_NOT_ENABLED": "enabled_regions",
            },
            artifact_review_owners={
                "accounts-config.yaml": "platform-owner",
                "global-config.yaml": "platform-owner",
                "iam-config.yaml": "security-owner",
                "network-config.yaml": "network-owner",
                "organization-config.yaml": "platform-owner",
                "security-config.yaml": "security-owner",
            },
            reconfirmation_categories=(
                "accelerator",
                "accounts",
                "identity",
                "network",
                "organization",
                "security",
            ),
            reconfirmation_keys=(
                "baseline",
                "home_region",
                "enabled_regions",
                "identity_center_delegated_admin_account",
                "identity_center_permission_sets",
                "identity_center_assignments",
                "network_account",
                "network_cidr",
                "topology",
            ),
            forbidden_artifacts=("terraform.tfvars", "main.tf", "terragrunt.hcl"),
            plan_ready=True,
        )
    )


_register_pattern()
