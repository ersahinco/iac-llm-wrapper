"""Sanitized Terraform VPC plan evidence shaping."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from intent_engine.core.package_version import installed_version
from intent_engine.core.yaml_utils import load_bundle_yaml_mapping

from .target import (
    MODULE_SOURCE,
    MODULE_VERSION,
    PLAN_EVIDENCE_NAME,
    PROVIDER_SOURCE,
    PROVIDER_VERSION,
    TERRAFORM_VERSION,
    approved_root_digest,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PlanBlocker(_StrictModel):
    code: str
    message: str
    next_action: str = Field(serialization_alias="nextAction")


class PlanStage(_StrictModel):
    name: str
    status: Literal["pass", "fail", "not-run"]
    exit_code: int | None = Field(default=None, serialization_alias="exitCode")


class ResourceChange(_StrictModel):
    address: str
    provider: str
    resource_type: str = Field(serialization_alias="resourceType")
    actions: list[str]


class PlanEvidence(_StrictModel):
    schema_version: Literal["intent-engine/terraform-plan-evidence/v1"] = Field(
        serialization_alias="schemaVersion"
    )
    timestamp: str
    status: Literal["pass", "fail"]
    pattern: Literal["terraform-vpc"] = "terraform-vpc"
    bundle: dict[str, str]
    target: dict[str, Any]
    toolchain: dict[str, str]
    plan: dict[str, Any]
    stages: list[PlanStage]
    resource_changes: list[ResourceChange] = Field(serialization_alias="resourceChanges")
    change_summary: dict[str, int] = Field(serialization_alias="changeSummary")
    blockers: list[PlanBlocker]
    guidance: list[str]
    apply_allowed: Literal[False] = Field(default=False, serialization_alias="applyAllowed")
    boundary: str


def blocker(code: str, message: str, next_action: str) -> PlanBlocker:
    return PlanBlocker(code=code, message=message, next_action=next_action)


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
                provider=str(item.get("provider_name", "")),
                resource_type=str(item.get("type", "")),
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
    stages: list[PlanStage],
    resource_changes: list[ResourceChange],
    summary: dict[str, int],
    blockers: list[PlanBlocker],
) -> PlanEvidence:
    return PlanEvidence(
        schema_version="intent-engine/terraform-plan-evidence/v1",
        timestamp=datetime.now(UTC).isoformat(),
        status="fail" if blockers else "pass",
        bundle=replay_identity,
        target={
            "moduleSource": MODULE_SOURCE,
            "moduleVersion": MODULE_VERSION,
            "providerSource": PROVIDER_SOURCE,
            "providerVersion": PROVIDER_VERSION,
            "requestedAccountId": requested_account,
            "observedAccountId": observed_account_id,
        },
        toolchain={
            "terraformVersion": TERRAFORM_VERSION,
            "wrapperVersion": installed_version(),
            "approvedRootSha256": approved_root_digest(),
        },
        plan={
            "status": "not-run" if plan_exit_code is None else "proven",
            "exitCode": plan_exit_code,
            "hasChanges": plan_exit_code == 2,
            "temporaryWorkspaceRetained": False,
            "binaryPlanRetained": False,
            "stateRetained": False,
        },
        stages=_complete_stages(stages),
        resource_changes=resource_changes,
        change_summary=summary,
        blockers=blockers,
        guidance=[
            "Fix the source requirement and recompile when an input is wrong.",
            "Select credentials for the intended AWS account when identity does not match.",
            "Correct the code-owned approved adapter when tool or schema validation fails.",
            "Seek owner review when destructive intent cannot be removed from the design.",
        ],
        boundary=(
            "Sanitized speculative-plan evidence only. Credentials, environment variables, "
            "raw plan JSON, resource values, binary plans, and Terraform state are excluded."
        ),
    )


def load_review_evidence(bundle: Path) -> dict[str, Any]:
    """Shape plan proof for the generic static review evidence section."""
    evidence = load_bundle_yaml_mapping(bundle, PLAN_EVIDENCE_NAME, required=False)
    blockers = evidence.get("blockers") if isinstance(evidence.get("blockers"), list) else []
    first = blockers[0] if blockers and isinstance(blockers[0], dict) else {}
    toolchain_value = evidence.get("toolchain")
    toolchain = toolchain_value if isinstance(toolchain_value, dict) else {}
    return {
        "label": "Terraform plan proof",
        "sectionTitle": "Terraform Plan Evidence",
        "artifactName": PLAN_EVIDENCE_NAME,
        "evidence": evidence,
        "summary": {
            "status": evidence.get("status", "not-run") if evidence else "not-run",
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
            "terraform-validate",
            "terraform-plan",
            "terraform-show",
        )
    ]
