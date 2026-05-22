"""LZA-specific validation logic.

These validators are registered as extra_validators on LZA patterns.
They handle cross-field and list-item checks that are hard to express
in the requirement graph (e.g., workload target_account, ECS runtime +
network mode, hub-spoke + network account, private CI/CD + placement,
egress inspection completeness, hybrid config completeness).
"""

from __future__ import annotations

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
