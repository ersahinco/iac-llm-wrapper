"""Approved Terraform VPC speculative plan boundary."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from intent_engine.core.compile_artifacts import validate_generated_violations
from intent_engine.core.contracts import ContractValidator
from intent_engine.core.package_version import installed_version
from intent_engine.core.paths import BundleFileError, resolve_bundle_file
from intent_engine.core.replay import sha256_file, verify_replay_manifest
from intent_engine.core.yaml_utils import load_bundle_yaml_mapping, write_yaml_artifact

from .contracts import PLAN_EVIDENCE_CONTRACT
from .evidence import (
    PlanBlocker as _Blocker,
)
from .evidence import (
    PlanStage as _Stage,
)
from .evidence import (
    ResourceChange as _ResourceChange,
)
from .evidence import (
    blocker as _blocker,
)
from .evidence import (
    build_evidence as _build_evidence,
)
from .evidence import (
    check_account as _check_account,
)
from .evidence import (
    empty_change_summary as _empty_change_summary,
)
from .evidence import (
    observed_account as _observed_account,
)
from .evidence import (
    summarize_changes as _summarize_changes,
)
from .target import (
    MODULE_SOURCE,
    MODULE_VARIABLES,
    MODULE_VERSION,
    PLAN_EVIDENCE_NAME,
    PROVIDER_SOURCE,
    PROVIDER_VERSION,
    ROOT_FILES,
    TERRAFORM_VERSION,
    approved_root_digest,
    approved_root_identities,
    approved_root_path,
)


class TerraformPlanError(ValueError):
    """The approved plan boundary could not safely create evidence."""


def run_plan(bundle: Path, *, terraform_command: str = "terraform") -> dict[str, Any]:
    """Run the approved speculative Terraform VPC plan and write sanitized evidence."""
    bundle = _safe_bundle_root(bundle)
    evidence_path = bundle / PLAN_EVIDENCE_NAME
    stages: list[_Stage] = []
    blockers: list[_Blocker] = []
    resource_changes: list[_ResourceChange] = []
    summary = _empty_change_summary()
    requested_account = ""
    observed_account = ""
    plan_exit_code: int | None = None

    pattern = _bundle_pattern(bundle, blockers)
    if pattern == "terraform-vpc":
        blockers.extend(_bundle_blockers(bundle))
    if not blockers:
        requested_account, variables = _plan_inputs(bundle, blockers)
    else:
        variables = {}
    replay_identity = _replay_identity(bundle)

    if not blockers:
        try:
            with tempfile.TemporaryDirectory(prefix="intent-engine-terraform-vpc-") as tmp:
                workspace = Path(tmp)
                _copy_approved_root(workspace)
                (workspace / "terraform.auto.tfvars.json").write_text(
                    json.dumps(variables, sort_keys=True)
                )
                environment = {**os.environ, "TF_IN_AUTOMATION": "1"}
                _require_terraform_version(
                    terraform_command, workspace, environment, stages, blockers
                )
                if not blockers:
                    _run_init(terraform_command, workspace, environment, stages, blockers)
                if not blockers:
                    _run_validate(terraform_command, workspace, environment, stages, blockers)
                plan_path = workspace / "terraform.plan"
                if not blockers:
                    plan_exit_code = _run_speculative_plan(
                        terraform_command,
                        workspace,
                        plan_path,
                        environment,
                        stages,
                        blockers,
                    )
                if not blockers:
                    plan_json = _show_plan(
                        terraform_command,
                        workspace,
                        plan_path,
                        environment,
                        stages,
                        blockers,
                    )
                    if plan_json:
                        observed_account = _observed_account(plan_json)
                        resource_changes, summary = _summarize_changes(plan_json, blockers)
        except OSError as exc:
            blockers.append(
                _blocker(
                    "TERRAFORM_EXECUTION_FAILED",
                    f"Terraform could not be executed: {type(exc).__name__}.",
                    "Install the exact approved Terraform version and retry.",
                )
            )

    if plan_exit_code in {0, 2}:
        _check_account(requested_account, observed_account, blockers)
    evidence = _build_evidence(
        replay_identity=replay_identity,
        requested_account=requested_account,
        observed_account_id=observed_account,
        plan_exit_code=plan_exit_code,
        stages=stages,
        resource_changes=resource_changes,
        summary=summary,
        blockers=blockers,
    )
    write_yaml_artifact(
        evidence_path,
        evidence.model_dump(by_alias=True, mode="json"),
        "",
    )
    evidence_violations = ContractValidator(PLAN_EVIDENCE_CONTRACT).validate_artifacts(bundle)
    if evidence_violations:
        raise TerraformPlanError(
            "Generated Terraform plan evidence violated its schema: "
            + "; ".join(item.message for item in evidence_violations)
        )
    return evidence.model_dump(by_alias=True, mode="json")


def validate_approved_root(*, terraform_command: str = "terraform") -> None:
    """Run the credential-free CI init/validate proof for the approved root."""
    with tempfile.TemporaryDirectory(prefix="intent-engine-terraform-vpc-contract-") as tmp:
        workspace = Path(tmp)
        _copy_approved_root(workspace)
        (workspace / "terraform.auto.tfvars.json").write_text(
            json.dumps(
                {
                    "region": "eu-central-1",
                    "name": "contract-proof",
                    "cidr": "10.30.0.0/16",
                    "azs": ["eu-central-1a", "eu-central-1b"],
                    "public_subnets": ["10.30.0.0/24", "10.30.1.0/24"],
                    "private_subnets": ["10.30.10.0/24", "10.30.11.0/24"],
                    "enable_nat_gateway": True,
                    "single_nat_gateway": False,
                    "enable_dns_hostnames": True,
                },
                sort_keys=True,
            )
        )
        environment = {**os.environ, "TF_IN_AUTOMATION": "1"}
        version = _command([terraform_command, "version", "-json"], workspace, environment)
        if version.returncode or _terraform_version(version.stdout) != TERRAFORM_VERSION:
            raise TerraformPlanError(f"Terraform {TERRAFORM_VERSION} is required.")
        init = _command(
            [terraform_command, "init", "-backend=false", "-input=false", "-lockfile=readonly"],
            workspace,
            environment,
        )
        if init.returncode:
            raise TerraformPlanError("Approved Terraform root init failed.")
        validation = _command([terraform_command, "validate", "-json"], workspace, environment)
        data = _json_mapping(validation.stdout)
        if validation.returncode or not data or data.get("valid") is not True:
            raise TerraformPlanError("Approved Terraform root validation failed.")


def _safe_bundle_root(bundle: Path) -> Path:
    try:
        resolve_bundle_file(bundle, "decision-report.yaml")
    except BundleFileError as exc:
        raise TerraformPlanError(str(exc)) from exc
    return bundle.resolve(strict=True)


def _bundle_pattern(bundle: Path, blockers: list[_Blocker]) -> str:
    try:
        report = load_bundle_yaml_mapping(bundle, "decision-report.yaml")
    except (BundleFileError, ValueError) as exc:
        blockers.append(
            _blocker("BUNDLE_METADATA_INVALID", str(exc), "Recompile the bundle and retry.")
        )
        return ""
    pattern = report.get("pattern")
    if pattern != "terraform-vpc":
        blockers.append(
            _blocker(
                "TERRAFORM_PLAN_PATTERN_UNSUPPORTED",
                f"Terraform plan supports only 'terraform-vpc', got {pattern!r}.",
                "Use the plan command only with a terraform-vpc bundle.",
            )
        )
    return str(pattern or "")


def _bundle_blockers(bundle: Path) -> list[_Blocker]:
    blockers = [
        _blocker(item.code, item.message, "Recompile the bundle and retry.")
        for item in validate_generated_violations(bundle, "terraform-vpc")
    ]
    blockers.extend(
        _blocker(item.code, item.message, "Restore the immutable bundle and retry.")
        for item in verify_replay_manifest(bundle, "terraform-vpc")
    )
    blockers.extend(_approved_manifest_blockers(bundle))
    return blockers


def _approved_manifest_blockers(bundle: Path) -> list[_Blocker]:
    try:
        manifest = load_bundle_yaml_mapping(bundle, "plan-manifest.yaml")
        replay = load_bundle_yaml_mapping(bundle, "replay-manifest.yaml")
    except (BundleFileError, ValueError) as exc:
        return [
            _blocker(
                "TERRAFORM_PLAN_MANIFEST_INVALID",
                str(exc),
                "Recompile the bundle and retry.",
            )
        ]
    target = manifest.get("target")
    toolchain = manifest.get("toolchain")
    approved_root = manifest.get("approvedRoot")
    immutable_inputs = manifest.get("immutableInputs")
    source = manifest.get("sourceDocument")
    maturity = manifest.get("maturity")
    config_ready = maturity.get("configReady") if isinstance(maturity, dict) else None
    plan_ready = maturity.get("planReady") if isinstance(maturity, dict) else None
    try:
        expected_inputs = [
            {
                "artifact": name,
                "sha256": _bundle_file_digest(bundle, name),
            }
            for name in ("decision-report.yaml", "module-inputs.yaml", "terraform.tfvars")
        ]
    except BundleFileError:
        expected_inputs = []
    checks = [
        (
            isinstance(target, dict)
            and target.get("module") == {"source": MODULE_SOURCE, "version": MODULE_VERSION}
            and target.get("provider") == {"source": PROVIDER_SOURCE, "version": PROVIDER_VERSION},
            "TERRAFORM_APPROVED_TARGET_CHANGED",
            "Plan manifest does not identify the exact approved module and provider.",
        ),
        (
            isinstance(toolchain, dict)
            and toolchain.get("terraformVersion") == TERRAFORM_VERSION
            and toolchain.get("wrapperVersion") == installed_version(),
            "TERRAFORM_APPROVED_TOOLCHAIN_CHANGED",
            "Plan manifest does not identify the running approved toolchain.",
        ),
        (
            isinstance(approved_root, dict)
            and approved_root.get("sha256") == approved_root_digest()
            and approved_root.get("files") == approved_root_identities(),
            "TERRAFORM_APPROVED_ROOT_CHANGED",
            "The code-owned Terraform root or provider lockfile changed.",
        ),
        (
            immutable_inputs == expected_inputs,
            "TERRAFORM_IMMUTABLE_INPUTS_INVALID",
            "Plan manifest does not identify the exact required input artifacts.",
        ),
        (
            isinstance(config_ready, dict)
            and config_ready.get("allowed") is True
            and isinstance(plan_ready, dict)
            and plan_ready.get("planAllowed") is True,
            "TERRAFORM_PLAN_INVOCATION_BLOCKED",
            "Configuration or plan readiness does not allow Terraform invocation.",
        ),
        (
            isinstance(source, dict)
            and isinstance(replay.get("source"), dict)
            and source.get("mode") == replay["source"].get("mode")
            and source.get("sha256") == replay["source"].get("sha256"),
            "TERRAFORM_SOURCE_IDENTITY_CHANGED",
            "Plan and replay manifests disagree about the source document.",
        ),
    ]
    return [
        _blocker(code, message, "Recompile with the approved adapter and retry.")
        for passed, code, message in checks
        if not passed
    ]


def _bundle_file_digest(bundle: Path, name: str) -> str:
    path = resolve_bundle_file(bundle, name)
    assert path is not None
    return sha256_file(path)


def _plan_inputs(bundle: Path, blockers: list[_Blocker]) -> tuple[str, dict[str, Any]]:
    try:
        report = load_bundle_yaml_mapping(bundle, "decision-report.yaml")
        module_inputs = load_bundle_yaml_mapping(bundle, "module-inputs.yaml")
    except (BundleFileError, ValueError) as exc:
        blockers.append(
            _blocker("TERRAFORM_INPUT_INVALID", str(exc), "Recompile the bundle and retry.")
        )
        return "", {}
    vpc = report.get("vpc")
    delivery = report.get("delivery")
    entries = module_inputs.get("moduleInputs")
    if not isinstance(vpc, dict) or not isinstance(delivery, dict):
        blockers.append(
            _blocker(
                "TERRAFORM_INPUT_INVALID",
                "Decision report VPC or delivery metadata is invalid.",
                "Recompile the bundle and retry.",
            )
        )
        return "", {}
    if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
        blockers.append(
            _blocker(
                "TERRAFORM_INPUT_INVALID",
                "Exactly one approved Terraform VPC module input is required.",
                "Recompile the bundle and retry.",
            )
        )
        return "", {}
    entry = entries[0]
    variables = entry.get("variables")
    if entry.get("moduleName") != "terraform-aws-vpc" or not isinstance(variables, dict):
        blockers.append(
            _blocker(
                "TERRAFORM_INPUT_INVALID",
                "Module inputs do not target the approved Terraform VPC module.",
                "Recompile the bundle and retry.",
            )
        )
        return "", {}
    if set(variables) != MODULE_VARIABLES:
        blockers.append(
            _blocker(
                "TERRAFORM_INPUT_SET_INVALID",
                "Module input keys do not match the approved root variables.",
                "Correct the pattern adapter and recompile the bundle.",
            )
        )
        return "", {}
    region = vpc.get("region")
    account = delivery.get("targetAccountId")
    if not isinstance(region, str) or not isinstance(account, str):
        blockers.append(
            _blocker(
                "TERRAFORM_DELIVERY_IDENTITY_INVALID",
                "Region and target AWS account ID must be strings.",
                "Fix the delivery requirements and recompile the bundle.",
            )
        )
        return "", {}
    return account, {"region": region, **variables}


def _copy_approved_root(workspace: Path) -> None:
    for name in ROOT_FILES:
        source = approved_root_path() / name
        if source.is_symlink() or not source.is_file():
            raise TerraformPlanError(f"Approved Terraform root file is invalid: {name}.")
        shutil.copy2(source, workspace / name)


def _require_terraform_version(
    command: str,
    workspace: Path,
    environment: dict[str, str],
    stages: list[_Stage],
    blockers: list[_Blocker],
) -> None:
    try:
        result = _command([command, "version", "-json"], workspace, environment)
    except FileNotFoundError:
        stages.append(_Stage(name="terraform-version", status="fail"))
        blockers.append(
            _blocker(
                "TERRAFORM_NOT_FOUND",
                f"Terraform {TERRAFORM_VERSION} was not found.",
                "Install the exact approved Terraform version and retry.",
            )
        )
        return
    version = _terraform_version(result.stdout)
    passed = result.returncode == 0 and version == TERRAFORM_VERSION
    stages.append(
        _Stage(
            name="terraform-version",
            status="pass" if passed else "fail",
            exit_code=result.returncode,
        )
    )
    if not passed:
        blockers.append(
            _blocker(
                "TERRAFORM_VERSION_MISMATCH",
                f"Terraform {TERRAFORM_VERSION} is required; observed {version or 'unknown'}.",
                "Select the exact approved Terraform binary and retry.",
            )
        )


def _run_init(
    command: str,
    workspace: Path,
    environment: dict[str, str],
    stages: list[_Stage],
    blockers: list[_Blocker],
) -> None:
    result = _command(
        [command, "init", "-input=false", "-lockfile=readonly", "-no-color"],
        workspace,
        environment,
    )
    passed = result.returncode == 0
    stages.append(
        _Stage(
            name="terraform-init", status="pass" if passed else "fail", exit_code=result.returncode
        )
    )
    if not passed:
        blockers.append(
            _blocker(
                "TERRAFORM_INIT_FAILED",
                "Terraform locked initialization failed.",
                "Restore the approved adapter or module registry access and retry.",
            )
        )


def _run_validate(
    command: str,
    workspace: Path,
    environment: dict[str, str],
    stages: list[_Stage],
    blockers: list[_Blocker],
) -> None:
    result = _command([command, "validate", "-json"], workspace, environment)
    data = _json_mapping(result.stdout)
    passed = result.returncode == 0 and data is not None and data.get("valid") is True
    stages.append(
        _Stage(
            name="terraform-validate",
            status="pass" if passed else "fail",
            exit_code=result.returncode,
        )
    )
    if not passed:
        blockers.append(
            _blocker(
                "TERRAFORM_VALIDATE_FAILED",
                "Terraform validation failed or returned malformed JSON.",
                "Correct the approved adapter and retry.",
            )
        )


def _run_speculative_plan(
    command: str,
    workspace: Path,
    plan_path: Path,
    environment: dict[str, str],
    stages: list[_Stage],
    blockers: list[_Blocker],
) -> int:
    result = _command(
        [
            command,
            "plan",
            "-input=false",
            "-no-color",
            "-detailed-exitcode",
            f"-out={plan_path}",
        ],
        workspace,
        environment,
    )
    passed = result.returncode in {0, 2}
    stages.append(
        _Stage(
            name="terraform-plan", status="pass" if passed else "fail", exit_code=result.returncode
        )
    )
    if not passed:
        blockers.append(
            _blocker(
                "TERRAFORM_PLAN_FAILED",
                "Terraform speculative plan failed.",
                "Check read-only AWS credentials, the target account, and approved adapter inputs.",
            )
        )
    return result.returncode


def _show_plan(
    command: str,
    workspace: Path,
    plan_path: Path,
    environment: dict[str, str],
    stages: list[_Stage],
    blockers: list[_Blocker],
) -> dict[str, Any] | None:
    result = _command([command, "show", "-json", str(plan_path)], workspace, environment)
    data = _json_mapping(result.stdout)
    passed = result.returncode == 0 and data is not None
    stages.append(
        _Stage(
            name="terraform-show", status="pass" if passed else "fail", exit_code=result.returncode
        )
    )
    if not passed:
        blockers.append(
            _blocker(
                "TERRAFORM_SHOW_FAILED",
                "Terraform show failed or returned malformed JSON.",
                "Correct the approved adapter or Terraform installation and retry.",
            )
        )
    return data


def _command(
    argv: list[str], cwd: Path, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _terraform_version(output: str) -> str:
    data = _json_mapping(output)
    return str(data.get("terraform_version", "")) if data else ""


def _json_mapping(output: str) -> dict[str, Any] | None:
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _replay_identity(bundle: Path) -> dict[str, str]:
    try:
        replay = resolve_bundle_file(bundle, "replay-manifest.yaml", required=False)
    except BundleFileError:
        replay = None
    if replay is None:
        return {"replayManifestSha256": "", "bundleDigest": ""}
    try:
        manifest = load_bundle_yaml_mapping(bundle, "replay-manifest.yaml")
    except (BundleFileError, ValueError):
        return {"replayManifestSha256": sha256_file(replay), "bundleDigest": ""}
    artifacts = manifest.get("artifacts")
    files = artifacts.get("files") if isinstance(artifacts, dict) else []
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":"))
    return {
        "replayManifestSha256": sha256_file(replay),
        "bundleDigest": hashlib.sha256(encoded.encode()).hexdigest(),
    }
