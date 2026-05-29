"""AWS LZA artifact generators."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import (
    _INFRASTRUCTURE_OU,
    _LZA_CONTRACT,
    _WORKLOADS_OU,
    _aws_lza_intent,
    _central_network_services_config,
    _core_vpc_config,
    _guardduty_config,
    _identity_center_config,
    _management_access_role,
    _mandatory_accounts,
    _sample_recommendation_runbook_lines,
    _security_hub_config,
    _workload_accounts,
    _write_yaml,
)


def gen_lza_organization_config(intent: Any, output_dir: Path) -> None:
    intent = _aws_lza_intent(intent)
    if intent is None:
        return
    data = {
        "enable": True,
        "organizationalUnits": [{"name": name} for name in intent.organizational_units],
        "serviceControlPolicies": [],
        "taggingPolicies": [],
        "backupPolicies": [],
    }
    _write_yaml(output_dir, "organization-config.yaml", data)


def gen_lza_accounts_config(intent: Any, output_dir: Path) -> None:
    intent = _aws_lza_intent(intent)
    if intent is None:
        return
    _write_yaml(
        output_dir,
        "accounts-config.yaml",
        {
            "mandatoryAccounts": _mandatory_accounts(intent),
            "workloadAccounts": _workload_accounts(intent),
        },
    )


def gen_lza_global_config(intent: Any, output_dir: Path) -> None:
    intent = _aws_lza_intent(intent)
    if intent is None:
        return
    data = {
        "homeRegion": intent.home_region,
        "enabledRegions": intent.enabled_regions,
        "managementAccountAccessRole": _management_access_role(intent),
        "terminationProtection": True,
        "cloudwatchLogRetentionInDays": 2555,
        "cdkOptions": {
            "centralizeBuckets": True,
            "useManagementAccessRole": True,
        },
        "controlTower": {"enable": str(intent.org_mode) == "control-tower"},
        "snsTopics": [],
        "tags": [],
        "logging": {
            "account": intent.log_archive_account,
            "centralizedLoggingRegion": intent.home_region,
            "cloudtrail": {
                "enable": intent.centralized_logging,
                "organizationTrail": intent.centralized_logging,
            },
            "sessionManager": {
                "sendToCloudWatchLogs": intent.centralized_logging,
                "sendToS3": intent.centralized_logging,
            },
            "centralLogBucket": {"lifecycleRules": []},
            "accessLogBucket": {"lifecycleRules": []},
        },
    }
    _write_yaml(output_dir, "global-config.yaml", data)


def gen_lza_security_config(intent: Any, output_dir: Path) -> None:
    intent = _aws_lza_intent(intent)
    if intent is None:
        return
    data = {
        "homeRegion": intent.home_region,
        "accessAnalyzer": {"enable": True},
        "iamPasswordPolicy": {
            "allowUsersToChangePassword": True,
            "hardExpiry": False,
            "requireUppercaseCharacters": True,
            "requireLowercaseCharacters": True,
            "requireSymbols": True,
            "requireNumbers": True,
            "minimumPasswordLength": 14,
            "passwordReusePrevention": 24,
            "maxPasswordAge": 90,
        },
        "awsConfig": {"enableConfigurationRecorder": True},
        "cloudWatch": {
            "metricSets": [],
            "alarmSets": [],
        },
        "centralSecurityServices": {
            "delegatedAdminAccount": intent.security_tooling_account,
            "ebsDefaultVolumeEncryption": {"enable": True, "excludeRegions": []},
            "s3PublicAccessBlock": {"enable": True, "excludeAccounts": []},
            "scpRevertChangesConfig": {"enable": True, "snsTopicName": "Security"},
            "macie": {
                "enable": str(intent.compliance_overlay) != "none",
                "excludeRegions": [],
                "policyFindingsPublishingFrequency": "FIFTEEN_MINUTES",
                "publishSensitiveDataFindings": str(intent.compliance_overlay)
                in {"regulated", "financial-services", "healthcare"},
            },
            "guardduty": _guardduty_config(intent),
            "snsSubscriptions": [],
            "securityHub": _security_hub_config(intent),
            "ssmAutomation": {"excludeRegions": [], "documentSets": []},
        },
    }
    _write_yaml(output_dir, "security-config.yaml", data)


def gen_lza_iam_config(intent: Any, output_dir: Path) -> None:
    intent = _aws_lza_intent(intent)
    if intent is None:
        return
    data = {
        "homeRegion": intent.home_region,
        "identityCenter": _identity_center_config(intent),
    }
    _write_yaml(output_dir, "iam-config.yaml", data)


def gen_lza_network_config(intent: Any, output_dir: Path) -> None:
    intent = _aws_lza_intent(intent)
    if intent is None:
        return
    data = {
        "homeRegion": intent.home_region,
        "defaultVpc": {"delete": True, "excludeAccounts": []},
        "endpointPolicies": [],
        "transitGateways": [],
        "vpcs": [_core_vpc_config(intent)],
    }
    if intent.topology == "hub-spoke":
        data["centralNetworkServices"] = _central_network_services_config(intent)
        data["transitGateways"] = [
            {
                "name": "Core",
                "account": intent.network_account,
                "region": intent.home_region,
                "asn": 64512,
                "dnsSupport": "enable",
                "vpnEcmpSupport": "enable",
                "defaultRouteTableAssociation": "disable",
                "defaultRouteTablePropagation": "disable",
                "autoAcceptSharingAttachments": "enable",
                "routeTables": [{"name": "Core", "routes": []}],
                "shareTargets": {"organizationalUnits": [_INFRASTRUCTURE_OU, _WORKLOADS_OU]},
                "tags": [],
            }
        ]
    _write_yaml(output_dir, "network-config.yaml", data)


def gen_lza_lineage_manifest(intent: Any, output_dir: Path) -> None:
    intent = _aws_lza_intent(intent)
    if intent is None:
        return
    data = {
        "sourceContract": {
            "name": _LZA_CONTRACT.name,
            "kind": _LZA_CONTRACT.kind,
            "url": _LZA_CONTRACT.source_url,
            "baseline": str(intent.baseline),
            "mandatoryConfigFiles": _LZA_CONTRACT.required_artifacts,
            "optionalConfigFiles": _LZA_CONTRACT.optional_artifacts,
        },
        "artifacts": [artifact.model_dump(by_alias=True) for artifact in _LZA_CONTRACT.artifacts],
        "lineage": [item.model_dump() for item in _LZA_CONTRACT.lineage],
    }
    _write_yaml(output_dir, "lineage-manifest.yaml", data)


def gen_lza_deployment_runbook(intent: Any, output_dir: Path) -> None:
    readiness = getattr(intent, "deployment_readiness", {})
    intent = _aws_lza_intent(intent)
    if intent is None:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# AWS LZA Deployment Runbook",
        "",
        "## Inputs",
        "",
        f"- Baseline: `{intent.baseline}`",
        f"- Organization mode: `{intent.org_mode}`",
        f"- Home region: `{intent.home_region}`",
        f"- Enabled regions: `{', '.join(intent.enabled_regions)}`",
        "",
        "## LZA Config Contract",
        "",
        "Mandatory configuration files:",
        "",
        *[f"- `{name}`" for name in _LZA_CONTRACT.required_artifacts],
        "",
        "Optional configuration files are emitted only when custom target contracts require them:",
        "",
        *[f"- `{name}`" for name in _LZA_CONTRACT.optional_artifacts],
        "",
        "## Recommended Sample Configs",
        "",
        *_sample_recommendation_runbook_lines(intent),
        "## Sequence",
        "",
        (
            "1. Platform owner confirms AWS Organizations or Control Tower baseline "
            "matches `org_mode`."
        ),
        "2. Network owner reviews generated LZA network config against approved CIDR plan.",
        (
            "3. Security owner reviews logging, Security Hub, GuardDuty, and "
            "delegated admin decisions."
        ),
        (
            "4. Populate customer-specific Identity Center assignments and permission "
            "sets; identity owner approves delegated admin."
        ),
        "5. Release owner replaces placeholder account emails before deployment.",
        (
            "6. Platform owner populates customer-specific VPC route tables/subnets, "
            "TGW attachments, and optional security exports."
        ),
        "7. Manual gate: approve `decision-report.yaml`, `lineage-manifest.yaml`, and LZA diff.",
        "8. Run AWS LZA deployment using its documented installer and pipeline.",
        (
            "9. Preserve `decision-report.yaml`, `decision-audit.yaml`, and "
            "`lineage-manifest.yaml` as handoff evidence."
        ),
        (
            "10. Rollback note: revert through AWS LZA pipeline history; do not "
            "hand-edit generated artifacts."
        ),
        "",
        "## Manual Gates",
        "",
        "- Architecture owner approves unresolved decisions are zero.",
        "- Security owner approves logging/security services and IAM Identity Center scope.",
        "- Network owner approves CIDRs, TGW attachments, and routing boundaries.",
        "- Release owner confirms AWS LZA pipeline prereqs and rollback owner.",
        "",
        "## Dependencies",
        "",
        "- AWS Organizations or Control Tower baseline exists before LZA deploy.",
        "- Account vending/email ownership complete before accounts config deploy.",
        "- Identity Center delegated admin exists before IAM config deploy.",
        "- Network CIDR/IPAM plan approved before network config deploy.",
        "",
        "## Rollback",
        "",
        "- Stop AWS LZA pipeline before re-running with corrected config.",
        "- Revert to previous known-good LZA config commit.",
        "- Keep generated reports as evidence; regenerate after decision changes.",
        "",
        "## Boundary",
        "",
        "This handoff does not generate a parallel Terraform or Terragrunt landing-zone stack.",
        "Use AWS LZA for landing-zone deployment unless a documented gap requires custom IaC.",
    ]
    if readiness:
        lines.extend(
            [
                "",
                "## Deployment Readiness",
                "",
                f"- Status: `{readiness.get('status', 'unknown')}`",
                f"- Deployment allowed: `{readiness.get('deploymentAllowed', False)}`",
            ]
        )
    (output_dir / "deployment-runbook.md").write_text("\n".join(lines) + "\n")


def gen_lza_decision_report(intent: Any, output_dir: Path) -> None:
    readiness = getattr(intent, "deployment_readiness", {})
    intent = _aws_lza_intent(intent)
    if intent is None:
        return
    data = {
        "pattern": "aws-lza",
        "baseline": str(intent.baseline),
        "orgMode": str(intent.org_mode),
        "organizationName": intent.organization_name,
        "homeRegion": intent.home_region,
        "enabledRegions": intent.enabled_regions,
        "organizationalUnits": intent.organizational_units,
        "accounts": {
            "audit": intent.audit_account,
            "logArchive": intent.log_archive_account,
            "securityTooling": intent.security_tooling_account,
            "network": intent.network_account,
            "workloads": intent.workload_accounts,
        },
        "identity": {
            "identityCenterDelegatedAdmin": intent.identity_center_delegated_admin_account,
            "identityCenterPermissionSets": intent.identity_center_permission_sets,
            "identityCenterAssignments": intent.identity_center_assignments,
        },
        "network": {
            "topology": str(intent.topology),
            "cidr": intent.network_cidr,
        },
        "security": {
            "centralizedLogging": intent.centralized_logging,
            "securityHubEnabled": intent.security_hub_enabled,
            "guardDutyEnabled": intent.guardduty_enabled,
            "complianceOverlay": str(intent.compliance_overlay),
        },
    }
    if readiness:
        data["deploymentReadiness"] = readiness
    _write_yaml(output_dir, "decision-report.yaml", data)
