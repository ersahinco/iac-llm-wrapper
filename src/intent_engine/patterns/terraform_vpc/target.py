"""Approved Terraform VPC target identities and compile-time artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from intent_engine.core.package_version import installed_version
from intent_engine.core.replay import contract_digest, sha256_file
from intent_engine.core.yaml_utils import write_yaml_artifact

from .contracts import CONTRACT

TERRAFORM_VERSION = "1.15.8"
MODULE_SOURCE = "terraform-aws-modules/vpc/aws"
MODULE_VERSION = "6.6.1"
PROVIDER_SOURCE = "hashicorp/aws"
PROVIDER_VERSION = "6.53.0"
PLAN_EVIDENCE_NAME = "terraform-plan-evidence.yaml"
ROOT_FILES = ("main.tf", "variables.tf", ".terraform.lock.hcl")
MODULE_VARIABLES = {
    "name",
    "cidr",
    "azs",
    "public_subnets",
    "private_subnets",
    "enable_nat_gateway",
    "single_nat_gateway",
    "enable_dns_hostnames",
}


def enrich_handoff_readiness(_: Any, readiness: dict[str, Any]) -> dict[str, Any]:
    """Declare plan invocation only after configuration readiness is clean."""
    allowed = bool(readiness.get("handoffAllowed", False))
    blockers = list(readiness.get("configReady", {}).get("blockers", []))
    enriched = dict(readiness)
    enriched["planReady"] = {
        "status": "ready" if allowed else "blocked",
        "planAllowed": allowed,
        "summary": (
            "The immutable approved Terraform VPC adapter may run a speculative plan."
            if allowed
            else "Plan invocation is blocked until configuration readiness is clean."
        ),
        "blockers": [] if allowed else blockers,
        "planProven": False,
    }
    return enriched


def build_target_report(decisions: dict[str, Any], _: str) -> dict[str, Any]:
    """Describe the one approved target path and prove full decision coverage."""
    handled = sorted(decisions)
    return {
        "schemaVersion": "intent-engine/target-capability-graph/v1",
        "selectedTargetPath": ["approved-terraform-vpc-module"],
        "coverage": {
            "acceptedDecisionCount": len(handled),
            "handledAcceptedDecisions": handled,
            "unhandledAcceptedDecisions": [],
        },
        "capabilities": [
            {
                "key": "approved-terraform-vpc-module",
                "label": "Approved Terraform AWS VPC module",
                "type": "module-composition",
                "description": (
                    "Code-owned Terraform root for one immutable VPC module and speculative "
                    "account-bound plan proof."
                ),
                "handledDecisions": handled,
                "producedArtifacts": [
                    "module-inputs.yaml",
                    "terraform.tfvars",
                    "plan-manifest.yaml",
                    PLAN_EVIDENCE_NAME,
                ],
            }
        ],
        "unsupportedGaps": [],
        "manualGates": [
            "Use credentials for the declared non-production account.",
            "Reject delete or replace actions.",
            "Re-plan in the owner pipeline before any apply.",
        ],
    }


def gen_target_capability_graph(payload: Any, output_dir: Path) -> None:
    """Persist the Terraform VPC target coverage report."""
    report = getattr(payload, "target_capability_report", {})
    if report:
        write_yaml_artifact(output_dir / "target-capability-graph.yaml", report, "")


def gen_plan_manifest(payload: Any, output_dir: Path) -> None:
    """Write exact approved target and toolchain identities for replay."""
    readiness = dict(getattr(payload, "handoff_readiness", {}))
    immutable_names = ("decision-report.yaml", "module-inputs.yaml", "terraform.tfvars")
    immutable_inputs = [
        {"artifact": name, "sha256": sha256_file(output_dir / name)}
        for name in immutable_names
        if (output_dir / name).is_file()
    ]
    data = {
        "schemaVersion": "intent-engine/plan-manifest/v1",
        "target": {
            "name": "terraform-vpc",
            "type": "terraform-module",
            "contract": CONTRACT.name,
            "contractSha256": contract_digest(CONTRACT),
            "module": {"source": MODULE_SOURCE, "version": MODULE_VERSION},
            "provider": {"source": PROVIDER_SOURCE, "version": PROVIDER_VERSION},
        },
        "toolchain": {
            "terraformVersion": TERRAFORM_VERSION,
            "wrapperVersion": installed_version(),
        },
        "approvedRoot": {
            "files": approved_root_identities(),
            "sha256": approved_root_digest(),
        },
        "sourceDocument": dict(getattr(payload, "source_context", {})),
        "maturity": {
            "configReady": readiness.get("configReady", {}),
            "planReady": readiness.get("planReady", {}),
            "planProven": {
                "status": "not-run",
                "proven": False,
                "evidenceArtifact": PLAN_EVIDENCE_NAME,
            },
        },
        "immutableInputs": immutable_inputs,
        "planInvocation": {
            "mode": "metadata-only",
            "approvedCommand": "iac-llm-wrapper terraform plan --bundle <bundle>",
            "applyAllowed": False,
        },
        "expectedPlanOutputs": [PLAN_EVIDENCE_NAME],
        "manualGates": [
            "Use read-only credentials for the intended non-production AWS account.",
            "Reject delete or replace actions in this greenfield v1 proof.",
            "The owner pipeline must re-plan against its real backend before any apply.",
        ],
        "blockers": readiness.get("planReady", {}).get("blockers", []),
        "boundary": (
            "This manifest permits only a temporary speculative plan through the exact "
            "approved adapter. It never permits apply, destroy, remote state, or retained plans."
        ),
    }
    write_yaml_artifact(output_dir / "plan-manifest.yaml", data, "")


def approved_root_path() -> Path:
    return Path(__file__).with_name("plan_root")


def approved_root_identities() -> list[dict[str, str]]:
    """Return stable identities for the code-owned approved root."""
    return [
        {"name": name, "sha256": sha256_file(approved_root_path() / name)} for name in ROOT_FILES
    ]


def approved_root_digest() -> str:
    """Return one identity for the ordered approved-root inventory."""
    encoded = json.dumps(approved_root_identities(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()
