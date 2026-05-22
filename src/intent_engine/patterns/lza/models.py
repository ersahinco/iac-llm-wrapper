"""Pydantic models for the intent-engine-wrapper intent representation."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Topology(StrEnum):
    HUB_SPOKE = "hub-spoke"
    SINGLE_VPC = "single-vpc"


class CI_CDMode(StrEnum):
    PRIVATE = "private"
    PUBLIC = "public"


class NetworkMode(StrEnum):
    PRIVATE = "private"
    PUBLIC = "public"


class EgressInspection(StrEnum):
    REQUIRED = "required"
    NONE = "none"


class CICDPlatform(StrEnum):
    """Whether CI/CD runners are self-hosted or enterprise-managed."""

    SELF_HOSTED = "self-hosted"
    ENTERPRISE = "enterprise"


class CICDTool(StrEnum):
    """CI/CD tool/platform selection."""

    JENKINS = "jenkins"
    GITLAB_CI = "gitlab-ci"
    GITHUB_ACTIONS = "github-actions"
    CODEBUILD = "codebuild"
    CODEPIPELINE = "codepipeline"


class SecretProvider(StrEnum):
    """Secret management provider."""

    AWS_SECRETS_MANAGER = "aws-secrets-manager"
    HASHICORP_VAULT = "hashicorp-vault"
    CYBERARK = "cyberark"
    CUSTOM = "custom"


class ApplianceLicense(StrEnum):
    """Network appliance licensing model."""

    BYOL = "byol"
    SUBSCRIPTION = "subscription"
    MARKETPLACE = "marketplace"


class ApplianceHA(StrEnum):
    """Network appliance high-availability mode."""

    NONE = "none"
    ACTIVE_PASSIVE = "active-passive"
    ACTIVE_ACTIVE = "active-active"
    CLUSTER = "cluster"


class OU(BaseModel):
    name: str
    description: str = ""


class Account(BaseModel):
    name: str
    ou: str
    description: str = ""


class NetworkConfig(BaseModel):
    topology: Topology = Topology.SINGLE_VPC
    cidr: str = "10.0.0.0/16"
    central_network_account: str | None = None
    hub_cidr: str | None = None
    spoke_cidrs: dict[str, str] = Field(default_factory=dict)


class SecurityConfig(BaseModel):
    audit_retention_days: int = 2555
    kms_rotation_required: bool = True
    s3_block_public_access: bool = True
    cloudtrail_org_trail: bool = True
    centralized_logging: bool = False
    egress_inspection: EgressInspection = EgressInspection.NONE
    inspection_pattern: str | None = None
    inspection_vendor: str | None = None


class HybridConfig(BaseModel):
    required: bool = False
    dns_model: str | None = None
    on_prem_cidrs: list[str] = Field(default_factory=list)
    ip_model: str | None = None


class NetworkApplianceConfig(BaseModel):
    """Network firewall/NVA appliance settings."""

    vendor: str = "aws-network-firewall"
    license_type: ApplianceLicense = ApplianceLicense.MARKETPLACE
    ha_mode: ApplianceHA = ApplianceHA.ACTIVE_PASSIVE
    instance_type: str = ""


class CICDRunnerConfig(BaseModel):
    """CI/CD runner platform and tool selection."""

    platform: CICDPlatform = CICDPlatform.ENTERPRISE
    tool: CICDTool = CICDTool.CODEPIPELINE
    placement: str = ""
    ephemeral: bool = True


class SecretManagementConfig(BaseModel):
    """Secret management provider and rotation policy."""

    provider: SecretProvider = SecretProvider.AWS_SECRETS_MANAGER
    rotation_days: int = 90
    backup_enabled: bool = True
    backup_location: str = ""


class CICDConfig(BaseModel):
    mode: CI_CDMode = CI_CDMode.PUBLIC
    placement: str | None = None
    vpc_endpoints: list[str] = Field(default_factory=list)
    runner: CICDRunnerConfig = Field(default_factory=CICDRunnerConfig)


class Workload(BaseModel):
    name: str
    target_account: str | None = None
    network_mode: NetworkMode = NetworkMode.PRIVATE
    runtime: str = "ecs-fargate"
    public_ingress: bool = False
    port: int = 8080
    cpu: int = 256
    memory: int = 512


class RawIntent(BaseModel):
    """Intermediate representation extracted from Markdown."""

    primary_region: str = "eu-central-1"
    topology: Topology | None = None
    ous: list[OU] = Field(default_factory=list)
    accounts: list[Account] = Field(default_factory=list)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    hybrid: HybridConfig = Field(default_factory=HybridConfig)
    cicd: CICDConfig = Field(default_factory=CICDConfig)
    workloads: list[Workload] = Field(default_factory=list)
    network_appliance: NetworkApplianceConfig = Field(default_factory=NetworkApplianceConfig)
    secret_management: SecretManagementConfig = Field(default_factory=SecretManagementConfig)
