"""AWS LZA thin-path pattern tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import ruamel.yaml

import intent_engine.patterns.aws_lza  # noqa: F401 — triggers pattern registration
from intent_engine.core.compiler import CompileError, compile_from_interview
from intent_engine.core.contracts import GLOBAL_CONTRACT_REGISTRY, ContractValidator
from intent_engine.core.generator import generate_all
from intent_engine.core.patterns import GLOBAL_REGISTRY
from intent_engine.patterns.aws_lza.contracts import AWS_LZA_SAMPLE_CONFIG_CONTRACT
from intent_engine.patterns.aws_lza.models import AwsLzaIntent

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


class TestAwsLzaPattern:
    def test_pattern_is_registered(self):
        assert "aws-lza" in GLOBAL_REGISTRY.list()
        pattern = GLOBAL_REGISTRY.get("aws-lza")
        assert pattern.description
        assert pattern.contracts == [AWS_LZA_SAMPLE_CONFIG_CONTRACT]
        assert pattern.required_artifacts == []
        assert "lineage-manifest.yaml" in pattern.expected_artifacts()
        assert "sample-recommendations.yaml" in pattern.expected_artifacts()
        for artifact in AWS_LZA_SAMPLE_CONFIG_CONTRACT.required_artifacts:
            assert artifact in pattern.expected_artifacts()

    def test_contract_matches_graph(self):
        graph = GLOBAL_REGISTRY.get("aws-lza").create_graph()
        assert graph._requirements["enabled_regions"].target_type == "string_list"
        assert graph._requirements["organizational_units"].target_type == "string_list"
        assert graph._requirements["workload_accounts"].target_type == "string_list"
        assert ContractValidator(AWS_LZA_SAMPLE_CONFIG_CONTRACT).validate_graph(graph) == []

    def test_contract_is_registered(self):
        contract = GLOBAL_CONTRACT_REGISTRY.get("aws-lza-sample-configuration")
        assert contract is AWS_LZA_SAMPLE_CONFIG_CONTRACT

    def test_compile_from_interview_creates_handoff_artifacts(self, tmp_path: Path):
        decisions = {
            "baseline": "standard",
            "org_mode": "control-tower",
            "organization_name": "Acme",
            "home_region": "eu-central-1",
            "enabled_regions": "eu-central-1, eu-west-1",
            "organizational_units": "Security, Infrastructure, Workloads",
            "workload_accounts": "Dev, Prod",
            "audit_account": "Audit",
            "log_archive_account": "LogArchive",
            "security_tooling_account": "SecurityTooling",
            "network_account": "Network",
            "identity_center_delegated_admin_account": "SecurityTooling",
            "topology": "hub-spoke",
            "network_cidr": "10.0.0.0/16",
            "centralized_logging": "true",
            "security_hub_enabled": "true",
            "guardduty_enabled": "true",
            "compliance_overlay": "none",
        }
        output = tmp_path / "output"
        compile_from_interview(decisions, output, pattern="aws-lza")

        for artifact in GLOBAL_REGISTRY.get("aws-lza").expected_artifacts():
            assert (output / artifact).exists(), artifact
        assert (output / "decision-audit.yaml").exists()
        assert not (output / "module-inputs.yaml").exists()
        assert not (output / "terraform.tfvars").exists()

        yaml = ruamel.yaml.YAML(typ="safe")
        org = yaml.load((output / "organization-config.yaml").read_text())
        assert org["enable"] is True
        assert {ou["name"] for ou in org["organizationalUnits"]} == {
            "Security",
            "Infrastructure",
            "Workloads",
        }

        accounts = yaml.load((output / "accounts-config.yaml").read_text())
        mandatory_names = {account["name"] for account in accounts["mandatoryAccounts"]}
        workload_names = {account["name"] for account in accounts["workloadAccounts"]}
        assert {"Management", "Audit", "LogArchive"} <= mandatory_names
        assert {"SecurityTooling", "Network", "Dev", "Prod"} <= workload_names
        assert all("@" in account["email"] for account in accounts["mandatoryAccounts"])

        iam = yaml.load((output / "iam-config.yaml").read_text())
        assert iam["identityCenter"]["delegatedAdminAccount"] == "SecurityTooling"
        assert iam["homeRegion"] == "eu-central-1"
        assert iam["identityCenter"]["identityCenterPermissionSets"] == []
        assert iam["identityCenter"]["identityCenterAssignments"] == []

        network = yaml.load((output / "network-config.yaml").read_text())
        assert network["vpcs"][0]["enableDnsHostnames"] is True
        assert network["vpcs"][0]["enableDnsSupport"] is True
        assert network["vpcs"][0]["routeTables"] == []
        assert network["vpcs"][0]["subnets"] == []
        assert network["vpcs"][0]["transitGatewayAttachments"] == []

        security = yaml.load((output / "security-config.yaml").read_text())
        assert security["centralSecurityServices"]["delegatedAdminAccount"] == "SecurityTooling"
        assert security["centralSecurityServices"]["ebsDefaultVolumeEncryption"] == {
            "enable": True,
            "excludeRegions": [],
        }
        assert security["centralSecurityServices"]["s3PublicAccessBlock"] == {
            "enable": True,
            "excludeAccounts": [],
        }
        assert security["centralSecurityServices"]["scpRevertChangesConfig"] == {
            "enable": True,
            "snsTopicName": "Security",
        }
        assert security["centralSecurityServices"]["macie"] == {
            "enable": False,
            "excludeRegions": [],
            "policyFindingsPublishingFrequency": "FIFTEEN_MINUTES",
            "publishSensitiveDataFindings": False,
        }
        assert security["centralSecurityServices"]["guardduty"]["autoEnableOrgMembers"] is True
        assert security["centralSecurityServices"]["guardduty"]["exportConfiguration"] == {
            "enable": True,
            "overrideExisting": True,
            "destinationType": "S3",
            "exportFrequency": "FIFTEEN_MINUTES",
        }
        assert security["centralSecurityServices"]["guardduty"]["s3Protection"] == {
            "enable": True,
            "excludeRegions": [],
        }
        assert security["centralSecurityServices"]["guardduty"]["eksProtection"] == {
            "enable": True,
            "excludeRegions": [],
        }
        assert security["centralSecurityServices"]["guardduty"]["lifecycleRules"] == []
        assert security["centralSecurityServices"]["snsSubscriptions"] == []
        assert security["centralSecurityServices"]["securityHub"]["autoEnableOrgMembers"] is True
        assert security["centralSecurityServices"]["securityHub"]["regionAggregation"] is True
        assert security["centralSecurityServices"]["securityHub"]["snsTopicName"] == "Security"
        assert security["centralSecurityServices"]["securityHub"]["notificationLevel"] == "HIGH"
        assert security["centralSecurityServices"]["securityHub"]["excludeRegions"] == []
        assert security["centralSecurityServices"]["securityHub"]["standards"][0][
            "deploymentTargets"
        ] == {"organizationalUnits": ["Root"]}
        assert (
            security["centralSecurityServices"]["securityHub"]["standards"][0]["controlsToDisable"]
            == []
        )
        assert security["centralSecurityServices"]["ssmAutomation"] == {
            "excludeRegions": [],
            "documentSets": [],
        }

        recommendations = yaml.load((output / "sample-recommendations.yaml").read_text())
        assert recommendations["pattern"] == "aws-lza"
        recommendation_names = [item["name"] for item in recommendations["recommendations"]]
        assert "aws-lza-standard-v1" in recommendation_names
        assert "aws-lza-regulated-v1" in recommendation_names

        lineage = yaml.load((output / "lineage-manifest.yaml").read_text())
        assert lineage["sourceContract"]["kind"] == "aws-lza-sample-configuration"
        assert lineage["sourceContract"]["url"] == AWS_LZA_SAMPLE_CONFIG_CONTRACT.source_url
        assert "iam-config.yaml" in lineage["sourceContract"]["mandatoryConfigFiles"]
        artifact_contracts = {item["name"]: item for item in lineage["artifacts"]}
        assert artifact_contracts["network-config.yaml"]["requiredPaths"] == [
            "defaultVpc.delete",
            "endpointPolicies",
            "transitGateways",
            "vpcs[]",
            "vpcs[].name",
            "vpcs[].account",
            "vpcs[].region",
            "vpcs[].cidrs[]",
            "vpcs[].enableDnsHostnames",
            "vpcs[].enableDnsSupport",
            "vpcs[].routeTables",
            "vpcs[].subnets",
            "vpcs[].transitGatewayAttachments",
        ]
        assert any(item["decision"] == "security_tooling_account" for item in lineage["lineage"])
        assert any(item["decision"] == "network_cidr" for item in lineage["lineage"])
        assert len(lineage["lineage"]) == len(AWS_LZA_SAMPLE_CONFIG_CONTRACT.lineage)

        runbook = (output / "deployment-runbook.md").read_text()
        assert "AWS LZA Deployment Runbook" in runbook
        assert "Mandatory configuration files" in runbook
        assert "Populate customer-specific Identity Center assignments" in runbook
        assert "parallel Terraform or Terragrunt" in runbook

    def test_standard_defaults_match_golden_fixture(self, tmp_path: Path):
        output = tmp_path / "output"
        compile_from_interview({}, output, pattern="aws-lza")

        yaml = ruamel.yaml.YAML(typ="safe")
        fixture_dir = FIXTURES / "aws-lza-standard-v1"
        for name in [
            "accounts-config.yaml",
            "global-config.yaml",
            "iam-config.yaml",
            "network-config.yaml",
            "organization-config.yaml",
            "security-config.yaml",
            "lineage-manifest.yaml",
            "sample-recommendations.yaml",
        ]:
            assert yaml.load((output / name).read_text()) == yaml.load(
                (fixture_dir / name).read_text()
            )
        assert (output / "deployment-runbook.md").read_text() == (
            fixture_dir / "deployment-runbook.md"
        ).read_text()

    def test_template_generation(self):
        from intent_engine.core.compiler import generate_template

        markdown = generate_template(pattern="aws-lza")
        assert "# Design Document — aws-lza pattern" in markdown
        assert "## LZA Baseline" in markdown
        assert "## Organization" in markdown
        assert "## Identity" in markdown
        assert "baseline: standard" in markdown
        assert "enabled_regions: eu-central-1" in markdown

    def test_validate_command_passes_for_generated_artifacts(self, tmp_path: Path):
        from typer.testing import CliRunner

        from intent_engine.cli import app

        output = tmp_path / "output"
        compile_from_interview({}, output, pattern="aws-lza")

        runner = CliRunner()
        result = runner.invoke(app, ["validate", "--input", str(output), "--pattern", "aws-lza"])
        assert result.exit_code == 0
        assert "Validation passed" in result.stdout

    def test_contract_artifact_validation_has_no_duplicate_errors(self, tmp_path: Path):
        from intent_engine.core.compiler import validate_generated, validate_generated_violations

        output = tmp_path / "output"
        compile_from_interview({}, output, pattern="aws-lza")
        (output / "iam-config.yaml").unlink()

        errors = validate_generated(output, pattern="aws-lza")
        assert errors.count("Missing required file: iam-config.yaml") == 1
        violations = validate_generated_violations(output, pattern="aws-lza")
        assert [violation.message for violation in violations].count(
            "Missing required file: iam-config.yaml"
        ) == 1

    def test_expected_artifact_validation_uses_contract_files(self, tmp_path: Path):
        from intent_engine.core.compiler import validate_generated

        output = tmp_path / "output"
        output.mkdir()

        errors = validate_generated(output, pattern="aws-lza")

        assert "Missing required file: accounts-config.yaml" in errors
        assert "Missing required file: lineage-manifest.yaml" in errors
        assert "Missing required file: sample-recommendations.yaml" in errors

    def test_contract_artifact_validation_catches_schema_drift(self, tmp_path: Path):
        from intent_engine.core.compiler import validate_generated

        output = tmp_path / "output"
        compile_from_interview({}, output, pattern="aws-lza")
        (output / "network-config.yaml").write_text(
            "defaultVpc: {}\nendpointPolicies: []\ntransitGateways: []\nvpcs: []\n"
        )

        errors = validate_generated(output, pattern="aws-lza")

        assert "network-config.yaml missing required path: defaultVpc.delete" in errors
        assert "network-config.yaml missing required path: vpcs[]" in errors

    def test_contract_artifact_validation_catches_security_hub_schema_drift(self, tmp_path: Path):
        from intent_engine.core.compiler import validate_generated

        output = tmp_path / "output"
        compile_from_interview({}, output, pattern="aws-lza")
        (output / "security-config.yaml").write_text(
            "homeRegion: eu-central-1\n"
            "accessAnalyzer:\n"
            "  enable: true\n"
            "iamPasswordPolicy:\n"
            "  allowUsersToChangePassword: true\n"
            "awsConfig:\n"
            "  enableConfigurationRecorder: true\n"
            "cloudWatch:\n"
            "  metricSets: []\n"
            "  alarmSets: []\n"
            "centralSecurityServices:\n"
            "  delegatedAdminAccount: SecurityTooling\n"
            "  ebsDefaultVolumeEncryption:\n"
            "    enable: true\n"
            "    excludeRegions: []\n"
            "  s3PublicAccessBlock:\n"
            "    enable: true\n"
            "    excludeAccounts: []\n"
            "  scpRevertChangesConfig:\n"
            "    enable: true\n"
            "    snsTopicName: Security\n"
            "  macie:\n"
            "    enable: false\n"
            "    excludeRegions: []\n"
            "    policyFindingsPublishingFrequency: FIFTEEN_MINUTES\n"
            "    publishSensitiveDataFindings: false\n"
            "  snsSubscriptions: []\n"
            "  guardduty:\n"
            "    enable: true\n"
            "    autoEnableOrgMembers: true\n"
            "    excludeRegions: []\n"
            "    s3Protection:\n"
            "      enable: true\n"
            "      excludeRegions: []\n"
            "    eksProtection:\n"
            "      enable: true\n"
            "      excludeRegions: []\n"
            "    exportConfiguration:\n"
            "      enable: true\n"
            "      overrideExisting: true\n"
            "      destinationType: S3\n"
            "      exportFrequency: FIFTEEN_MINUTES\n"
            "    lifecycleRules: []\n"
            "  securityHub:\n"
            "    enable: true\n"
            "    autoEnableOrgMembers: true\n"
            "    regionAggregation: true\n"
            "    snsTopicName: Security\n"
            "    notificationLevel: HIGH\n"
            "    excludeRegions: []\n"
            "    standards: []\n"
            "  ssmAutomation:\n"
            "    excludeRegions: []\n"
            "    documentSets: []\n"
        )

        errors = validate_generated(output, pattern="aws-lza")

        assert (
            "security-config.yaml missing required path: "
            "centralSecurityServices.securityHub.standards[]"
        ) in errors
        assert (
            "security-config.yaml missing required path: "
            "centralSecurityServices.securityHub.standards[].deploymentTargets"
            ".organizationalUnits[]"
        ) in errors

    def test_aws_generators_are_pattern_scoped(self, tmp_path: Path):
        generate_all(AwsLzaIntent(), tmp_path / "output", pattern="baseline")

        assert not (tmp_path / "output" / "organization-config.yaml").exists()

    def test_hub_spoke_requires_network_account(self, tmp_path: Path):
        with pytest.raises(CompileError) as excinfo:
            compile_from_interview(
                {
                    "topology": "hub-spoke",
                    "network_account": "",
                    "organizational_units": "Security, Infrastructure, Workloads",
                },
                tmp_path / "output",
                pattern="aws-lza",
            )

        codes = {violation.code for violation in excinfo.value.violations}
        assert "AWS_LZA_NETWORK_ACCOUNT_REQUIRED" in codes
