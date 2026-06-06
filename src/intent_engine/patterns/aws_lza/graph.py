"""AWS LZA requirement graph."""

from __future__ import annotations

from intent_engine.core.requirements import Requirement, RequirementGraph


def build_aws_lza_graph() -> RequirementGraph:
    graph = RequirementGraph()
    graph.add(
        Requirement(
            key="baseline",
            target_field="baseline",
            target_type="LzaBaseline",
            label="LZA Baseline",
            question="Which AWS LZA sample configuration baseline should be used?",
            options=["standard", "universal", "healthcare", "education", "govcloud"],
            default="standard",
            category="accelerator",
            hint=(
                "Start from AWS-maintained sample configurations, then override only what differs."
            ),
        )
    )
    graph.add(
        Requirement(
            key="org_mode",
            target_field="org_mode",
            target_type="LzaOrgMode",
            label="Organization Mode",
            question="Should this landing zone use Control Tower or raw AWS Organizations?",
            options=["control-tower", "raw-orgs"],
            default="control-tower",
            category="organization",
            hint="AWS recommends Control Tower first for greenfield commercial landing zones.",
        )
    )
    graph.add(
        Requirement(
            key="organization_name",
            target_field="organization_name",
            target_type="string",
            label="Organization Name",
            question="What organization name should be used in the LZA handoff?",
            default="ExampleCorp",
            category="organization",
        )
    )
    graph.add(
        Requirement(
            key="home_region",
            target_field="home_region",
            target_type="string",
            label="Home Region",
            question="Which AWS region is the home region?",
            default="eu-central-1",
            category="organization",
        )
    )
    graph.add(
        Requirement(
            key="enabled_regions",
            target_field="enabled_regions",
            target_type="string_list",
            label="Enabled Regions",
            question="Which AWS regions should LZA enable? Use comma-separated values.",
            default="eu-central-1",
            category="organization",
        )
    )
    graph.add(
        Requirement(
            key="organizational_units",
            target_field="organizational_units",
            target_type="string_list",
            label="Organizational Units",
            question="Which OUs are required? Use comma-separated values.",
            default="Security, Infrastructure, Workloads",
            category="organization",
        )
    )
    graph.add(
        Requirement(
            key="workload_accounts",
            target_field="workload_accounts",
            target_type="string_list",
            label="Workload Accounts",
            question="Which workload accounts should be included? Use comma-separated values.",
            default="Prod",
            category="accounts",
            signals=["workload-infrastructure"],
            hint=(
                "AWS LZA can vend workload accounts; application resources need a separate "
                "approved module or generator target."
            ),
        )
    )
    graph.add(
        Requirement(
            key="audit_account",
            target_field="audit_account",
            target_type="string",
            label="Audit Account",
            question="Which account owns audit and security audit functions?",
            default="Audit",
            category="accounts",
        )
    )
    graph.add(
        Requirement(
            key="log_archive_account",
            target_field="log_archive_account",
            target_type="string",
            label="Log Archive Account",
            question="Which account stores immutable centralized logs?",
            default="LogArchive",
            category="accounts",
        )
    )
    graph.add(
        Requirement(
            key="security_tooling_account",
            target_field="security_tooling_account",
            target_type="string",
            label="Security Tooling Account",
            question="Which account owns delegated security tooling administration?",
            default="SecurityTooling",
            category="accounts",
        )
    )
    graph.add(
        Requirement(
            key="network_account",
            target_field="network_account",
            target_type="string",
            label="Network Account",
            question="Which account owns shared networking?",
            category="network",
            applies_when={"equals": {"decision": "topology", "value": "hub-spoke"}},
            violation_code="AWS_LZA_NETWORK_ACCOUNT_REQUIRED",
            violation_message="Hub-spoke topology requires a network account.",
        )
    )
    graph.add(
        Requirement(
            key="identity_center_delegated_admin_account",
            target_field="identity_center_delegated_admin_account",
            target_type="string",
            label="Identity Center Delegated Admin",
            question="Which account is delegated administrator for IAM Identity Center?",
            default="SecurityTooling",
            category="identity",
        )
    )
    graph.add(
        Requirement(
            key="identity_center_permission_sets",
            target_field="identity_center_permission_sets",
            target_type="string_list",
            label="Identity Center Permission Sets",
            question=(
                "Which IAM Identity Center permission sets are approved? Use comma-separated names."
            ),
            category="identity",
            violation_code="AWS_LZA_IDENTITY_CENTER_PERMISSION_SETS_REQUIRED",
            violation_message="IAM Identity Center handoff requires approved permission sets.",
        )
    )
    graph.add(
        Requirement(
            key="identity_center_assignments",
            target_field="identity_center_assignments",
            target_type="string_list",
            label="Identity Center Assignments",
            question=(
                "Which IAM Identity Center assignments are approved? "
                "Use Principal:PermissionSet:Account entries separated by commas."
            ),
            depends_on=["identity_center_permission_sets"],
            category="identity",
            violation_code="AWS_LZA_IDENTITY_CENTER_ASSIGNMENTS_REQUIRED",
            violation_message="IAM Identity Center handoff requires approved assignments.",
        )
    )
    graph.add(
        Requirement(
            key="topology",
            target_field="topology",
            target_type="LzaTopology",
            label="Network Topology",
            question="Which network topology should LZA configure?",
            options=["single-vpc", "hub-spoke"],
            default="hub-spoke",
            category="network",
        )
    )
    graph.add(
        Requirement(
            key="network_cidr",
            target_field="network_cidr",
            target_type="string",
            label="Network CIDR",
            question="What private CIDR should the landing zone reserve for networking?",
            default="10.0.0.0/16",
            category="network",
        )
    )
    graph.add(
        Requirement(
            key="centralized_logging",
            target_field="centralized_logging",
            target_type="bool",
            label="Centralized Logging",
            question="Should centralized logging be enabled?",
            options=["true", "false"],
            default="true",
            category="security",
        )
    )
    graph.add(
        Requirement(
            key="security_hub_enabled",
            target_field="security_hub_enabled",
            target_type="bool",
            label="Security Hub",
            question="Should AWS Security Hub be enabled by the LZA baseline?",
            options=["true", "false"],
            default="true",
            category="security",
        )
    )
    graph.add(
        Requirement(
            key="guardduty_enabled",
            target_field="guardduty_enabled",
            target_type="bool",
            label="GuardDuty",
            question="Should GuardDuty be enabled by the LZA baseline?",
            options=["true", "false"],
            default="true",
            category="security",
        )
    )
    graph.add(
        Requirement(
            key="compliance_overlay",
            target_field="compliance_overlay",
            target_type="ComplianceOverlay",
            label="Compliance Overlay",
            question="Which compliance overlay applies?",
            options=["none", "regulated", "financial-services", "healthcare", "education"],
            default="none",
            category="security",
            hint="Overlay selects extra decisions; it does not replace AWS/customer attestation.",
        )
    )
    return graph
