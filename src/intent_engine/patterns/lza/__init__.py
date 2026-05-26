"""LZA-specific pattern registrations and addon definitions.

This module registers all LZA patterns, addons, and their associated
template metadata. It is imported for side effects by cli.py.
"""

from __future__ import annotations

from intent_engine.core.patterns import ADDON_REGISTRY, GLOBAL_REGISTRY, Addon, Pattern
from intent_engine.core.requirements import Requirement, RequirementGraph

# Import catalog for side-effect registration of builtin entries
from . import catalog as _lza_catalog  # noqa: F401
from .discovery import check_lza_legacy_consistency, detect_lza_legacy_signals
from .generators import (  # noqa: F401  — registers generators
    gen_accounts_config,
    gen_customizations_config,
    gen_decision_report,
    gen_deployment_graph,
    gen_global_config,
    gen_iam_config,
    gen_network_config,
    gen_organization_config,
    gen_security_config,
    gen_workload_skeleton,
    map_lza_intent_to_modules,
)
from .models import RawIntent
from .normalizer import normalize_lza
from .requirements import build_lza_baseline_graph, build_workload_account_graph
from .validators import validate_lza_artifacts, validate_lza_intent


def _baseline_graph_factory() -> RequirementGraph:
    return build_lza_baseline_graph()


def _workload_graph_factory() -> RequirementGraph:
    return build_workload_account_graph()


def _minimal_graph_factory() -> RequirementGraph:
    """Bare minimum: region, topology, network CIDR, audit retention."""
    g = RequirementGraph()
    g.add(
        Requirement(
            key="primary_region",
            target_field="primary_region",
            target_type="string",
            label="Primary Region",
            question="Which AWS region is the primary landing zone region?",
            default="eu-central-1",
            category="organization",
            hint="EU compliance default.",
        )
    )
    g.add(
        Requirement(
            key="topology",
            target_field="topology",
            target_type="Topology",
            label="Network Topology",
            question="What network topology do you want?",
            options=["hub-spoke", "single-vpc"],
            default="single-vpc",
            category="network",
            hint="Single-vpc for simplest start.",
        )
    )
    g.add(
        Requirement(
            key="network_cidr",
            target_field="network.cidr",
            target_type="string",
            label="Network CIDR",
            question="What is the VPC CIDR block?",
            default="10.0.0.0/16",
            category="network",
            hint="Private CIDR only.",
        )
    )
    g.add(
        Requirement(
            key="audit_retention_days",
            target_field="security.audit_retention_days",
            target_type="int",
            label="Audit Retention",
            question="How many days to retain audit logs?",
            default="2555",
            category="security",
            hint="2555 days (~7yr) for compliance.",
        )
    )
    return g


def _hybrid_enterprise_graph_factory() -> RequirementGraph:
    """Enterprise with hybrid: baseline + hybrid connectivity + extra security."""

    g = _baseline_graph_factory()
    # Already has hybrid fields from baseline, just override defaults/hints
    return g


def _financial_services_graph_factory() -> RequirementGraph:
    """Baseline + PCI-DSS, SOX, and financial services requirements."""
    g = _baseline_graph_factory()
    g = ADDON_REGISTRY.compose(g, ["pci-compliance"])
    return g


def _healthcare_graph_factory() -> RequirementGraph:
    """Baseline + HIPAA, PHI handling, and healthcare requirements."""
    g = _baseline_graph_factory()
    g = ADDON_REGISTRY.compose(g, ["hipaa"])
    return g


_BASELINE_SECTION_ORDER = [
    "Region",
    "Topology",
    "Organizational Units",
    "Accounts",
    "Network",
    "Security",
    "Hybrid Connectivity",
    "CI/CD",
    "Workloads",
]

_BASELINE_FREE_FORM_EXAMPLES: dict[str, list[str]] = {
    "Organizational Units": [
        "Security: Security team accounts and audit infrastructure",
        "Infrastructure: Shared networking and CI/CD accounts",
        "Workloads/Prod: Production workload accounts",
    ],
    "Accounts": [
        "Network: ou=Infrastructure, description=Central VPC management",
        "Audit: ou=Security, description=Centralized audit logging",
        "LogArchive: ou=Security, description=Immutable log storage",
    ],
    "Workloads": [
        "api: target_account=Prod, network_mode=private, port=8080, cpu=256, memory=512",
        "web: target_account=Prod, network_mode=public, port=443, cpu=512, memory=1024",
    ],
}

