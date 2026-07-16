"""Strict evidence models for Terraform VPC plan conformance."""

from __future__ import annotations

from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

Outcome: TypeAlias = Literal[
    "proven", "failed", "unknown", "not-observable", "attested", "unresolved"
]
ProofClass: TypeAlias = Literal["immutable-input", "plan-observation", "owner-attestation", "none"]
ObservationStatus: TypeAlias = Literal["match", "mismatch", "unknown", "missing", "sensitive"]
ConformanceStatus: TypeAlias = Literal[
    "conformant", "conformant-with-deferred-gates", "nonconformant", "incomplete"
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_by_alias=True, validate_by_name=True)


class Observation(_StrictModel):
    reference: str
    status: ObservationStatus
    value: Any = None


class RequirementOutcome(_StrictModel):
    requirement_id: str = Field(alias="requirementId")
    graph_key: str = Field(alias="graphKey")
    outcome: Outcome
    proof_class: ProofClass = Field(alias="proofClass")
    expected: Any = None
    observations: list[Observation]
    message: str


class ControlOutcome(_StrictModel):
    control_id: str = Field(alias="controlId")
    outcome: Outcome
    proof_class: ProofClass = Field(alias="proofClass")
    evidence_references: list[str] = Field(alias="evidenceReferences")
    deferred_to: str | None = Field(default=None, alias="deferredTo")
    message: str


class DeferredGate(_StrictModel):
    id: str
    control_id: str = Field(alias="controlId")
    later_phase: str = Field(alias="laterPhase")
    required_evidence: str = Field(alias="requiredEvidence")


class ResourceProvenance(_StrictModel):
    address: str
    mode: Literal["managed", "data"]
    provider: str
    resource_type: str = Field(alias="resourceType")
    target_contract: Literal["terraform-aws-vpc-module"] = Field(
        default="terraform-aws-vpc-module", alias="targetContract"
    )
    requirement_ids: list[str] = Field(alias="requirementIds")
    control_ids: list[str] = Field(alias="controlIds")


class ConformanceIssue(_StrictModel):
    code: str
    message: str
    next_action: str = Field(alias="nextAction")


class ConformanceSpecification(_StrictModel):
    id: Literal["terraform-vpc/plan-conformance/v2"]
    sha256: str


class ConformanceIdentities(_StrictModel):
    requirement_graph_sha256: str = Field(alias="requirementGraphSha256")
    decision_audit_sha256: str = Field(alias="decisionAuditSha256")
    policy_graph_sha256: str = Field(alias="policyGraphSha256")
    plan_manifest_sha256: str = Field(alias="planManifestSha256")
    decision_report_sha256: str = Field(alias="decisionReportSha256")
    module_inputs_sha256: str = Field(alias="moduleInputsSha256")
    target_contract_sha256: str = Field(alias="targetContractSha256")
    policy_pack_sha256: str = Field(alias="policyPackSha256")


class ConformanceResult(_StrictModel):
    status: ConformanceStatus
    requirement_set_id: Literal["terraform-vpc/requirements/v1"] = Field(
        default="terraform-vpc/requirements/v1", alias="requirementSetId"
    )
    specification: ConformanceSpecification
    identities: ConformanceIdentities
    requirements: list[RequirementOutcome]
    controls: list[ControlOutcome]
    not_applicable_requirement_ids: list[str] = Field(alias="notApplicableRequirementIds")
    deferred_gates: list[DeferredGate] = Field(alias="deferredGates")
    resources: list[ResourceProvenance]
    owner_review_required: Literal[True] = Field(default=True, alias="ownerReviewRequired")
