"""Approved Terraform VPC target identities and compile-time artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from intent_engine.core.graph_export import graph_to_json
from intent_engine.core.package_version import installed_version
from intent_engine.core.replay import contract_digest, sha256_file
from intent_engine.core.yaml_utils import write_yaml_artifact

from .contracts import CONTRACT
from .graph import build_graph

TERRAFORM_VERSION = "1.15.8"
MODULE_SOURCE = "terraform-aws-modules/vpc/aws"
MODULE_VERSION = "6.6.1"
MODULE_RELEASE_COMMIT = "3ffbd46fb1c7733e1b34d8666893280454e27436"
MODULE_TREE_SHA256 = "38386a5d1a9e99cc1fdf8273a70b25b6f9dddca836545a960159d019d193c807"
APPROVED_ROOT_SHA256 = "5986a358169a90b2f22be1afc04319c923332d848ed4641359d7f7db7a0dc5f4"
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
    """Describe compile-time routing coverage for the approved target path."""
    handled = sorted(decisions)
    return {
        "schemaVersion": "intent-engine/target-capability-graph/v1",
        "selectedTargetPath": ["approved-terraform-vpc-module"],
        "coverage": {
            "acceptedDecisionCount": len(handled),
            "handledAcceptedDecisions": handled,
            "unhandledAcceptedDecisions": [],
            "semantics": (
                "Compile-time routing coverage only. Plan-time requirement conformance is "
                "established only by terraform-plan-evidence.yaml v2."
            ),
        },
        "capabilities": [
            {
                "key": "approved-terraform-vpc-module",
                "label": "Approved Terraform AWS VPC module",
                "type": "module-composition",
                "description": (
                    "Code-owned Terraform root for one version- and content-pinned VPC module "
                    "and speculative account-bound plan conformance evidence."
                ),
                "handledDecisions": handled,
                "producedArtifacts": [
                    "module-inputs.yaml",
                    "terraform.tfvars",
                    "atmos/stacks/catalog/terraform-vpc-intent.yaml",
                    "atmos/components/terraform/terraform-vpc/",
                    "plan-manifest.yaml",
                    PLAN_EVIDENCE_NAME,
                ],
            }
        ],
        "unsupportedGaps": [],
        "manualGates": [
            "Copy the generated Atmos catalog and component root into the owner repository.",
            "Create an owner-named real component that inherits terraform-vpc/intent-defaults.",
            "Configure backend, authentication, workspace, and approvals only in the owner "
            "repository.",
            "Review Atmos component provenance and validation in a pull request.",
            "Let Atlantis or another owner-controlled OSS pipeline re-plan before any apply.",
        ],
    }


def gen_target_capability_graph(payload: Any, output_dir: Path) -> None:
    """Persist the Terraform VPC target coverage report."""
    report = getattr(payload, "target_capability_report", {})
    if report:
        write_yaml_artifact(output_dir / "target-capability-graph.yaml", report, "")


def gen_requirement_graph(payload: Any, output_dir: Path) -> None:
    """Persist the resolved graph that the plan conformance specification covers."""
    decisions = dict(getattr(payload, "decisions", {}))
    graph = build_graph()
    for key in graph.topological_order():
        if graph.is_applicable(key):
            if key not in decisions:
                raise ValueError(f"Resolved Terraform VPC graph is missing decision: {key}.")
            graph.decide(key, _graph_decision_value(decisions[key]))
        else:
            graph.skip(key, "not applicable in the compiled bundle")
    (output_dir / "requirement-graph.json").write_text(graph_to_json(graph, "terraform-vpc"))


def _graph_decision_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def gen_plan_manifest(payload: Any, output_dir: Path) -> None:
    """Write exact approved target and toolchain identities for replay."""
    approved_root_sha256 = assert_approved_root_identity()
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
            "sha256": approved_root_sha256,
        },
        "approvedModule": {
            "releaseCommit": MODULE_RELEASE_COMMIT,
            "treeSha256": MODULE_TREE_SHA256,
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
            "Use owner-approved restricted credentials for the intended non-production AWS "
            "account; the core verifies account identity, not permission scope.",
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
    identities: list[dict[str, str]] = []
    for name in ROOT_FILES:
        path = approved_root_path() / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Approved Terraform root file is missing or unsafe: {name}.")
        identities.append({"name": name, "sha256": sha256_file(path)})
    return identities


def approved_root_digest() -> str:
    """Return one identity for the ordered approved-root inventory."""
    encoded = json.dumps(approved_root_identities(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def assert_approved_root_identity() -> str:
    """Fail closed when the packaged root differs from its reviewed identity."""
    digest = approved_root_digest()
    if digest != APPROVED_ROOT_SHA256:
        raise ValueError("Approved Terraform root content does not match its reviewed identity.")
    return digest


def installed_module_tree_digest(workspace: Path) -> str:
    """Verify the initialized module identity and hash its portable source tree."""
    manifest_path = workspace / ".terraform" / "modules" / "modules.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Terraform module manifest is missing or unsafe.")
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Terraform module manifest is malformed.") from exc
    modules = manifest.get("Modules") if isinstance(manifest, dict) else None
    if not isinstance(modules, list):
        raise ValueError("Terraform module manifest has no module inventory.")
    matches = [entry for entry in modules if isinstance(entry, dict) and entry.get("Key") == "vpc"]
    if len(matches) != 1:
        raise ValueError("Terraform module manifest must identify exactly one VPC module.")
    entry = matches[0]
    if entry.get("Source") != f"registry.terraform.io/{MODULE_SOURCE}":
        raise ValueError("Initialized Terraform module source is not approved.")
    if entry.get("Version") != MODULE_VERSION:
        raise ValueError("Initialized Terraform module version is not approved.")
    module_dir = _safe_module_dir(workspace, entry.get("Dir"))
    digest = _portable_module_tree_digest(module_dir)
    if digest != MODULE_TREE_SHA256:
        raise ValueError("Initialized Terraform module content does not match the approved tree.")
    return digest


def _safe_module_dir(workspace: Path, raw_dir: Any) -> Path:
    if not isinstance(raw_dir, str):
        raise ValueError("Terraform module directory is invalid.")
    portable = PurePosixPath(raw_dir)
    if portable.is_absolute() or ".." in portable.parts:
        raise ValueError("Terraform module directory is unsafe.")
    module_dir = workspace.joinpath(*portable.parts)
    current = workspace
    for part in portable.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("Terraform module directory contains a symlink.")
    if not module_dir.is_dir():
        raise ValueError("Terraform module directory is missing.")
    if not module_dir.resolve().is_relative_to(workspace.resolve()):
        raise ValueError("Terraform module directory escapes the temporary workspace.")
    return module_dir


def _portable_module_tree_digest(module_dir: Path) -> str:
    digest = hashlib.sha256()
    entries = sorted(
        module_dir.rglob("*"), key=lambda path: path.relative_to(module_dir).as_posix()
    )
    for path in entries:
        relative = path.relative_to(module_dir)
        if path.is_symlink():
            raise ValueError(f"Terraform module tree contains a symlink: {relative.as_posix()}.")
        if path.is_dir() or ".git" in relative.parts:
            continue
        if not path.is_file():
            raise ValueError(
                f"Terraform module tree contains an unsafe entry: {relative.as_posix()}."
            )
        digest.update(relative.as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