_BASELINE_SECTION_MAP: dict[str, tuple[str, str | None]] = {
    "primary_region": ("Region", "primary"),
    "topology": ("Topology", None),
    "network_cidr": ("Network", "cidr"),
    "hub_cidr": ("Network", "hub_cidr"),
    "central_network_account": ("Network", "central_network_account"),
    "network_segmentation": ("Network", "network_segmentation"),
    "audit_retention_days": ("Security", "audit_retention_days"),
    "centralized_logging": ("Security", "centralized_logging"),
    "egress_inspection": ("Security", "egress_inspection"),
    "inspection_pattern": ("Security", "inspection_pattern"),
    "inspection_vendor": ("Security", "inspection_vendor"),
    "data_residency": ("Security", "data_residency"),
    "encryption_key_management": ("Security", "encryption_key_management"),
    "phi_encryption": ("Security", "phi_encryption"),
    "audit_access_logging": ("Security", "audit_access_logging"),
    "business_associate_agreements": ("Security", "business_associate_agreements"),
    "cicd_mode": ("CI/CD", "mode"),
    "cicd_placement": ("CI/CD", "placement"),
    "hybrid_required": ("Hybrid Connectivity", "required"),
    "hybrid_dns_model": ("Hybrid Connectivity", "dns_model"),
    "hybrid_ip_model": ("Hybrid Connectivity", "ip_model"),
    "hybrid_on_prem_cidrs": ("Hybrid Connectivity", "on_prem_cidrs"),
}

