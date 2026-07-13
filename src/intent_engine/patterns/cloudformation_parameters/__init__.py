"""Bring-your-own CloudFormation template parameter handoff pattern."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from intent_engine.core.contracts import (
    ArtifactContract,
    DecisionLineage,
    TargetContract,
)
from intent_engine.core.patterns import GLOBAL_REGISTRY, Pattern, PatternGenerator
from intent_engine.core.requirements import Requirement, RequirementGraph
from intent_engine.core.validator import Violation
from intent_engine.core.yaml_utils import write_yaml_artifact

from .models import CloudFormationParametersIntent


def _intent(payload: Any) -> CloudFormationParametersIntent | None:
    intent = getattr(payload, "intent", payload)
    if isinstance(intent, CloudFormationParametersIntent):
        return intent
    return None


def _graph_factory() -> RequirementGraph:
    graph = RequirementGraph()
    graph.add(
        Requirement(
            key="stack_name",
            target_field="stack_name",
            target_type="string",
            label="Stack Name",
            question="What existing CloudFormation stack should receive parameters?",
            default="app-stack",
            category="cloudformation",
        )
    )
    graph.add(
        Requirement(
            key="template_url",
            target_field="template_url",
            target_type="string",
            label="Template URL",
            question="Where is the approved CloudFormation template stored?",
            category="cloudformation",
            violation_code="CLOUDFORMATION_TEMPLATE_URL_REQUIRED",
            violation_message="CloudFormation handoff requires an approved template URL.",
        )
    )
    graph.add(
        Requirement(
            key="region",
            target_field="region",
            target_type="string",
            label="Region",
            question="Which AWS region should receive this CloudFormation handoff?",
            default="eu-central-1",
            category="cloudformation",
        )
    )
    graph.add(
        Requirement(
            key="parameter_overrides",
            target_field="parameter_overrides",
            target_type="string_list",
            label="Parameter Overrides",
            question="Which TemplateParameter=Value overrides are approved?",
            category="cloudformation",
            violation_code="CLOUDFORMATION_PARAMETERS_REQUIRED",
            violation_message="CloudFormation handoff requires approved parameter overrides.",
        )
    )
    graph.add(
        Requirement(
            key="capabilities",
            target_field="capabilities",
            target_type="string_list",
            label="Capabilities",
            question="Which CloudFormation capabilities are approved?",
            default="CAPABILITY_NAMED_IAM",
            category="cloudformation",
        )
    )
    graph.add(
        Requirement(
            key="execution_role_arn",
            target_field="execution_role_arn",
            target_type="string",
            label="Execution Role ARN",
            question="Which existing execution role should the pipeline use?",
            default="",
            category="cloudformation",
            required_when_applicable=False,
        )
    )
    return graph


_CONTRACT = TargetContract(
    name="cloudformation-parameters-handoff",
    kind="cloudformation-parameters",
    source_url="https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/parameters-section-structure.html",
    required_decisions=[
        "stack_name",
        "template_url",
        "region",
        "parameter_overrides",
    ],
    artifacts=[
        ArtifactContract(
            name="decision-report.yaml",
            required_paths=[
                "stack.name",
                "stack.templateUrl",
                "stack.region",
                "stack.parameters[]",
            ],
        ),
        ArtifactContract(
            name="cloudformation-parameters.yaml",
            required_paths=[
                "stackName",
                "templateUrl",
                "region",
                "parameters[]",
                "parameters[].ParameterKey",
                "parameters[].ParameterValue",
                "capabilities[]",
            ],
        ),
    ],
    lineage=[
        DecisionLineage(
            decision="stack_name",
            artifact="cloudformation-parameters.yaml",
            path="stackName",
        ),
        DecisionLineage(
            decision="template_url",
            artifact="cloudformation-parameters.yaml",
            path="templateUrl",
        ),
        DecisionLineage(
            decision="parameter_overrides",
            artifact="cloudformation-parameters.yaml",
            path="parameters[]",
        ),
    ],
)


def _parameter_items(values: list[str]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for value in values:
        if "=" not in value:
            continue
        key, parameter_value = value.split("=", 1)
        items.append({"ParameterKey": key.strip(), "ParameterValue": parameter_value.strip()})
    return items


def _validate_intent(intent: Any) -> list[Violation]:
    model = _intent(intent)
    if model is None:
        return []
    violations: list[Violation] = []
    if model.parameter_overrides and not _parameter_items(model.parameter_overrides):
        violations.append(
            Violation(
                code="CLOUDFORMATION_PARAMETER_FORMAT_INVALID",
                message="CloudFormation parameters must use ParameterKey=ParameterValue format.",
            )
        )
    return violations


def gen_cloudformation_parameters(intent: Any, output_dir: Path) -> None:
    model = _intent(intent)
    if model is None:
        return
    data: dict[str, Any] = {
        "stackName": model.stack_name,
        "templateUrl": model.template_url,
        "region": model.region,
        "parameters": _parameter_items(model.parameter_overrides),
        "capabilities": model.capabilities,
        "executionRoleArn": model.execution_role_arn,
    }
    write_yaml_artifact(output_dir / "cloudformation-parameters.yaml", data, header="")


def gen_decision_report(intent: Any, output_dir: Path) -> None:
    readiness = getattr(intent, "handoff_readiness", {})
    model = _intent(intent)
    if model is None:
        return
    data = {
        "pattern": "cloudformation-parameters",
        "stack": {
            "name": model.stack_name,
            "templateUrl": model.template_url,
            "region": model.region,
            "parameters": model.parameter_overrides,
            "capabilities": model.capabilities,
            "executionRoleArn": model.execution_role_arn,
        },
        "boundary": (
            "Parameter handoff for an existing CloudFormation template; no stack is generated."
        ),
    }
    if readiness:
        data["handoffReadiness"] = readiness
    write_yaml_artifact(output_dir / "decision-report.yaml", data, header="")


SECTION_MAP: dict[str, tuple[str, str | None]] = {
    "stack_name": ("CloudFormation", "stack_name"),
    "template_url": ("CloudFormation", "template_url"),
    "region": ("CloudFormation", "region"),
    "parameter_overrides": ("Parameters", "parameter_overrides"),
    "capabilities": ("Execution", "capabilities"),
    "execution_role_arn": ("Execution", "execution_role_arn"),
}

GLOBAL_REGISTRY.register(
    Pattern(
        name="cloudformation-parameters",
        description="Bring-your-own CloudFormation template parameter handoff",
        graph_factory=_graph_factory,
        intent_factory=CloudFormationParametersIntent,
        section_map=SECTION_MAP,
        section_order=["CloudFormation", "Parameters", "Execution"],
        free_form_examples={
            "Parameters": ["parameter_overrides: Environment=prod, InstanceType=t3.small"],
        },
        prompt_context=(
            "This pattern captures parameter values for an existing approved "
            "CloudFormation template handoff. Extract stack name, template URL, region, "
            "capabilities, and explicit parameter overrides only. Do not generate a "
            "deployable stack or template."
        ),
        validators=[_validate_intent],
        generators=[
            PatternGenerator(
                "cloudformation-parameters",
                gen_cloudformation_parameters,
                priority=10,
            ),
            PatternGenerator("cloudformation-decision-report", gen_decision_report, priority=11),
        ],
        contracts=[_CONTRACT],
    )
)
