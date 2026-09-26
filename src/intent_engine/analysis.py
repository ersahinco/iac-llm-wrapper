"""Deterministic gap and conflict analysis.

Nothing here asks a model anything. Gaps come from graph applicability, conflicts
come from named rules. Each rule names its own cause: a missing answer, an
unusable value, and two answers that cannot both hold are three different
findings with three different fixes.
"""

from __future__ import annotations

from collections.abc import Callable
from ipaddress import ip_network
from typing import Any

from .catalog import coerce
from .graph import KnowledgeGraph
from .models import Conflict, Decision, Fact, Review

_STRICT_OVERLAYS = {"regulated", "financial-services", "healthcare"}
_IMPLICIT_ACCOUNTS = {"Management"}
_ACCOUNT_KEYS = (
    "audit_account",
    "log_archive_account",
    "security_tooling_account",
    "network_account",
)


def raw_values(facts: list[Fact]) -> dict[str, str]:
    """First stated answer per decision. Duplicates are reported as conflicts."""
    values: dict[str, str] = {}
    for fact in facts:
        values.setdefault(fact.decision_key, fact.value)
    return values


def effective_values(catalog: dict[str, Decision], facts: list[Fact]) -> dict[str, str]:
    """Stated answers, falling back to catalog defaults for gate evaluation only."""
    stated = raw_values(facts)
    return {
        key: stated.get(key) or (decision.default or "")
        for key, decision in catalog.items()
        if stated.get(key) or decision.default
    }


def applicable_keys(catalog: dict[str, Decision], facts: list[Fact]) -> list[str]:
    values = effective_values(catalog, facts)
    applicable: list[str] = []
    for key, decision in catalog.items():
        gate = decision.gate
        if gate is None or values.get(gate.decision) == gate.equals:
            applicable.append(key)
    return applicable


def _origin(facts: list[Fact]) -> dict[str, str]:
    where: dict[str, str] = {}
    for fact in facts:
        where.setdefault(fact.decision_key, f"{fact.section}:{fact.line}")
    return where


def typed_values(
    catalog: dict[str, Decision], facts: list[Fact]
) -> tuple[dict[str, Any], list[Conflict]]:
    """Coerce stated answers. Values that cannot be coerced become conflicts."""
    where = _origin(facts)
    typed: dict[str, Any] = {}
    invalid: list[Conflict] = []
    for key, raw in raw_values(facts).items():
        decision = catalog.get(key)
        if decision is None:
            continue
        try:
            typed[key] = coerce(decision, raw)
        except ValueError as exc:
            invalid.append(
                Conflict(
                    code="UNUSABLE_VALUE",
                    message=str(exc),
                    decision_keys=[key],
                    evidence=[where.get(key, "unknown location")],
                )
            )
    return typed, invalid


def _declared_accounts(values: dict[str, Any]) -> set[str]:
    accounts = set(_IMPLICIT_ACCOUNTS)
    for key in _ACCOUNT_KEYS:
        name = values.get(key)
        if isinstance(name, str):
            accounts.add(name)
    accounts.update(values.get("workload_accounts") or [])
    return accounts


def _rule_home_region(values: dict[str, Any]) -> list[Conflict]:
    home = values.get("home_region")
    enabled = values.get("enabled_regions")
    if not home or not enabled or home in enabled:
        return []
    return [
        Conflict(
            code="HOME_REGION_NOT_ENABLED",
            message=(
                f"home region '{home}' is not in the enabled regions "
                f"({', '.join(enabled)})"
            ),
            decision_keys=["home_region", "enabled_regions"],
        )
    ]


def _rule_network_account_scope(values: dict[str, Any]) -> list[Conflict]:
    if values.get("topology") != "single-vpc" or not values.get("network_account"):
        return []
    return [
        Conflict(
            code="NETWORK_ACCOUNT_NOT_APPLICABLE",
            message=(
                "a shared network account is stated but the topology is single-vpc, "
                "which has no hub account to own"
            ),
            decision_keys=["topology", "network_account"],
        )
    ]