BUILTIN_PATTERNS: list[Pattern] = [
    Pattern(
        name="baseline",
        description="Full LZA with hub-spoke, security, CI/CD, hybrid support",
        graph_factory=_baseline_graph_factory,
        intent_factory=RawIntent,
        catalog_name="lza-sample",
        normalizer=normalize_lza,
        validators=[validate_lza_intent],
        artifact_validators=[validate_lza_artifacts],
        section_map=dict(_BASELINE_SECTION_MAP),
        section_order=list(_BASELINE_SECTION_ORDER),
        free_form_examples=dict(_BASELINE_FREE_FORM_EXAMPLES),
        prompt_context=(
            "This pattern designs AWS Landing Zone Accelerator configurations. "
            "The design document uses Markdown sections. Extract values as follows:\n"
            "- Region section → primary_region\n"
            "- Topology section → topology (hub-spoke or single-vpc)\n"
            "- Network section → network_cidr, hub_cidr, central_network_account\n"
            "- Security section → audit_retention_days, centralized_logging, kms_rotation\n"
            "- CI/CD section → cicd_mode, cicd_placement\n"
            "- Organizational Units section → each line is an OU with name, description\n"
            "- Accounts section → each line is an account with name, ou, description\n"
            "- Workloads section → each line: name, target_account, network_mode, "
            "port, cpu, memory\n"
            "- Hybrid Connectivity section → hybrid_required, hybrid_dns_model, "
            "hybrid_ip_model, on_prem_cidrs"
        ),
        required_artifacts=[
            "organization-config.yaml",
            "accounts-config.yaml",
            "global-config.yaml",
            "security-config.yaml",
            "network-config.yaml",
            "iam-config.yaml",
            "customizations-config.yaml",
            "decision-report.yaml",
            "deployment-graph.yaml",
        ],
    ),
    Pattern(
        name="workload",
        description="Workload account deployment only",
        graph_factory=_workload_graph_factory,
        intent_factory=RawIntent,
        normalizer=normalize_lza,
        validators=[validate_lza_intent],
        section_map={
            "workload_name": ("Workloads", "name"),
            "target_account": ("Workloads", "target_account"),
            "network_mode": ("Workloads", "network_mode"),
            "public_ingress": ("Workloads", "public_ingress"),
            "port": ("Workloads", "port"),
            "cpu": ("Workloads", "cpu"),
            "memory": ("Workloads", "memory"),
        },
        section_order=["Workloads"],
        free_form_examples={
            "Workloads": [
                "api: target_account=Prod, network_mode=private, port=8080, cpu=256, memory=512",
            ],
        },
    ),
    Pattern(
        name="minimal",
        description="Bare minimum: region, topology, CIDR, audit",
        graph_factory=_minimal_graph_factory,
        intent_factory=RawIntent,
        catalog_name="lza-minimal",
        normalizer=normalize_lza,
        validators=[validate_lza_intent],
        section_map={
            "primary_region": ("Region", "primary"),
            "topology": ("Topology", None),
            "network_cidr": ("Network", "cidr"),
            "audit_retention_days": ("Security", "audit_retention_days"),
        },
        section_order=[
            "Region",
            "Topology",
            "Network",
            "Security",
            "Organizational Units",
            "Accounts",
            "Workloads",
        ],
        free_form_examples={
            "Organizational Units": [
                "Security: Security team accounts and audit infrastructure",
            ],
            "Accounts": [
                "Network: ou=Infrastructure, description=Central VPC management",
            ],
            "Workloads": [
                "api: target_account=Prod, network_mode=private, port=8080, cpu=256, memory=512",
            ],
        },
        prompt_context="This pattern designs minimal AWS landing zone configurations.",
    ),
    Pattern(
        name="hybrid-enterprise",
        description="Baseline with hybrid connectivity and enhanced security defaults",
        graph_factory=_hybrid_enterprise_graph_factory,
        intent_factory=RawIntent,
        catalog_name="lza-hybrid",
        normalizer=normalize_lza,
        validators=[validate_lza_intent],
        section_map=dict(_BASELINE_SECTION_MAP),
        section_order=list(_BASELINE_SECTION_ORDER),
        free_form_examples=dict(_BASELINE_FREE_FORM_EXAMPLES),
        prompt_context="This pattern designs hybrid enterprise AWS landing zone configurations.",
        required_artifacts=[
            "organization-config.yaml",
            "accounts-config.yaml",
            "global-config.yaml",
            "security-config.yaml",
            "network-config.yaml",
            "iam-config.yaml",
            "customizations-config.yaml",
            "decision-report.yaml",
            "deployment-graph.yaml",
        ],
    ),
    Pattern(
        name="financial-services",
        description="Baseline + PCI-DSS, SOX, data residency, and payment network segmentation",
        graph_factory=_financial_services_graph_factory,
        intent_factory=RawIntent,
        catalog_name="lza-financial",
        normalizer=normalize_lza,
        validators=[validate_lza_intent],
        section_map=dict(_BASELINE_SECTION_MAP),
        section_order=list(_BASELINE_SECTION_ORDER),
        free_form_examples=dict(_BASELINE_FREE_FORM_EXAMPLES),
        prompt_context="This pattern designs financial services AWS landing zone configurations.",
        required_artifacts=[
            "organization-config.yaml",
            "accounts-config.yaml",
            "global-config.yaml",
            "security-config.yaml",
            "network-config.yaml",
            "iam-config.yaml",
            "customizations-config.yaml",
            "decision-report.yaml",
            "deployment-graph.yaml",
        ],
    ),
    Pattern(
        name="healthcare",
        description="Baseline + HIPAA, PHI encryption, audit access logging, and BAA requirements",
        graph_factory=_healthcare_graph_factory,
        intent_factory=RawIntent,
        catalog_name="lza-healthcare",
        normalizer=normalize_lza,
        validators=[validate_lza_intent],
        section_map=dict(_BASELINE_SECTION_MAP),
        section_order=list(_BASELINE_SECTION_ORDER),
        free_form_examples=dict(_BASELINE_FREE_FORM_EXAMPLES),
        prompt_context="This pattern designs healthcare AWS landing zone configurations.",
        required_artifacts=[
            "organization-config.yaml",
            "accounts-config.yaml",
            "global-config.yaml",
            "security-config.yaml",
            "network-config.yaml",
            "iam-config.yaml",
            "customizations-config.yaml",
            "decision-report.yaml",
            "deployment-graph.yaml",
        ],
    ),
]


# Built-in addons -------------------------------------------------------------


