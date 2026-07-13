"""CloudFormation parameter handoff pattern tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import ruamel.yaml

import intent_engine.patterns.cloudformation_parameters  # noqa: F401
from intent_engine.core.compiler import CompileError, compile_from_interview, validate_generated
from intent_engine.core.patterns import GLOBAL_REGISTRY


def test_cloudformation_parameters_pattern_compiles(tmp_path: Path):
    decisions = {
        "stack_name": "orders-service-prod",
        "template_url": "s3://approved-templates/orders-service.yaml",
        "region": "eu-central-1",
        "parameter_overrides": "Environment=prod, ServiceName=orders, DesiredCount=3",
        "capabilities": "CAPABILITY_NAMED_IAM",
        "execution_role_arn": "arn:aws:iam::123456789012:role/cfn-execution-orders",
    }

    compile_from_interview(decisions, tmp_path, pattern="cloudformation-parameters")

    assert validate_generated(tmp_path, pattern="cloudformation-parameters") == []
    assert (tmp_path / "cloudformation-parameters.yaml").exists()
    assert (tmp_path / "decision-report.yaml").exists()
    assert (tmp_path / "handoff-plan.yaml").exists()
    assert not (tmp_path / "template.yaml").exists()
    assert not (tmp_path / "terraform.tfvars").exists()

    yaml = ruamel.yaml.YAML(typ="safe")
    handoff = yaml.load((tmp_path / "cloudformation-parameters.yaml").read_text())
    assert handoff["stackName"] == "orders-service-prod"
    assert handoff["parameters"] == [
        {"ParameterKey": "Environment", "ParameterValue": "prod"},
        {"ParameterKey": "ServiceName", "ParameterValue": "orders"},
        {"ParameterKey": "DesiredCount", "ParameterValue": "3"},
    ]
    report = yaml.load((tmp_path / "decision-report.yaml").read_text())
    assert report["pattern"] == "cloudformation-parameters"
    assert report["handoffReadiness"]["handoffAllowed"] is True
    safe_path = " ".join(report["handoffReadiness"]["safeHandoffPath"])
    assert "existing target toolchain" in safe_path
    assert "accelerator/module toolchain" not in safe_path


def test_cloudformation_parameters_pattern_is_registered():
    pattern = GLOBAL_REGISTRY.get("cloudformation-parameters")

    assert pattern.description
    assert "cloudformation-parameters.yaml" in pattern.expected_artifacts()
    assert "handoff-plan.yaml" in pattern.expected_artifacts()


def test_cloudformation_parameters_rejects_any_malformed_override(tmp_path: Path):
    with pytest.raises(CompileError) as exc_info:
        compile_from_interview(
            {
                "template_url": "s3://approved-templates/orders-service.yaml",
                "parameter_overrides": "Environment=prod, malformed",
            },
            tmp_path,
            pattern="cloudformation-parameters",
        )

    assert {violation.code for violation in exc_info.value.violations} == {
        "CLOUDFORMATION_PARAMETER_FORMAT_INVALID"
    }
