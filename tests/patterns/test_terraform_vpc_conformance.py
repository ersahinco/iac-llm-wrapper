"""Requirement-to-plan conformance tests for the approved Terraform VPC target."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from intent_engine.core.yaml_utils import load_yaml_mapping
from intent_engine.patterns.terraform_vpc.conformance import evaluate_plan_conformance
from intent_engine.patterns.terraform_vpc.conformance_spec import (
    CONFORMANCE_SPEC_ID,
    CONTROL_IDS,
    REQUIREMENT_KEYS,
    REQUIREMENT_SET_ID,
    conformance_spec_digest,
)
from intent_engine.patterns.terraform_vpc.evidence import (
    PlanEvidence,
    evidence_semantic_violations,
)
from intent_engine.patterns.terraform_vpc.models import TerraformVpcIntent

_GOOD_PLAN = Path(__file__).parents[1] / "fixtures" / "terraform-vpc-plan" / "good-two-az.json"
_GOOD_EVIDENCE = _GOOD_PLAN.with_name("good-evidence-v2.yaml")


@pytest.fixture
def plan() -> dict[str, Any]:
    return json.loads(_GOOD_PLAN.read_text())


@pytest.fixture
def intent() -> TerraformVpcIntent:
    return TerraformVpcIntent(
        vpc_name="orders-vpc",
        primary_region="eu-central-1",
        cidr="10.30.0.0/16",
        az_count=2,
        public_subnet_cidrs=["10.30.0.0/24", "10.30.1.0/24"],
        private_subnet_cidrs=["10.30.10.0/24", "10.30.11.0/24"],
        enable_nat_gateway=True,
        single_nat_gateway=False,
        enable_dns_hostnames=True,
        target_account_id="111122223333",
        deployment_pipeline_ref="github://platform-networking/vpc-deploy",
    )


def _evaluate(plan: dict[str, Any], intent: TerraformVpcIntent):
    module_inputs = {
        key: entry["value"] for key, entry in plan["variables"].items() if key != "region"
    }
    return evaluate_plan_conformance(
        plan,
        intent=intent,
        module_inputs=module_inputs,
        identities={
            "requirementGraphSha256": "1" * 64,
            "decisionAuditSha256": "1" * 64,
            "policyGraphSha256": "1" * 64,
            "planManifestSha256": "1" * 64,
            "decisionReportSha256": "1" * 64,
            "moduleInputsSha256": "1" * 64,
            "targetContractSha256": "1" * 64,
            "policyPackSha256": "1" * 64,
        },
    )


def _outcomes(result: Any) -> dict[str, str]:
    return {item.graph_key: item.outcome for item in result.requirements}


def _change(plan: dict[str, Any], address: str) -> dict[str, Any]:
    return next(item for item in plan["resource_changes"] if item["address"] == address)


def test_known_good_plan_has_complete_stable_coverage(
    plan: dict[str, Any], intent: TerraformVpcIntent
) -> None:
    result, issues = _evaluate(plan, intent)

    assert not issues
    assert result.status == "conformant-with-deferred-gates"
    assert result.requirement_set_id == REQUIREMENT_SET_ID
    assert result.specification.id == CONFORMANCE_SPEC_ID
    assert result.specification.sha256 == conformance_spec_digest()
    assert [item.graph_key for item in result.requirements] == list(REQUIREMENT_KEYS)
    assert {item.outcome for item in result.requirements} == {"proven"}
    assert [item.control_id for item in result.controls] == list(CONTROL_IDS)
    assert [item.control_id for item in result.controls if item.outcome == "not-observable"] == [
        "VPC-DELIVERY-001",
        "VPC-NETWORK-001",
        "VPC-ATTACHMENT-001",
    ]
    assert len(result.deferred_gates) == 3
    assert len(result.resources) == 23
    assert all(item.requirement_ids and item.control_ids for item in result.resources)
    assert all(item.outcome != "attested" for item in [*result.requirements, *result.controls])


def test_golden_v2_evidence_is_strict_and_sanitized() -> None:
    payload = load_yaml_mapping(_GOOD_EVIDENCE)

    evidence = PlanEvidence.model_validate(payload)
    rendered = _GOOD_EVIDENCE.read_text()

    assert evidence.status == "pass"
    assert evidence.conformance.status == "conformant-with-deferred-gates"
    assert len(evidence.conformance.requirements) == len(REQUIREMENT_KEYS)
    assert len(evidence.conformance.controls) == len(CONTROL_IDS)
    for forbidden in (
        "after_unknown",
        "after_sensitive",
        "planned_values",
        "resource_changes",
        "AWS_SECRET_ACCESS_KEY",
        "temporary-plan",
    ):
        assert forbidden not in rendered


def test_v2_semantics_reject_incomplete_coverage_or_blocking_pass() -> None:
    missing = PlanEvidence.model_validate(load_yaml_mapping(_GOOD_EVIDENCE))
    missing.conformance.requirements.pop()
    assert evidence_semantic_violations(missing) == [
        "Requirement outcomes do not cover the exact requirement set once."
    ]

    blocking = PlanEvidence.model_validate(load_yaml_mapping(_GOOD_EVIDENCE))
    blocking.conformance.requirements[0].outcome = "failed"
    assert "Passing evidence cannot contain blocking terminal outcomes." in (
        evidence_semantic_violations(blocking)
    )

    bad_identity = PlanEvidence.model_validate(load_yaml_mapping(_GOOD_EVIDENCE))
    bad_identity.conformance.specification.sha256 = "0" * 64
    assert "Conformance specification identity does not match the code-owned spec." in (
        evidence_semantic_violations(bad_identity)
    )


def test_v2_nested_evidence_models_forbid_unregistered_fields() -> None:
    payload = load_yaml_mapping(_GOOD_EVIDENCE)
    payload["plan"]["rawPlan"] = {"secret": "must-not-enter-evidence"}

    with pytest.raises(ValidationError):
        PlanEvidence.model_validate(payload)


@pytest.mark.parametrize(
    ("mutate", "requirement", "outcome"),
    [
        (
            lambda value: value["change"]["after"].__setitem__("cidr_block", "10.99.0.0/16"),
            "cidr",
            "failed",
        ),
        (
            lambda value: value["change"]["after"]["tags"].__setitem__("Name", "wrong"),
            "vpc_name",
            "failed",
        ),
        (
            lambda value: value["change"]["after"].__setitem__("enable_dns_hostnames", False),
            "enable_dns_hostnames",
            "failed",
        ),
    ],
)
def test_known_resource_contradictions_fail_the_exact_requirement(
    plan: dict[str, Any],
    intent: TerraformVpcIntent,
    mutate: Any,
    requirement: str,
    outcome: str,
) -> None:
    mutate(_change(plan, "module.vpc.aws_vpc.this[0]"))

    result, issues = _evaluate(plan, intent)

    assert result.status == "nonconformant"
    assert _outcomes(result)[requirement] == outcome
    assert "TERRAFORM_REQUIREMENT_FAILED" in {item.code for item in issues}


def test_unknown_and_sensitive_values_never_pass(
    plan: dict[str, Any], intent: TerraformVpcIntent
) -> None:
    subnet = _change(plan, "module.vpc.aws_subnet.public[0]")
    subnet["change"]["after"].pop("cidr_block")
    subnet["change"]["after_unknown"]["cidr_block"] = True

    unknown, issues = _evaluate(plan, intent)

    assert unknown.status == "incomplete"
    assert _outcomes(unknown)["public_subnet_cidrs"] == "unknown"
    assert "TERRAFORM_REQUIREMENT_UNKNOWN" in {item.code for item in issues}

    sensitive_plan = deepcopy(json.loads(_GOOD_PLAN.read_text()))
    vpc = _change(sensitive_plan, "module.vpc.aws_vpc.this[0]")
    vpc["change"]["after_sensitive"]["cidr_block"] = True
    sensitive, sensitive_issues = _evaluate(sensitive_plan, intent)
    cidr = next(item for item in sensitive.requirements if item.graph_key == "cidr")
    assert cidr.outcome == "unresolved"
    assert all(
        item.value != "10.30.0.0/16" for item in cidr.observations if item.status == "sensitive"
    )
    assert "TERRAFORM_REQUIREMENT_UNRESOLVED" in {item.code for item in sensitive_issues}


def test_plan_variable_cannot_hide_a_matching_resource(
    plan: dict[str, Any], intent: TerraformVpcIntent
) -> None:
    plan["variables"]["cidr"]["value"] = "10.99.0.0/16"

    result, _ = _evaluate(plan, intent)

    cidr = next(item for item in result.requirements if item.graph_key == "cidr")
    assert cidr.outcome == "failed"
    assert {item.reference for item in cidr.observations if item.status == "mismatch"} == {
        "module-inputs.yaml:variables.cidr",
        "plan.variables.cidr",
    }


def test_account_only_and_empty_plans_are_incomplete(
    plan: dict[str, Any], intent: TerraformVpcIntent
) -> None:
    plan["resource_changes"] = [plan["resource_changes"][0]]

    result, issues = _evaluate(plan, intent)

    assert result.status == "incomplete"
    assert _outcomes(result)["target_account_id"] == "proven"
    assert _outcomes(result)["cidr"] == "unresolved"
    assert "TERRAFORM_RESOURCE_PROVENANCE_UNRESOLVED" in {item.code for item in issues}


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("format_version", "2.0", "TERRAFORM_PLAN_FORMAT_UNSUPPORTED"),
        ("terraform_version", "1.15.7", "TERRAFORM_PLAN_TOOLCHAIN_MISMATCH"),
        ("errored", True, "TERRAFORM_PLAN_ERRORED_INVALID"),
        ("complete", False, "TERRAFORM_PLAN_COMPLETE_INVALID"),
        ("applyable", False, "TERRAFORM_PLAN_APPLYABLE_INVALID"),
    ],
)
def test_unsupported_or_incomplete_plan_metadata_is_untrusted(
    plan: dict[str, Any],
    intent: TerraformVpcIntent,
    field: str,
    value: Any,
    code: str,
) -> None:
    plan[field] = value

    result, issues = _evaluate(plan, intent)

    assert result.status == "incomplete"
    assert {item.outcome for item in result.requirements} == {"unresolved"}
    assert code in {item.code for item in issues}


@pytest.mark.parametrize(
    "mutation",
    [
        "foreign-root",
        "sibling-module",
        "module-address",
        "provider",
        "data-provider",
        "missing-sentinel",
        "unknown-family",
        "duplicate-resource",
    ],
)
def test_resource_origin_and_inventory_drift_is_unresolved(
    plan: dict[str, Any], intent: TerraformVpcIntent, mutation: str
) -> None:
    if mutation == "foreign-root":
        foreign = deepcopy(_change(plan, "module.vpc.aws_vpc.this[0]"))
        foreign["address"] = "aws_vpc.foreign"
        foreign.pop("module_address")
        plan["resource_changes"].append(foreign)
    elif mutation == "sibling-module":
        foreign = deepcopy(_change(plan, "module.vpc.aws_vpc.this[0]"))
        foreign["address"] = "module.other.aws_vpc.this[0]"
        foreign["module_address"] = "module.other"
        plan["resource_changes"].append(foreign)
    elif mutation == "module-address":
        _change(plan, "module.vpc.aws_vpc.this[0]")["module_address"] = "module.other"
    elif mutation == "provider":
        _change(plan, "module.vpc.aws_vpc.this[0]")["provider_name"] = (
            "registry.terraform.io/example/aws"
        )
    elif mutation == "data-provider":
        _change(plan, "data.aws_caller_identity.current")["provider_name"] = (
            "registry.terraform.io/example/aws"
        )
    elif mutation == "missing-sentinel":
        plan["resource_changes"].remove(_change(plan, "module.vpc.aws_vpc.this[0]"))
    elif mutation == "unknown-family":
        unknown = _change(plan, "module.vpc.aws_default_security_group.this[0]")
        unknown["address"] = "module.vpc.aws_security_group.unexpected[0]"
        unknown["type"] = "aws_security_group"
    else:
        plan["resource_changes"].append(deepcopy(_change(plan, "module.vpc.aws_vpc.this[0]")))

    result, issues = _evaluate(plan, intent)

    assert result.status == "incomplete"
    assert "TERRAFORM_RESOURCE_PROVENANCE_UNRESOLVED" in {item.code for item in issues}


def test_nat_count_mismatch_fails_egress_requirements(
    plan: dict[str, Any], intent: TerraformVpcIntent
) -> None:
    plan["resource_changes"].remove(_change(plan, "module.vpc.aws_nat_gateway.this[1]"))

    result, _ = _evaluate(plan, intent)

    assert _outcomes(result)["enable_nat_gateway"] == "failed"
    assert _outcomes(result)["single_nat_gateway"] == "failed"
    egress = next(item for item in result.controls if item.control_id == "VPC-EGRESS-001")
    assert egress.outcome == "failed"


def test_disabled_nat_makes_single_nat_requirement_not_applicable(
    plan: dict[str, Any], intent: TerraformVpcIntent
) -> None:
    intent.enable_nat_gateway = False
    intent.single_nat_gateway = True
    plan["variables"]["enable_nat_gateway"]["value"] = False
    plan["variables"]["single_nat_gateway"]["value"] = True
    prefixes = (
        "module.vpc.aws_eip.nat[",
        "module.vpc.aws_nat_gateway.this[",
        "module.vpc.aws_route.private_nat_gateway[",
    )
    plan["resource_changes"] = [
        item
        for item in plan["resource_changes"]
        if not str(item["address"]).startswith(prefixes)
        and item["address"] != "module.vpc.aws_route_table.private[1]"
    ]

    result, issues = _evaluate(plan, intent)

    assert not issues
    assert result.status == "conformant-with-deferred-gates"
    assert "terraform-vpc/requirements/v1/single_nat_gateway" in (
        result.not_applicable_requirement_ids
    )
    assert "single_nat_gateway" not in _outcomes(result)
    not_applicable = set(result.not_applicable_requirement_ids)
    assert all(
        not not_applicable.intersection(resource.requirement_ids) for resource in result.resources
    )