ADDON_REGISTRY.register(
    Addon(
        name="pci-compliance",
        description=(
            "PCI-DSS and SOX compliance: data residency, "
            "encryption key management, network segmentation"
        ),
        requirements=[
            Requirement(
                key="data_residency",
                label="Data Residency",
                question="Is data residency required for payment data?",
                options=["true", "false"],
                default="true",
                category="compliance",
                compliance_controls=["PCI-DSS-3.4", "GDPR-Art44"],
                tradeoffs=[
                    "Required: data never leaves primary region",
                    "Optional: cross-region DR possible",
                ],
                consequences=["Determines S3 replication and RDS backup strategy"],
            ),
            Requirement(
                key="encryption_key_management",
                label="Encryption Key Management",
                question="How are encryption keys managed for payment data?",
                options=["aws-kms-hsm", "aws-kms", "customer-managed-hsm"],
                default="aws-kms-hsm",
                category="security",
                compliance_controls=["PCI-DSS-3.5", "SOX-404"],
                tradeoffs=[
                    "AWS KMS with CloudHSM: FIPS 140-2 Level 3",
                    "AWS KMS: managed, less operational burden",
                    "Customer-managed HSM: full control, highest cost",
                ],
            ),
            Requirement(
                key="network_segmentation",
                label="Payment Network Segmentation",
                question="Require dedicated VPC for payment processing?",
                options=["true", "false"],
                default="true",
                category="network",
                compliance_controls=["PCI-DSS-1.2"],
                tradeoffs=[
                    "Dedicated VPC: isolation, easier audit scope",
                    "Shared VPC: lower cost, harder to prove scope",
                ],
                consequences=["Adds VPC peering complexity for shared services"],
            ),
        ],
        field_map={
            "data_residency": None,
            "encryption_key_management": None,
            "network_segmentation": None,
        },
        section_map={
            "data_residency": ("Security", "data_residency"),
            "encryption_key_management": ("Security", "encryption_key_management"),
            "network_segmentation": ("Network", "network_segmentation"),
        },
    )
)

ADDON_REGISTRY.register(
    Addon(
        name="hipaa",
        description="HIPAA compliance: PHI encryption, audit access logging, BAA coverage",
        requirements=[
            Requirement(
                key="phi_encryption",
                label="PHI Encryption",
                question="Is end-to-end encryption required for all PHI access?",
                options=["true", "false"],
                default="true",
                category="compliance",
                compliance_controls=["HIPAA-164.312"],
                consequences=["All DB connections must use TLS 1.3"],
            ),
            Requirement(
                key="audit_access_logging",
                label="Audit Access Logging",
                question="Log all access to PHI-containing systems?",
                options=["true", "false"],
                default="true",
                category="security",
                compliance_controls=["HIPAA-164.308", "HIPAA-164.312"],
                consequences=["All API calls to health workloads must be logged"],
            ),
            Requirement(
                key="business_associate_agreements",
                label="BAA Coverage",
                question="Do all third-party services require Business Associate Agreements?",
                options=["true", "false"],
                default="true",
                category="compliance",
                compliance_controls=["HIPAA-164.502"],
                tradeoffs=[
                    "Required: restricts service selection to BAA-covered vendors",
                    "Optional: broader vendor selection, manual risk assessment",
                ],
            ),
        ],
        field_map={
            "phi_encryption": None,
            "audit_access_logging": None,
            "business_associate_agreements": None,
        },
        section_map={
            "phi_encryption": ("Security", "phi_encryption"),
            "audit_access_logging": ("Security", "audit_access_logging"),
            "business_associate_agreements": ("Security", "business_associate_agreements"),
        },
    )
)

ADDON_REGISTRY.register(
    Addon(
        name="self-hosted-cicd",
        description="Self-hosted CI/CD runners (Jenkins/GitLab) with VPC placement",
        requirements=[
            Requirement(
                key="cicd_runner_platform",
                target_field="cicd.runner.platform",
                target_type="CICDPlatform",
                label="CI/CD Runner Platform",
                question="Are CI/CD runners self-hosted or enterprise-managed?",
                options=["self-hosted", "enterprise"],
                default="self-hosted",
                category="cicd",
                wa_pillars=["Security", "Operational Excellence"],
                hint="Self-hosted: Jenkins/GitLab on your compute.",
            ),
            Requirement(
                key="cicd_runner_tool",
                target_field="cicd.runner.tool",
                target_type="CICDTool",
                label="CI/CD Tool",
                question="Which self-hosted CI/CD tool?",
                options=["jenkins", "gitlab-ci"],
                default="jenkins",
                depends_on=["cicd_runner_platform"],
                category="cicd",
                wa_pillars=["Operational Excellence"],
                hint="Jenkins for extensibility, GitLab CI for unified SCM+pipelines.",
            ),
        ],
        field_map={
            "cicd_runner_platform": None,
            "cicd_runner_tool": None,
        },
        section_map={
            "cicd_runner_platform": ("CI/CD", "runner_platform"),
            "cicd_runner_tool": ("CI/CD", "runner_tool"),
        },
    )
)

