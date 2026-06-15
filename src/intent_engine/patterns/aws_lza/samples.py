"""AWS LZA sample configuration registrations."""

from __future__ import annotations

from typing import Any

from intent_engine.core.sample_config import SampleConfig

from .utils import _LZA_CONTRACT

_AWS_LZA_SAMPLE_RELEASE_DATE = "2026-05-27"


def _aws_lza_sample(
    *,
    name: str,
    description: str,
    upstream_variant: str,
    tags: list[str],
    decisions: dict[str, Any],
) -> SampleConfig:
    return SampleConfig(
        name=name,
        pattern="aws-lza",
        description=description,
        version="1.0.0",
        release_date=_AWS_LZA_SAMPLE_RELEASE_DATE,
        source_url=_LZA_CONTRACT.source_url,
        source_contract=_LZA_CONTRACT.name,
        upstream_variant=upstream_variant,
        tags=tags,
        decisions=decisions,
    )


def aws_lza_samples() -> list[SampleConfig]:
    return [
        _aws_lza_sample(
            name="aws-lza-standard-v1",
            description=(
                "Commercial Control Tower baseline with hub-spoke networking and central logging."
            ),
            upstream_variant="standard",
            tags=["aws-lza", "standard", "control-tower", "hub-spoke"],
            decisions={
                "baseline": "standard",
                "org_mode": "control-tower",
                "home_region": "eu-central-1",
                "enabled_regions": ["eu-central-1"],
                "organizational_units": ["Security", "Infrastructure", "Workloads"],
                "workload_accounts": ["Prod"],
                "security_tooling_account": "SecurityTooling",
                "network_account": "Network",
                "identity_center_delegated_admin_account": "SecurityTooling",
                "identity_center_permission_sets": ["ReadOnlyAccess", "PowerUserAccess"],
                "identity_center_assignments": ["PlatformAdmins:PowerUserAccess:Management"],
                "topology": "hub-spoke",
                "centralized_logging": "true",
                "security_hub_enabled": "true",
                "guardduty_enabled": "true",
            },
        ),
        _aws_lza_sample(
            name="aws-lza-regulated-v1",
            description="Standard AWS LZA baseline plus regulated-industry security overlay.",
            upstream_variant="standard",
            tags=["aws-lza", "regulated", "security-hub", "nist"],
            decisions={
                "baseline": "standard",
                "org_mode": "control-tower",
                "home_region": "eu-central-1",
                "enabled_regions": ["eu-central-1", "eu-west-1"],
                "organizational_units": ["Security", "Infrastructure", "Workloads"],
                "workload_accounts": ["Prod"],
                "security_tooling_account": "SecurityTooling",
                "network_account": "Network",
                "identity_center_delegated_admin_account": "SecurityTooling",
                "identity_center_permission_sets": ["ReadOnlyAccess", "AuditAccess"],
                "identity_center_assignments": [
                    "SecurityAuditors:AuditAccess:Audit",
                    "PlatformAdmins:ReadOnlyAccess:Management",
                ],
                "topology": "hub-spoke",
                "centralized_logging": "true",
                "security_hub_enabled": "true",
                "guardduty_enabled": "true",
                "compliance_overlay": "regulated",
            },
        ),
        _aws_lza_sample(
            name="aws-lza-healthcare-v1",
            description=(
                "Healthcare AWS LZA sample path with healthcare baseline and PHI-focused overlay."
            ),
            upstream_variant="healthcare",
            tags=["aws-lza", "healthcare", "hipaa", "phi"],
            decisions={
                "baseline": "healthcare",
                "org_mode": "control-tower",
                "home_region": "eu-central-1",
                "enabled_regions": ["eu-central-1"],
                "organizational_units": ["Security", "Infrastructure", "Workloads"],
                "workload_accounts": ["ClinicalProd"],
                "security_tooling_account": "SecurityTooling",
                "network_account": "Network",
                "identity_center_delegated_admin_account": "SecurityTooling",
                "identity_center_permission_sets": ["ClinicalReadOnly", "SecurityAudit"],
                "identity_center_assignments": [
                    "ClinicalPlatform:ClinicalReadOnly:ClinicalProd",
                    "SecurityAuditors:SecurityAudit:Audit",
                ],
                "topology": "hub-spoke",
                "centralized_logging": "true",
                "security_hub_enabled": "true",
                "guardduty_enabled": "true",
                "compliance_overlay": "healthcare",
            },
        ),
    ]
