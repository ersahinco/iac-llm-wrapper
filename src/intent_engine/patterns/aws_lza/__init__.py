"""AWS LZA handoff pattern registration."""

from __future__ import annotations

from intent_engine.core.generator import register_generator
from intent_engine.core.patterns import GLOBAL_REGISTRY, Pattern

from .contracts import AWS_LZA_SAMPLE_CONFIG_CONTRACT
from .generators import (
    gen_lza_accounts_config,
    gen_lza_decision_report,
    gen_lza_deployment_runbook,
    gen_lza_global_config,
    gen_lza_iam_config,
    gen_lza_lineage_manifest,
    gen_lza_network_config,
    gen_lza_organization_config,
    gen_lza_security_config,
)
from .graph import build_aws_lza_graph
from .models import AwsLzaIntent
from .samples import register_aws_lza_samples
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
    "identity_center_delegated_admin_account": (
        "Identity",
        "identity_center_delegated_admin_account",
    ),
    "identity_center_permission_sets": ("Identity", "identity_center_permission_sets"),
    "identity_center_assignments": ("Identity", "identity_center_assignments"),
    "topology": ("Network", "topology"),
    "network_cidr": ("Network", "network_cidr"),
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

_AWS_LZA_GENERATOR_SCOPE = {"aws-lza"}


def _register_generators() -> None:
    register_generator(
        "aws-lza-organization",
        gen_lza_organization_config,
        priority=20,
        applies_to=_AWS_LZA_GENERATOR_SCOPE,
    )
    register_generator(
        "aws-lza-accounts",
        gen_lza_accounts_config,
        priority=21,
        applies_to=_AWS_LZA_GENERATOR_SCOPE,
    )
    register_generator(
        "aws-lza-global",
        gen_lza_global_config,
        priority=22,
        applies_to=_AWS_LZA_GENERATOR_SCOPE,
    )
    register_generator(
        "aws-lza-security",
        gen_lza_security_config,
        priority=23,
        applies_to=_AWS_LZA_GENERATOR_SCOPE,
    )
    register_generator(
        "aws-lza-iam",
        gen_lza_iam_config,
        priority=24,
        applies_to=_AWS_LZA_GENERATOR_SCOPE,
    )
    register_generator(
        "aws-lza-network",
        gen_lza_network_config,
        priority=25,
        applies_to=_AWS_LZA_GENERATOR_SCOPE,
    )
    register_generator(
        "aws-lza-decision-report",
        gen_lza_decision_report,
        priority=26,
        applies_to=_AWS_LZA_GENERATOR_SCOPE,
    )
    register_generator(
        "aws-lza-lineage",
        gen_lza_lineage_manifest,
        priority=27,
        applies_to=_AWS_LZA_GENERATOR_SCOPE,
    )
    register_generator(
        "aws-lza-runbook",
        gen_lza_deployment_runbook,
        priority=28,
        applies_to=_AWS_LZA_GENERATOR_SCOPE,
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
            prompt_context=(
                "This pattern gathers decisions for AWS Landing Zone Accelerator. "
                "Use AWS LZA sample configurations as the downstream deployment contract. "
                "Extract only decisions needed for LZA configuration and handoff; do not "
                "infer custom Terraform unless explicitly requested."
            ),
            contracts=[AWS_LZA_SAMPLE_CONFIG_CONTRACT],
        )
    )


_register_generators()
_register_pattern()
register_aws_lza_samples()