ADDON_REGISTRY.register(
    Addon(
        name="hashicorp-vault",
        description="HashiCorp Vault for secret management with dynamic secrets",
        requirements=[
            Requirement(
                key="secret_provider",
                target_field="secret_management.provider",
                target_type="SecretProvider",
                label="Secret Management Provider",
                question="Which secrets management provider?",
                options=[
                    "aws-secrets-manager",
                    "hashicorp-vault",
                    "cyberark",
                    "custom",
                ],
                default="hashicorp-vault",
                category="security",
                wa_pillars=["Security", "Operational Excellence"],
                compliance_controls=["PCI-DSS-3.5", "SOC2-CC6.1"],
                hint="Vault for dynamic secrets, multi-cloud support.",
            ),
            Requirement(
                key="secret_rotation_days",
                target_field="secret_management.rotation_days",
                target_type="int",
                label="Secret Rotation Period",
                question="How often (in days) should secrets be rotated?",
                default="30",
                category="security",
                wa_pillars=["Security"],
                hint="30 days recommended for high-security Vault deployments.",
            ),
        ],
        field_map={
            "secret_provider": None,
            "secret_rotation_days": None,
        },
        section_map={
            "secret_provider": ("Security", "secret_provider"),
            "secret_rotation_days": ("Security", "secret_rotation_days"),
        },
    )
)

ADDON_REGISTRY.register(
    Addon(
        name="paloalto-fw",
        description="Palo Alto Networks firewall appliance with BYOL licensing",
        requirements=[
            Requirement(
                key="appliance_vendor",
                target_field="network_appliance.vendor",
                target_type="string",
                label="Network Appliance Vendor",
                question="Which network appliance vendor?",
                options=[
                    "paloalto",
                    "checkpoint",
                    "fortinet",
                    "aviatrix",
                    "aws-network-firewall",
                ],
                default="paloalto",
                depends_on=["egress_inspection"],
                applies_if={"egress_inspection": ["required"]},
                category="network",
                wa_pillars=["Security"],
                hint="Palo Alto for enterprise threat prevention.",
            ),
            Requirement(
                key="appliance_license",
                target_field="network_appliance.license_type",
                target_type="ApplianceLicense",
                label="Appliance License Model",
                question="Licensing model for Palo Alto?",
                options=["byol", "subscription", "marketplace"],
                default="byol",
                depends_on=["appliance_vendor"],
                category="cost",
                wa_pillars=["Cost Optimization"],
                hint="BYOL leverages existing Palo Alto license investments.",
            ),
        ],
        field_map={
            "appliance_vendor": None,
            "appliance_license": None,
        },
        section_map={
            "appliance_vendor": ("Network", "appliance_vendor"),
            "appliance_license": ("Network", "appliance_license"),
        },
    )
)

