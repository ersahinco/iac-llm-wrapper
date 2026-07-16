"""Approved Terraform VPC speculative plan boundary tests."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from intent_engine.core.artifact_review import render_review_html
from intent_engine.core.compiler import compile_from_interview
from intent_engine.core.replay import verify_replay_manifest
from intent_engine.core.yaml_utils import load_bundle_yaml_mapping, write_yaml_artifact
from intent_engine.patterns.terraform_vpc import plan as plan_module
from intent_engine.patterns.terraform_vpc.contracts import PLAN_EVIDENCE_CONTRACT
from intent_engine.patterns.terraform_vpc.plan import (
    TerraformPlanError,
    run_plan,
    validate_approved_root,
)
from intent_engine.patterns.terraform_vpc.target import (
    MODULE_SOURCE,
    MODULE_VERSION,
    PLAN_EVIDENCE_NAME,
    PROVIDER_VERSION,
    TERRAFORM_VERSION,
)

_DECISIONS = {
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


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    output = tmp_path / "bundle"
    compile_from_interview(_DECISIONS, output, pattern="terraform-vpc")
    return output


def _result(argv: list[str], code: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, code, stdout, "")


def _fake_terraform(
    calls: list[list[str]],
    *,
    plan_exit: int = 2,
    account: str | None = "111122223333",
    changes: list[dict] | None = None,
    fail_stage: str = "",
    malformed_stage: str = "",
) -> Callable[[list[str], Path, dict[str, str]], subprocess.CompletedProcess[str]]:
    def fake(argv: list[str], cwd: Path, _: dict[str, str]) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        stage = argv[1]
        if stage == "version":
            if fail_stage == stage:
                return _result(argv, 1)
            return _result(argv, stdout=json.dumps({"terraform_version": TERRAFORM_VERSION}))
        if stage == "init":
            return _result(argv, 1 if fail_stage == stage else 0)
        if stage == "validate":
            if malformed_stage == stage:
                return _result(argv, stdout="not-json")
            return _result(argv, 1 if fail_stage == stage else 0, json.dumps({"valid": True}))
        if stage == "plan":
            if fail_stage == stage:
                return _result(argv, 1, "credential=secret-value")
            plan_path = Path(
                next(item.removeprefix("-out=") for item in argv if item.startswith("-out="))
            )
            plan_path.write_bytes(b"temporary-plan")
            return _result(argv, plan_exit)
        if stage == "show":
            if malformed_stage == stage:
                return _result(argv, stdout="not-json")
            if fail_stage == stage:
                return _result(argv, 1)
            outputs = {"aws_caller_identity": {"value": account}} if account is not None else {}
            return _result(
                argv,
                stdout=json.dumps(
                    {
                        "planned_values": {"outputs": outputs},
                        "resource_changes": changes or [],
                    }
                ),
            )
        raise AssertionError(f"Unexpected Terraform command: {argv}")

    return fake


@pytest.mark.parametrize("plan_exit", [0, 2])
def test_plan_accepts_terraform_detailed_success_codes_and_cleans_temp(
    bundle: Path, monkeypatch: pytest.MonkeyPatch, plan_exit: int
):
    calls: list[list[str]] = []
    workspaces: list[Path] = []
    fake = _fake_terraform(calls, plan_exit=plan_exit)

    def record(
        argv: list[str], cwd: Path, environment: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        workspaces.append(cwd)
        return fake(argv, cwd, environment)

    monkeypatch.setattr(plan_module, "_command", record)

    evidence = run_plan(bundle)

    assert evidence["status"] == "pass"
    assert evidence["plan"]["status"] == "proven"
    assert evidence["plan"]["hasChanges"] is (plan_exit == 2)
    assert [call[1] for call in calls] == ["version", "init", "validate", "plan", "show"]
    assert calls[1][2:] == ["-input=false", "-lockfile=readonly", "-no-color"]
    assert calls[3][2:5] == ["-input=false", "-no-color", "-detailed-exitcode"]
    assert not any("apply" in call or "destroy" in call for call in calls)
    assert workspaces and not workspaces[0].exists()
    assert evidence["plan"]["binaryPlanRetained"] is False
    assert evidence["plan"]["stateRetained"] is False


def test_plan_records_sorted_sanitized_resource_changes(
    bundle: Path, monkeypatch: pytest.MonkeyPatch
):
    changes = [
        {
            "address": "module.vpc.aws_vpc.this[0]",
            "type": "aws_vpc",
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "change": {"actions": ["create"]},
        },
        {
            "address": "module.vpc.aws_route_table.private[0]",
            "type": "aws_route_table",
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "change": {"actions": ["no-op"]},
        },
    ]
    calls: list[list[str]] = []
    monkeypatch.setattr(plan_module, "_command", _fake_terraform(calls, changes=changes))

    evidence = run_plan(bundle)

    assert [item["address"] for item in evidence["resourceChanges"]] == sorted(
        item["address"] for item in evidence["resourceChanges"]
    )
    assert evidence["changeSummary"]["create"] == 1
    assert evidence["changeSummary"]["noOp"] == 1
    rendered = (bundle / PLAN_EVIDENCE_NAME).read_text()
    assert "resource values" in rendered
    assert "planned_values" not in rendered
    assert "secret-value" not in rendered
    assert str(bundle) not in rendered


@pytest.mark.parametrize(
    ("fail_stage", "malformed_stage", "expected_code"),
    [
        ("init", "", "TERRAFORM_INIT_FAILED"),
        ("", "validate", "TERRAFORM_VALIDATE_FAILED"),
        ("plan", "", "TERRAFORM_PLAN_FAILED"),
        ("show", "", "TERRAFORM_SHOW_FAILED"),
        ("", "show", "TERRAFORM_SHOW_FAILED"),
    ],
)
def test_plan_fails_closed_at_each_terraform_stage(
    bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
    fail_stage: str,
    malformed_stage: str,
    expected_code: str,
):
    calls: list[list[str]] = []
    monkeypatch.setattr(
        plan_module,
        "_command",
        _fake_terraform(calls, fail_stage=fail_stage, malformed_stage=malformed_stage),
    )

    evidence = run_plan(bundle)

    assert evidence["status"] == "fail"
    assert expected_code in {item["code"] for item in evidence["blockers"]}
    assert len(evidence["stages"]) == 5
    assert "secret-value" not in json.dumps(evidence)


def test_missing_and_wrong_terraform_versions_fail_before_init(
    bundle: Path, monkeypatch: pytest.MonkeyPatch
):
    def missing(*_: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    monkeypatch.setattr(plan_module, "_command", missing)
    missing_evidence = run_plan(bundle)
    assert {item["code"] for item in missing_evidence["blockers"]} == {"TERRAFORM_NOT_FOUND"}

    calls: list[list[str]] = []

    def wrong(argv: list[str], _: Path, __: dict[str, str]) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return _result(argv, stdout=json.dumps({"terraform_version": "1.15.7"}))

    monkeypatch.setattr(plan_module, "_command", wrong)
    wrong_evidence = run_plan(bundle)
    assert {item["code"] for item in wrong_evidence["blockers"]} == {"TERRAFORM_VERSION_MISMATCH"}
    assert [call[1] for call in calls] == ["version"]


@pytest.mark.parametrize(
    ("account", "expected_code"),
    [(None, "AWS_CALLER_IDENTITY_MISSING"), ("999900001111", "AWS_ACCOUNT_MISMATCH")],
)
def test_plan_is_bound_to_the_requested_aws_account(
    bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
    account: str | None,
    expected_code: str,
):
    monkeypatch.setattr(plan_module, "_command", _fake_terraform([], account=account))

    evidence = run_plan(bundle)

    assert evidence["status"] == "fail"
    assert expected_code in {item["code"] for item in evidence["blockers"]}


def test_delete_and_replace_actions_are_destructive_blockers(
    bundle: Path, monkeypatch: pytest.MonkeyPatch
):
    changes = [
        {
            "address": "module.vpc.aws_vpc.this[0]",
            "type": "aws_vpc",
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "change": {"actions": ["delete"]},
        },
        {
            "address": "module.vpc.aws_subnet.private[0]",
            "type": "aws_subnet",
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "change": {"actions": ["delete", "create"]},
        },
    ]
    monkeypatch.setattr(plan_module, "_command", _fake_terraform([], changes=changes))

    evidence = run_plan(bundle)

    assert evidence["changeSummary"]["delete"] == 1
    assert evidence["changeSummary"]["replace"] == 1
    assert "TERRAFORM_DESTRUCTIVE_CHANGE_BLOCKED" in {item["code"] for item in evidence["blockers"]}


def test_replay_tampering_and_symlinks_block_execution(
    bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module_inputs = bundle / "module-inputs.yaml"
    module_inputs.write_text(module_inputs.read_text() + "# changed\n")

    def must_not_run(*_: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("Terraform must not run")

    monkeypatch.setattr(plan_module, "_command", must_not_run)
    changed = run_plan(bundle)
    assert "REPLAY_ARTIFACT_CHANGED" in {item["code"] for item in changed["blockers"]}

    outside = tmp_path / "outside.yaml"
    outside.write_text("moduleInputs: []\n")
    module_inputs.unlink()
    module_inputs.symlink_to(outside)
    symlinked = run_plan(bundle)
    codes = {item["code"] for item in symlinked["blockers"]}
    assert "REQUIRED_ARTIFACT_INVALID" in codes or "REPLAY_FILE_UNSAFE" in codes


def test_replay_rejects_unsafe_names_and_wrong_patterns(
    bundle: Path, monkeypatch: pytest.MonkeyPatch
):
    replay = load_bundle_yaml_mapping(bundle, "replay-manifest.yaml")
    replay["artifacts"]["files"][0]["name"] = "../decision-report.yaml"
    write_yaml_artifact(bundle / "replay-manifest.yaml", replay, "")
    violations = verify_replay_manifest(bundle, "terraform-vpc")
    assert "REPLAY_FILE_UNSAFE" in {item.code for item in violations}

    report = load_bundle_yaml_mapping(bundle, "decision-report.yaml")
    report["pattern"] = "aws-lza"
    write_yaml_artifact(bundle / "decision-report.yaml", report, "")
    monkeypatch.setattr(
        plan_module,
        "_command",
        lambda *_: (_ for _ in ()).throw(AssertionError("Terraform must not run")),
    )
    evidence = run_plan(bundle)
    assert {item["code"] for item in evidence["blockers"]} == {"TERRAFORM_PLAN_PATTERN_UNSUPPORTED"}


def test_approved_root_or_lock_drift_blocks_execution(
    bundle: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(plan_module, "approved_root_digest", lambda: "0" * 64)
    monkeypatch.setattr(
        plan_module,
        "_command",
        lambda *_: (_ for _ in ()).throw(AssertionError("Terraform must not run")),
    )

    evidence = run_plan(bundle)

    assert "TERRAFORM_APPROVED_ROOT_CHANGED" in {item["code"] for item in evidence["blockers"]}


def test_plan_invocation_requires_configuration_and_plan_readiness(bundle: Path):
    manifest = load_bundle_yaml_mapping(bundle, "plan-manifest.yaml")
    manifest["maturity"]["planReady"]["planAllowed"] = False
    write_yaml_artifact(bundle / "plan-manifest.yaml", manifest, "")

    blockers = plan_module._approved_manifest_blockers(bundle)

    assert "TERRAFORM_PLAN_INVOCATION_BLOCKED" in {item.code for item in blockers}


def test_manifest_and_evidence_pin_the_exact_approved_target(bundle: Path):
    manifest = load_bundle_yaml_mapping(bundle, "plan-manifest.yaml")

    assert manifest["target"]["module"] == {"source": MODULE_SOURCE, "version": MODULE_VERSION}
    assert manifest["target"]["provider"]["version"] == PROVIDER_VERSION
    assert manifest["toolchain"]["terraformVersion"] == TERRAFORM_VERSION
    assert manifest["maturity"]["configReady"]["allowed"] is True
    assert manifest["maturity"]["planReady"]["planAllowed"] is True
    assert manifest["maturity"]["planProven"]["proven"] is False
    assert manifest["planInvocation"]["applyAllowed"] is False
    assert {item["artifact"] for item in manifest["immutableInputs"]} == {
        "decision-report.yaml",
        "module-inputs.yaml",
        "terraform.tfvars",
    }
    assert PLAN_EVIDENCE_CONTRACT.artifacts[0].name == PLAN_EVIDENCE_NAME


def test_static_review_surfaces_plan_evidence_and_actionable_guidance(
    bundle: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        plan_module,
        "_command",
        _fake_terraform([], account="999900001111"),
    )
    run_plan(bundle)

    html = render_review_html(bundle)

    assert "Terraform Plan Evidence" in html
    assert "AWS_ACCOUNT_MISMATCH" in html
    assert "Select credentials for the intended account" in html
    assert "Fix the source requirement and recompile" in html
    assert "Seek owner review" in html


def test_validate_approved_root_runs_only_locked_init_and_validate(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[list[str]] = []

    def fake(argv: list[str], _: Path, __: dict[str, str]) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if argv[1] == "version":
            return _result(argv, stdout=json.dumps({"terraform_version": TERRAFORM_VERSION}))
        if argv[1] == "validate":
            return _result(argv, stdout=json.dumps({"valid": True}))
        return _result(argv)

    monkeypatch.setattr(plan_module, "_command", fake)

    validate_approved_root()

    assert [call[1] for call in calls] == ["version", "init", "validate"]
    assert calls[1][2:] == ["-backend=false", "-input=false", "-lockfile=readonly"]
    assert not any("plan" in call or "apply" in call for call in calls)


def test_invalid_bundle_root_cannot_create_evidence(tmp_path: Path):
    with pytest.raises(TerraformPlanError, match="Missing required bundle file"):
        run_plan(tmp_path)
