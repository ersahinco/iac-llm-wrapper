"""Policy graph metadata for regulated handoff bundles."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, Field

FrameworkLabel = Literal["SOC2", "PCI", "HIPAA", "NIST"]


class PolicyCheckRef(BaseModel):
    """Reference to an external policy-as-code check."""

    tool: str = "checkov"
    check_id: str = Field(serialization_alias="checkId")
    name: str = ""
    source: str = "registered"
    description: str = ""


class PolicyRequirementMapping(BaseModel):
    """How a policy control maps to captured intent and emitted handoff artifacts."""

    requirement_keys: list[str] = Field(default_factory=list, serialization_alias="requirementKeys")
    target_contracts: list[str] = Field(default_factory=list, serialization_alias="targetContracts")
    artifact_paths: list[str] = Field(default_factory=list, serialization_alias="artifactPaths")
    module_variables: list[str] = Field(default_factory=list, serialization_alias="moduleVariables")
    checkov_check_ids: list[str] = Field(
        default_factory=list,
        serialization_alias="checkovCheckIds",
    )
    owner_policy_refs: list[str] = Field(
        default_factory=list,
        serialization_alias="ownerPolicyRefs",
    )


class PolicyControl(BaseModel):
    """A reviewable compliance or client policy control."""

    id: str
    title: str
    description: str = ""
    frameworks: list[str] = Field(default_factory=list)
    mapping: PolicyRequirementMapping = Field(default_factory=PolicyRequirementMapping)
    checks: list[PolicyCheckRef] = Field(default_factory=list)


class PolicyPack(BaseModel):
    """Registered policy metadata owned by a pattern."""

    name: str
    version: str
    description: str = ""
    frameworks: list[str] = Field(default_factory=list)
    controls: list[PolicyControl] = Field(default_factory=list)
    boundary: str = (
        "Policy graph metadata maps requirements, contracts, artifacts, and "
        "shift-left policy checks. It is not compliance attestation and does "
        "not deploy or mutate cloud resources."
    )


def policy_pack_to_dict(pack: PolicyPack) -> dict[str, Any]:
    return pack.model_dump(by_alias=True)


def policy_packs_to_dict(packs: Iterable[PolicyPack]) -> list[dict[str, Any]]:
    return [policy_pack_to_dict(pack) for pack in sorted(packs, key=lambda item: item.name)]


def policy_pack_inventory(packs: Iterable[PolicyPack]) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for pack in sorted(packs, key=lambda item: item.name):
        inventory.append(
            {
                "name": pack.name,
                "version": pack.version,
                "frameworks": pack.frameworks,
                "controlCount": len(pack.controls),
                "checkovCheckIds": sorted(
                    {
                        check_id
                        for control in pack.controls
                        for check_id in control.mapping.checkov_check_ids
                    }
                ),
            }
        )
    return inventory


def select_policy_packs(
    available: Iterable[PolicyPack],
    requested_names: Iterable[str] | None,
) -> tuple[list[PolicyPack], list[str]]:
    available_by_name = {pack.name: pack for pack in available}
    requested = [name for name in (requested_names or []) if name]
    if not requested:
        return list(available_by_name.values()), []
    selected: list[PolicyPack] = []
    missing: list[str] = []
    for name in requested:
        pack = available_by_name.get(name)
        if pack is None:
            missing.append(name)
        elif pack not in selected:
            selected.append(pack)
    return selected, missing


def map_findings_to_controls(
    findings: Iterable[dict[str, Any]],
    packs: Iterable[PolicyPack],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    controls_by_check_id: dict[str, list[tuple[PolicyPack, PolicyControl]]] = {}
    for pack in packs:
        for control in pack.controls:
            check_ids = {
                *control.mapping.checkov_check_ids,
                *(check.check_id for check in control.checks if check.tool == "checkov"),
            }
            for check_id in check_ids:
                controls_by_check_id.setdefault(check_id, []).append((pack, control))

    mapped: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    for finding in findings:
        check_id = str(finding.get("checkId", ""))
        matches = controls_by_check_id.get(check_id, [])
        if not matches:
            unmapped.append(finding)
            continue
        for pack, control in matches:
            mapped.append(
                {
                    "policyPack": pack.name,
                    "controlId": control.id,
                    "controlTitle": control.title,
                    "frameworks": control.frameworks or pack.frameworks,
                    "checkId": check_id,
                    "resource": finding.get("resource", ""),
                    "filePath": finding.get("filePath", ""),
                    "status": "fail",
                }
            )
    return mapped, unmapped