ADDON_REGISTRY.register(
    Addon(
        name="hybrid-challenges",
        description=(
            "Hybrid connectivity challenges: DX redundancy, VPN failover, and identity integration"
        ),
        requirements=[
            Requirement(
                key="dx_redundancy",
                label="Direct Connect Redundancy",
                question="Is redundant Direct Connect required?",
                options=["true", "false"],
                default="true",
                depends_on=["hybrid_required"],
                applies_if={"hybrid_required": ["true"]},
                category="hybrid",
                wa_pillars=["Reliability", "Security"],
                hint="Dual DX connections for high availability.",
                tradeoffs=[
                    "Redundant: 99.99% SLA, higher cost",
                    "Single: lower cost, single point of failure",
                ],
                consequences=["Impacts DX partner selection and circuit procurement"],
            ),
            Requirement(
                key="vpn_failover",
                label="VPN Failover",
                question="Use VPN as Direct Connect failover?",
                options=["true", "false"],
                default="true",
                depends_on=["hybrid_required"],
                applies_if={"hybrid_required": ["true"]},
                category="hybrid",
                wa_pillars=["Reliability"],
                hint="Site-to-site VPN backup when DX is unavailable.",
                tradeoffs=[
                    "VPN failover: continuous connectivity, added complexity",
                    "No failover: simpler, outage risk during DX maintenance",
                ],
                consequences=["Requires VGW or Transit Gateway with VPN attachments"],
            ),
            Requirement(
                key="hybrid_identity",
                label="Hybrid Identity Model",
                question="What identity model for hybrid workloads?",
                options=["ad-connector", "managed-ad", "self-hosted-ad", "none"],
                default="ad-connector",
                depends_on=["hybrid_required"],
                applies_if={"hybrid_required": ["true"]},
                category="hybrid",
                wa_pillars=["Security", "Operational Excellence"],
                hint="How EC2 instances join the on-prem AD domain.",
                tradeoffs=[
                    "AD Connector: proxy to on-prem AD, no replication",
                    "Managed AD: AWS-managed, supports trust relationships",
                    "Self-hosted AD: full control, highest ops burden",
                    "None: cloud-native identity, no AD dependency",
                ],
                consequences=["Determines EC2 join strategy and GPO application"],
                signals=["on-prem-ad", "active-directory", "mainframe-integration"],
            ),
        ],
        field_map={
            "dx_redundancy": None,
            "vpn_failover": None,
            "hybrid_identity": None,
        },
        section_map={
            "dx_redundancy": ("Hybrid Connectivity", "dx_redundancy"),
            "vpn_failover": ("Hybrid Connectivity", "vpn_failover"),
            "hybrid_identity": ("Hybrid Connectivity", "hybrid_identity"),
        },
    )
)


# Attach LZA discovery hooks to all patterns
for _p in BUILTIN_PATTERNS:
    _p.extra_consistency_checks = [check_lza_legacy_consistency]
    _p.extra_signal_detectors = [detect_lza_legacy_signals]

# Register patterns after addons so validation can resolve addon dependencies ----
for _p in BUILTIN_PATTERNS:
    GLOBAL_REGISTRY.register(_p)


# ---------------------------------------------------------------------------
# Versioned sample configurations
# ---------------------------------------------------------------------------

from intent_engine.core.sample_config import (  # noqa: E402
    GLOBAL_SAMPLE_REGISTRY,
    ModuleRef,
    SampleConfig,
)

GLOBAL_SAMPLE_REGISTRY.register(
    SampleConfig(
        name="lza-baseline-v1",
        pattern="baseline",
        version="1.0.0",
        release_date="2025-06-01",
        source_url="https://github.com/aws/lza-universal-configuration/tree/main/modules/base/default",
        decisions={
            "primary_region": "eu-central-1",
            "topology": "hub-spoke",
            "network_cidr": "10.0.0.0/16",
            "hub_cidr": "10.0.0.0/20",
            "central_network_account": "Network",
            "audit_retention_days": "2555",
            "centralized_logging": True,
            "egress_inspection": "none",
            "cicd_mode": "public",
        },
        module_refs=[
            ModuleRef(
                module_name="lza-network",
                source="terraform-aws-modules/vpc/aws",
                version="~> 5.0",
                description="VPC with public/private subnets, NAT gateways, Transit Gateway",
            ),
            ModuleRef(
                module_name="lza-security-baseline",
                source="terraform-aws-modules/security-group/aws",
                version="~> 5.0",
                description="Security groups, KMS keys, audit logging, IAM baseline",
            ),
        ],
    )
)

GLOBAL_SAMPLE_REGISTRY.register(
    SampleConfig(
        name="lza-minimal-v1",
        pattern="minimal",
        version="1.0.0",
        release_date="2025-06-01",
        source_url="https://github.com/awslabs/landing-zone-accelerator-on-aws",
        decisions={
            "primary_region": "eu-central-1",
            "topology": "single-vpc",
            "network_cidr": "10.0.0.0/16",
            "audit_retention_days": "2555",
        },
        module_refs=[
            ModuleRef(
                module_name="lza-network",
                source="terraform-aws-modules/vpc/aws",
                version="~> 5.0",
                description="Single VPC with minimal setup",
            ),
        ],
    )
)
