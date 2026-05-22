"""LZA-specific requirement graph factories.

These functions build RequirementGraph instances for the LZA use case.
They are imported and registered by lza_patterns.py.
"""

from __future__ import annotations

from intent_engine.core.requirements import Requirement, RequirementGraph


def build_lza_baseline_graph() -> RequirementGraph:
    """Build the full LZA requirement graph with LZA baseline pattern."""
    from .models import RawIntent

    g = RequirementGraph(intent_model=RawIntent)

    g.add(
        Requirement(
            key="primary_region",
            target_field="primary_region",
            target_type="string",
            label="Primary Region",
            question="Which AWS region is the primary landing zone region?",
            default="eu-central-1",
            category="organization",
            wa_pillars=["Operational Excellence", "Security"],
            hint="EU compliance default. Choose region closest to your main users.",
            compliance_controls=["GDPR-Art44"],
            tradeoffs=[
                "eu-central-1: GDPR-aligned, low latency for EU users",
                "us-east-1: broadest service availability",
                "ap-southeast-1: low latency for APAC",
            ],
            consequences=["Determines data residency for all workloads"],
        )
    )

    g.add(
        Requirement(
            key="topology",
            target_field="topology",
            target_type="Topology",
            cascade={"network.topology": "{value}"},
            label="Network Topology",
            question="What network topology do you want for this landing zone?",
            options=["hub-spoke", "single-vpc"],
            default="single-vpc",
            category="network",
            wa_pillars=["Security", "Reliability"],
            hint="Hub-spoke for multi-account, single-VPC for simple.",
            tradeoffs=[
                "hub-spoke: transitive routing, central control, higher complexity",
                "single-vpc: simpler, lower cost, limited scalability",
            ],
            alternatives=["peering-mesh (not recommended: O(n^2) complexity)"],
            consequences=[
                "hub-spoke requires central Network account + NAT/DNS infrastructure",
                "single-vpc limits account isolation for compliance boundaries",
            ],
            signals=[
                "on-prem-ad",
                "mpls",
                "5+-accounts",
                "sap-workload",
                "oracle-workload",
                "mainframe-integration",
                "multi-cloud",
            ],
        )
    )

    g.add(
        Requirement(
            key="central_network_account",
            target_field="network.central_network_account",
            target_type="string",
            label="Central Network Account",
            question="What is the name of the central Network account?",
            depends_on=["topology"],
            applies_if={"topology": ["hub-spoke"]},
            why_applies="Only applies when topology is hub-spoke (not single-vpc)",
            category="network",
            wa_pillars=["Security"],
            hint="Holds transitive VPC peers and central routing.",
            compliance_controls=["PCI-DSS-1.3"],
            violation_code="HUB_SPOKE_NETWORK_ACCOUNT_REQUIRED",
            violation_message=(
                "Hub-spoke topology requires a central Network account. "
                "Add '- central_network_account: <name>' to your Network section."
            ),
            tradeoffs=[
                "Dedicated Network account: isolation, blast radius control",
                "Shared with other roles: simpler but violates least privilege",
            ],
            consequences=["Becomes the transit hub for all cross-VPC traffic"],
        )
    )

    g.add(
        Requirement(
            key="network_cidr",
            target_field="network.cidr",
            target_type="string",
            label="Network CIDR",
            question="What is the VPC CIDR block for the primary network?",
            default="10.0.0.0/16",
            category="network",
            wa_pillars=["Security"],
            hint="Use private CIDR, no overlap with on-prem or other clouds.",
            enterprise_standards=["RFC1918-PRIVATE-ONLY"],
            tradeoffs=[
                "/16: 65k IPs, room for 16 /20 spokes",
                "/20: 4k IPs, limited growth",
            ],
            consequences=["Cannot change without VPC rebuild"],
            signals=["sap-workload", "oracle-workload", "multi-cloud"],
        )
    )

    g.add(
        Requirement(
            key="hub_cidr",
            target_field="network.hub_cidr",
            target_type="string",
            label="Hub VPC CIDR",
            question="What is the hub VPC CIDR block?",
            depends_on=["topology"],
            applies_if={"topology": ["hub-spoke"]},
            why_applies="Only applies when topology is hub-spoke",
            default="10.0.0.0/20",
            category="network",
            wa_pillars=["Security"],
            hint="Hub: central DNS, firewall, NACLs. No overlap with spokes.",
            tradeoffs=[
                "/20 from parent /16: reserved block for hub services",
                "Separate /16: more isolation but complex routing",
            ],
            consequences=["Must not overlap with spoke CIDRs"],
        )
    )

    g.add(
        Requirement(
            key="audit_retention_days",
            target_field="security.audit_retention_days",
            target_type="int",
            label="Audit Log Retention",
            question="How many days should audit logs be retained?",
            default="2555",
            category="security",
            wa_pillars=["Security", "Operational Excellence"],
            hint="2555 days (~7yr) for PCI/SOC. 90 days minimum for CloudTrail.",
            compliance_controls=["PCI-DSS-10.7", "SOC2-CC7.2", "ISO27017-12.4"],
            tradeoffs=[
                "2555 days: satisfies all major frameworks",
                "365 days: lighter storage cost, may not satisfy PCI",
                "90 days: minimum viable, high risk for forensics",
            ],
            consequences=["Storage cost scales linearly with retention"],
        )
    )

    g.add(
        Requirement(
            key="centralized_logging",
            target_field="security.centralized_logging",
            target_type="bool",
            label="Centralized Logging",
            question="Enable centralized logging to the Audit account?",
            options=["true", "false"],
            default="true",
            category="security",
            wa_pillars=["Security", "Operational Excellence"],
            hint="Sends all CloudTrail and config logs to central Audit account.",
            compliance_controls=["PCI-DSS-10.2", "SOC2-CC7.2"],
            tradeoffs=[
                "Centralized: tamper-resistant, unified forensics",
                "Decentralized: lower latency, harder to correlate",
            ],
            consequences=["Audit account becomes critical infrastructure"],
        )
    )

    g.add(
        Requirement(
            key="cicd_mode",
            target_field="cicd.mode",
            target_type="CI_CDMode",
            label="CI/CD Mode",
            question="What CI/CD deployment mode?",
            options=["private", "public"],
            default="public",
            category="cicd",
            wa_pillars=["Security", "Operational Excellence"],
            hint="Private: VPC + endpoints. Public: AWS managed CI/CD.",
            compliance_controls=["PCI-DSS-6.5"],
            tradeoffs=[
                "Private: no internet egress for builds, higher setup cost",
                "Public: simpler, requires IP allowlisting for compliance",
            ],
            signals=["pci-scope", "data-classified"],
        )
    )

    g.add(
        Requirement(
            key="cicd_placement",
            target_field="cicd.placement",
            target_type="string",
            label="CI/CD Placement",
            question="What is the VPC or subnet name for private CI/CD?",
            depends_on=["cicd_mode"],
            applies_if={"cicd_mode": ["private"]},
            why_applies="Only asked when CI/CD mode is private (not public)",
            category="cicd",
            wa_pillars=["Security"],
            hint="E.g., SharedServices/BuildVPC. Must be pre-existing VPC.",
            violation_code="PRIVATE_CICD_PLACEMENT_REQUIRED",
            violation_message=(
                "Private CI/CD requires placement configuration. "
                "Add '- placement: <vpc/subnet>' to your CI/CD section."
            ),
            tradeoffs=[
                "SharedServices VPC: consolidated endpoints, shared blast radius",
                "Dedicated Build VPC: isolation, higher cost",
            ],
        )
    )

    g.add(
        Requirement(
            key="egress_inspection",
            target_field="security.egress_inspection",
            target_type="EgressInspection",
            label="Egress Inspection",
            question="Is explicit egress traffic inspection required (firewall/NGFW)?",
            options=["required", "none"],
            default="none",
            category="security",
            wa_pillars=["Security"],
            hint="PCI-DSS/SOC2: centralized outbound traffic inspection.",
            compliance_controls=["PCI-DSS-1.3.1", "SOC2-CC6.1"],
            tradeoffs=[
                "Required: full packet inspection, compliance coverage",
                "None: lower cost, relies on security groups + NACLs",
            ],
            signals=[
                "pci-scope",
                "data-classified",
                "regulated-industry",
                "sap-workload",
                "oracle-workload",
            ],
            consequences=["Adds latency to all outbound traffic"],
        )
    )

    g.add(
        Requirement(
            key="inspection_pattern",
            target_field="security.inspection_pattern",
            target_type="string",
            label="Inspection Pattern",
            question="What is the egress inspection architecture?",
            depends_on=["egress_inspection"],
            applies_if={"egress_inspection": ["required"]},
            why_applies="Only asked when egress inspection is required",
            category="security",
            wa_pillars=["Security", "Performance Efficiency"],
            hint="E.g., centralized-nat, distributed-inspection, gateway-agg.",
            required_when_applicable=False,  # vendor OR pattern satisfies
            tradeoffs=[
                "centralized-nat: single point of control, potential bottleneck",
                "distributed-inspection: scales better, harder to audit",
                "gateway-agg: AWS-managed, least operational burden",
            ],
            alternatives=["inline-proxy (rejected: too complex for initial rollout)"],
        )
    )

    g.add(
        Requirement(
            key="inspection_vendor",
            target_field="security.inspection_vendor",
            target_type="string",
            label="Inspection Vendor",
            question="Which security vendor provides the inspection appliances?",
            depends_on=["egress_inspection"],
            applies_if={"egress_inspection": ["required"]},
            why_applies="Only asked when egress inspection is required",
            category="security",
            wa_pillars=["Security", "Cost Optimization"],
            hint="E.g., paloalto, checkpoint, fortinet, aws-network-firewall.",
            required_when_applicable=False,  # vendor OR pattern satisfies
            tradeoffs=[
                "aws-network-firewall: native integration, no licensing",
                "paloalto/checkpoint: familiar tooling, licensing cost",
                "fortinet: good price/performance, smaller community",
            ],
        )
    )

    g.add(
        Requirement(
            key="hybrid_required",
            target_field="hybrid.required",
            target_type="bool",
            label="Hybrid Connectivity",
            question="Is hybrid connectivity to on-premises or other clouds required?",
            options=["true", "false"],
            default="false",
            category="hybrid",
            wa_pillars=["Security", "Reliability"],
            hint="Only if you have on-prem or multi-cloud connectivity.",
            signals=[
                "on-prem-ad",
                "on-prem-dns",
                "mpls",
                "direct-connect-existing",
                "sap-workload",
                "oracle-workload",
                "mainframe-integration",
                "multi-cloud",
            ],
            tradeoffs=[
                "Hybrid: seamless migration, extends on-prem security model",
                "Cloud-native: simpler, requires rethinking identity and network",
            ],
            consequences=[
                "Requires Direct Connect or VPN infrastructure",
                "Extends blast radius to on-prem",
            ],
        )
    )

    g.add(
        Requirement(
            key="hybrid_dns_model",
            target_field="hybrid.dns_model",
            target_type="string",
            label="Hybrid DNS Model",
            question="What DNS resolution model for hybrid connectivity?",
            depends_on=["hybrid_required"],
            applies_if={"hybrid_required": ["true"]},
            why_applies="Only asked when hybrid connectivity is required",
            category="hybrid",
            wa_pillars=["Security", "Reliability"],
            hint="E.g., aws-resolver, shared-services, route53-resolver.",
            violation_code="HYBRID_CONFIG_INCOMPLETE",
            violation_message=(
                "Hybrid connectivity is enabled but missing dns_model. "
                "Add it to your Hybrid Connectivity section."
            ),
            signals=["on-prem-dns", "active-directory", "mainframe-integration"],
            tradeoffs=[
                "aws-resolver: managed, integrates with Route53",
                "shared-services: central control, single point of failure",
                "route53-resolver: hybrid forwarding, most flexible",
            ],
            consequences=["Determines AD join strategy for EC2 instances"],
        )
    )

    g.add(
        Requirement(
            key="hybrid_ip_model",
            target_field="hybrid.ip_model",
            target_type="string",
            label="Hybrid IP Model",
            question="What IP addressing model for hybrid?",
            depends_on=["hybrid_required"],
            applies_if={"hybrid_required": ["true"]},
            why_applies="Only asked when hybrid connectivity is required",
            category="hybrid",
            wa_pillars=["Security", "Reliability"],
            hint="E.g., bring-your-own, rfc1918-only, unified-cidr.",
            violation_code="HYBRID_CONFIG_INCOMPLETE",
            violation_message=(
                "Hybrid connectivity is enabled but missing ip_model. "
                "Add it to your Hybrid Connectivity section."
            ),
            signals=["on-prem-cidr-overlap-risk"],
            tradeoffs=[
                "bring-your-own: reuse existing IPs, complex renumbering",
                "rfc1918-only: clean separation, may break legacy apps",
                "unified-cidr: seamless routing, requires careful planning",
            ],
            consequences=["Cannot easily change after Direct Connect is established"],
        )
    )

    g.add(
        Requirement(
            key="hybrid_on_prem_cidrs",
            target_field="hybrid.on_prem_cidrs",
            target_type="cidr_list",
            label="On-Premises CIDRs",
            question="What are the on-premises CIDR blocks (comma-separated)?",
            depends_on=["hybrid_required"],
            applies_if={"hybrid_required": ["true"]},
            why_applies="Only asked when hybrid connectivity is required",
            category="hybrid",
            wa_pillars=["Security"],
            hint="Comma-separated, e.g., 10.100.0.0/16,192.168.0.0/24.",
            violation_code="HYBRID_CONFIG_INCOMPLETE",
            violation_message=(
                "Hybrid connectivity is enabled but missing on_prem_cidrs. "
                "Add it to your Hybrid Connectivity section."
            ),
            enterprise_standards=["RFC1918-PRIVATE-ONLY"],
            consequences=["Must not overlap with AWS CIDRs"],
        )
    )

    # -- CI/CD runner platform --
    g.add(
        Requirement(
            key="cicd_runner_platform",
            target_field="cicd.runner.platform",
            target_type="CICDPlatform",
            label="CI/CD Runner Platform",
            question="Are CI/CD runners self-hosted or enterprise-managed?",
            options=["self-hosted", "enterprise"],
            default="enterprise",
            category="cicd",
            wa_pillars=["Security", "Operational Excellence"],
            hint="Self-hosted: Jenkins/GitLab on your compute. "
            "Enterprise: AWS CodePipeline/GitHub Actions managed.",
            tradeoffs=[
                "self-hosted: full control, custom plugins, higher ops burden",
                "enterprise: managed, less control, lower maintenance",
            ],
            consequences=[
                "self-hosted requires runner placement (EC2/ECS/EKS), patches, scaling",
                "enterprise has built-in secrets, auto-scaling, no infra to manage",
            ],
            signals=["custom-cicd", "existing-jenkins", "on-prem-cicd"],
        )
    )

    g.add(
        Requirement(
            key="cicd_runner_tool",
            target_field="cicd.runner.tool",
            target_type="CICDTool",
            label="CI/CD Tool",
            question="Which CI/CD tool will run the pipelines?",
            options=["jenkins", "gitlab-ci", "github-actions", "codebuild", "codepipeline"],
            default="codepipeline",
            depends_on=["cicd_runner_platform"],
            category="cicd",
            wa_pillars=["Operational Excellence"],
            hint="Match to your existing engineering toolchain.",
            tradeoffs=[
                "jenkins: extensible, familiar for ops teams, plugin management burden",
                "gitlab-ci: unified SCM + CI, good for GitLab shops",
                "github-actions: rich ecosystem, good for OSS-style workflows",
                "codebuild: AWS-native, pay-per-use, limited customization",
                "codepipeline: multi-stage, integrates with CodeCommit/Build/Deploy",
            ],
            consequences=["Determines pipeline syntax, plugin ecosystem, and team training"],
            signals=["existing-jenkins", "gitlab-shop", "github-enterprise"],
        )
    )

    # -- Secret management --
    g.add(
        Requirement(
            key="secret_provider",
            target_field="secret_management.provider",
            target_type="SecretProvider",
            label="Secret Management Provider",
            question="Which secrets management provider will you use?",
            options=[
                "aws-secrets-manager",
                "hashicorp-vault",
                "cyberark",
                "custom",
            ],
            default="aws-secrets-manager",
            category="security",
            wa_pillars=["Security", "Operational Excellence"],
            hint="Managed or self-hosted secrets store for credentials, API keys, certificates.",
            compliance_controls=["PCI-DSS-3.5", "SOC2-CC6.1", "ISO27001-9.4"],
            tradeoffs=[
                "aws-secrets-manager: native, auto-rotate, integrated with RDS/ASM",
                "hashicorp-vault: dynamic secrets, multi-cloud, higher ops cost",
                "cyberark: enterprise PAM, compliance-focused, expensive",
                "custom: DIY, full control, highest security risk if misconfigured",
            ],
            consequences=[
                "Determines secrets rotation strategy and access patterns",
                "Impacts RDS credential rotation and CI/CD pipeline integration",
            ],
            signals=["existing-vault", "pam-required", "multi-cloud"],
        )
    )

    g.add(
        Requirement(
            key="secret_rotation_days",
            target_field="secret_management.rotation_days",
            target_type="int",
            label="Secret Rotation Period",
            question="How often (in days) should secrets be rotated?",
            default="90",
            category="security",
            wa_pillars=["Security"],
            hint="90 days for standard compliance, 30 days for high-security environments.",
            compliance_controls=["PCI-DSS-3.5", "SOC2-CC6.1"],
            tradeoffs=[
                "30 days: maximum security, higher rotation event risk",
                "90 days: balanced trade-off for most compliance frameworks",
                "180 days: lower operational load, may fail audit",
            ],
            consequences=["Short rotation increases API call volume and potential for disruption"],
        )
    )

    g.add(
        Requirement(
            key="secret_backup",
            target_field="secret_management.backup_enabled",
            target_type="bool",
            label="Secret Backup",
            question="Enable cross-region backup of secrets for disaster recovery?",
            options=["true", "false"],
            default="true",
            category="security",
            wa_pillars=["Reliability", "Security"],
            hint="Replicates secrets to a secondary region for DR scenarios.",
            tradeoffs=[
                "Backup: DR-ready, protects against region failure",
                "No backup: simpler, lower cost, data loss risk on region failure",
            ],
        )
    )

    # -- Network appliance --
    g.add(
        Requirement(
            key="appliance_vendor",
            target_field="network_appliance.vendor",
            target_type="string",
            label="Network Appliance Vendor",
            question="Which network appliance vendor for inspection/security?",
            options=["paloalto", "checkpoint", "fortinet", "aviatrix", "aws-network-firewall"],
            default="aws-network-firewall",
            depends_on=["egress_inspection"],
            applies_if={"egress_inspection": ["required"]},
            why_applies="Only asked when egress inspection is required",
            category="network",
            wa_pillars=["Security", "Cost Optimization"],
            hint="Vendor for firewall/NVA. AWS Network Firewall is the simplest managed option.",
            tradeoffs=[
                "aws-network-firewall: managed, no licensing overhead, native integration",
                "paloalto: enterprise-grade threat prevention, familiar to security teams",
                "checkpoint: strong IPS, centralized management, license cost",
                "fortinet: good price/performance, broad feature set",
                "aviatrix: cloud-native, advanced routing, multicloud focus",
            ],
            signals=["existing-firewall-vendor", "paloalto-shop", "checkpoint-enterprise"],
        )
    )

    g.add(
        Requirement(
            key="appliance_license",
            target_field="network_appliance.license_type",
            target_type="ApplianceLicense",
            label="Appliance License Model",
            question="What licensing model for the network appliance?",
            options=["byol", "subscription", "marketplace"],
            default="marketplace",
            depends_on=["appliance_vendor"],
            applies_if={"egress_inspection": ["required"]},
            why_applies="Only asked when egress inspection is required",
            category="cost",
            wa_pillars=["Cost Optimization"],
            hint="BYOL if you have existing licenses. Marketplace for pay-as-you-go.",
            tradeoffs=[
                "byol: leverages existing investment, limited to licensed capacity",
                "subscription: predictable cost, term commitment",
                "marketplace: flexible, pay-as-you-go, no upfront cost",
            ],
            consequences=["Impacts procurement process and cost forecasting"],
            signals=["existing-license-portfolio"],
        )
    )

    g.add(
        Requirement(
            key="appliance_ha",
            target_field="network_appliance.ha_mode",
            target_type="ApplianceHA",
            label="Appliance High-Availability",
            question="What HA mode for the network appliance?",
            options=["none", "active-passive", "active-active", "cluster"],
            default="active-passive",
            depends_on=["appliance_vendor"],
            applies_if={"egress_inspection": ["required"]},
            why_applies="Only asked when egress inspection is required",
            category="network",
            wa_pillars=["Reliability", "Security"],
            hint="active-passive for most workloads, active-active for throughput-critical.",
            tradeoffs=[
                "none: simplest, single point of failure",
                "active-passive: failover on failure, half capacity idle",
                "active-active: full capacity utilization, more complex failover",
                "cluster: maximum throughput, significant complexity",
            ],
            consequences=["Determines throughput, failover time, and operational complexity"],
        )
    )

    return g


