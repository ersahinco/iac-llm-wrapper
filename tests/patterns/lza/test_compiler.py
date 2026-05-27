"""Tests for intent-engine-wrapper compiler."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import ruamel.yaml

from intent_engine.core.compiler import (
    CompileError,
    compile_design,
    generate_template,
    review_reports,
    validate_generated,
)
from intent_engine.core.llm_caller import LLMCaller
from intent_engine.core.validator import validate
from intent_engine.patterns.lza.models import CI_CDMode, NetworkMode, RawIntent, Topology
from intent_engine.patterns.lza.normalizer import normalize_lza
from intent_engine.patterns.lza.validators import validate_lza_intent

from .conftest import MockLLMBackend
from .helpers import invalid_design_json, valid_payments_json

FIXTURES = Path(__file__).parent.parent.parent.parent / "fixtures"


def _load_yaml(path: Path):
    yaml = ruamel.yaml.YAML(typ="safe")
    with open(path) as f:
        return yaml.load(f)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestValidPaymentsCompilation:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path):
        self.output = tmp_path / "output"
        mock_backend = MockLLMBackend(valid_payments_json())
        llm_caller = LLMCaller(mock_backend)
        compile_design(FIXTURES / "valid-payments.md", self.output, llm_caller=llm_caller)

    def test_compilation_succeeds(self):
        assert self.output.exists()

    def test_all_generated_files_exist(self):
        required = [
            "organization-config.yaml",
            "accounts-config.yaml",
            "global-config.yaml",
            "security-config.yaml",
            "network-config.yaml",
            "iam-config.yaml",
            "customizations-config.yaml",
            "decision-report.yaml",
            "sample-recommendations.yaml",
            "deployment-graph.yaml",
        ]
        for fname in required:
            assert (self.output / fname).exists(), f"Missing: {fname}"

    def test_required_accounts_exist(self):
        data = _load_yaml(self.output / "accounts-config.yaml")
        names = {a["name"] for a in data["accounts"]}
        required = {"Network", "Audit", "LogArchive", "SharedServices", "PaymentsProd"}
        assert required <= names

    def test_security_controls_generated(self):
        sec = _load_yaml(self.output / "security-config.yaml")["security"]
        assert sec["s3"]["blockPublicAccess"] is True

    def test_iam_config_is_flat(self):
        """IAM config should have flat top-level properties (no 'iam:' wrapper)."""
        data = _load_yaml(self.output / "iam-config.yaml")
        assert "permissionBoundary" in data
        assert "iam" not in data

    def test_schema_version_present(self):
        """All LZA config files should have schemaVersion."""
        config_files = [
            "organization-config.yaml",
            "accounts-config.yaml",
            "global-config.yaml",
            "security-config.yaml",
            "network-config.yaml",
            "iam-config.yaml",
            "customizations-config.yaml",
        ]
        for fname in config_files:
            data = _load_yaml(self.output / fname)
            assert "schemaVersion" in data, f"{fname} missing schemaVersion"

    def test_global_config_has_cloudtrail(self):
        glb = _load_yaml(self.output / "global-config.yaml")["global"]
        assert glb["cloudtrail"]["organizationTrail"] is True
        assert glb["kms"]["rotationRequired"] is True

    def test_private_cicd_endpoints_auto_added(self):
        cust = _load_yaml(self.output / "customizations-config.yaml")
        endpoints = cust["customizations"][0]["endpoints"]
        required = {
            "s3",
            "sts",
            "kms",
            "logs",
            "ecr.api",
            "ecr.dkr",
            "secretsmanager",
            "ssm",
            "ec2messages",
            "ssmmessages",
        }
        assert required <= set(endpoints)

    def test_workload_config_generated(self):
        wl = _load_yaml(self.output / "workload-payments-api.yaml")
        assert wl["workload"]["name"] == "payments-api"
        assert wl["workload"]["account"] == "PaymentsProd"
        assert wl["workload"]["networkMode"] == "private"
        assert wl["workload"]["publicIngress"] is False

    def test_deployment_graph_has_ordered_phases(self):
        graph = _load_yaml(self.output / "deployment-graph.yaml")
        phases = graph["phases"]
        assert len(phases) >= 2
        all_steps = []
        for phase in phases:
            all_steps.extend(phase["steps"])
        assert "organization" in all_steps
        assert "workloads" in all_steps

    def test_decision_report_complete(self):
        report = _load_yaml(self.output / "decision-report.yaml")
        assert report["primaryRegion"] == "eu-central-1"
        assert report["topology"] == "hub-spoke"
        assert report["security"]["auditRetentionDays"] == 2555
        assert report["network"]["centralNetworkAccount"] == "Network"

    def test_organization_config(self):
        org = _load_yaml(self.output / "organization-config.yaml")
        assert org["organization"]["primaryRegion"] == "eu-central-1"
        ou_names = {ou["name"] for ou in org["organizationalUnits"]}
        assert {"Security", "Infrastructure", "Workloads/Prod"} <= ou_names

    def test_network_config(self):
        net = _load_yaml(self.output / "network-config.yaml")["network"]
        assert net["topology"] == "hub-spoke"
        assert net["centralNetworkAccount"] == "Network"


class TestDeterministicOutput:
    def test_same_input_produces_identical_output(self, tmp_path: Path):
        out1 = tmp_path / "out1"
        out2 = tmp_path / "out2"
        mock_backend = MockLLMBackend(valid_payments_json())
        llm_caller = LLMCaller(mock_backend)
        compile_design(FIXTURES / "valid-payments.md", out1, llm_caller=llm_caller)
        compile_design(FIXTURES / "valid-payments.md", out2, llm_caller=llm_caller)

        files1 = {f.name for f in out1.iterdir()}
        files2 = {f.name for f in out2.iterdir()}
        assert files1 == files2

        for fname in files1:
            h1 = _file_hash(out1 / fname)
            h2 = _file_hash(out2 / fname)
            assert h1 == h2, f"Non-deterministic output: {fname}"


class TestInvalidDesign:
    def test_hub_spoke_without_network_account_fails(self, tmp_path: Path):
        mock_backend = MockLLMBackend(invalid_design_json())
        llm_caller = LLMCaller(mock_backend)
        with pytest.raises(CompileError) as exc_info:
            compile_design(FIXTURES / "invalid-design.md", tmp_path / "out", llm_caller=llm_caller)

        codes = {v.code for v in exc_info.value.violations}
        assert "HUB_SPOKE_NETWORK_ACCOUNT_REQUIRED" in codes

    def test_private_cicd_without_placement_fails(self, tmp_path: Path):
        mock_backend = MockLLMBackend(invalid_design_json())
        llm_caller = LLMCaller(mock_backend)
        with pytest.raises(CompileError) as exc_info:
            compile_design(FIXTURES / "invalid-design.md", tmp_path / "out", llm_caller=llm_caller)

        codes = {v.code for v in exc_info.value.violations}
        assert "PRIVATE_CICD_PLACEMENT_REQUIRED" in codes


class TestNormalizer:
    def test_applies_cicd_endpoints(self):
        intent = RawIntent()
        intent.cicd.mode = CI_CDMode.PRIVATE
        result = normalize_lza(intent)
        assert "s3" in result.cicd.vpc_endpoints
        assert "kms" in result.cicd.vpc_endpoints
        assert len(result.cicd.vpc_endpoints) == 10

    def test_defaults_primary_region(self):
        intent = RawIntent()
        result = normalize_lza(intent)
        assert result.primary_region == "eu-central-1"

    def test_defaults_audit_retention(self):
        intent = RawIntent()
        result = normalize_lza(intent)
        assert result.security.audit_retention_days == 2555


class TestValidator:
    def test_hub_spoke_without_network_account(self):
        intent = RawIntent()
        intent.topology = Topology.HUB_SPOKE
        violations = validate(intent, extra_validators=[validate_lza_intent])
        codes = {v.code for v in violations}
        assert "HUB_SPOKE_NETWORK_ACCOUNT_REQUIRED" in codes

    def test_private_cicd_without_placement(self):
        intent = RawIntent()
        intent.cicd.mode = CI_CDMode.PRIVATE
        violations = validate(intent, extra_validators=[validate_lza_intent])
        codes = {v.code for v in violations}
        assert "PRIVATE_CICD_PLACEMENT_REQUIRED" in codes

    def test_workload_without_target_account(self):
        intent = RawIntent()
        from intent_engine.patterns.lza.models import Workload

        intent.workloads.append(Workload(name="test"))
        violations = validate(intent, extra_validators=[validate_lza_intent])
        codes = {v.code for v in violations}
        assert "WORKLOAD_TARGET_ACCOUNT_REQUIRED" in codes

    def test_private_ecs_with_public_networking(self):
        intent = RawIntent()
        from intent_engine.patterns.lza.models import Workload

        intent.workloads.append(
            Workload(name="test", target_account="acct", network_mode=NetworkMode.PUBLIC)
        )
        violations = validate(intent, extra_validators=[validate_lza_intent])
        codes = {v.code for v in violations}
        assert "PRIVATE_ECS_REQUIRES_PRIVATE_NETWORKING" in codes

    def test_egress_inspection_incomplete(self):
        from intent_engine.patterns.lza.models import EgressInspection

        intent = RawIntent()
        intent.security.egress_inspection = EgressInspection.REQUIRED
        violations = validate(intent, extra_validators=[validate_lza_intent])
        codes = {v.code for v in violations}
        assert "EGRESS_INSPECTION_INCOMPLETE" in codes

    def test_hybrid_config_incomplete(self):
        intent = RawIntent()
        intent.hybrid.required = True
        violations = validate(intent, extra_validators=[validate_lza_intent])
        codes = {v.code for v in violations}
        assert "HYBRID_CONFIG_INCOMPLETE" in codes

    def test_valid_intent_no_violations(self):
        mock_backend = MockLLMBackend(valid_payments_json())
        llm_caller = LLMCaller(mock_backend)
        out = Path("/tmp/test-validate-valid")
        compile_design(FIXTURES / "valid-payments.md", out, llm_caller=llm_caller, dry_run=True)


class TestDeterministicEntityExtraction:
    """Verify deterministic entity extraction works end-to-end (no LLM)."""

    def test_deterministic_path_populates_accounts_ous_workloads(self, tmp_path: Path):
        out = tmp_path / "output"
        compile_design(FIXTURES / "valid-payments.md", out, llm_caller=None)
        assert out.exists()

        # Accounts config should have all 5 accounts from markdown
        acct = _load_yaml(out / "accounts-config.yaml")
        names = {a["name"] for a in acct["accounts"]}
        assert names == {"Network", "Audit", "LogArchive", "SharedServices", "PaymentsProd"}

        # Organization config should have all 3 OUs
        org = _load_yaml(out / "organization-config.yaml")
        ou_names = {ou["name"] for ou in org["organizationalUnits"]}
        assert ou_names == {"Security", "Infrastructure", "Workloads/Prod"}

        # Workload config should exist
        wl = _load_yaml(out / "workload-payments-api.yaml")
        assert wl["workload"]["name"] == "payments-api"
        assert wl["workload"]["account"] == "PaymentsProd"

    def test_deterministic_path_catalog_diff_matches(self, tmp_path: Path):
        out = tmp_path / "output"
        compile_design(FIXTURES / "valid-payments.md", out, llm_caller=None)
        report = _load_yaml(out / "decision-report.yaml")
        # Core decisions from graph defaults + cascades
        assert report["primaryRegion"] == "eu-central-1"
        assert report["topology"] == "hub-spoke"
        # Network account auto-derived from account name containing "network"
        assert report["network"]["centralNetworkAccount"] == "Network"


class TestValidateGenerated:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path):
        self.output = tmp_path / "output"
        mock_backend = MockLLMBackend(valid_payments_json())
        llm_caller = LLMCaller(mock_backend)
        compile_design(FIXTURES / "valid-payments.md", self.output, llm_caller=llm_caller)

    def test_validate_generated_passes(self):
        errors = validate_generated(self.output)
        assert errors == []

    def test_validate_missing_file(self, tmp_path: Path):
        errors = validate_generated(tmp_path)
        assert len(errors) > 0
        assert any("organization-config.yaml" in e for e in errors)


class TestArtifactValidators:
    def test_cross_reference_workload_account(self, tmp_path: Path):
        from intent_engine.patterns.lza.validators import validate_lza_artifacts

        output = tmp_path / "out"
        output.mkdir()
        # Account exists
        (output / "accounts-config.yaml").write_text("accounts:\n  - name: PaymentsProd\n")
        # Workload references non-existent account
        (output / "workload-api.yaml").write_text(
            "workload:\n  name: api\n  account: NonExistent\n"
        )
        errors = validate_lza_artifacts(output)
        assert any("NonExistent" in e for e in errors)

    def test_cross_reference_network_account(self, tmp_path: Path):
        from intent_engine.patterns.lza.validators import validate_lza_artifacts

        output = tmp_path / "out"
        output.mkdir()
        (output / "accounts-config.yaml").write_text("accounts:\n  - name: Network\n")
        (output / "network-config.yaml").write_text(
            "network:\n  topology: hub-spoke\n  centralNetworkAccount: Missing\n"
        )
        errors = validate_lza_artifacts(output)
        assert any("Missing" in e for e in errors)

    def test_cross_reference_account_ou(self, tmp_path: Path):
        from intent_engine.patterns.lza.validators import validate_lza_artifacts

        output = tmp_path / "out"
        output.mkdir()
        (output / "organization-config.yaml").write_text(
            "organization:\n  primaryRegion: eu-central-1\n"
        )
        (output / "accounts-config.yaml").write_text("accounts:\n  - name: Test\n    ou: BadOU\n")
        errors = validate_lza_artifacts(output)
        assert any("BadOU" in e for e in errors)

    def test_valid_cross_references_pass(self, tmp_path: Path):
        from intent_engine.patterns.lza.validators import validate_lza_artifacts

        output = tmp_path / "out"
        output.mkdir()
        (output / "organization-config.yaml").write_text(
            "organization:\n  primaryRegion: eu-central-1\n"
            "organizationalUnits:\n  - name: Infrastructure\n"
        )
        (output / "accounts-config.yaml").write_text(
            "accounts:\n  - name: Network\n    ou: Infrastructure\n"
        )
        (output / "network-config.yaml").write_text(
            "network:\n  topology: hub-spoke\n  centralNetworkAccount: Network\n"
        )
        (output / "workload-api.yaml").write_text("workload:\n  name: api\n  account: Network\n")
        errors = validate_lza_artifacts(output)
        assert errors == []


def _write_report(path: Path, data: dict) -> None:
    yaml = ruamel.yaml.YAML()
    with open(path, "w") as f:
        yaml.dump(data, f)


class TestReviewReports:
    def test_identical_reports(self, tmp_path: Path):
        before = tmp_path / "before.yaml"
        after = tmp_path / "after.yaml"
        data = {"primaryRegion": "eu-central-1", "topology": "single-vpc"}
        _write_report(before, data)
        _write_report(after, data)
        result = review_reports(before, after)
        assert result["changes"] == []
        assert result["added"] == []
        assert result["removed"] == []

    def test_changed_values(self, tmp_path: Path):
        before = tmp_path / "before.yaml"
        after = tmp_path / "after.yaml"
        _write_report(before, {"primaryRegion": "eu-central-1", "topology": "single-vpc"})
        _write_report(after, {"primaryRegion": "eu-west-1", "topology": "hub-spoke"})
        result = review_reports(before, after)
        changes = {c["key"]: c for c in result["changes"]}
        assert changes["primaryRegion"]["before"] == "eu-central-1"
        assert changes["primaryRegion"]["after"] == "eu-west-1"
        assert changes["topology"]["before"] == "single-vpc"
        assert changes["topology"]["after"] == "hub-spoke"

    def test_added_keys(self, tmp_path: Path):
        before = tmp_path / "before.yaml"
        after = tmp_path / "after.yaml"
        _write_report(before, {"primaryRegion": "eu-central-1"})
        _write_report(after, {"primaryRegion": "eu-central-1", "topology": "hub-spoke"})
        result = review_reports(before, after)
        assert len(result["added"]) == 1
        assert result["added"][0]["key"] == "topology"
        assert result["added"][0]["value"] == "hub-spoke"

    def test_removed_keys(self, tmp_path: Path):
        before = tmp_path / "before.yaml"
        after = tmp_path / "after.yaml"
        _write_report(before, {"primaryRegion": "eu-central-1", "topology": "hub-spoke"})
        _write_report(after, {"primaryRegion": "eu-central-1"})
        result = review_reports(before, after)
        assert len(result["removed"]) == 1
        assert result["removed"][0]["key"] == "topology"

    def test_nested_security_diff(self, tmp_path: Path):
        before = tmp_path / "before.yaml"
        after = tmp_path / "after.yaml"
        _write_report(before, {"security": {"auditRetentionDays": 2555}})
        _write_report(after, {"security": {"auditRetentionDays": 365}})
        result = review_reports(before, after)
        changes = {c["key"]: c for c in result["changes"]}
        assert "security.auditRetentionDays" in changes
        assert changes["security.auditRetentionDays"]["before"] == 2555
        assert changes["security.auditRetentionDays"]["after"] == 365

    def test_wa_coverage_diff(self, tmp_path: Path):
        before = tmp_path / "before.yaml"
        after = tmp_path / "after.yaml"
        _write_report(before, {"wellArchitectedCoverage": {"Security": [{"decision": "topology"}]}})
        _write_report(
            after,
            {
                "wellArchitectedCoverage": {
                    "Security": [{"decision": "topology"}],
                    "Reliability": [{"decision": "audit_retention"}],
                }
            },
        )
        result = review_reports(before, after)
        assert len(result["wellArchitectedCoverage"]["before"]) == 1
        assert len(result["wellArchitectedCoverage"]["after"]) == 2

    def test_audit_trail_new_entries(self, tmp_path: Path):
        before = tmp_path / "before.yaml"
        after = tmp_path / "after.yaml"
        entry1 = {
            "timestamp": "2024-01-01",
            "key": "topology",
            "value": "single-vpc",
            "how": "decided",
        }
        entry2 = {
            "timestamp": "2024-02-01",
            "key": "region",
            "value": "eu-west-1",
            "how": "decided",
        }
        _write_report(before, {"decisionAuditTrail": [entry1]})
        _write_report(after, {"decisionAuditTrail": [entry1, entry2]})
        result = review_reports(before, after)
        assert result["audit"]["before_count"] == 1
        assert result["audit"]["after_count"] == 2
        assert len(result["audit"]["new_entries"]) == 1
        assert result["audit"]["new_entries"][0]["key"] == "region"

    def test_flat_list_values_diff(self, tmp_path: Path):
        before = tmp_path / "before.yaml"
        after = tmp_path / "after.yaml"
        _write_report(before, {"accounts": ["Network", "Audit"]})
        _write_report(after, {"accounts": ["Network", "Audit", "LogArchive"]})
        result = review_reports(before, after)
        changes = {c["key"]: c for c in result["changes"]}
        assert "accounts" in changes


class TestGenerateTemplate:
    def test_minimal_template_includes_core_sections(self):
        markdown = generate_template(pattern="minimal")
        assert "## Region" in markdown
        assert "## Topology" in markdown
        assert "## Network" in markdown
        assert "## Security" in markdown
        assert "primary: eu-central-1" in markdown
        assert "cidr: 10.0.0.0/16" in markdown
        assert "audit_retention_days: 2555" in markdown

    def test_minimal_template_excludes_unused_sections(self):
        markdown = generate_template(pattern="minimal")
        assert "## Hybrid Connectivity" not in markdown
        assert "## CI/CD" not in markdown

    def test_baseline_template_includes_all_sections(self):
        markdown = generate_template(pattern="baseline")
        assert "## Region" in markdown
        assert "## Topology" in markdown
        assert "## Network" in markdown
        assert "## Security" in markdown
        assert "## Hybrid Connectivity" in markdown
        assert "## CI/CD" in markdown

    def test_baseline_shows_conditional_fields_with_comment(self):
        markdown = generate_template(pattern="baseline")
        assert "Only when" in markdown
        assert "central_network_account" in markdown
        assert "hub_cidr" in markdown
        assert "inspection_pattern" in markdown
        assert "inspection_vendor" in markdown
        assert "cicd_mode" in markdown

    def test_template_includes_free_form_sections(self):
        markdown = generate_template(pattern="minimal")
        assert "## Organizational Units" in markdown
        assert "## Accounts" in markdown
        assert "## Workloads" in markdown
        assert "Security team accounts" in markdown

    def test_template_pattern_order_consistent(self):
        markdown = generate_template(pattern="baseline")
        region_idx = markdown.index("## Region")
        network_idx = markdown.index("## Network")
        security_idx = markdown.index("## Security")
        assert region_idx < network_idx < security_idx

    def test_template_financial_includes_compliance_fields(self):
        markdown = generate_template(pattern="financial-services")
        assert "data_residency" in markdown
        assert "encryption_key_management" in markdown
        assert "network_segmentation" in markdown

    def test_template_healthcare_includes_phi_fields(self):
        markdown = generate_template(pattern="healthcare")
        assert "phi_encryption" in markdown
        assert "audit_access_logging" in markdown
        assert "business_associate_agreements" in markdown

    def test_template_includes_question_comments(self):
        markdown = generate_template(pattern="minimal")
        assert "# Which AWS region is the primary landing zone region?" in markdown
        assert "# What network topology do you want?" in markdown

    def test_template_includes_options_and_defaults(self):
        markdown = generate_template(pattern="minimal")
        assert "# Options:" in markdown
        assert "# Default:" in markdown

    def test_topology_shows_default_uncommented_alternative_commented(self):
        markdown = generate_template(pattern="minimal")
        # Both options should appear
        assert "hub-spoke" in markdown
        assert "single-vpc" in markdown
        # At least one option should be commented
        assert "# - hub-spoke" in markdown or "# - single-vpc" in markdown

    def test_unknown_pattern_raises(self):
        import pytest

        with pytest.raises(KeyError):
            generate_template(pattern="nonexistent")
