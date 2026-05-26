"""LZA-specific validation logic.

These validators are registered as extra_validators on LZA patterns.
They handle cross-field and list-item checks that are hard to express
in the requirement graph (e.g., workload target_account, ECS runtime +
network mode, hub-spoke + network account, private CI/CD + placement,
egress inspection completeness, hybrid config completeness).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from intent_engine.core.requirements import RequirementGraph
from intent_engine.core.validator import Violation


def _graph_has(graph: RequirementGraph | None, requirement_key: str) -> bool:
    """Check if a graph has the given requirement key and it is applicable."""
    if graph is None:
        return True
    if requirement_key not in graph._requirements:
        return False
    return graph.is_applicable(requirement_key) and not graph.is_blocked(requirement_key)


def validate_lza_intent(intent: Any, graph: RequirementGraph | None = None) -> list[Violation]:
    """Validate LZA-specific cross-field constraints.

    Uses optional graph context to skip checks for requirements that
    don't apply to the current pattern.
    """
    violations: list[Violation] = []

    # Workload constraints: each workload needs a target_account
    # Only enforce when the graph has workload-related requirements
    has_workload_graph = _graph_has(graph, "target_account") or _graph_has(graph, "workload_name")
    if has_workload_graph and hasattr(intent, "workloads"):
        for w in intent.workloads:
            if hasattr(w, "target_account") and not w.target_account:
                violations.append(
                    Violation(
                        code="WORKLOAD_TARGET_ACCOUNT_REQUIRED",
                        message=(
                            f"Workload '{w.name}' requires a target_account. "
                            f"Add 'target_account=<account>' to the workload line."
                        ),
                    )
                )

            if (
                hasattr(w, "runtime")
                and hasattr(w, "network_mode")
                and w.runtime
                and w.runtime.startswith("ecs")
                and str(getattr(w.network_mode, "value", w.network_mode)).lower() == "public"
            ):
                violations.append(
                    Violation(
                        code="PRIVATE_ECS_REQUIRES_PRIVATE_NETWORKING",
                        message=(
                            f"ECS workload '{w.name}' with public networking is not allowed. "
                            f"Change to 'network_mode=private' for private ECS workloads."
                        ),
                    )
                )

    # Hub-spoke topology requires central Network account
    # Only enforced when the graph has the central_network_account requirement
    if _graph_has(graph, "central_network_account"):
        if (
            hasattr(intent, "topology")
            and hasattr(intent, "network")
            and hasattr(intent.network, "central_network_account")
            and str(getattr(intent.topology, "value", intent.topology)).lower() == "hub-spoke"
            and not intent.network.central_network_account
        ):
            violations.append(
                Violation(
                    code="HUB_SPOKE_NETWORK_ACCOUNT_REQUIRED",
                    message=(
                        "Hub-spoke topology requires a central Network account. "
                        "Add '- central_network_account: <name>' to your Network section."
                    ),
                )
            )

    # Private CI/CD requires placement
    if _graph_has(graph, "cicd_placement"):
        if (
            hasattr(intent, "cicd")
            and hasattr(intent.cicd, "mode")
            and hasattr(intent.cicd, "placement")
            and getattr(intent.cicd.mode, "value", str(intent.cicd.mode)) == "private"
            and not intent.cicd.placement
        ):
            violations.append(
                Violation(
                    code="PRIVATE_CICD_PLACEMENT_REQUIRED",
                    message=(
                        "Private CI/CD requires placement configuration. "
                        "Add '- placement: <vpc/subnet>' to your CI/CD section."
                    ),
                )
            )

    # Egress inspection completeness
    if _graph_has(graph, "egress_inspection"):
        if hasattr(intent, "security") and hasattr(intent.security, "egress_inspection"):
            inspection_val = getattr(
                intent.security.egress_inspection, "value", str(intent.security.egress_inspection)
            )
            if inspection_val == "required":
                if not intent.security.inspection_pattern and not intent.security.inspection_vendor:
                    violations.append(
                        Violation(
                            code="EGRESS_INSPECTION_INCOMPLETE",
                            message=(
                                "Egress inspection is 'required' but no pattern or vendor specified"
                            ),
                        )
                    )

    # Hybrid configuration completeness
    if _graph_has(graph, "hybrid_dns_model"):
        if hasattr(intent, "hybrid") and getattr(intent.hybrid, "required", False):
            missing = []
            if hasattr(intent.hybrid, "dns_model") and not intent.hybrid.dns_model:
                missing.append("dns_model")
            if hasattr(intent.hybrid, "ip_model") and not intent.hybrid.ip_model:
                missing.append("ip_model")
            if hasattr(intent.hybrid, "on_prem_cidrs") and not intent.hybrid.on_prem_cidrs:
                missing.append("on_prem_cidrs")
            if missing:
                violations.append(
                    Violation(
                        code="HYBRID_CONFIG_INCOMPLETE",
                        message=(
                            f"Hybrid connectivity is enabled but missing: {', '.join(missing)}."
                        ),
                    )
                )

    return violations


def validate_lza_artifacts(output_dir: Path) -> list[str]:
    """Validate generated LZA artifacts for cross-file consistency.

    Checks:
    - Workload targetAccount values exist in accounts-config.yaml
    - Network centralNetworkAccount exists in accounts-config.yaml
    - Account OU values exist in organization-config.yaml
    - All config files have required top-level keys
    """
    errors: list[str] = []
    import ruamel.yaml

    yaml = ruamel.yaml.YAML(typ="safe")

    # Load reference files
    accounts_data = None
    org_data = None

    accounts_path = output_dir / "accounts-config.yaml"
    if accounts_path.exists():
        with open(accounts_path) as f:
            accounts_data = yaml.load(f)

    org_path = output_dir / "organization-config.yaml"
    if org_path.exists():
        with open(org_path) as f:
            org_data = yaml.load(f)

    # Collect valid account names
    valid_accounts: set[str] = set()
    if accounts_data and isinstance(accounts_data, dict):
        for acct in accounts_data.get("accounts") or []:
            if isinstance(acct, dict) and "name" in acct:
                valid_accounts.add(acct["name"])

    # Collect valid OU names
    valid_ous: set[str] = set()
    if org_data and isinstance(org_data, dict):
        for ou in org_data.get("organizationalUnits") or []:
            if isinstance(ou, dict) and "name" in ou:
                valid_ous.add(ou["name"])

    # Check workload target accounts
    for wl_path in sorted(output_dir.glob("workload-*.yaml")):
        with open(wl_path) as f:
            wl_data = yaml.load(f)
        if isinstance(wl_data, dict):
            workload = wl_data.get("workload", {})
            target = workload.get("account")
            if target and target not in valid_accounts:
                errors.append(
                    f"Workload '{workload.get('name', wl_path.stem)}' "
                    f"targetAccount '{target}' not found in accounts-config.yaml"
                )

    # Check network centralNetworkAccount
    net_path = output_dir / "network-config.yaml"
    if net_path.exists():
        with open(net_path) as f:
            net_data = yaml.load(f)
        if isinstance(net_data, dict):
            network = net_data.get("network", {})
            central = network.get("centralNetworkAccount")
            if central and central not in valid_accounts:
                errors.append(
                    f"network-config.yaml centralNetworkAccount '{central}' "
                    f"not found in accounts-config.yaml"
                )

    # Check account OU references
    if accounts_data and isinstance(accounts_data, dict):
        for acct in accounts_data.get("accounts") or []:
            if isinstance(acct, dict):
                ou = acct.get("ou")
                if ou and ou not in valid_ous:
                    errors.append(
                        f"Account '{acct.get('name')}' references OU '{ou}' "
                        f"not found in organization-config.yaml"
                    )

    # Check top-level keys in config files
    required_keys = {
        "organization-config.yaml": ["organization"],
        "accounts-config.yaml": ["accounts"],
        "global-config.yaml": ["global"],
        "security-config.yaml": ["security"],
        "network-config.yaml": ["network"],
    }
    for fname, keys in required_keys.items():
        fpath = output_dir / fname
        if fpath.exists():
            with open(fpath) as f:
                data = yaml.load(f)
            if not isinstance(data, dict):
                errors.append(f"{fname}: expected dict at top level")
                continue
            for key in keys:
                if key not in data:
                    errors.append(f"{fname}: missing required key '{key}'")

    return errors