def build_workload_account_graph() -> RequirementGraph:
    """Build requirement graph for a workload account pattern."""
    from .models import RawIntent

    g = RequirementGraph(intent_model=RawIntent)

    g.add(
        Requirement(
            key="workload_name",
            label="Workload Name",
            question="What is the workload name?",
            category="workload",
        )
    )

    g.add(
        Requirement(
            key="target_account",
            label="Target Account",
            question="Which account hosts this workload?",
            category="workload",
        )
    )

    g.add(
        Requirement(
            key="network_mode",
            label="Network Mode",
            question="Network mode for the workload?",
            options=["private", "public"],
            default="private",
            category="workload",
        )
    )

    g.add(
        Requirement(
            key="public_ingress",
            label="Public Ingress",
            question="Allow public ingress?",
            options=["true", "false"],
            default="false",
            category="workload",
        )
    )

    g.add(
        Requirement(
            key="port",
            label="Service Port",
            question="What port does the service listen on?",
            default="8080",
            category="workload",
        )
    )

    g.add(
        Requirement(
            key="cpu",
            label="CPU Units",
            question="CPU units for the task?",
            default="256",
            category="workload",
        )
    )

    g.add(
        Requirement(
            key="memory",
            label="Memory (MiB)",
            question="Memory in MiB for the task?",
            default="512",
            category="workload",
        )
    )

    return g
