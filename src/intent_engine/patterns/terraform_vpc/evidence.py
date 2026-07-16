"""Sanitized Terraform VPC plan evidence shaping."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from intent_engine.core.package_version import installed_version
from intent_engine.core.yaml_utils import load_bundle_yaml_mapping

from .conformance_models import ConformanceResult
from .conformance_spec import (
    CONTROL_IDS,
    LEGACY_CONFORMANCE_SPEC_ID,
    REQUIREMENT_KEYS,
    REQUIREMENT_SET_ID,
    conformance_spec_digest,
)
from .target import (
    MODULE_RELEASE_COMMIT,
    MODULE_SOURCE,
    MODULE_TREE_SHA256,
    MODULE_VERSION,
    PLAN_EVIDENCE_NAME,
    PROVIDER_SOURCE,
    PROVIDER_VERSION,
    TERRAFORM_VERSION,
    approved_root_digest,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_by_alias=True, validate_by_name=True)


class PlanBlocker(_StrictModel):
    code: str
    message: str
    next_action: str = Field(alias="nextAction")


class PlanStage(_StrictModel):
    name: str
    status: Literal["pass", "fail", "not-run"]
    exit_code: int | None = Field(default=None, alias="exitCode")


class ResourceChange(_StrictModel):
    address: str
    mode: str
    provider: str
    resource_type: str = Field(alias="resourceType")
    actions: list[str]


class BundleIdentity(_StrictModel):
    replay_manifest_sha256: str = Field(alias="replayManifestSha256")
    bundle_digest: str = Field(alias="bundleDigest")
    source_sha256: str = Field(alias="sourceSha256")


class TargetIdentity(_StrictModel):
    module_source: Literal["terraform-aws-modules/vpc/aws"] = Field(alias="moduleSource")
    module_version: Literal["6.6.1"] = Field(alias="moduleVersion")
    module_release_commit: Literal["3ffbd46fb1c7733e1b34d8666893280454e27436"] = Field(
        alias="moduleReleaseCommit"
    )
    module_tree_sha256: Literal[
        "38386a5d1a9e99cc1fdf8273a70b25b6f9dddca836545a960159d019d193c807"
    ] = Field(alias="moduleTreeSha256")
    provider_source: Literal["hashicorp/aws"] = Field(alias="providerSource")
    provider_version: Literal["6.53.0"] = Field(alias="providerVersion")
    requested_account_id: str = Field(alias="requestedAccountId")
    observed_account_id: str = Field(alias="observedAccountId")


class ToolchainIdentity(_StrictModel):
    terraform_version: Literal["1.15.8"] = Field(alias="terraformVersion")
    wrapper_version: str = Field(alias="wrapperVersion")
    approved_root_sha256: str = Field(alias="approvedRootSha256")


class PlanIdentity(_StrictModel):
    execution_status: Literal["not-run", "produced", "failed"] = Field(alias="executionStatus")
    exit_code: int | None = Field(alias="exitCode")
    has_changes: bool = Field(alias="hasChanges")
    format_version: str = Field(alias="formatVersion")
    terraform_version: str = Field(alias="terraformVersion")
    applyable: bool
    complete: bool
    errored: bool
    binary_plan_sha256: str = Field(alias="binaryPlanSha256")
    plan_json_sha256: str = Field(alias="planJsonSha256")
    module_content_verified: bool = Field(alias="moduleContentVerified")
    temporary_workspace_retained: Literal[False] = Field(alias="temporaryWorkspaceRetained")
    binary_plan_retained: Literal[False] = Field(alias="binaryPlanRetained")
    state_retained: Literal[False] = Field(alias="stateRetained")


class PlanEvidence(_StrictModel):
    schema_version: Literal["intent-engine/terraform-plan-evidence/v2"] = Field(
        alias="schemaVersion"
    )
    timestamp: str
    status: Literal["pass", "fail"]
    pattern: Literal["terraform-vpc"] = "terraform-vpc"
    bundle: BundleIdentity
    target: TargetIdentity
    toolchain: ToolchainIdentity
    plan: PlanIdentity
    stages: list[PlanStage]
    resource_changes: list[ResourceChange] = Field(alias="resourceChanges")
    change_summary: dict[str, int] = Field(alias="changeSummary")
    blockers: list[PlanBlocker]
    conformance: ConformanceResult
    guidance: list[str]
    owner_review_required: Literal[True] = Field(default=True, alias="ownerReviewRequired")
    apply_allowed: Literal[False] = Field(default=False, alias="applyAllowed")
    boundary: str


def blocker(code: str, message: str, next_action: str) -> PlanBlocker:
    return PlanBlocker(code=code, message=message, nextAction=next_action)


def evidence_semantic_violations(evidence: PlanEvidence) -> list[str]:
    """Enforce v2 coverage and pass semantics beyond path-level artifact checks."""
    violations: list[str] = []
    expected_requirements = {f"{REQUIREMENT_SET_ID}/{key}" for key in REQUIREMENT_KEYS}
    applicable = [item.requirement_id for item in evidence.conformance.requirements]
    reported = applicable + evidence.conformance.not_applicable_requirement_ids
    if len(reported) != len(set(reported)) or set(reported) != expected_requirements:
        violations.append("Requirement outcomes do not cover the exact requirement set once.")
    controls = [item.control_id for item in evidence.conformance.controls]
    if len(controls) != len(set(controls)) or set(controls) != set(CONTROL_IDS):
        violations.append("Control outcomes do not cover the exact registered control set once.")
    outcomes = [item.outcome for item in evidence.conformance.requirements]
    outcomes.extend(item.outcome for item in evidence.conformance.controls)
    if "attested" in outcomes:
        violations.append("Requirement-to-Plan Conformance v1 cannot emit attested outcomes.")
    if evidence.conformance.specification.sha256 != conformance_spec_digest():
        violations.append("Conformance specification identity does not match the code-owned spec.")
    if evidence.status == "pass":
        if evidence.conformance.status not in {
            "conformant",
            "conformant-with-deferred-gates",
        }:
            violations.append("Passing evidence requires a conformant terminal status.")
        if set(outcomes) & {"failed", "unknown", "unresolved"}:
            violations.append("Passing evidence cannot contain blocking terminal outcomes.")
        if evidence.plan.execution_status != "produced":
            violations.append("Passing evidence requires a produced Terraform plan.")
        if evidence.plan.module_content_verified is not True:
            violations.append("Passing evidence requires verified module content.")
        identity_values = [
            evidence.bundle.replay_manifest_sha256,
            evidence.bundle.bundle_digest,
            evidence.bundle.source_sha256,
            evidence.target.module_tree_sha256,
            evidence.toolchain.approved_root_sha256,
            evidence.plan.binary_plan_sha256,
            evidence.plan.plan_json_sha256,
            evidence.conformance.specification.sha256,
            *evidence.conformance.identities.model_dump().values(),
        ]
        if not all(_is_sha256(value) for value in identity_values):
            violations.append("Passing evidence requires complete SHA-256 identities.")
    return violations


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def empty_change_summary() -> dict[str, int]:
    return {"create": 0, "update": 0, "delete": 0, "replace": 0, "noOp": 0, "other": 0}


def observed_account(plan: dict[str, Any]) -> str:
    planned = plan.get("planned_values")
    outputs = planned.get("outputs") if isinstance(planned, dict) else None
    identity = outputs.get("aws_caller_identity") if isinstance(outputs, dict) else None
    value = identity.get("value") if isinstance(identity, dict) else None
    return value if isinstance(value, str) else ""


def summarize_changes(
    plan: dict[str, Any], blockers: list[PlanBlocker]
) -> tuple[list[ResourceChange], dict[str, int]]:
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        blockers.append(
            blocker(
                "TERRAFORM_PLAN_JSON_INVALID",
                "Terraform plan JSON is missing resource changes.",
                "Correct the Terraform adapter or toolchain and retry.",
            )
        )
        return [], empty_change_summary()
    rows: list[ResourceChange] = []
    summary = empty_change_summary()
    for item in changes:
        if not isinstance(item, dict) or not isinstance(item.get("change"), dict):
            blockers.append(
                blocker(
                    "TERRAFORM_PLAN_JSON_INVALID",
                    "Terraform plan JSON contains an invalid resource change.",
                    "Correct the Terraform adapter or toolchain and retry.",
                )
            )
            continue
        actions = item["change"].get("actions")
        if not isinstance(actions, list) or not all(isinstance(action, str) for action in actions):
            blockers.append(
                blocker(
                    "TERRAFORM_PLAN_JSON_INVALID",
                    "Terraform plan JSON contains invalid resource actions.",
                    "Correct the Terraform adapter or toolchain and retry.",
                )
            )
            continue
        summary[_action_category(actions)] += 1
        rows.append(
            ResourceChange(
                address=str(item.get("address", "")),
                mode=str(item.get("mode", "")),
                provider=str(item.get("provider_name", "")),
                resourceType=str(item.get("type", "")),
                actions=actions,
            )
        )
    rows.sort(key=lambda row: row.address)
    if summary["delete"] or summary["replace"]:
        blockers.append(
            blocker(
                "TERRAFORM_DESTRUCTIVE_CHANGE_BLOCKED",
                "Delete or replace actions are not allowed in the greenfield v1 proof.",
                "Fix the requirements or seek explicit owner review outside this v1 path.",
            )
        )
    return rows, summary


def check_account(requested: str, observed: str, blockers: list[PlanBlocker]) -> None:
    if not observed:
        blockers.append(
            blocker(
                "AWS_CALLER_IDENTITY_MISSING",
                "Terraform plan did not expose the AWS caller account ID.",
                "Use valid read-only AWS credentials and retry.",
            )
        )
    elif observed != requested:
        blockers.append(
            blocker(
                "AWS_ACCOUNT_MISMATCH",
                f"Observed AWS account {observed} does not match requested account {requested}.",
                "Select credentials for the intended account and retry.",
            )
        )


def build_evidence(
    *,
    replay_identity: dict[str, str],
    requested_account: str,
    observed_account_id: str,
    plan_exit_code: int | None,
    plan_produced: bool,
    plan_metadata: dict[str, Any],
    module_tree_sha256: str,
    stages: list[PlanStage],
    resource_changes: list[ResourceChange],
    summary: dict[str, int],
    blockers: list[PlanBlocker],
    conformance: ConformanceResult,
) -> PlanEvidence:
    passed = not blockers and conformance.status in {
        "conformant",
        "conformant-with-deferred-gates",
    }
    return PlanEvidence(
        schemaVersion="intent-engine/terraform-plan-evidence/v2",
        timestamp=datetime.now(UTC).isoformat(),
        status="pass" if passed else "fail",
        bundle=BundleIdentity.model_validate(replay_identity),
        target=TargetIdentity.model_validate(
            {
                "moduleSource": MODULE_SOURCE,
                "moduleVersion": MODULE_VERSION,
                "moduleReleaseCommit": MODULE_RELEASE_COMMIT,
                "moduleTreeSha256": module_tree_sha256 or MODULE_TREE_SHA256,
                "providerSource": PROVIDER_SOURCE,
                "providerVersion": PROVIDER_VERSION,
                "requestedAccountId": requested_account,
                "observedAccountId": observed_account_id,
            }
        ),
        toolchain=ToolchainIdentity.model_validate(
            {
                "terraformVersion": TERRAFORM_VERSION,
                "wrapperVersion": installed_version(),
                "approvedRootSha256": approved_root_digest(),
            }
        ),
        plan=PlanIdentity.model_validate(
            {
                "executionStatus": (
                    "produced"
                    if plan_produced
                    else "failed"
                    if plan_exit_code is not None
                    else "not-run"
                ),
                "exitCode": plan_exit_code,
                "hasChanges": plan_exit_code == 2,
                **plan_metadata,
                "temporaryWorkspaceRetained": False,
                "binaryPlanRetained": False,
                "stateRetained": False,
            }
        ),
        stages=_complete_stages(stages),
        resourceChanges=resource_changes,
        changeSummary=summary,
        blockers=blockers,
        conformance=conformance,
        guidance=[
            "Fix the source requirement and recompile when an input is wrong.",
            "Select credentials for the intended AWS account when identity does not match.",
            "Correct the code-owned approved adapter when tool or schema validation fails.",
            "Seek owner review when destructive intent cannot be removed from the design.",
        ],
        boundary=(
            "Sanitized speculative-plan evidence only. It retains approved non-secret VPC "
            "observations, identities, outcomes, actions, counts, and hashes. Credentials, "
            "environment variables, generic/raw resource values, raw plan JSON, binary plans, "
            "and Terraform state are excluded."
        ),
    )


def load_review_evidence(bundle: Path) -> dict[str, Any]:
    """Shape plan proof for the generic static review evidence section."""
    evidence = load_bundle_yaml_mapping(bundle, PLAN_EVIDENCE_NAME, required=False)
    blockers = evidence.get("blockers") if isinstance(evidence.get("blockers"), list) else []
    first = blockers[0] if blockers and isinstance(blockers[0], dict) else {}
    toolchain_value = evidence.get("toolchain")
    toolchain = toolchain_value if isinstance(toolchain_value, dict) else {}
    legacy = evidence.get("schemaVersion") == "intent-engine/terraform-plan-evidence/v1"
    conformance = evidence.get("conformance")
    specification = conformance.get("specification") if isinstance(conformance, dict) else None
    legacy_spec = (
        evidence.get("schemaVersion") == "intent-engine/terraform-plan-evidence/v2"
        and isinstance(specification, dict)
        and specification.get("id") == LEGACY_CONFORMANCE_SPEC_ID
    )
    conformance_status = (
        conformance.get("status", "incomplete") if isinstance(conformance, dict) else "incomplete"
    )
    legacy_label = "Terraform legacy plan evidence" if legacy else "Terraform legacy conformance"
    legacy_title = (
        "Terraform Legacy Plan Evidence" if legacy else "Terraform Legacy Conformance Evidence"
    )
    return {
        "label": legacy_label if legacy or legacy_spec else "Terraform plan conformance",
        "sectionTitle": legacy_title
        if legacy or legacy_spec
        else "Terraform Plan Conformance Evidence",
        "artifactName": PLAN_EVIDENCE_NAME,
        "evidence": evidence,
        "summary": {
            "status": "legacy-plan-only"
            if legacy
            else "legacy-conformance-spec"
            if legacy_spec
            else conformance_status
            if evidence
            else "not-run",
            "exitCode": evidence.get("plan", {}).get("exitCode", "unknown")
            if isinstance(evidence.get("plan"), dict)
            else "unknown",
            "packageVersion": toolchain.get("wrapperVersion", "unknown"),
            "gitCommit": "not-recorded",
            "sourcePath": str(bundle),
            "command": "iac-llm-wrapper terraform plan --bundle <bundle>",
            "diagnosticCategory": first.get("code", "passed"),
            "diagnosticNextAction": first.get("nextAction", ""),
            "failureExcerpt": first.get("message", ""),
            "configFileDigests": [],
        },
    }


def _action_category(actions: list[str]) -> str:
    action_set = set(actions)
    if "delete" in action_set and "create" in action_set:
        return "replace"
    if actions == ["create"]:
        return "create"
    if actions == ["update"]:
        return "update"
    if actions == ["delete"]:
        return "delete"
    if actions == ["no-op"]:
        return "noOp"
    return "other"


def _complete_stages(stages: list[PlanStage]) -> list[PlanStage]:
    by_name = {stage.name: stage for stage in stages}
    return [
        by_name.get(name, PlanStage(name=name, status="not-run"))
        for name in (
            "terraform-version",
            "terraform-init",
            "terraform-module",
            "terraform-validate",
            "terraform-plan",
            "terraform-show",
        )
    ]
