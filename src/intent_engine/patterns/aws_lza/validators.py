"""AWS LZA pattern validators."""

from __future__ import annotations

from intent_engine.core.validator import Violation

from .models import AwsLzaIntent
from .utils import (
    _INFRASTRUCTURE_OU,
    _MANAGEMENT_ACCOUNT,
    _SECURITY_OU,
    _WORKLOADS_OU,
    _normalized_ous,
)


def validate_aws_lza_intent(intent: AwsLzaIntent, graph=None) -> list[Violation]:
    violations: list[Violation] = []
    ous = _normalized_ous(intent)
    if _SECURITY_OU.lower() not in ous:
        violations.append(
            Violation(
                code="AWS_LZA_SECURITY_OU_REQUIRED",
                message="AWS LZA baseline requires a Security OU for audit and log accounts.",
            )
        )
    if intent.topology == "hub-spoke" and _INFRASTRUCTURE_OU.lower() not in ous:
        violations.append(
            Violation(
                code="AWS_LZA_INFRASTRUCTURE_OU_REQUIRED",
                message="Hub-spoke topology requires an Infrastructure OU for the network account.",
            )
        )
    if intent.workload_accounts and _WORKLOADS_OU.lower() not in ous:
        violations.append(
            Violation(
                code="AWS_LZA_WORKLOADS_OU_REQUIRED",
                message="Workload accounts require a Workloads OU in organization-config.yaml.",
            )
        )
    if intent.centralized_logging and not intent.log_archive_account.strip():
        violations.append(
            Violation(
                code="AWS_LZA_LOG_ARCHIVE_ACCOUNT_REQUIRED",
                message="Centralized logging requires a log archive account.",
            )
        )
    if intent.centralized_logging and not intent.audit_account.strip():
        violations.append(
            Violation(
                code="AWS_LZA_AUDIT_ACCOUNT_REQUIRED",
                message="Centralized logging requires an audit account.",
            )
        )
    if not intent.security_tooling_account.strip():
        violations.append(
            Violation(
                code="AWS_LZA_SECURITY_TOOLING_ACCOUNT_REQUIRED",
                message="AWS LZA handoff requires a security tooling account.",
            )
        )
    all_accounts = {
        intent.audit_account,
        intent.log_archive_account,
        intent.security_tooling_account,
        intent.network_account,
        *intent.workload_accounts,
    }
    if intent.identity_center_delegated_admin_account not in all_accounts:
        violations.append(
            Violation(
                code="AWS_LZA_IDENTITY_CENTER_ADMIN_UNKNOWN",
                message="Identity Center delegated administrator must reference a known account.",
            )
        )
    permission_sets = set(intent.identity_center_permission_sets)
    for assignment in intent.identity_center_assignments:
        parts = [part.strip() for part in assignment.split(":") if part.strip()]
        if len(parts) < 3:
            violations.append(
                Violation(
                    code="AWS_LZA_IDENTITY_CENTER_ASSIGNMENT_FORMAT_INVALID",
                    message=(
                        "Identity Center assignments must use "
                        "Principal:PermissionSet:Account format."
                    ),
                )
            )
            continue
        if parts[1] not in permission_sets:
            violations.append(
                Violation(
                    code="AWS_LZA_IDENTITY_CENTER_ASSIGNMENT_PERMISSION_SET_UNKNOWN",
                    message="Identity Center assignments must reference approved permission sets.",
                )
            )
        if parts[2] not in all_accounts and parts[2] != _MANAGEMENT_ACCOUNT:
            violations.append(
                Violation(
                    code="AWS_LZA_IDENTITY_CENTER_ASSIGNMENT_ACCOUNT_UNKNOWN",
                    message="Identity Center assignments must target known accounts.",
                )
            )
    if intent.home_region not in intent.enabled_regions:
        violations.append(
            Violation(
                code="AWS_LZA_HOME_REGION_NOT_ENABLED",
                message="Home region must be present in enabled regions.",
            )
        )
    return violations
