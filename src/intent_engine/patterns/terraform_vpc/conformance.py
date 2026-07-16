"""Requirement-to-plan conformance for the approved Terraform VPC target."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from intent_engine.core.replay import contract_digest

from .contracts import CONTRACT, POLICY_PACK
from .graph import build_graph
from .models import TerraformVpcIntent
from .target import MODULE_SOURCE, MODULE_VARIABLES, PROVIDER_SOURCE, TERRAFORM_VERSION

REQUIREMENT_SET_ID = "terraform-vpc/requirements/v1"
CONFORMANCE_SPEC_ID = "terraform-vpc/plan-conformance/v1"
REQUIREMENT_KEYS = (
    "vpc_name",
    "primary_region",
    "cidr",
    "az_count",
    "public_subnet_cidrs",
    "private_subnet_cidrs",
    "enable_nat_gateway",
    "single_nat_gateway",
    "enable_dns_hostnames",
    "target_account_id",
    "deployment_pipeline_ref",
)
CONTROL_IDS = (
    "VPC-DELIVERY-001",
    "VPC-NETWORK-001",
    "VPC-EGRESS-001",
    "VPC-DNS-001",
    "VPC-ATTACHMENT-001",
)

Outcome = Literal[
    "proven",
    "failed",
    "unknown",
    "not-observable",
    "attested",
    "unresolved",
]
ProofClass = Literal["immutable-input", "plan-observation", "owner-attestation", "none"]
ObservationStatus = Literal["match", "mismatch", "unknown", "missing", "sensitive"]


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
    id: Literal["terraform-vpc/plan-conformance/v1"]
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
    status: Literal["conformant", "conformant-with-deferred-gates", "nonconformant", "incomplete"]
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


_REQUIREMENT_SPEC = {
    "vpc_name": ("name", "module.vpc.aws_vpc.this[0].tags.Name"),
    "primary_region": ("region", "provider.aws.region", "planned subnet AZ set"),
    "cidr": ("cidr", "module.vpc.aws_vpc.this[0].cidr_block"),
    "az_count": ("azs", "planned public/private subnet counts"),
    "public_subnet_cidrs": ("public_subnets", "planned public subnet CIDR set"),
    "private_subnet_cidrs": ("private_subnets", "planned private subnet CIDR set"),
    "enable_nat_gateway": ("enable_nat_gateway", "planned NAT resource count"),
    "single_nat_gateway": ("single_nat_gateway", "planned NAT resource count"),
    "enable_dns_hostnames": (
        "enable_dns_hostnames",
        "module.vpc.aws_vpc.this[0].enable_dns_hostnames",
    ),
    "target_account_id": ("delivery.targetAccountId", "aws_caller_identity output"),
    "deployment_pipeline_ref": ("delivery.deploymentPipelineRef", "immutable input"),
}

_CONTROL_SPEC = {
    "VPC-DELIVERY-001": ("target_account_id", "deployment_pipeline_ref"),
    "VPC-NETWORK-001": ("cidr", "public_subnet_cidrs", "private_subnet_cidrs"),
    "VPC-EGRESS-001": ("enable_nat_gateway", "single_nat_gateway"),
    "VPC-DNS-001": ("enable_dns_hostnames",),
    "VPC-ATTACHMENT-001": ("vpc_name", "cidr"),
}

_RESOURCE_SPEC = (
    (
        "aws_vpc.this",
        "aws_vpc",
        ("vpc_name", "primary_region", "cidr", "enable_dns_hostnames"),
        ("VPC-NETWORK-001", "VPC-DNS-001", "VPC-ATTACHMENT-001"),
        "one",
    ),
    (
        "aws_internet_gateway.this",
        "aws_internet_gateway",
        ("cidr", "public_subnet_cidrs"),
        ("VPC-NETWORK-001",),
        "one",
    ),
    (
        "aws_route_table.public",
        "aws_route_table",
        ("public_subnet_cidrs",),
        ("VPC-NETWORK-001",),
        "one",
    ),
    (
        "aws_route.public_internet_gateway",
        "aws_route",
        ("public_subnet_cidrs",),
        ("VPC-NETWORK-001",),
        "one",
    ),
    (
        "aws_default_security_group.this",
        "aws_default_security_group",
        ("vpc_name", "cidr"),
        ("VPC-ATTACHMENT-001",),
        "one",
    ),
    (
        "aws_default_network_acl.this",
        "aws_default_network_acl",
        ("vpc_name", "cidr"),
        ("VPC-ATTACHMENT-001",),
        "one",
    ),
    (
        "aws_default_route_table.default",
        "aws_default_route_table",
        ("vpc_name", "cidr"),
        ("VPC-ATTACHMENT-001",),
        "one",
    ),
    (
        "aws_subnet.public",
        "aws_subnet",
        ("primary_region", "az_count", "public_subnet_cidrs"),
        ("VPC-NETWORK-001",),
        "az_count",
    ),
    (
        "aws_subnet.private",
        "aws_subnet",
        ("primary_region", "az_count", "private_subnet_cidrs"),
        ("VPC-NETWORK-001",),
        "az_count",
    ),
    (
        "aws_route_table_association.public",
        "aws_route_table_association",
        ("az_count", "public_subnet_cidrs"),
        ("VPC-NETWORK-001",),
        "az_count",
    ),
    (
        "aws_route_table_association.private",
        "aws_route_table_association",
        ("az_count", "private_subnet_cidrs"),
        ("VPC-NETWORK-001",),
        "az_count",
    ),
    (
        "aws_route_table.private",
        "aws_route_table",
        ("private_subnet_cidrs", "enable_nat_gateway", "single_nat_gateway"),
        ("VPC-NETWORK-001", "VPC-EGRESS-001"),
        "private_route_count",
    ),
    (
        "aws_eip.nat",
        "aws_eip",
        ("enable_nat_gateway", "single_nat_gateway"),
        ("VPC-EGRESS-001",),
        "nat_count",
    ),
    (
        "aws_nat_gateway.this",
        "aws_nat_gateway",
        ("enable_nat_gateway", "single_nat_gateway"),
        ("VPC-EGRESS-001",),
        "nat_count",
    ),
    (
        "aws_route.private_nat_gateway",
        "aws_route",
        ("enable_nat_gateway", "single_nat_gateway"),
        ("VPC-EGRESS-001",),
        "nat_count",
    ),
)


def conformance_spec_digest() -> str:
    """Return the canonical identity of the code-owned observation specification."""
    encoded = json.dumps(
        {
            "id": CONFORMANCE_SPEC_ID,
            "requirements": _REQUIREMENT_SPEC,
            "controls": _CONTROL_SPEC,
            "resources": _RESOURCE_SPEC,
            "rootDataSource": "data.aws_caller_identity.current",
            "resourceProvider": f"registry.terraform.io/{PROVIDER_SOURCE}",
            "module": MODULE_SOURCE,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def evaluate_plan_conformance(
    plan: dict[str, Any],
    *,
    intent: TerraformVpcIntent,
    module_inputs: dict[str, Any],
    identities: dict[str, str],
) -> tuple[ConformanceResult, list[ConformanceIssue]]:
    """Compare one Terraform plan with replay-bound VPC decisions and inputs."""
    applicable, not_applicable, coverage_issue = _applicability(intent)
    if coverage_issue is not None:
        result = empty_conformance(identities=identities, applicable=applicable)
        return result, [coverage_issue]
    metadata_issues = _plan_metadata_issues(plan)
    if metadata_issues:
        return (
            empty_conformance(
                identities=identities,
                applicable=applicable,
                not_applicable=not_applicable,
                intent=intent,
            ),
            metadata_issues,
        )

    checks = _new_checks(intent, applicable)
    issues = _record_input_and_configuration_checks(plan, intent, module_inputs, checks)
    changes, change_issues = _resource_changes(plan)
    issues.extend(change_issues)
    provenance, inventory_issues = _resource_provenance(changes, module_inputs, set(applicable))
    issues.extend(inventory_issues)
    _record_resource_observations(plan, changes, intent, module_inputs, checks)
    requirements = [_finish_check(checks[key]) for key in applicable]
    issues.extend(_requirement_issues(requirements))
    controls = _control_outcomes(requirements)
    status = _overall_status(requirements, controls, issues)
    result = ConformanceResult(
        status=status,
        specification=ConformanceSpecification.model_validate(
            {"id": CONFORMANCE_SPEC_ID, "sha256": conformance_spec_digest()}
        ),
        identities=ConformanceIdentities.model_validate(identities),
        requirements=requirements,
        controls=controls,
        notApplicableRequirementIds=[_requirement_id(key) for key in not_applicable],
        deferredGates=_deferred_gates(controls),
        resources=provenance,
    )
    return result, issues


def empty_conformance(
    *,
    identities: dict[str, str],
    applicable: list[str] | None = None,
    not_applicable: list[str] | None = None,
    intent: TerraformVpcIntent | None = None,
) -> ConformanceResult:
    """Build complete fail-closed outcomes when no trusted plan is available."""
    applicable = list(applicable or REQUIREMENT_KEYS)
    not_applicable = list(not_applicable or [])
    expected = _expected_values(intent) if intent is not None else {}
    requirements = [
        RequirementOutcome(
            requirementId=_requirement_id(key),
            graphKey=key,
            outcome="unresolved",
            proofClass="none",
            expected=expected.get(key),
            observations=[],
            message="No trusted plan observation is available.",
        )
        for key in applicable
    ]
    controls = [
        ControlOutcome(
            controlId=control_id,
            outcome="unresolved",
            proofClass="none",
            evidenceReferences=[],
            message="No trusted conformance result is available.",
        )
        for control_id in CONTROL_IDS
    ]
    return ConformanceResult(
        status="incomplete",
        specification=ConformanceSpecification.model_validate(
            {"id": CONFORMANCE_SPEC_ID, "sha256": conformance_spec_digest()}
        ),
        identities=ConformanceIdentities.model_validate(identities),
        requirements=requirements,
        controls=controls,
        notApplicableRequirementIds=[_requirement_id(key) for key in not_applicable],
        deferredGates=[],
        resources=[],
    )


@dataclass
class _Check:
    key: str
    expected: Any
    proof_class: ProofClass = "plan-observation"
    observations: list[Observation] = field(default_factory=list)


def _new_checks(intent: TerraformVpcIntent, applicable: list[str]) -> dict[str, _Check]:
    expected = _expected_values(intent)
    return {
        key: _Check(
            key=key,
            expected=expected[key],
            proof_class="immutable-input"
            if key == "deployment_pipeline_ref"
            else "plan-observation",
        )
        for key in applicable
    }


def _expected_values(intent: TerraformVpcIntent | None) -> dict[str, Any]:
    return intent.model_dump() if intent is not None else {}


def _applicability(
    intent: TerraformVpcIntent,
) -> tuple[list[str], list[str], ConformanceIssue | None]:
    graph = build_graph()
    graph_keys = graph.topological_order()
    policy_ids = tuple(control.id for control in POLICY_PACK.controls)
    if set(graph_keys) != set(REQUIREMENT_KEYS) or set(policy_ids) != set(CONTROL_IDS):
        return (
            graph_keys,
            [],
            _issue(
                "TERRAFORM_CONFORMANCE_SPEC_DRIFT",
                "The Terraform VPC graph or policy controls are not fully covered by "
                "the plan specification.",
                "Update and review the target-local conformance specification before planning.",
            ),
        )
    values = intent.model_dump()
    applicable_set: set[str] = set()
    not_applicable_set: set[str] = set()
    for key in graph_keys:
        if graph.is_applicable(key):
            applicable_set.add(key)
            graph.decide(key, _graph_value(values[key]))
        else:
            not_applicable_set.add(key)
            graph.skip(key, "not applicable during plan conformance")
    applicable = [key for key in REQUIREMENT_KEYS if key in applicable_set]
    not_applicable = [key for key in REQUIREMENT_KEYS if key in not_applicable_set]
    return applicable, not_applicable, None


def _graph_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def _plan_metadata_issues(plan: dict[str, Any]) -> list[ConformanceIssue]:
    issues: list[ConformanceIssue] = []
    format_version = plan.get("format_version")
    major = format_version.split(".", 1)[0] if isinstance(format_version, str) else ""
    if major != "1":
        issues.append(
            _issue(
                "TERRAFORM_PLAN_FORMAT_UNSUPPORTED",
                f"Terraform plan JSON format major 1 is required; observed {format_version!r}.",
                "Use the approved Terraform version and adapter.",
            )
        )
    if plan.get("terraform_version") != TERRAFORM_VERSION:
        issues.append(
            _issue(
                "TERRAFORM_PLAN_TOOLCHAIN_MISMATCH",
                "Terraform plan JSON does not identify the approved Terraform version.",
                "Use the exact approved Terraform binary.",
            )
        )
    for field_name, required in (("errored", False), ("complete", True), ("applyable", True)):
        if plan.get(field_name) is not required:
            issues.append(
                _issue(
                    f"TERRAFORM_PLAN_{field_name.upper()}_INVALID",
                    f"Terraform plan field {field_name!r} must be {required}.",
                    "Produce a complete, non-errored plan with the approved adapter.",
                )
            )
    return issues


def _record_input_and_configuration_checks(
    plan: dict[str, Any],
    intent: TerraformVpcIntent,
    module_inputs: dict[str, Any],
    checks: dict[str, _Check],
) -> list[ConformanceIssue]:
    issues: list[ConformanceIssue] = []
    expected_variables = _expected_root_variables(intent)
    _record_module_inputs(module_inputs, expected_variables, checks)
    variables = plan.get("variables")
    if not isinstance(variables, dict) or set(variables) != {"region", *MODULE_VARIABLES}:
        issues.append(
            _issue(
                "TERRAFORM_PLAN_VARIABLES_INVALID",
                "Terraform plan variables do not exactly match the approved root input set.",
                "Re-plan from the replay-verified module inputs.",
            )
        )
    else:
        _record_plan_variables(variables, expected_variables, checks)
    issues.extend(_configuration_issues(plan))
    provider_refs = _provider_region_references(plan)
    _record(
        checks,
        "primary_region",
        "plan.configuration.provider.aws.region",
        ["var.region"],
        provider_refs,
    )
    return issues


def _expected_root_variables(intent: TerraformVpcIntent) -> dict[str, Any]:
    return {
        "region": intent.primary_region,
        "name": intent.vpc_name,
        "cidr": intent.cidr,
        "azs": [f"{intent.primary_region}{suffix}" for suffix in "abcdef"[: intent.az_count]],
        "public_subnets": intent.public_subnet_cidrs,
        "private_subnets": intent.private_subnet_cidrs,
        "enable_nat_gateway": intent.enable_nat_gateway,
        "single_nat_gateway": intent.single_nat_gateway,
        "enable_dns_hostnames": intent.enable_dns_hostnames,
    }


def _record_module_inputs(
    actual: dict[str, Any], expected: dict[str, Any], checks: dict[str, _Check]
) -> None:
    for variable in MODULE_VARIABLES:
        _record_variable_observations(
            checks,
            f"module-inputs.yaml:variables.{variable}",
            variable,
            expected[variable],
            actual.get(variable, _MISSING),
        )


def _record_plan_variables(
    variables: dict[str, Any], expected: dict[str, Any], checks: dict[str, _Check]
) -> None:
    for variable in expected:
        entry = variables.get(variable)
        actual = entry.get("value", _MISSING) if isinstance(entry, dict) else _MISSING
        _record_variable_observations(
            checks,
            f"plan.variables.{variable}",
            variable,
            expected[variable],
            actual,
        )


def _record_variable_observations(
    checks: dict[str, _Check],
    reference: str,
    variable: str,
    expected: Any,
    actual: Any,
) -> None:
    key_by_variable = {
        "region": "primary_region",
        "name": "vpc_name",
        "cidr": "cidr",
        "public_subnets": "public_subnet_cidrs",
        "private_subnets": "private_subnet_cidrs",
        "enable_nat_gateway": "enable_nat_gateway",
        "single_nat_gateway": "single_nat_gateway",
        "enable_dns_hostnames": "enable_dns_hostnames",
    }
    if variable == "azs":
        _record(checks, "primary_region", reference, sorted(expected), _sorted_value(actual))
        count = len(actual) if isinstance(actual, list) else _MISSING
        _record(checks, "az_count", reference + ".count", len(expected), count)
        return
    key = key_by_variable[variable]
    normalized_expected = sorted(expected) if isinstance(expected, list) else expected
    _record(checks, key, reference, normalized_expected, _sorted_value(actual))


def _configuration_issues(plan: dict[str, Any]) -> list[ConformanceIssue]:
    configuration = plan.get("configuration")
    root = configuration.get("root_module") if isinstance(configuration, dict) else None
    if not isinstance(root, dict):
        return [
            _issue(
                "TERRAFORM_PLAN_CONFIGURATION_MISSING",
                "Terraform plan JSON has no root configuration.",
                "Produce plan JSON with the approved Terraform adapter.",
            )
        ]
    module_calls = root.get("module_calls")
    resources = root.get("resources")
    provider = configuration.get("provider_config") if isinstance(configuration, dict) else None
    checks = [
        isinstance(module_calls, dict) and set(module_calls) == {"vpc"},
        _approved_module_call(module_calls.get("vpc") if isinstance(module_calls, dict) else None),
        _approved_root_resources(resources),
        _approved_provider_configuration(provider),
    ]
    if all(checks):
        return []
    return [
        _issue(
            "TERRAFORM_PLAN_CONFIGURATION_UNAPPROVED",
            "Terraform plan configuration is not the exact approved root/module/provider shape.",
            "Restore the code-owned root and re-plan.",
        )
    ]


def _approved_module_call(call: Any) -> bool:
    if not isinstance(call, dict):
        return False
    source = call.get("source") or call.get("resolved_source")
    expressions = call.get("expressions")
    if source not in {MODULE_SOURCE, f"registry.terraform.io/{MODULE_SOURCE}"}:
        return False
    if not isinstance(expressions, dict) or set(expressions) != MODULE_VARIABLES:
        return False
    return all(
        isinstance(expressions[name], dict)
        and expressions[name].get("references") == [f"var.{name}"]
        for name in MODULE_VARIABLES
    )


def _approved_root_resources(resources: Any) -> bool:
    return (
        isinstance(resources, list)
        and len(resources) == 1
        and isinstance(resources[0], dict)
        and resources[0].get("address") == "data.aws_caller_identity.current"
        and resources[0].get("mode") == "data"
        and resources[0].get("type") == "aws_caller_identity"
        and resources[0].get("provider_config_key") == "aws"
    )


def _approved_provider_configuration(provider: Any) -> bool:
    if not isinstance(provider, dict) or len(provider) != 1:
        return False
    value = next(iter(provider.values()))
    return (
        isinstance(value, dict)
        and value.get("full_name") == f"registry.terraform.io/{PROVIDER_SOURCE}"
        and isinstance(value.get("expressions"), dict)
    )


def _provider_region_references(plan: dict[str, Any]) -> Any:
    configuration = plan.get("configuration")
    providers = configuration.get("provider_config") if isinstance(configuration, dict) else None
    if not isinstance(providers, dict) or len(providers) != 1:
        return _MISSING
    provider = next(iter(providers.values()))
    expressions = provider.get("expressions") if isinstance(provider, dict) else None
    region = expressions.get("region") if isinstance(expressions, dict) else None
    return region.get("references", _MISSING) if isinstance(region, dict) else _MISSING


def _resource_changes(
    plan: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[ConformanceIssue]]:
    raw = plan.get("resource_changes")
    if not isinstance(raw, list):
        return [], [
            _issue(
                "TERRAFORM_PLAN_RESOURCE_CHANGES_INVALID",
                "Terraform plan JSON has no resource change inventory.",
                "Produce complete plan JSON with the approved adapter.",
            )
        ]
    changes = [item for item in raw if isinstance(item, dict)]
    if len(changes) != len(raw):
        return changes, [
            _issue(
                "TERRAFORM_PLAN_RESOURCE_CHANGE_INVALID",
                "Terraform plan JSON contains a malformed resource change.",
                "Produce complete plan JSON with the approved adapter.",
            )
        ]
    return changes, []


@dataclass(frozen=True)
class _ResourceRule:
    resource_type: str
    requirements: tuple[str, ...]
    controls: tuple[str, ...]


def _expected_resources(module_inputs: dict[str, Any]) -> dict[str, _ResourceRule]:
    azs = module_inputs.get("azs")
    az_count = len(azs) if isinstance(azs, list) else 0
    single_nat = module_inputs.get("single_nat_gateway") is True
    nat_enabled = module_inputs.get("enable_nat_gateway") is True
    nat_count = (1 if single_nat else az_count) if nat_enabled else 0
    private_route_count = 1 if single_nat else az_count
    counts = {
        "one": 1,
        "az_count": az_count,
        "private_route_count": private_route_count,
        "nat_count": nat_count,
    }
    return {
        f"module.vpc.{name}[{index}]": _ResourceRule(resource_type, requirements, controls)
        for name, resource_type, requirements, controls, count_driver in _RESOURCE_SPEC
        for index in range(counts[count_driver])
    }


def _resource_provenance(
    changes: list[dict[str, Any]],
    module_inputs: dict[str, Any],
    applicable: set[str],
) -> tuple[list[ResourceProvenance], list[ConformanceIssue]]:
    expected = _expected_resources(module_inputs)
    provider = f"registry.terraform.io/{PROVIDER_SOURCE}"
    provenance: list[ResourceProvenance] = []
    issues: list[ConformanceIssue] = []
    observed_managed: set[str] = set()
    seen: set[str] = set()
    for change in changes:
        address = change.get("address")
        mode = change.get("mode")
        if not isinstance(address, str) or address in seen:
            issues.append(
                _resource_issue("Terraform plan resource addresses are missing or duplicated.")
            )
            continue
        seen.add(address)
        if mode == "data":
            if not _approved_data_change(change, provider):
                issues.append(
                    _resource_issue(f"Root data resource {address!r} has unapproved provenance.")
                )
            continue
        rule = expected.get(address)
        if mode != "managed" or rule is None:
            issues.append(_resource_issue(f"Managed resource {address!r} is not approved."))
            continue
        observed_managed.add(address)
        if (
            change.get("module_address") != "module.vpc"
            or change.get("provider_name") != provider
            or change.get("type") != rule.resource_type
        ):
            issues.append(
                _resource_issue(f"Managed resource {address!r} has unapproved provenance.")
            )
            continue
        actions = (
            change.get("change", {}).get("actions")
            if isinstance(change.get("change"), dict)
            else None
        )
        if actions != ["create"]:
            issues.append(
                _resource_issue(f"Managed resource {address!r} is not a greenfield create.")
            )
        provenance.append(
            ResourceProvenance(
                address=address,
                mode="managed",
                provider=provider,
                resourceType=rule.resource_type,
                requirementIds=[
                    _requirement_id(key) for key in rule.requirements if key in applicable
                ],
                controlIds=list(rule.controls),
            )
        )
    missing = sorted(set(expected) - observed_managed)
    if missing:
        issues.append(
            _resource_issue("Approved managed resources are missing: " + ", ".join(missing))
        )
    return sorted(provenance, key=lambda item: item.address), issues


def _approved_data_change(change: dict[str, Any], provider: str) -> bool:
    payload = change.get("change")
    actions = payload.get("actions") if isinstance(payload, dict) else None
    return (
        change.get("address") == "data.aws_caller_identity.current"
        and change.get("module_address") in {None, ""}
        and change.get("provider_name") == provider
        and change.get("type") == "aws_caller_identity"
        and actions == ["read"]
    )


def _resource_issue(message: str) -> ConformanceIssue:
    return _issue(
        "TERRAFORM_RESOURCE_PROVENANCE_UNRESOLVED",
        message,
        "Restore the approved root/module invocation and re-plan.",
    )


def _record_resource_observations(
    plan: dict[str, Any],
    changes: list[dict[str, Any]],
    intent: TerraformVpcIntent,
    module_inputs: dict[str, Any],
    checks: dict[str, _Check],
) -> None:
    by_address = {
        item.get("address"): item for item in changes if isinstance(item.get("address"), str)
    }
    vpc = by_address.get("module.vpc.aws_vpc.this[0]")
    _record_change_attribute(checks, "vpc_name", vpc, ("tags", "Name"))
    _record_change_attribute(checks, "primary_region", vpc, ("region",))
    _record_change_attribute(checks, "cidr", vpc, ("cidr_block",))
    _record_change_attribute(checks, "enable_dns_hostnames", vpc, ("enable_dns_hostnames",))
    public = _changes_with_prefix(changes, "module.vpc.aws_subnet.public[")
    private = _changes_with_prefix(changes, "module.vpc.aws_subnet.private[")
    _record_subnet_observations(checks, "public_subnet_cidrs", public, intent.az_count)
    _record_subnet_observations(checks, "private_subnet_cidrs", private, intent.az_count)
    az_values = _attribute_set(public + private, ("availability_zone",))
    _record(
        checks,
        "primary_region",
        "plan.resources.aws_subnet.availability_zone.set",
        sorted(_expected_root_variables(intent)["azs"]),
        az_values,
    )
    nat_count = len(_changes_with_prefix(changes, "module.vpc.aws_nat_gateway.this["))
    expected_nat = (
        (1 if intent.single_nat_gateway else intent.az_count) if intent.enable_nat_gateway else 0
    )
    observed_nat_count: Any = nat_count if nat_count or expected_nat == 0 else _MISSING
    _record(
        checks,
        "enable_nat_gateway",
        "plan.resources.aws_nat_gateway.count",
        expected_nat,
        observed_nat_count,
    )
    if "single_nat_gateway" in checks:
        _record(
            checks,
            "single_nat_gateway",
            "plan.resources.aws_nat_gateway.count",
            expected_nat,
            observed_nat_count,
        )
    _record_account_output(plan, checks)
    _record(
        checks,
        "deployment_pipeline_ref",
        "decision-report.yaml:delivery.deploymentPipelineRef",
        intent.deployment_pipeline_ref,
        intent.deployment_pipeline_ref,
    )


def _record_subnet_observations(
    checks: dict[str, _Check], key: str, changes: list[dict[str, Any]], az_count: int
) -> None:
    observed_count: Any = len(changes) if changes else _MISSING
    _record(checks, "az_count", f"plan.resources.{key}.count", az_count, observed_count)
    _record(
        checks,
        key,
        f"plan.resources.{key}.cidr_block.set",
        _EXPECTED_FROM_CHECK,
        _attribute_set(changes, ("cidr_block",)),
    )


def _record_account_output(plan: dict[str, Any], checks: dict[str, _Check]) -> None:
    planned = plan.get("planned_values")
    outputs = planned.get("outputs") if isinstance(planned, dict) else None
    output = outputs.get("aws_caller_identity") if isinstance(outputs, dict) else None
    if not isinstance(output, dict):
        value: Any = _MISSING
    elif output.get("sensitive") is True:
        value = _SENSITIVE
    elif output.get("unknown") is True:
        value = _UNKNOWN
    else:
        value = output.get("value", _MISSING)
    _record(
        checks, "target_account_id", "plan.outputs.aws_caller_identity", _EXPECTED_FROM_CHECK, value
    )


def _changes_with_prefix(changes: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    return sorted(
        [item for item in changes if str(item.get("address", "")).startswith(prefix)],
        key=lambda item: str(item.get("address", "")),
    )


def _record_change_attribute(
    checks: dict[str, _Check], key: str, change: dict[str, Any] | None, path: tuple[str, ...]
) -> None:
    value = _change_attribute(change, path)
    _record(
        checks,
        key,
        f"plan.resources.module.vpc.aws_vpc.this[0].{'.'.join(path)}",
        _EXPECTED_FROM_CHECK,
        value,
    )


def _attribute_set(changes: list[dict[str, Any]], path: tuple[str, ...]) -> Any:
    if not changes:
        return _MISSING
    values = [_change_attribute(change, path) for change in changes]
    if any(value is _SENSITIVE for value in values):
        return _SENSITIVE
    if any(value is _UNKNOWN for value in values):
        return _UNKNOWN
    if any(value is _MISSING for value in values):
        return _MISSING
    return sorted(dict.fromkeys(values))


def _change_attribute(change: dict[str, Any] | None, path: tuple[str, ...]) -> Any:
    if not isinstance(change, dict) or not isinstance(change.get("change"), dict):
        return _MISSING
    payload = change["change"]
    if _mask_value(payload.get("after_sensitive"), path):
        return _SENSITIVE
    if _mask_value(payload.get("after_unknown"), path):
        return _UNKNOWN
    value: Any = payload.get("after", _MISSING)
    for part in path:
        if not isinstance(value, dict) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _mask_value(mask: Any, path: tuple[str, ...]) -> bool:
    value = mask
    for part in path:
        if value is True:
            return True
        if not isinstance(value, dict) or part not in value:
            return False
        value = value[part]
    return value is True


def _record(
    checks: dict[str, _Check], key: str, reference: str, expected: Any, observed: Any
) -> None:
    check = checks.get(key)
    if check is None:
        return
    if expected is _EXPECTED_FROM_CHECK:
        expected = check.expected
    if observed is _MISSING:
        check.observations.append(Observation(reference=reference, status="missing"))
    elif observed is _UNKNOWN:
        check.observations.append(Observation(reference=reference, status="unknown"))
    elif observed is _SENSITIVE:
        check.observations.append(Observation(reference=reference, status="sensitive"))
    else:
        check.observations.append(
            Observation(
                reference=reference,
                status="match" if _equal(expected, observed) else "mismatch",
                value=observed,
            )
        )


def _finish_check(check: _Check) -> RequirementOutcome:
    statuses = {item.status for item in check.observations}
    if "mismatch" in statuses:
        outcome: Outcome = "failed"
        message = "Known immutable input or plan observations contradict the accepted requirement."
    elif "unknown" in statuses:
        outcome = "unknown"
        message = "Terraform marks a required plan observation as unknown."
    elif statuses & {"missing", "sensitive"} or not statuses:
        outcome = "unresolved"
        message = "A required non-sensitive observation is missing, unsupported, or sensitive."
    else:
        outcome = "proven"
        message = "Immutable input and required plan observations agree."
    return RequirementOutcome(
        requirementId=_requirement_id(check.key),
        graphKey=check.key,
        outcome=outcome,
        proofClass=check.proof_class,
        expected=check.expected,
        observations=check.observations,
        message=message,
    )


def _requirement_issues(requirements: list[RequirementOutcome]) -> list[ConformanceIssue]:
    issues: list[ConformanceIssue] = []
    labels = {
        "failed": "TERRAFORM_REQUIREMENT_FAILED",
        "unknown": "TERRAFORM_REQUIREMENT_UNKNOWN",
        "unresolved": "TERRAFORM_REQUIREMENT_UNRESOLVED",
    }
    for requirement in requirements:
        code = labels.get(requirement.outcome)
        if code is not None:
            issues.append(
                _issue(
                    code,
                    f"{requirement.requirement_id}: {requirement.message}",
                    "Correct the source packet or code-owned target, then recompile and re-plan.",
                )
            )
    return issues


def _control_outcomes(requirements: list[RequirementOutcome]) -> list[ControlOutcome]:
    by_key = {item.graph_key: item for item in requirements}
    controls: list[ControlOutcome] = []
    for control_id in CONTROL_IDS:
        members = [by_key[key] for key in _CONTROL_SPEC[control_id] if key in by_key]
        blocking = _blocking_outcome(members)
        if blocking is not None:
            controls.append(
                ControlOutcome(
                    controlId=control_id,
                    outcome=blocking,
                    proofClass="none",
                    evidenceReferences=[member.requirement_id for member in members],
                    message="A mapped requirement has no passing terminal outcome.",
                )
            )
        elif control_id in {"VPC-DELIVERY-001", "VPC-NETWORK-001", "VPC-ATTACHMENT-001"}:
            controls.append(_deferred_control(control_id, members))
        else:
            controls.append(
                ControlOutcome(
                    controlId=control_id,
                    outcome="proven",
                    proofClass="plan-observation",
                    evidenceReferences=[member.requirement_id for member in members],
                    message="All plan-observable mapped requirements are proven.",
                )
            )
    return controls


def _blocking_outcome(requirements: list[RequirementOutcome]) -> Outcome | None:
    outcomes = {item.outcome for item in requirements}
    if "failed" in outcomes:
        return "failed"
    if "unknown" in outcomes:
        return "unknown"
    if "unresolved" in outcomes:
        return "unresolved"
    return None


def _deferred_control(control_id: str, requirements: list[RequirementOutcome]) -> ControlOutcome:
    later = {
        "VPC-DELIVERY-001": "owner pipeline-control review",
        "VPC-NETWORK-001": "owner IPAM/allocation review",
        "VPC-ATTACHMENT-001": "downstream attachment review",
    }[control_id]
    return ControlOutcome(
        controlId=control_id,
        outcome="not-observable",
        proofClass="owner-attestation",
        evidenceReferences=[item.requirement_id for item in requirements],
        deferredTo=later,
        message="Plan-observable subclaims pass; independent owner evidence is still required.",
    )


def _deferred_gates(controls: list[ControlOutcome]) -> list[DeferredGate]:
    return [
        DeferredGate(
            id=f"terraform-vpc/deferred-gates/v1/{control.control_id.lower()}",
            controlId=control.control_id,
            laterPhase=control.deferred_to or "owner review",
            requiredEvidence="Independent owner evidence bound to the exact v2 evidence digest.",
        )
        for control in controls
        if control.outcome == "not-observable"
    ]


def _overall_status(
    requirements: list[RequirementOutcome],
    controls: list[ControlOutcome],
    issues: list[ConformanceIssue],
) -> Literal["conformant", "conformant-with-deferred-gates", "nonconformant", "incomplete"]:
    outcomes = {item.outcome for item in requirements} | {item.outcome for item in controls}
    if "failed" in outcomes:
        return "nonconformant"
    if outcomes & {"unknown", "unresolved"} or issues:
        return "incomplete"
    if "not-observable" in outcomes:
        return "conformant-with-deferred-gates"
    return "conformant"


def _equal(expected: Any, observed: Any) -> bool:
    if isinstance(expected, list) and isinstance(observed, list):
        return sorted(expected) == sorted(observed)
    return bool(expected == observed)


def _sorted_value(value: Any) -> Any:
    return sorted(value) if isinstance(value, list) else value


def _requirement_id(key: str) -> str:
    return f"{REQUIREMENT_SET_ID}/{key}"


def _issue(code: str, message: str, next_action: str) -> ConformanceIssue:
    return ConformanceIssue(code=code, message=message, nextAction=next_action)


_MISSING = object()
_UNKNOWN = object()
_SENSITIVE = object()
_EXPECTED_FROM_CHECK = object()


def conformance_identities(identities: dict[str, str]) -> dict[str, str]:
    """Add code-owned contract and policy identities to bundle artifact identities."""
    policy = json.dumps(
        POLICY_PACK.model_dump(by_alias=True), sort_keys=True, separators=(",", ":")
    )
    return {
        **identities,
        "targetContractSha256": contract_digest(CONTRACT),
        "policyPackSha256": hashlib.sha256(policy.encode()).hexdigest(),
    }