def _rule_network_cidr(values: dict[str, Any]) -> list[Conflict]:
    cidr = values.get("network_cidr")
    if not isinstance(cidr, str):
        return []
    try:
        network = ip_network(cidr, strict=False)
    except ValueError:
        return [
            Conflict(
                code="NETWORK_CIDR_MALFORMED",
                message=f"network CIDR '{cidr}' is not a valid IPv4/IPv6 network",
                decision_keys=["network_cidr"],
            )
        ]
    if network.is_private:
        return []
    return [
        Conflict(
            code="NETWORK_CIDR_NOT_PRIVATE",
            message=f"network CIDR '{cidr}' is publicly routable address space",
            decision_keys=["network_cidr"],
        )
    ]


def _rule_overlay_logging(values: dict[str, Any]) -> list[Conflict]:
    overlay = values.get("compliance_overlay")
    if overlay not in _STRICT_OVERLAYS or values.get("centralized_logging") is not False:
        return []
    return [
        Conflict(
            code="OVERLAY_REQUIRES_CENTRAL_LOGGING",
            message=(
                f"compliance overlay '{overlay}' requires centralized logging, "
                "which is stated as disabled"
            ),
            decision_keys=["compliance_overlay", "centralized_logging"],
        )
    ]


def _rule_overlay_detection(values: dict[str, Any]) -> list[Conflict]:
    overlay = values.get("compliance_overlay")
    if overlay not in _STRICT_OVERLAYS:
        return []
    disabled = [
        key
        for key in ("security_hub_enabled", "guardduty_enabled")
        if values.get(key) is False
    ]
    if not disabled:
        return []
    return [
        Conflict(
            code="OVERLAY_REQUIRES_DETECTION",
            message=(
                f"compliance overlay '{overlay}' requires organization-wide detection, "
                f"but {' and '.join(disabled)} is stated as disabled"
            ),
            decision_keys=["compliance_overlay", *disabled],
        )
    ]


def _rule_assignments(values: dict[str, Any]) -> list[Conflict]:
    assignments = values.get("identity_center_assignments") or []
    permission_sets = set(values.get("identity_center_permission_sets") or [])
    accounts = _declared_accounts(values)
    conflicts: list[Conflict] = []
    for entry in assignments:
        parts = [part.strip() for part in entry.split(":")]
        if len(parts) != 3 or not all(parts):
            conflicts.append(
                Conflict(
                    code="ASSIGNMENT_MALFORMED",
                    message=(
                        f"assignment '{entry}' is not Principal:PermissionSet:Account"
                    ),
                    decision_keys=["identity_center_assignments"],
                )
            )
            continue
        _, permission_set, account = parts
        if permission_sets and permission_set not in permission_sets:
            conflicts.append(
                Conflict(
                    code="ASSIGNMENT_UNKNOWN_PERMISSION_SET",
                    message=(
                        f"assignment '{entry}' uses permission set '{permission_set}', "
                        "which is not in the approved permission sets"
                    ),
                    decision_keys=[
                        "identity_center_assignments",
                        "identity_center_permission_sets",
                    ],
                )
            )
        if account not in accounts:
            conflicts.append(
                Conflict(
                    code="ASSIGNMENT_UNKNOWN_ACCOUNT",
                    message=(
                        f"assignment '{entry}' targets account '{account}', "
                        "which is not a declared account"
                    ),
                    decision_keys=["identity_center_assignments", "workload_accounts"],
                )
            )
    return conflicts


