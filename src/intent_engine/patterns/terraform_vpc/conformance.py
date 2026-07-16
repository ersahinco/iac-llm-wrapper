"""Requirement-focused plan conformance for the approved Terraform VPC target."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from . import conformance_spec as spec
from .conformance_models import (
    ConformanceIdentities,
    ConformanceIssue,
    ConformanceResult,
    ConformanceSpecification,
    ConformanceStatus,
    ControlOutcome,
    DeferredGate,
    Observation,
    ObservationStatus,
    Outcome,
    ProofClass,
    RequirementOutcome,
    ResourceProvenance,
)
from .contracts import POLICY_PACK
from .graph import build_graph
from .models import TerraformVpcIntent
from .target import MODULE_SOURCE, MODULE_VARIABLES, PROVIDER_SOURCE, TERRAFORM_VERSION

_MISSING = object()
_UNKNOWN = object()
_SENSITIVE = object()
_CHECK_EXPECTED = object()


@dataclass
class _Check:
    key: str
    expected: Any
    proof_class: ProofClass = "plan-observation"
    observations: list[Observation] = field(default_factory=list)


def evaluate_plan_conformance(
    plan: dict[str, Any],
    *,
    intent: TerraformVpcIntent,
    module_inputs: dict[str, Any],
    identities: dict[str, str],
) -> tuple[ConformanceResult, list[ConformanceIssue]]:
    """Compare one Terraform plan with replay-bound VPC decisions and inputs."""
    applicable, not_applicable, coverage_issue = _applicability(intent)
    if coverage_issue:
        return empty_conformance(identities=identities, applicable=applicable), [coverage_issue]
    issues = _plan_metadata_issues(plan)
    if issues:
        return (
            empty_conformance(
                identities=identities,
                applicable=applicable,
                not_applicable=not_applicable,
                intent=intent,
            ),
            issues,
        )
    checks = _checks(intent, applicable)
    issues = _record_inputs(plan, intent, module_inputs, checks)
    changes, change_issues = _resource_changes(plan)
    issues.extend(change_issues)
    resources, provenance_issues = _resource_provenance(changes, set(applicable))
    issues.extend(provenance_issues)
    _record_plan_observations(plan, changes, intent, checks, issues)
    requirements = [_finish(checks[key]) for key in applicable]
    issues.extend(_requirement_issues(requirements))
    controls = _controls(requirements)
    result = ConformanceResult(
        status=_overall_status(requirements, controls, issues),
        specification=ConformanceSpecification(
            id="terraform-vpc/plan-conformance/v2", sha256=spec.conformance_spec_digest()
        ),
        identities=ConformanceIdentities.model_validate(identities),
        requirements=requirements,
        controls=controls,
        notApplicableRequirementIds=[spec.requirement_id(key) for key in not_applicable],
        deferredGates=_deferred_gates(controls),
        resources=resources,
    )
    return result, issues


def empty_conformance(
    *,
    identities: dict[str, str],
    applicable: list[str] | None = None,
    not_applicable: list[str] | None = None,
    intent: TerraformVpcIntent | None = None,
) -> ConformanceResult:
    applicable = list(applicable or spec.REQUIREMENT_KEYS)
    expected = intent.model_dump() if intent else {}
    requirements = [
        RequirementOutcome(
            requirementId=spec.requirement_id(key),
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
        for control_id in spec.CONTROL_IDS
    ]
    return ConformanceResult(
        status="incomplete",
        specification=ConformanceSpecification(
            id="terraform-vpc/plan-conformance/v2", sha256=spec.conformance_spec_digest()
        ),
        identities=ConformanceIdentities.model_validate(identities),
        requirements=requirements,
        controls=controls,
        notApplicableRequirementIds=[spec.requirement_id(key) for key in not_applicable or []],
        deferredGates=[],
        resources=[],
    )


def _applicability(
    intent: TerraformVpcIntent,
) -> tuple[list[str], list[str], ConformanceIssue | None]:
    graph = build_graph()
    graph_keys = graph.topological_order()
    if set(graph_keys) != set(spec.REQUIREMENT_KEYS) or {
        control.id for control in POLICY_PACK.controls
    } != set(spec.CONTROL_IDS):
        return (
            graph_keys,
            [],
            _issue(
                "TERRAFORM_CONFORMANCE_SPEC_DRIFT",
                "The VPC plan specification does not cover the current graph or controls.",
                "Update and review the target-local specification before planning.",
            ),
        )
    values = intent.model_dump()
    applicable: set[str] = set()
    skipped: set[str] = set()
    for key in graph_keys:
        if graph.is_applicable(key):
            applicable.add(key)
            graph.decide(key, _graph_value(values[key]))
        else:
            skipped.add(key)
            graph.skip(key, "not applicable during plan conformance")
    return (
        [key for key in spec.REQUIREMENT_KEYS if key in applicable],
        [key for key in spec.REQUIREMENT_KEYS if key in skipped],
        None,
    )


def _graph_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return ",".join(str(item) for item in value) if isinstance(value, list) else str(value)


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
    checks = (
        ("terraform_version", TERRAFORM_VERSION, "TOOLCHAIN_MISMATCH"),
        ("errored", False, "ERRORED_INVALID"),
        ("complete", True, "COMPLETE_INVALID"),
        ("applyable", True, "APPLYABLE_INVALID"),
    )
    for name, expected, code in checks:
        if plan.get(name) == expected:
            continue
        issues.append(
            _issue(
                f"TERRAFORM_PLAN_{code}",
                f"Terraform plan field {name!r} must be {expected!r}.",
                "Produce a complete plan with the exact approved Terraform adapter.",
            )
        )
    return issues


def _checks(intent: TerraformVpcIntent, applicable: list[str]) -> dict[str, _Check]:
    expected = intent.model_dump()
    return {
        key: _Check(
            key,
            expected[key],
            "immutable-input" if key == "deployment_pipeline_ref" else "plan-observation",
        )
        for key in applicable
    }


def _expected_variables(intent: TerraformVpcIntent) -> dict[str, Any]:
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


def _record_inputs(
    plan: dict[str, Any],
    intent: TerraformVpcIntent,
    module_inputs: dict[str, Any],
    checks: dict[str, _Check],
) -> list[ConformanceIssue]:
    expected = _expected_variables(intent)
    issues: list[ConformanceIssue] = []
    if set(module_inputs) != MODULE_VARIABLES:
        issues.append(
            _issue(
                "TERRAFORM_MODULE_INPUTS_INVALID",
                "Replay-bound module inputs do not match the approved module variable set.",
                "Recompile the source packet with the registered target.",
            )
        )
    for name in MODULE_VARIABLES:
        _record_variable(
            checks,
            f"module-inputs.yaml:variables.{name}",
            name,
            expected[name],
            module_inputs.get(name, _MISSING),
        )
    variables = plan.get("variables")
    if not isinstance(variables, dict) or set(variables) != spec.ROOT_VARIABLES:
        issues.append(
            _issue(
                "TERRAFORM_PLAN_VARIABLES_INVALID",
                "Terraform plan variables do not exactly match the approved root input set.",
                "Re-plan from the replay-verified module inputs.",
            )
        )
    else:
        for name, expected_value in expected.items():
            entry = variables.get(name)
            actual = entry.get("value", _MISSING) if isinstance(entry, dict) else _MISSING
            _record_variable(checks, f"plan.variables.{name}", name, expected_value, actual)
    configuration_issue = _configuration_issue(plan)
    if configuration_issue:
        issues.append(configuration_issue)
    _record(
        checks,
        "primary_region",
        "plan.configuration.provider.aws.region",
        ["var.region"],
        _provider_region_references(plan),
    )
    return issues


def _record_variable(
    checks: dict[str, _Check], reference: str, name: str, expected: Any, actual: Any
) -> None:
    if name == "azs":
        _record(
            checks,
            "primary_region",
            reference,
            sorted(expected),
            sorted(actual) if isinstance(actual, list) else actual,
        )
        count = len(actual) if isinstance(actual, list) else _MISSING
        _record(checks, "az_count", reference + ".count", len(expected), count)
        return
    normalized = sorted(expected) if isinstance(expected, list) else expected
    observed = sorted(actual) if isinstance(actual, list) else actual
    _record(checks, spec.VARIABLE_REQUIREMENT[name], reference, normalized, observed)


def _configuration_issue(plan: dict[str, Any]) -> ConformanceIssue | None:
    configuration = plan.get("configuration")
    root = configuration.get("root_module") if isinstance(configuration, dict) else None
    calls = root.get("module_calls") if isinstance(root, dict) else None
    call = calls.get("vpc") if isinstance(calls, dict) else None
    expressions = call.get("expressions") if isinstance(call, dict) else None
    resources = root.get("resources") if isinstance(root, dict) else None
    providers = configuration.get("provider_config") if isinstance(configuration, dict) else None
    provider = (
        next(iter(providers.values()))
        if isinstance(providers, dict) and len(providers) == 1
        else None
    )
    source = call.get("source") or call.get("resolved_source") if isinstance(call, dict) else None
    module_ok = (
        isinstance(calls, dict)
        and set(calls) == {"vpc"}
        and source in {MODULE_SOURCE, f"registry.terraform.io/{MODULE_SOURCE}"}
        and isinstance(expressions, dict)
        and set(expressions) == MODULE_VARIABLES
        and all(
            isinstance(expressions[name], dict)
            and expressions[name].get("references") == [f"var.{name}"]
            for name in MODULE_VARIABLES
        )
    )
    resource_ok = (
        isinstance(resources, list)
        and len(resources) == 1
        and isinstance(resources[0], dict)
        and (
            resources[0].get("address"),
            resources[0].get("mode"),
            resources[0].get("type"),
            resources[0].get("provider_config_key"),
        )
        == ("data.aws_caller_identity.current", "data", "aws_caller_identity", "aws")
    )
    provider_ok = (
        isinstance(provider, dict)
        and provider.get("full_name") == f"registry.terraform.io/{PROVIDER_SOURCE}"
        and isinstance(provider.get("expressions"), dict)
    )
    if module_ok and resource_ok and provider_ok:
        return None
    return _issue(
        "TERRAFORM_PLAN_CONFIGURATION_UNAPPROVED",
        "Terraform plan configuration is not the exact approved root/module/provider shape.",
        "Restore the code-owned root and re-plan.",
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
        return [], [_resource_issue("Terraform plan JSON has no resource change inventory.")]
    changes = [item for item in raw if isinstance(item, dict)]
    if len(changes) != len(raw):
        return changes, [_resource_issue("Terraform plan contains a malformed resource change.")]
    return changes, []


def _resource_provenance(
    changes: list[dict[str, Any]], applicable: set[str]
) -> tuple[list[ResourceProvenance], list[ConformanceIssue]]:
    provider = f"registry.terraform.io/{PROVIDER_SOURCE}"
    resources: list[ResourceProvenance] = []
    issues: list[ConformanceIssue] = []
    seen: set[str] = set()
    data_seen = False
    for change in changes:
        address = change.get("address")
        if not isinstance(address, str) or address in seen:
            issues.append(_resource_issue("Resource addresses are missing or duplicated."))
            continue
        seen.add(address)
        if change.get("mode") == "data":
            if _approved_data_change(change, provider):
                data_seen = True
            else:
                issues.append(_resource_issue(f"Data resource {address!r} is not approved."))
            continue
        family = _resource_family(change)
        change_block = change.get("change")
        actions = change_block.get("actions") if isinstance(change_block, dict) else None
        if (
            change.get("mode") != "managed"
            or change.get("module_address") != "module.vpc"
            or change.get("provider_name") != provider
            or not address.startswith("module.vpc.")
            or family is None
            or actions != ["create"]
        ):
            issues.append(_resource_issue(f"Managed resource {address!r} has unapproved origin."))
            continue
        requirements, controls = spec.RESOURCE_FAMILIES[family]
        resources.append(
            ResourceProvenance(
                address=address,
                mode="managed",
                provider=provider,
                resourceType=str(change.get("type", "")),
                requirementIds=[
                    spec.requirement_id(key) for key in requirements if key in applicable
                ],
                controlIds=list(controls),
            )
        )
    if not data_seen:
        issues.append(_resource_issue("The approved caller-identity data read is missing."))
    return sorted(resources, key=lambda item: item.address), issues


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


def _resource_family(change: dict[str, Any]) -> str | None:
    address = str(change.get("address", ""))
    resource_type = change.get("type")
    if resource_type == "aws_vpc":
        return "vpc" if address == "module.vpc.aws_vpc.this[0]" else None
    return next(
        (
            family
            for prefix, expected_type, family in spec.RESOURCE_RULES
            if address.startswith(prefix) and resource_type == expected_type
        ),
        None,
    )


def _record_plan_observations(
    plan: dict[str, Any],
    changes: list[dict[str, Any]],
    intent: TerraformVpcIntent,
    checks: dict[str, _Check],
    issues: list[ConformanceIssue],
) -> None:
    by_address = {
        item.get("address"): item for item in changes if isinstance(item.get("address"), str)
    }
    vpc = by_address.get("module.vpc.aws_vpc.this[0]")
    for key, path in (
        ("vpc_name", ("tags", "Name")),
        ("primary_region", ("region",)),
        ("cidr", ("cidr_block",)),
        ("enable_dns_hostnames", ("enable_dns_hostnames",)),
    ):
        _record(
            checks,
            key,
            f"plan.resources.module.vpc.aws_vpc.this[0].{'.'.join(path)}",
            _CHECK_EXPECTED,
            _change_value(vpc, path),
        )
    public = _with_prefix(changes, "module.vpc.aws_subnet.public[")
    private = _with_prefix(changes, "module.vpc.aws_subnet.private[")
    _record_subnets(checks, "public_subnet_cidrs", public, intent.az_count)
    _record_subnets(checks, "private_subnet_cidrs", private, intent.az_count)
    _record(
        checks,
        "primary_region",
        "plan.resources.aws_subnet.availability_zone.set",
        sorted(_expected_variables(intent)["azs"]),
        _attribute_set(public + private, ("availability_zone",)),
    )
    nat = _with_prefix(changes, "module.vpc.aws_nat_gateway.this[")
    expected_nat = (
        (1 if intent.single_nat_gateway else intent.az_count) if intent.enable_nat_gateway else 0
    )
    topology = (int(vpc is not None), len(public), len(private), len(nat))
    if topology != (1, intent.az_count, intent.az_count, expected_nat):
        issues.append(_resource_issue("VPC, subnet, or NAT topology does not match the intent."))
    observed_nat: Any = len(nat) if nat or expected_nat == 0 else _MISSING
    _record(
        checks,
        "enable_nat_gateway",
        "plan.resources.aws_nat_gateway.count",
        expected_nat,
        observed_nat,
    )
    _record(
        checks,
        "single_nat_gateway",
        "plan.resources.aws_nat_gateway.count",
        expected_nat,
        observed_nat,
    )
    _record_account(plan, checks)
    _record(
        checks,
        "deployment_pipeline_ref",
        "decision-report.yaml:delivery.deploymentPipelineRef",
        intent.deployment_pipeline_ref,
        intent.deployment_pipeline_ref,
    )


def _record_subnets(
    checks: dict[str, _Check], key: str, changes: list[dict[str, Any]], count: int
) -> None:
    observed_count: Any = len(changes) if changes else _MISSING
    _record(checks, "az_count", f"plan.resources.{key}.count", count, observed_count)
    _record(
        checks,
        key,
        f"plan.resources.{key}.cidr_block.set",
        _CHECK_EXPECTED,
        _attribute_set(changes, ("cidr_block",)),
    )


def _record_account(plan: dict[str, Any], checks: dict[str, _Check]) -> None:
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
    _record(checks, "target_account_id", "plan.outputs.aws_caller_identity", _CHECK_EXPECTED, value)


def _with_prefix(changes: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    return sorted(
        [item for item in changes if str(item.get("address", "")).startswith(prefix)],
        key=lambda item: str(item.get("address", "")),
    )


def _attribute_set(changes: list[dict[str, Any]], path: tuple[str, ...]) -> Any:
    if not changes:
        return _MISSING
    values = [_change_value(change, path) for change in changes]
    for marker in (_SENSITIVE, _UNKNOWN, _MISSING):
        if any(value is marker for value in values):
            return marker
    return sorted(dict.fromkeys(values))


def _change_value(change: dict[str, Any] | None, path: tuple[str, ...]) -> Any:
    if not isinstance(change, dict) or not isinstance(change.get("change"), dict):
        return _MISSING
    payload = change["change"]
    if _masked(payload.get("after_sensitive"), path):
        return _SENSITIVE
    if _masked(payload.get("after_unknown"), path):
        return _UNKNOWN
    value: Any = payload.get("after", _MISSING)
    for part in path:
        if not isinstance(value, dict) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _masked(mask: Any, path: tuple[str, ...]) -> bool:
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
    if not check:
        return
    expected = check.expected if expected is _CHECK_EXPECTED else expected
    markers: dict[int, ObservationStatus] = {
        id(_MISSING): "missing",
        id(_UNKNOWN): "unknown",
        id(_SENSITIVE): "sensitive",
    }
    status = markers.get(id(observed))
    if status:
        check.observations.append(Observation(reference=reference, status=status))
        return
    check.observations.append(
        Observation(
            reference=reference,
            status="match" if _equal(expected, observed) else "mismatch",
            value=observed,
        )
    )


def _finish(check: _Check) -> RequirementOutcome:
    statuses = {item.status for item in check.observations}
    if "mismatch" in statuses:
        outcome: Outcome = "failed"
        message = "Known immutable input or plan observations contradict the requirement."
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
        requirementId=spec.requirement_id(check.key),
        graphKey=check.key,
        outcome=outcome,
        proofClass=check.proof_class,
        expected=check.expected,
        observations=check.observations,
        message=message,
    )


def _requirement_issues(requirements: list[RequirementOutcome]) -> list[ConformanceIssue]:
    codes = {
        "failed": "TERRAFORM_REQUIREMENT_FAILED",
        "unknown": "TERRAFORM_REQUIREMENT_UNKNOWN",
        "unresolved": "TERRAFORM_REQUIREMENT_UNRESOLVED",
    }
    return [
        _issue(
            codes[item.outcome],
            f"{item.requirement_id}: {item.message}",
            "Correct the source packet or code-owned target, then recompile and re-plan.",
        )
        for item in requirements
        if item.outcome in codes
    ]


def _controls(requirements: list[RequirementOutcome]) -> list[ControlOutcome]:
    by_key = {item.graph_key: item for item in requirements}
    controls: list[ControlOutcome] = []
    deferred = {
        "VPC-DELIVERY-001": "owner pipeline-control review",
        "VPC-NETWORK-001": "owner IPAM/allocation review",
        "VPC-ATTACHMENT-001": "downstream attachment review",
    }
    for control_id in spec.CONTROL_IDS:
        members = [by_key[key] for key in spec.CONTROL_SPEC[control_id] if key in by_key]
        outcomes = {item.outcome for item in members}
        blocking: Outcome | None = None
        for candidate in ("failed", "unknown", "unresolved"):
            if candidate in outcomes:
                blocking = cast(Outcome, candidate)
                break
        if blocking:
            outcome, proof, message = (
                blocking,
                "none",
                "A mapped requirement has no passing terminal outcome.",
            )
        elif control_id in deferred:
            outcome, proof, message = (
                "not-observable",
                "owner-attestation",
                "Plan-observable subclaims pass; independent owner evidence is still required.",
            )
        else:
            outcome, proof, message = (
                "proven",
                "plan-observation",
                "All plan-observable mapped requirements are proven.",
            )
        controls.append(
            ControlOutcome(
                controlId=control_id,
                outcome=outcome,
                proofClass=cast(ProofClass, proof),
                evidenceReferences=[item.requirement_id for item in members],
                deferredTo=deferred.get(control_id) if outcome == "not-observable" else None,
                message=message,
            )
        )
    return controls


def _deferred_gates(controls: list[ControlOutcome]) -> list[DeferredGate]:
    return [
        DeferredGate(
            id=f"terraform-vpc/deferred-gates/v1/{item.control_id.lower()}",
            controlId=item.control_id,
            laterPhase=item.deferred_to or "owner review",
            requiredEvidence="Independent owner evidence bound to the exact v2 evidence digest.",
        )
        for item in controls
        if item.outcome == "not-observable"
    ]


def _overall_status(
    requirements: list[RequirementOutcome],
    controls: list[ControlOutcome],
    issues: list[ConformanceIssue],
) -> ConformanceStatus:
    outcomes = {item.outcome for item in requirements} | {item.outcome for item in controls}
    if "failed" in outcomes:
        return "nonconformant"
    if outcomes & {"unknown", "unresolved"} or issues:
        return "incomplete"
    return "conformant-with-deferred-gates" if "not-observable" in outcomes else "conformant"


def _equal(expected: Any, observed: Any) -> bool:
    if isinstance(expected, list) and isinstance(observed, list):
        return sorted(expected) == sorted(observed)
    return bool(expected == observed)


def _resource_issue(message: str) -> ConformanceIssue:
    return _issue(
        "TERRAFORM_RESOURCE_PROVENANCE_UNRESOLVED",
        message,
        "Restore the approved root/module invocation and re-plan.",
    )


def _issue(code: str, message: str, next_action: str) -> ConformanceIssue:
    return ConformanceIssue(code=code, message=message, nextAction=next_action)
