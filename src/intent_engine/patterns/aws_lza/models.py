"""AWS LZA thin-path intent models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class LzaBaseline(StrEnum):
    """Known AWS LZA starting points."""

    STANDARD = "standard"
    UNIVERSAL = "universal"
    HEALTHCARE = "healthcare"
    EDUCATION = "education"
    GOVCLOUD = "govcloud"


class LzaOrgMode(StrEnum):
    """Organization bootstrap mode."""

    CONTROL_TOWER = "control-tower"
    RAW_ORGS = "raw-orgs"


class LzaTopology(StrEnum):
    """Landing-zone network topology."""

    SINGLE_VPC = "single-vpc"
    HUB_SPOKE = "hub-spoke"


class ComplianceOverlay(StrEnum):
    """Compliance overlay requested for LZA configuration."""

    NONE = "none"
    REGULATED = "regulated"
    FINANCIAL = "financial-services"
    HEALTHCARE = "healthcare"
    EDUCATION = "education"


class AwsLzaIntent(BaseModel):
    """Thin AWS LZA handoff intent.

    The model captures decisions needed to select and parameterize existing
    AWS LZA sample configurations. Deployment remains owned by AWS LZA.
    """

    baseline: LzaBaseline = LzaBaseline.STANDARD
    org_mode: LzaOrgMode = LzaOrgMode.CONTROL_TOWER
    organization_name: str = "ExampleCorp"
    home_region: str = "eu-central-1"
    enabled_regions: list[str] = Field(default_factory=lambda: ["eu-central-1"])
    organizational_units: list[str] = Field(
        default_factory=lambda: ["Security", "Infrastructure", "Workloads"]
    )
    workload_accounts: list[str] = Field(default_factory=lambda: ["Prod"])
    audit_account: str = "Audit"
    log_archive_account: str = "LogArchive"
    security_tooling_account: str = "SecurityTooling"
    network_account: str = ""
    identity_center_delegated_admin_account: str = "SecurityTooling"
    topology: LzaTopology = LzaTopology.HUB_SPOKE
    network_cidr: str = "10.0.0.0/16"
    centralized_logging: bool = True
    security_hub_enabled: bool = True
    guardduty_enabled: bool = True
    compliance_overlay: ComplianceOverlay = ComplianceOverlay.NONE
