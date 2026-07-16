"""Tests for bring-your-own Terraform VPC module pattern."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import ruamel.yaml

import intent_engine.patterns.terraform_vpc  # noqa: F401 - triggers registration
from intent_engine.core.artifact_review import render_review_html
from intent_engine.core.compiler import CompileError, compile_from_interview, validate_generated
from intent_engine.core.patterns import GLOBAL_REGISTRY
from intent_engine.patterns.terraform_vpc import atmos as atmos_module
from intent_engine.patterns.terraform_vpc.atmos import (
    ATMOS_ABSTRACT_COMPONENT,
    ATMOS_CATALOG_ARTIFACT,
    ATMOS_COMPONENT_ROOT,
)
from intent_engine.patterns.terraform_vpc.target import ROOT_FILES, approved_root_path


def _yaml_load(path: Path) -> dict:
    yaml = ruamel.yaml.YAML(typ="safe")
    return yaml.load(path.read_text())


def _assert_atmos_handoff(bundle: Path, module_variables: dict) -> None:
    replay = _yaml_load(bundle / "replay-manifest.yaml")
    assert replay["pattern"] == "terraform-vpc"
    assert {item["name"] for item in replay["contracts"]} == {
        "terraform-aws-vpc-module",
        "terraform-vpc-atmos-handoff",
        "generic-plan-ready-bundle",
    }
    replay_files = {item["name"] for item in replay["artifacts"]["files"]}
    assert ATMOS_CATALOG_ARTIFACT in replay_files
    assert {f"{ATMOS_COMPONENT_ROOT}/{name}" for name in ROOT_FILES} <= replay_files
    catalog = _yaml_load(bundle / ATMOS_CATALOG_ARTIFACT)
    component = catalog["components"]["terraform"][ATMOS_ABSTRACT_COMPONENT]
    assert set(component) == {"metadata", "vars"}
    assert component["metadata"] == {
        "type": "abstract",
        "component": "terraform-vpc",
        "description": (
            "Approved Terraform VPC intent defaults. Create an owner-named real component "
            "that inherits this abstract component."
        ),
    }
    assert component["vars"] == {"region": "eu-central-1", **module_variables}
    assert not {
        "backend",
        "backend_type",
        "workspace",
        "terraform_workspace",
        "env",
        "auth",
        "identity",
        "credentials",
        "apply",
        "target_account_id",
        "deployment_pipeline_ref",
    } & set(component)
    for name in ROOT_FILES:
        assert (bundle / ATMOS_COMPONENT_ROOT / name).read_bytes() == (
            approved_root_path() / name
        ).read_bytes()
    handoff = _yaml_load(bundle / "handoff-plan.yaml")
    manual_gates = " ".join(handoff["manualGates"])
    assert "inherits terraform-vpc/intent-defaults" in manual_gates
    assert "backend, authentication, workspace, and approvals" in manual_gates
    assert "owner-controlled OSS pipeline re-plan" in manual_gates
    review_html = render_review_html(bundle)
    assert ATMOS_CATALOG_ARTIFACT in review_html
    assert "inherits terraform-vpc/intent-defaults" in review_html
    assert "backend, authentication, workspace, and approvals" in review_html
    assert "owner-controlled OSS pipeline re-plan" in review_html


class TestTerraformVpcPattern:
    def test_pattern_is_registered(self):
        pattern = GLOBAL_REGISTRY.get("terraform-vpc")
        assert pattern.name == "terraform-vpc"
        assert pattern.contracts[0].name == "terraform-aws-vpc-module"

    def test_contract_is_registered(self):
        contract = GLOBAL_REGISTRY.contract("terraform-aws-vpc-module")
        assert contract.kind == "terraform-module"
        assert "module-inputs.yaml" in contract.required_artifacts
        atmos = GLOBAL_REGISTRY.contract("terraform-vpc-atmos-handoff")
        assert atmos.kind == "atmos-terraform-component"
        assert ATMOS_CATALOG_ARTIFACT in atmos.required_artifacts

    def test_compile_creates_module_handoff(self, tmp_path: Path):
        decisions = {
            "vpc_name": "orders-vpc",
            "primary_region": "eu-central-1",
            "cidr": "10.30.0.0/16",
            "az_count": "2",
            "public_subnet_cidrs": "10.30.0.0/24,10.30.1.0/24",
            "private_subnet_cidrs": "10.30.10.0/24,10.30.11.0/24",
            "enable_nat_gateway": "true",
            "single_nat_gateway": "false",
            "enable_dns_hostnames": "true",
            "target_account_id": "111122223333",
            "deployment_pipeline_ref": "github://platform-networking/vpc-deploy",
        }

        compile_from_interview(decisions, tmp_path, pattern="terraform-vpc")

        assert not validate_generated(tmp_path, pattern="terraform-vpc")
        module_inputs = _yaml_load(tmp_path / "module-inputs.yaml")["moduleInputs"][0]
        assert module_inputs["moduleName"] == "terraform-aws-vpc"
        assert module_inputs["variables"]["name"] == "orders-vpc"
        assert module_inputs["variables"]["azs"] == ["eu-central-1a", "eu-central-1b"]
        assert module_inputs["variables"]["single_nat_gateway"] is False
        assert "target_account_id" not in module_inputs["variables"]
        assert "deployment_pipeline_ref" not in module_inputs["variables"]
        report = _yaml_load(tmp_path / "decision-report.yaml")
        assert report["pattern"] == "terraform-vpc"
        assert report["delivery"]["targetAccountId"] == "111122223333"
        assert report["delivery"]["deploymentPipelineRef"] == (
            "github://platform-networking/vpc-deploy"
        )
        assert report["handoffReadiness"]["handoffAllowed"] is True
        safe_path = " ".join(report["handoffReadiness"]["safeHandoffPath"])
        assert "existing target toolchain" in safe_path
        assert "accelerator/module toolchain" not in safe_path
        assert (tmp_path / "terraform.tfvars").exists()
        assert (tmp_path / "sample-recommendations.yaml").exists()
        policy_graph = _yaml_load(tmp_path / "policy-graph.yaml")
        assert policy_graph["schemaVersion"] == "intent-engine/policy-graph/v1"
        assert policy_graph["policyPacks"][0]["name"] == "regulated-vpc-baseline-v1"
        assert "SOC2" in policy_graph["policyPacks"][0]["frameworks"]
        context_manifest = _yaml_load(tmp_path / "context-manifest.yaml")
        assert context_manifest["contextInventory"]["policyPacks"][0]["name"] == (
            "regulated-vpc-baseline-v1"
        )
        assert "policy-graph.yaml" in context_manifest["outputs"]["expectedArtifacts"]
        assert "requirement-graph.json" in context_manifest["outputs"]["expectedArtifacts"]
        requirement_graph = json.loads((tmp_path / "requirement-graph.json").read_text())
        assert requirement_graph["nodeCount"] == 11
        assert {node["status"] for node in requirement_graph["nodes"]} == {"decided"}
        plan_manifest = _yaml_load(tmp_path / "plan-manifest.yaml")
        assert plan_manifest["target"]["module"]["version"] == "6.6.1"
        assert plan_manifest["target"]["provider"]["version"] == "6.53.0"
        assert plan_manifest["toolchain"]["terraformVersion"] == "1.15.8"
        assert plan_manifest["maturity"]["planReady"]["planAllowed"] is True
        assert plan_manifest["maturity"]["planProven"]["proven"] is False
        assert plan_manifest["planInvocation"]["applyAllowed"] is False
        _assert_atmos_handoff(tmp_path, module_inputs["variables"])
        target_capability = _yaml_load(tmp_path / "target-capability-graph.yaml")
        assert target_capability["coverage"]["unhandledAcceptedDecisions"] == []
        sample = GLOBAL_REGISTRY.get("terraform-vpc").samples[0]
        assert sample.module_refs[0].version == "6.6.1"

    def test_atmos_handoff_fails_when_approved_root_identity_changes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(
            atmos_module,
            "assert_approved_root_identity",
            lambda: (_ for _ in ()).throw(ValueError("approved root changed")),
        )
        with pytest.raises(ValueError, match="approved root changed"):
            compile_from_interview(
                {
                    "target_account_id": "111122223333",
                    "deployment_pipeline_ref": "github://platform-networking/vpc-deploy",
                },
                tmp_path,
                pattern="terraform-vpc",
            )

    def test_subnet_count_mismatch_fails(self, tmp_path: Path):
        decisions = {
            "vpc_name": "broken-vpc",
            "cidr": "10.30.0.0/16",
            "az_count": "2",
            "public_subnet_cidrs": "10.30.0.0/24",
            "private_subnet_cidrs": "10.30.10.0/24,10.30.11.0/24",
            "target_account_id": "111122223333",
            "deployment_pipeline_ref": "github://platform-networking/vpc-deploy",
        }

        with pytest.raises(CompileError) as excinfo:
            compile_from_interview(decisions, tmp_path, pattern="terraform-vpc")

        assert "PUBLIC_SUBNET_AZ_COUNT_MISMATCH" in str(excinfo.value)

    def test_az_count_outside_emitter_range_fails(self, tmp_path: Path):
        decisions = {
            "az_count": "7",
            "public_subnet_cidrs": ",".join(f"10.30.{index}.0/24" for index in range(7)),
            "private_subnet_cidrs": ",".join(f"10.31.{index}.0/24" for index in range(7)),
            "target_account_id": "111122223333",
            "deployment_pipeline_ref": "github://platform-networking/vpc-deploy",
        }

        with pytest.raises(CompileError) as excinfo:
            compile_from_interview(decisions, tmp_path, pattern="terraform-vpc")

        assert "INTENT_MODEL_AZ_COUNT_INVALID" in str(excinfo.value)

    def test_delivery_metadata_is_required(self, tmp_path: Path):
        decisions = {
            "vpc_name": "orders-vpc",
            "primary_region": "eu-central-1",
            "cidr": "10.30.0.0/16",
            "az_count": "2",
            "public_subnet_cidrs": "10.30.0.0/24,10.30.1.0/24",
            "private_subnet_cidrs": "10.30.10.0/24,10.30.11.0/24",
        }

        with pytest.raises(CompileError) as excinfo:
            compile_from_interview(decisions, tmp_path, pattern="terraform-vpc")

        text = str(excinfo.value)
        assert "TERRAFORM_VPC_TARGET_ACCOUNT_REQUIRED" in text
        assert "TERRAFORM_VPC_PIPELINE_REQUIRED" in text
