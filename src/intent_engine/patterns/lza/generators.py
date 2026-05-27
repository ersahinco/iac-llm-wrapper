"""LZA-specific output generators.

These generators produce configuration artifacts for the LZA (Landing Zone
Accelerator) use case. Registry-level pattern scoping is the main isolation
boundary; lightweight guards remain as fallback safety.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import ruamel.yaml

from intent_engine.core.generator import _write, register_generator
from intent_engine.core.module_mapping import ModuleInputs, register_module_mapper

from .models import RawIntent

_DEFAULTS_FILE = Path(__file__).parent / "defaults.yaml"


def _load_lza_generator_config() -> dict:
    with open(_DEFAULTS_FILE) as f:
        return ruamel.yaml.YAML(typ="safe").load(f) or {}


def gen_organization_config(intent: RawIntent, output_dir: Path) -> None:
    if not hasattr(intent, "primary_region"):
        return
    cfg = _load_lza_generator_config()
    org_name = cfg.get("generator", {}).get("organization_name", "")
    data: dict[str, Any] = {
        "organization": {
            "primaryRegion": intent.primary_region,
        },
        "organizationalUnits": [
            {"name": ou.name, "description": ou.description} for ou in getattr(intent, "ous", [])
        ],
    }
    if org_name:
        data["organization"]["organizationName"] = org_name
    _write(output_dir, "organization-config.yaml", data, schema_version="lza-v1")


def gen_accounts_config(intent: RawIntent, output_dir: Path) -> None:
    if not hasattr(intent, "accounts"):
        return
    accounts = []
    for acct in intent.accounts:
        accounts.append(
            {
                "name": acct.name,
                "ou": acct.ou,
                "description": acct.description,
            }
        )
    data = {"accounts": accounts}
    _write(output_dir, "accounts-config.yaml", data, schema_version="lza-v1")


def gen_global_config(intent: RawIntent, output_dir: Path) -> None:
    if not hasattr(intent, "primary_region") or not hasattr(intent, "security"):
        return
    data = {
        "global": {
            "primaryRegion": intent.primary_region,
            "cloudtrail": {
                "organizationTrail": intent.security.cloudtrail_org_trail,
            },
            "kms": {
                "rotationRequired": intent.security.kms_rotation_required,
            },
        },
    }
    _write(output_dir, "global-config.yaml", data, schema_version="lza-v1")


def gen_security_config(intent: RawIntent, output_dir: Path) -> None:
    if not hasattr(intent, "security"):
        return
    data: dict[str, Any] = {
        "security": {
            "audit": {
                "retentionDays": intent.security.audit_retention_days,
            },
            "s3": {
                "blockPublicAccess": intent.security.s3_block_public_access,
            },
            "logging": {
                "centralized": intent.security.centralized_logging,
            },
            "egressInspection": {
                "mode": intent.security.egress_inspection.value
                if intent.security.egress_inspection
                else "none",
            },
        },
    }
    if intent.security.inspection_pattern:
        data["security"]["egressInspection"]["pattern"] = intent.security.inspection_pattern
    if intent.security.inspection_vendor:
        data["security"]["egressInspection"]["vendor"] = intent.security.inspection_vendor
    _write(output_dir, "security-config.yaml", data, schema_version="lza-v1")


def gen_network_config(intent: RawIntent, output_dir: Path) -> None:
    if not hasattr(intent, "network"):
        return
    data: dict[str, Any] = {
        "network": {
            "topology": intent.network.topology.value if intent.network.topology else "single-vpc",
            "cidr": intent.network.cidr,
        },
    }
    if intent.network.central_network_account:
        data["network"]["centralNetworkAccount"] = intent.network.central_network_account
    if intent.network.hub_cidr:
        data["network"]["hubCidr"] = intent.network.hub_cidr
    if intent.network.spoke_cidrs:
        data["network"]["spokeCidrs"] = intent.network.spoke_cidrs
    _write(output_dir, "network-config.yaml", data, schema_version="lza-v1")


def gen_iam_config(intent: RawIntent, output_dir: Path) -> None:
    if not hasattr(intent, "primary_region"):
        return
    cfg = _load_lza_generator_config()
    role_prefix = cfg.get("generator", {}).get("role_prefix", "")
    # LZA IAM Config schema expects flat top-level properties (no "iam:" wrapper)
    data: dict[str, Any] = {"permissionBoundary": "enabled"}
    if role_prefix:
        data["rolePrefix"] = role_prefix
    _write(output_dir, "iam-config.yaml", data, schema_version="lza-v1")


def gen_customizations_config(intent: RawIntent, output_dir: Path) -> None:
    if not hasattr(intent, "cicd"):
        return
    customizations = []
    if intent.cicd.mode and intent.cicd.mode.value == "private" and intent.cicd.vpc_endpoints:
        customizations.append(
            {
                "name": "private-cicd-endpoints",
                "type": "vpc-endpoints",
                "endpoints": intent.cicd.vpc_endpoints,
            }
        )
    data = {"customizations": customizations}
    _write(output_dir, "customizations-config.yaml", data, schema_version="lza-v1")


def gen_decision_report(intent: RawIntent, output_dir: Path, graph=None) -> None:
    if not hasattr(intent, "primary_region"):
        return
    decisions: dict[str, Any] = {
        "primaryRegion": intent.primary_region,
    }
    if hasattr(intent, "network"):
        decisions["topology"] = (
            intent.network.topology.value if intent.network.topology else "single-vpc"
        )
    if hasattr(intent, "accounts"):
        decisions["accounts"] = [a.name for a in intent.accounts]
    if hasattr(intent, "ous"):
        decisions["ous"] = [o.name for o in intent.ous]
    if hasattr(intent, "security"):
        decisions["security"] = {
            "auditRetentionDays": intent.security.audit_retention_days,
            "kmsRotationRequired": intent.security.kms_rotation_required,
            "s3BlockPublicAccess": intent.security.s3_block_public_access,
            "cloudtrailOrgTrail": intent.security.cloudtrail_org_trail,
            "centralizedLogging": intent.security.centralized_logging,
        }
    if hasattr(intent, "secret_management"):
        decisions.setdefault("security", {})["secretManagement"] = {
            "provider": intent.secret_management.provider.value,
            "rotationDays": intent.secret_management.rotation_days,
            "backupEnabled": intent.secret_management.backup_enabled,
        }
    if hasattr(intent, "network"):
        decisions["network"] = {
            "cidr": intent.network.cidr,
            "centralNetworkAccount": intent.network.central_network_account,
        }
    if hasattr(intent, "network_appliance"):
        decisions.setdefault("network", {})["appliance"] = {
            "vendor": intent.network_appliance.vendor,
            "licenseType": intent.network_appliance.license_type.value,
            "haMode": intent.network_appliance.ha_mode.value,
        }
    if hasattr(intent, "cicd"):
        cicd_mode = intent.cicd.mode
        if cicd_mode is not None:
            decisions["cicd"] = {
                "mode": cicd_mode.value,
                "placement": intent.cicd.placement,
                "vpcEndpoints": intent.cicd.vpc_endpoints,
            }
            if hasattr(intent.cicd, "runner") and intent.cicd.runner:
                decisions["cicd"]["runner"] = {
                    "platform": intent.cicd.runner.platform.value
                    if intent.cicd.runner.platform
                    else "enterprise",
                    "tool": intent.cicd.runner.tool.value
                    if intent.cicd.runner.tool
                    else "codepipeline",
                    "ephemeral": intent.cicd.runner.ephemeral,
                }
    if hasattr(intent, "workloads"):
        decisions["workloads"] = [
            {
                "name": w.name,
                "targetAccount": w.target_account,
                "networkMode": w.network_mode.value if w.network_mode else "private",
                "runtime": w.runtime,
                "publicIngress": w.public_ingress,
                "port": w.port,
                "cpu": w.cpu,
                "memory": w.memory,
            }
            for w in intent.workloads
        ]

    # Add WA pillar coverage if graph is provided
    if graph:
        wa_coverage: dict[str, Any] = {}
        for key, req in graph._requirements.items():
            if req.wa_pillars:
                value = graph.get(key)
                if value:
                    for pillar in req.wa_pillars:
                        wa_coverage.setdefault(pillar, []).append(
                            {
                                "decision": key,
                                "value": value,
                                "compliance_controls": req.compliance_controls,
                            }
                        )
        if wa_coverage:
            decisions["wellArchitectedCoverage"] = wa_coverage

        # Add audit trail
        if graph._audit_log:
            decisions["decisionAuditTrail"] = graph.audit_log()

    _write(output_dir, "decision-report.yaml", decisions)


def gen_deployment_graph(intent: RawIntent, output_dir: Path) -> None:
    import networkx as nx

    if not hasattr(intent, "network"):
        return
    g = nx.DiGraph()

    g.add_node("organization")
    g.add_node("accounts")

    if getattr(intent, "accounts", None) or getattr(intent, "ous", None):
        g.add_edge("organization", "accounts")

    has_network = intent.network.topology is not None
    if has_network:
        g.add_node("network")
        g.add_edge("organization", "network")

    g.add_node("security")
    g.add_edge("organization", "security")
    if has_network:
        g.add_edge("network", "security")
    if getattr(intent, "accounts", None):
        g.add_edge("accounts", "security")

    g.add_node("iam")
    g.add_edge("organization", "iam")

    has_customizations = False
    if hasattr(intent, "cicd") and getattr(intent.cicd, "vpc_endpoints", None):
        has_customizations = True
    if has_customizations:
        g.add_node("customizations")
        if has_network:
            g.add_edge("network", "customizations")
        g.add_edge("security", "customizations")

    has_workloads = bool(getattr(intent, "workloads", None))
    if has_workloads:
        g.add_node("workloads")
        g.add_edge("iam", "workloads")
        if has_customizations:
            g.add_edge("customizations", "workloads")
        elif has_network:
            g.add_edge("network", "workloads")

    phases: list[list[str]] = []
    remaining = set(g.nodes)
    while remaining:
        ready = {n for n in remaining if all(p not in remaining for p in g.predecessors(n))}
        if not ready:
            ready = remaining
        phases.append(sorted(ready))
        remaining -= ready

    graph_data = {
        "phases": [{"phase": i + 1, "steps": phase} for i, phase in enumerate(phases)],
        "edges": [{"from": u, "to": v} for u, v in sorted(g.edges())],
    }
    _write(output_dir, "deployment-graph.yaml", graph_data)


def gen_workload_skeleton(intent: RawIntent, output_dir: Path) -> None:
    if not hasattr(intent, "workloads"):
        return
    for w in intent.workloads:
        skeleton = {
            "workload": {
                "name": w.name,
                "account": w.target_account,
                "region": getattr(intent, "primary_region", "unknown"),
                "runtime": w.runtime,
                "networkMode": w.network_mode.value if w.network_mode else "private",
                "publicIngress": w.public_ingress,
                "service": {
                    "port": w.port,
                    "cpu": w.cpu,
                    "memory": w.memory,
                    "taskDefinition": f"{w.name}-task",
                    "cluster": f"{w.name}-cluster",
                },
                "networking": {
                    "privateSubnets": True,
                    "publicSubnets": not (w.network_mode.value == "private")
                    if w.network_mode
                    else False,
                    "securityGroups": [f"{w.name}-sg"],
                },
            },
        }
        fname = f"workload-{w.name}.yaml"
        _write(output_dir, fname, skeleton)


def map_lza_intent_to_modules(intent: Any) -> list[ModuleInputs]:
    """Map LZA intent to IaC module variable inputs."""
    modules: list[ModuleInputs] = []

    # Network module inputs
    if hasattr(intent, "network") and intent.network.cidr:
        net_vars: dict[str, Any] = {
            "name": getattr(intent, "project_name", "lza-vpc") or "lza-vpc",
            "cidr": intent.network.cidr,
        }
        if getattr(intent.network, "hub_cidr", None):
            net_vars["hub_cidr"] = intent.network.hub_cidr
        if getattr(intent.network, "spoke_cidrs", None):
            net_vars["spoke_cidrs"] = intent.network.spoke_cidrs
        modules.append(
            ModuleInputs(
                module_name="lza-network",
                variables=net_vars,
            )
        )

    # Security module inputs
    if hasattr(intent, "security"):
        sec_vars: dict[str, Any] = {}
        if hasattr(intent.security, "audit_retention_days"):
            sec_vars["audit_retention_days"] = intent.security.audit_retention_days
        if hasattr(intent.security, "s3_block_public_access"):
            sec_vars["block_public_access"] = intent.security.s3_block_public_access
        if sec_vars:
            modules.append(
                ModuleInputs(
                    module_name="lza-security-baseline",
                    variables=sec_vars,
                )
            )

    # Workload module inputs
    if hasattr(intent, "workloads"):
        for w in intent.workloads:
            wl_vars: dict[str, Any] = {
                "name": w.name,
                "target_account": w.target_account,
                "network_mode": w.network_mode.value if w.network_mode else "private",
                "runtime": w.runtime,
                "port": w.port,
                "cpu": w.cpu,
                "memory": w.memory,
            }
            if w.public_ingress is not None:
                wl_vars["public_ingress"] = w.public_ingress
            modules.append(
                ModuleInputs(
                    module_name="lza-workload",
                    variables=wl_vars,
                )
            )

    return modules


_LZA_GENERATOR_SCOPE = {
    "baseline",
    "minimal",
    "workload",
    "hybrid-enterprise",
    "financial-services",
    "healthcare",
}


# Register module mappers for LZA patterns
for _lza_pattern in _LZA_GENERATOR_SCOPE:
    register_module_mapper(_lza_pattern, map_lza_intent_to_modules)


# Register generators at the pattern boundary; guards inside generators are fallback safety.
register_generator(
    "organization",
    gen_organization_config,
    priority=10,
    category="core",
    applies_to=_LZA_GENERATOR_SCOPE,
)
register_generator(
    "accounts",
    gen_accounts_config,
    priority=11,
    category="core",
    applies_to=_LZA_GENERATOR_SCOPE,
)
register_generator(
    "global",
    gen_global_config,
    priority=12,
    category="core",
    applies_to=_LZA_GENERATOR_SCOPE,
)
register_generator(
    "security",
    gen_security_config,
    priority=20,
    category="security",
    applies_to=_LZA_GENERATOR_SCOPE,
)
register_generator(
    "network",
    gen_network_config,
    priority=21,
    category="network",
    applies_to=_LZA_GENERATOR_SCOPE,
)
register_generator(
    "iam",
    gen_iam_config,
    priority=30,
    category="security",
    applies_to=_LZA_GENERATOR_SCOPE,
)
register_generator(
    "customizations",
    gen_customizations_config,
    priority=40,
    category="core",
    applies_to=_LZA_GENERATOR_SCOPE,
)
register_generator(
    "decision-report",
    gen_decision_report,
    priority=5,
    category="meta",
    applies_to=_LZA_GENERATOR_SCOPE,
)
register_generator(
    "deployment-graph",
    gen_deployment_graph,
    priority=6,
    category="meta",
    applies_to=_LZA_GENERATOR_SCOPE,
)
register_generator(
    "workload-skeletons",
    gen_workload_skeleton,
    priority=50,
    category="workload",
    applies_to=_LZA_GENERATOR_SCOPE,
)
