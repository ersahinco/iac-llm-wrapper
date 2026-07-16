"""AWS LZA typed semantic model and predicate constraints."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from typing import TypeVar

from intent_engine.core.semantic_model import (
    PredicateConstraint,
    PredicateStatus,
    SemanticEntity,
    SemanticModel,
    SemanticRelationship,
)

from .contracts import AWS_LZA_CONFIG_ARTIFACTS
from .models import (
    AwsLzaIntent,
    LzaAccount,
    LzaControl,
    LzaIdentityCenterAssignment,
    LzaOrganizationalUnit,
    LzaPermissionSet,
)
from .utils import (
    _INFRASTRUCTURE_OU,
    _MANAGEMENT_ACCOUNT,
    _SECURITY_OU,
    _WORKLOADS_OU,
)

_ROOT_OU = "Root"
T = TypeVar("T")


def build_aws_lza_semantic_model(intent: AwsLzaIntent) -> SemanticModel:
    """Build a typed property graph from AWS LZA handoff decisions."""

    ous = _organizational_units(intent)
    accounts = _accounts(intent)
    permission_sets = _permission_sets(intent)
    parsed_assignments = _assignments(intent)
    controls = _controls(intent)
    entities = [
        *(
            SemanticEntity(
                kind="OU",
                key=_key("ou", ou.name),
                label=ou.name,
                properties={"description": ou.description},
            )
            for ou in ous
        ),
        *(
            SemanticEntity(
                kind="Account",
                key=_key("account", account.name),
                label=account.name,
                properties={
                    "ou": account.ou,
                    "description": account.description,
                    "accountType": account.account_type,
                },
            )
            for account in accounts
        ),
        *(
            SemanticEntity(
                kind="PermissionSet",
                key=_key("permission-set", permission_set.name),
                label=permission_set.name,
                properties={"description": permission_set.description},
            )
            for permission_set in permission_sets
        ),
        *(
            SemanticEntity(
                kind="Assignment",
                key=_assignment_key(assignment),
                label=(
                    f"{assignment.principal}:{assignment.permission_set}:"
                    f"{assignment.target_account}"
                ),
                properties={
                    "principal": assignment.principal,
                    "principalType": "GROUP",
                    "permissionSet": assignment.permission_set,
                    "targetAccount": assignment.target_account,
                },
            )
            for assignment in parsed_assignments
        ),
        *(
            SemanticEntity(
                kind="Control",
                key=_key("control", control.name),
                label=control.name,
                properties={"enabled": control.enabled, "category": control.category},
            )
            for control in controls
        ),
        *(
            SemanticEntity(
                kind="Artifact",
                key=_key("artifact", artifact),
                label=artifact,
                properties={"contract": "aws-lza-sample-config"},
            )
            for artifact in AWS_LZA_CONFIG_ARTIFACTS
        ),
    ]
    relationships = [
        *(
            SemanticRelationship(
                source=_key("account", account.name),
                relationship="belongs_to",
                target=_key("ou", account.ou or _ROOT_OU),
            )
            for account in accounts
            if account.ou
        ),
        *(
            SemanticRelationship(
                source=_assignment_key(assignment),
                relationship="references_entity",
                target=_key("permission-set", assignment.permission_set),
            )
            for assignment in parsed_assignments
            if assignment.permission_set
        ),
        *(
            SemanticRelationship(
                source=_assignment_key(assignment),
                relationship="requires_entity",
                target=_key("account", assignment.target_account),
            )
            for assignment in parsed_assignments
            if assignment.target_account
        ),
        *(
            SemanticRelationship(
                source=_key("control", control.name),
                relationship="produces_artifact",
                target=_key("artifact", _control_artifact(control.name)),
            )
            for control in controls
        ),
    ]
    return SemanticModel(
        schema_version="intent-engine/aws-lza-semantic-model/v1",
        entities=entities,
        relationships=relationships,
        constraints=_constraints(intent, ous, accounts, permission_sets),
    )


def _constraints(
    intent: AwsLzaIntent,
    ous: list[LzaOrganizationalUnit],
    accounts: list[LzaAccount],
    permission_sets: list[LzaPermissionSet],
) -> list[PredicateConstraint]:
    ou_names = {item.name for item in ous}
    account_names = {item.name for item in accounts}
    account_ous = {item.name: item.ou for item in accounts}
    permission_set_names = {item.name for item in permission_sets}
    workload_ous = {
        account_ous.get(account_name, _WORKLOADS_OU) for account_name in intent.workload_accounts
    }
    workload_capable_ous = ou_names - {_ROOT_OU, _SECURITY_OU, _INFRASTRUCTURE_OU}
    explicit_workload_ous = {
        account.name: account.ou
        for account in intent.accounts
        if account.name in intent.workload_accounts and account.ou.strip()
    }
    ambiguous_workload_accounts = sorted(
        set(intent.workload_accounts) - set(explicit_workload_ous)
        if len(workload_capable_ous) > 1
        else set()
    )
    constraints = [
        _constraint(
            key="security-ou-present",
            label="Security OU exists",
            expression={"requires_entity": {"kind": "OU", "name": _SECURITY_OU}},
            passed=_SECURITY_OU in ou_names,
            evidence=f"organizational_units={sorted(ou_names)}",
            code="AWS_LZA_SECURITY_OU_REQUIRED",
            message="AWS LZA baseline requires a Security OU for audit and log accounts.",
        ),
        _constraint(
            key="hub-spoke-infrastructure-ou",
            label="Hub-spoke has Infrastructure OU",
            expression={
                "applies_when": {"equals": {"decision": "topology", "value": "hub-spoke"}},
                "requires_entity": {"kind": "OU", "name": _INFRASTRUCTURE_OU},
            },
            passed=str(intent.topology) != "hub-spoke" or _INFRASTRUCTURE_OU in ou_names,
            evidence=f"topology={intent.topology}; organizational_units={sorted(ou_names)}",
            code="AWS_LZA_INFRASTRUCTURE_OU_REQUIRED",
            message="Hub-spoke topology requires an Infrastructure OU for the network account.",
        ),
        _constraint(
            key="workload-account-ou-placement-explicit",
            label="Workload account OU placement is explicit when multiple OUs are eligible",
            expression={
                "applies_when": {
                    "multiple_workload_ous": sorted(workload_capable_ous),
                },
                "explicit_relationship": {
                    "source": "workload_accounts",
                    "relationship": "belongs_to",
                    "target": "organizational_units",
                },
            },
            passed=not ambiguous_workload_accounts,
            evidence=(
                f"workload_capable_ous={sorted(workload_capable_ous)}; "
                f"explicit_placements={explicit_workload_ous}; "
                f"unmapped_accounts={ambiguous_workload_accounts}"
            ),
            code="AWS_LZA_WORKLOAD_ACCOUNT_OU_AMBIGUOUS",
            message=(
                "Multiple workload-capable OUs exist, so every workload account must be "
                "mapped explicitly with '- AccountName: ou=OUName' under an Accounts or "
                "Account Inventory heading."
            ),
        ),
        _constraint(
            key="workload-account-ous-exist",
            label="Workload account OUs exist",
            expression={
                "applies_when": {"present": {"decision": "workload_accounts"}},
                "requires_entity": {"kind": "OU", "names": sorted(workload_ous)},
            },
            passed=workload_ous.issubset(ou_names),
            evidence=(
                f"workload_accounts={intent.workload_accounts}; "
                f"required_ous={sorted(workload_ous)}; ous={sorted(ou_names)}"
            ),
            code="AWS_LZA_WORKLOADS_OU_REQUIRED",
            message=(
                "Workload account OU placements must reference organizational units "
                "defined in organization-config.yaml."
            ),
        ),
        _constraint(
            key="centralized-logging-log-archive-account",
            label="Centralized logging has log archive account",
            expression={
                "applies_when": {"equals": {"decision": "centralized_logging", "value": True}},
                "present": {"decision": "log_archive_account"},
            },
            passed=not intent.centralized_logging or bool(intent.log_archive_account.strip()),
            evidence=f"centralized_logging={intent.centralized_logging}; "
            f"log_archive_account={intent.log_archive_account}",
            code="AWS_LZA_LOG_ARCHIVE_ACCOUNT_REQUIRED",
            message="Centralized logging requires a log archive account.",
        ),
        _constraint(
            key="centralized-logging-audit-account",
            label="Centralized logging has audit account",
            expression={
                "applies_when": {"equals": {"decision": "centralized_logging", "value": True}},
                "present": {"decision": "audit_account"},
            },
            passed=not intent.centralized_logging or bool(intent.audit_account.strip()),
            evidence=f"centralized_logging={intent.centralized_logging}; "
            f"audit_account={intent.audit_account}",
            code="AWS_LZA_AUDIT_ACCOUNT_REQUIRED",
            message="Centralized logging requires an audit account.",
        ),
        _constraint(
            key="security-tooling-account-present",
            label="Security tooling account exists",
            expression={"present": {"decision": "security_tooling_account"}},
            passed=bool(intent.security_tooling_account.strip()),
            evidence=f"security_tooling_account={intent.security_tooling_account}",
            code="AWS_LZA_SECURITY_TOOLING_ACCOUNT_REQUIRED",
            message="AWS LZA handoff requires a security tooling account.",
        ),
        _constraint(
            key="identity-admin-known-account",
            label="Identity Center delegated admin is known",
            expression={
                "references_known": {
                    "source": "identity_center_delegated_admin_account",
                    "target": "accounts.name",
                }
            },
            passed=intent.identity_center_delegated_admin_account in account_names,
            evidence=f"delegated_admin={intent.identity_center_delegated_admin_account}; "
            f"accounts={sorted(account_names)}",
            code="AWS_LZA_IDENTITY_CENTER_ADMIN_UNKNOWN",
            message="Identity Center delegated administrator must reference a known account.",
        ),
        _constraint(
            key="identity-admin-security-ou",
            label="Identity Center delegated admin belongs to Security OU",
            expression={
                "references_entity": {
                    "source": "identity_center_delegated_admin_account",
                    "relationship": "belongs_to",
                    "target": {"kind": "OU", "name": _SECURITY_OU},
                }
            },
            passed=account_ous.get(intent.identity_center_delegated_admin_account) == _SECURITY_OU,
            evidence=f"delegated_admin={intent.identity_center_delegated_admin_account}; "
            f"ou={account_ous.get(intent.identity_center_delegated_admin_account, '<unknown>')}",
            code="AWS_LZA_IDENTITY_CENTER_ADMIN_SECURITY_OU_REQUIRED",
            message="Identity Center delegated administrator must belong to the Security OU.",
        ),
        _constraint(
            key="home-region-enabled",
            label="Home region is enabled",
            expression={
                "contains": {
                    "decision": "enabled_regions",
                    "value_from": "home_region",
                }
            },
            passed=intent.home_region in intent.enabled_regions,
            evidence=f"home_region={intent.home_region}; enabled_regions={intent.enabled_regions}",
            code="AWS_LZA_HOME_REGION_NOT_ENABLED",
            message="Home region must be present in enabled regions.",
        ),
        _constraint(
            key="network-cidr-valid",
            label="Network CIDR is valid",
            expression={"cidr_valid": {"decision": "network_cidr"}},
            passed=_cidr_valid(intent.network_cidr),
            evidence=f"network_cidr={intent.network_cidr}",
            code="AWS_LZA_NETWORK_CIDR_INVALID",
            message="Network CIDR must be a valid IPv4 or IPv6 network.",
        ),
    ]
    constraints.extend(_account_conflict_constraints(intent))
    for index, raw_assignment in enumerate(intent.identity_center_assignments, 1):
        parts = _assignment_parts(raw_assignment)
        constraints.append(
            _constraint(
                key=f"identity-assignment-format-{index}",
                label="Identity Center assignment has Principal:PermissionSet:Account shape",
                expression={
                    "shape": {
                        "decision": "identity_center_assignments",
                        "format": "Principal:PermissionSet:Account",
                    }
                },
                passed=len(parts) == 3 and all(parts),
                evidence=raw_assignment,
                code="AWS_LZA_IDENTITY_CENTER_ASSIGNMENT_FORMAT_INVALID",
                message=(
                    "Identity Center assignments must use Principal:PermissionSet:Account format."
                ),
            )
        )
        if len(parts) != 3 or not all(parts):
            continue
        constraints.append(
            _constraint(
                key=f"identity-assignment-permission-set-{index}",
                label="Identity Center assignment references approved permission set",
                expression={
                    "references_known": {
                        "source": "identity_center_assignments.permission_set",
                        "target": "identity_center_permission_sets.name",
                    }
                },
                passed=parts[1] in permission_set_names,
                evidence=raw_assignment,
                code="AWS_LZA_IDENTITY_CENTER_ASSIGNMENT_PERMISSION_SET_UNKNOWN",
                message="Identity Center assignments must reference approved permission sets.",
            )
        )
        constraints.append(
            _constraint(
                key=f"identity-assignment-account-{index}",
                label="Identity Center assignment targets known account",
                expression={
                    "references_known": {
                        "source": "identity_center_assignments.target_account",
                        "target": "accounts.name",
                    }
                },
                passed=parts[2] in account_names or parts[2] == _MANAGEMENT_ACCOUNT,
                evidence=raw_assignment,
                code="AWS_LZA_IDENTITY_CENTER_ASSIGNMENT_ACCOUNT_UNKNOWN",
                message="Identity Center assignments must target known accounts.",
            )
        )
    return constraints


def _organizational_units(intent: AwsLzaIntent) -> list[LzaOrganizationalUnit]:
    items = [
        LzaOrganizationalUnit(name=_ROOT_OU, description="AWS Organizations root"),
        *(LzaOrganizationalUnit(name=name) for name in intent.organizational_units),
        *intent.ous,
    ]
    return _dedupe_by_name(item for item in items if item.name.strip())


def _accounts(intent: AwsLzaIntent) -> list[LzaAccount]:
    return _dedupe_accounts(item for item in _account_items(intent) if item.name.strip())


def _account_items(intent: AwsLzaIntent) -> list[LzaAccount]:
    explicit_account_ous = {
        account.name: account.ou
        for account in intent.accounts
        if account.name.strip() and account.ou.strip()
    }
    return [
        LzaAccount(name=_MANAGEMENT_ACCOUNT, ou=_ROOT_OU, account_type="management"),
        LzaAccount(name=intent.log_archive_account, ou=_SECURITY_OU, account_type="log-archive"),
        LzaAccount(name=intent.audit_account, ou=_SECURITY_OU, account_type="audit"),
        LzaAccount(
            name=intent.security_tooling_account,
            ou=_SECURITY_OU,
            account_type="security-tooling",
        ),
        *(
            [
                LzaAccount(
                    name=intent.network_account,
                    ou=_INFRASTRUCTURE_OU,
                    account_type="network",
                )
            ]
            if str(intent.topology) == "hub-spoke" and intent.network_account.strip()
            else []
        ),
        *(
            LzaAccount(
                name=name,
                ou=explicit_account_ous.get(name, _WORKLOADS_OU),
                account_type="workload",
            )
            for name in intent.workload_accounts
        ),
        *intent.accounts,
    ]


def _account_conflict_constraints(intent: AwsLzaIntent) -> list[PredicateConstraint]:
    by_name: dict[str, list[LzaAccount]] = {}
    for account in _account_items(intent):
        name = account.name.strip()
        if not name:
            continue
        by_name.setdefault(name, []).append(account)

    constraints: list[PredicateConstraint] = []
    for name, accounts in sorted(by_name.items()):
        if len(accounts) < 2:
            continue
        ous = sorted({account.ou for account in accounts if account.ou.strip()})
        account_types = sorted(
            {
                account.account_type
                for account in accounts
                if account.account_type.strip() and account.account_type != "workload"
            }
        )
        ou_conflict = len(ous) > 1
        type_conflict = len(account_types) > 1
        if not ou_conflict and not type_conflict:
            continue
        constraints.append(
            _constraint(
                key=f"account-conflict-{_key('account', name).split(':', 1)[1]}",
                label="Account entity has one placement and type",
                expression={
                    "unique_entity_properties": {
                        "kind": "Account",
                        "name": name,
                        "properties": ["ou", "accountType"],
                    }
                },
                passed=False,
                evidence=(
                    f"account={name}; ous={ous or ['<empty>']}; "
                    f"account_types={account_types or ['workload']}"
                ),
                code="AWS_LZA_ACCOUNT_ENTITY_CONFLICT",
                message=(
                    "Account entities with the same name must not declare conflicting "
                    "OU placement or account type."
                ),
            )
        )
    return constraints


def _permission_sets(intent: AwsLzaIntent) -> list[LzaPermissionSet]:
    items = [LzaPermissionSet(name=name) for name in intent.identity_center_permission_sets]
    return _dedupe_by_name(item for item in items if item.name.strip())


def _assignments(intent: AwsLzaIntent) -> list[LzaIdentityCenterAssignment]:
    parsed = []
    for raw_assignment in intent.identity_center_assignments:
        parts = _assignment_parts(raw_assignment)
        if len(parts) != 3 or not all(parts):
            continue
        parsed.append(
            LzaIdentityCenterAssignment(
                principal=parts[0],
                permission_set=parts[1],
                target_account=parts[2],
            )
        )
    return parsed


def _controls(intent: AwsLzaIntent) -> list[LzaControl]:
    items = [
        LzaControl(name="centralized-logging", enabled=intent.centralized_logging),
        LzaControl(name="security-hub", enabled=intent.security_hub_enabled),
        LzaControl(name="guardduty", enabled=intent.guardduty_enabled),
        LzaControl(
            name=f"compliance-overlay:{intent.compliance_overlay}",
            enabled=str(intent.compliance_overlay) != "none",
            category="compliance",
        ),
    ]
    return _dedupe_by_name(items)


def _constraint(
    *,
    key: str,
    label: str,
    expression: dict[str, object],
    passed: bool,
    evidence: str,
    code: str,
    message: str,
) -> PredicateConstraint:
    return PredicateConstraint(
        key=key,
        label=label,
        expression=expression,
        status=PredicateStatus.PASS if passed else PredicateStatus.FAIL,
        evidence=evidence,
        violation_code=code,
        violation_message=message,
    )


def _assignment_parts(value: str) -> list[str]:
    return [part.strip() for part in value.split(":")]


def _assignment_key(assignment: LzaIdentityCenterAssignment) -> str:
    return _key(
        "assignment",
        f"{assignment.principal}:{assignment.permission_set}:{assignment.target_account}",
    )


def _key(kind: str, name: str) -> str:
    normalized = "-".join(part for part in name.lower().replace("_", "-").split() if part)
    normalized = "".join(char for char in normalized if char.isalnum() or char in "-:.")
    return f"{kind}:{normalized or 'unknown'}"


def _dedupe_by_name(items: Iterable[T]) -> list[T]:
    by_name: dict[str, T] = {}
    for item in items:
        name = getattr(item, "name", "").strip()
        if not name:
            continue
        by_name.setdefault(name, item)
    return list(by_name.values())


def _dedupe_accounts(items: Iterable[LzaAccount]) -> list[LzaAccount]:
    by_name: dict[str, LzaAccount] = {}
    for item in items:
        current = by_name.get(item.name)
        if current is None:
            by_name[item.name] = item
            continue
        updates = {}
        if not current.ou and item.ou:
            updates["ou"] = item.ou
        if current.description == "" and item.description:
            updates["description"] = item.description
        if current.account_type == "workload" and item.account_type != "workload":
            updates["account_type"] = item.account_type
        if updates:
            by_name[item.name] = current.model_copy(update=updates)
    return list(by_name.values())


def _control_artifact(control_name: str) -> str:
    if control_name == "centralized-logging":
        return "global-config.yaml"
    if control_name in {"security-hub", "guardduty"} or control_name.startswith(
        "compliance-overlay:"
    ):
        return "security-config.yaml"
    return "decision-report.yaml"


def _cidr_valid(value: str) -> bool:
    try:
        ipaddress.ip_network(value, strict=False)
    except ValueError:
        return False
    return True