def _rule_account_emails(values: dict[str, Any]) -> list[Conflict]:
    entries = values.get("account_emails") or []
    accounts = _declared_accounts(values)
    conflicts: list[Conflict] = []
    for entry in entries:
        account, separator, email = (part.strip() for part in entry.partition("="))
        if not separator or not account or not email:
            conflicts.append(
                Conflict(
                    code="ACCOUNT_EMAIL_MALFORMED",
                    message=f"account email entry '{entry}' is not Account=email",
                    decision_keys=["account_emails"],
                )
            )
            continue
        if account not in accounts:
            conflicts.append(
                Conflict(
                    code="ACCOUNT_EMAIL_UNKNOWN_ACCOUNT",
                    message=(
                        f"account email entry '{entry}' names account '{account}', "
                        "which is not a declared account"
                    ),
                    decision_keys=["account_emails"],
                )
            )
    return conflicts


def _rule_missing_account_emails(values: dict[str, Any]) -> list[Conflict]:
    entries = values.get("account_emails") or []
    if not entries:
        return []
    covered = {entry.partition("=")[0].strip() for entry in entries}
    uncovered = sorted(_declared_accounts(values) - covered)
    if not uncovered:
        return []
    return [
        Conflict(
            code="ACCOUNT_EMAIL_MISSING",
            message=(
                "declared accounts have no approved root email: " f"{', '.join(uncovered)}"
            ),
            decision_keys=["account_emails"],
        )
    ]


def _rule_workload_ou(values: dict[str, Any]) -> list[Conflict]:
    workloads = values.get("workload_accounts") or []
    units = values.get("organizational_units") or []
    if not workloads or not units or "Workloads" in units:
        return []
    return [
        Conflict(
            code="WORKLOAD_OU_MISSING",
            message=(
                "workload accounts are requested but no 'Workloads' organizational unit "
                f"is declared ({', '.join(units)}); placement is not derivable"
            ),
            decision_keys=["workload_accounts", "organizational_units"],
        )
    ]


def _rule_duplicate_accounts(values: dict[str, Any]) -> list[Conflict]:
    workloads = values.get("workload_accounts") or []
    reserved = {values.get(key) for key in _ACCOUNT_KEYS} | _IMPLICIT_ACCOUNTS
    clashes = sorted({name for name in workloads if name in reserved})
    duplicates = sorted({name for name in workloads if workloads.count(name) > 1})
    conflicts: list[Conflict] = []
    if clashes:
        conflicts.append(
            Conflict(
                code="ACCOUNT_NAME_RESERVED",
                message=(
                    f"workload accounts reuse platform account names: {', '.join(clashes)}"
                ),
                decision_keys=["workload_accounts"],
            )
        )
    if duplicates:
        conflicts.append(
            Conflict(
                code="ACCOUNT_NAME_DUPLICATE",
                message=f"workload accounts are listed twice: {', '.join(duplicates)}",
                decision_keys=["workload_accounts"],
            )
        )
    return conflicts


_RULES: tuple[Callable[[dict[str, Any]], list[Conflict]], ...] = (
    _rule_home_region,
    _rule_network_account_scope,
    _rule_network_cidr,
    _rule_overlay_logging,
    _rule_overlay_detection,
    _rule_assignments,
    _rule_account_emails,
    _rule_missing_account_emails,
    _rule_workload_ou,
    _rule_duplicate_accounts,
)


def semantic_conflicts(catalog: dict[str, Decision], facts: list[Fact]) -> list[Conflict]:
    typed, invalid = typed_values(catalog, facts)
    conflicts = list(invalid)
    for rule in _RULES:
        conflicts.extend(rule(typed))
    return conflicts


def review(graph: KnowledgeGraph, catalog: dict[str, Decision]) -> Review:
    path, sha256 = graph.document()
    facts = graph.facts()
    applicable = applicable_keys(catalog, facts)
    return Review(
        document=path,
        sha256=sha256,
        applicable=sorted(applicable),
        answered=sorted({fact.decision_key for fact in facts}),
        gaps=graph.gaps(applicable),
        conflicts=graph.contradictions() + semantic_conflicts(catalog, facts),
    )
