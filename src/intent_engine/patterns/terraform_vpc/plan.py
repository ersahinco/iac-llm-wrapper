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

from pydantic import ValidationError

from intent_engine.core.compile_artifacts import validate_generated_violations
from intent_engine.core.contracts import ContractValidator
from intent_engine.core.package_version import installed_version
from intent_engine.core.paths import BundleFileError, resolve_bundle_file
from intent_engine.core.replay import sha256_file, verify_replay_manifest
from intent_engine.core.yaml_utils import load_bundle_yaml_mapping, write_yaml_artifact

from .conformance import (
    ConformanceResult,
    conformance_identities,
    empty_conformance,
    evaluate_plan_conformance,
)
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
from .evidence import evidence_semantic_violations as _evidence_semantic_violations
from .evidence import (
    observed_account as _observed_account,
)
from .evidence import (
    summarize_changes as _summarize_changes,
)
from .models import TerraformVpcIntent
from .target import (
    APPROVED_ROOT_SHA256,
    MODULE_RELEASE_COMMIT,
    MODULE_SOURCE,
    MODULE_TREE_SHA256,
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
    assert_approved_root_identity,
    installed_module_tree_digest,
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
    plan_produced = False
    module_tree_sha256 = ""
    plan_metadata: dict[str, Any] = {
        "formatVersion": "not-produced",
        "terraformVersion": "not-produced",
        "applyable": False,
        "complete": False,
        "errored": False,
        "binaryPlanSha256": "not-produced",
        "planJsonSha256": "not-produced",
        "moduleContentVerified": False,
    }
    intent: TerraformVpcIntent | None = None

    pattern = _bundle_pattern(bundle, blockers)
    if pattern == "terraform-vpc":
        blockers.extend(_bundle_blockers(bundle))
    if not blockers:
        intent, variables = _plan_inputs(bundle, blockers)
        requested_account = intent.target_account_id if intent is not None else ""
    else:
        variables = {}
    replay_identity = _replay_identity(bundle)
    identities = conformance_identities(_conformance_artifact_identities(bundle))
    conformance: ConformanceResult = empty_conformance(
        identities=identities,
        intent=intent,
    )

    if not blockers:
        try:
            with tempfile.TemporaryDirectory(prefix="intent-engine-terraform-vpc-") as tmp:
                workspace = Path(tmp)
                _copy_approved_root(workspace)
                (workspace / "terraform.auto.tfvars.json").write_text(
                    json.dumps(variables, sort_keys=True)
                )
                environment = _terraform_environment(workspace)
                _require_terraform_version(
                    terraform_command, workspace, environment, stages, blockers
                )
                if not blockers:
                    _run_init(terraform_command, workspace, environment, stages, blockers)
                if not blockers:
                    module_tree_sha256 = _verify_module(workspace, stages, blockers)
                    plan_metadata["moduleContentVerified"] = bool(module_tree_sha256)
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
                    plan_json, raw_plan_json = _show_plan(
                        terraform_command,
                        workspace,
                        plan_path,
                        environment,
                        stages,
                        blockers,
                    )
                    if plan_json is not None:
                        plan_produced = True
                        plan_metadata.update(
                            {
                                "formatVersion": plan_json.get("format_version", ""),
                                "terraformVersion": plan_json.get("terraform_version", ""),
                                "applyable": plan_json.get("applyable") is True,
                                "complete": plan_json.get("complete") is True,
                                "errored": plan_json.get("errored") is True,
                                "binaryPlanSha256": (
                                    sha256_file(plan_path) if plan_path.is_file() else ""
                                ),
                                "planJsonSha256": hashlib.sha256(raw_plan_json).hexdigest(),
                            }
                        )
                        observed_account = _observed_account(plan_json)
                        resource_changes, summary = _summarize_changes(plan_json, blockers)
                        if intent is not None:
                            conformance, issues = evaluate_plan_conformance(
                                plan_json,
                                intent=intent,
                                module_inputs={key: variables[key] for key in MODULE_VARIABLES},
                                identities=identities,
                            )
                            blockers.extend(
                                _blocker(issue.code, issue.message, issue.next_action)
                                for issue in issues
                            )
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
        plan_produced=plan_produced,
        plan_metadata=plan_metadata,
        module_tree_sha256=module_tree_sha256,
        stages=stages,
        resource_changes=resource_changes,
        summary=summary,
        blockers=blockers,
        conformance=conformance,
    )
    return _persist_evidence(bundle, evidence_path, evidence)


def _persist_evidence(bundle: Path, evidence_path: Path, evidence: Any) -> dict[str, Any]:
    semantic_violations = _evidence_semantic_violations(evidence)
    if semantic_violations:
        raise TerraformPlanError(
            "Generated Terraform plan evidence violated v2 semantics: "
            + "; ".join(semantic_violations)
        )
    payload: dict[str, Any] = evidence.model_dump(by_alias=True, mode="json")
    write_yaml_artifact(evidence_path, payload, "")
    violations = ContractValidator(PLAN_EVIDENCE_CONTRACT).validate_artifacts(bundle)
    if violations:
        messages = "; ".join(item.message for item in violations)
        raise TerraformPlanError(
            f"Generated Terraform plan evidence violated its schema: {messages}"
        )
    return payload


def validate_approved_root(*, terraform_command: str = "terraform") -> None:
    """Run the credential-free CI init/validate proof for the approved root."""
    try:
        assert_approved_root_identity()
    except ValueError as exc:
        raise TerraformPlanError(str(exc)) from exc
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
        environment = _terraform_environment(workspace)
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
        try:
            installed_module_tree_digest(workspace)
        except ValueError as exc:
            raise TerraformPlanError(str(exc)) from exc
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
    approved_module = manifest.get("approvedModule")
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
            and approved_root.get("sha256") == APPROVED_ROOT_SHA256
            and approved_root.get("files") == approved_root_identities(),
            "TERRAFORM_APPROVED_ROOT_CHANGED",
            "The code-owned Terraform root or provider lockfile changed.",
        ),
        (
            isinstance(approved_module, dict)
            and approved_module.get("releaseCommit") == MODULE_RELEASE_COMMIT
            and approved_module.get("treeSha256") == MODULE_TREE_SHA256,
            "TERRAFORM_APPROVED_MODULE_CHANGED",
            "The approved module release or content identity changed.",
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


def _plan_inputs(
    bundle: Path, blockers: list[_Blocker]
) -> tuple[TerraformVpcIntent | None, dict[str, Any]]:
    try:
        report = load_bundle_yaml_mapping(bundle, "decision-report.yaml")
        module_inputs = load_bundle_yaml_mapping(bundle, "module-inputs.yaml")
    except (BundleFileError, ValueError) as exc:
        blockers.append(
            _blocker("TERRAFORM_INPUT_INVALID", str(exc), "Recompile the bundle and retry.")
        )
        return None, {}
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
        return None, {}
    if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
        blockers.append(
            _blocker(
                "TERRAFORM_INPUT_INVALID",
                "Exactly one approved Terraform VPC module input is required.",
                "Recompile the bundle and retry.",
            )
        )
        return None, {}
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
        return None, {}
    if set(variables) != MODULE_VARIABLES:
        blockers.append(
            _blocker(
                "TERRAFORM_INPUT_SET_INVALID",
                "Module input keys do not match the approved root variables.",
                "Correct the pattern adapter and recompile the bundle.",
            )
        )
        return None, {}
    try:
        intent = TerraformVpcIntent.model_validate(
            {
                "vpc_name": vpc.get("name"),
                "primary_region": vpc.get("region"),
                "cidr": vpc.get("cidr"),
                "az_count": vpc.get("azCount"),
                "public_subnet_cidrs": vpc.get("publicSubnetCidrs"),
                "private_subnet_cidrs": vpc.get("privateSubnetCidrs"),
                "enable_nat_gateway": vpc.get("enableNatGateway"),
                "single_nat_gateway": vpc.get("singleNatGateway"),
                "enable_dns_hostnames": vpc.get("enableDnsHostnames"),
                "target_account_id": delivery.get("targetAccountId"),
                "deployment_pipeline_ref": delivery.get("deploymentPipelineRef"),
            }
        )
    except ValidationError:
        blockers.append(
            _blocker(
                "TERRAFORM_DELIVERY_IDENTITY_INVALID",
                "Decision report values cannot be reconstructed as typed Terraform VPC intent.",
                "Fix the delivery requirements and recompile the bundle.",
            )
        )
        return None, {}
    return intent, {"region": intent.primary_region, **variables}


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
            exitCode=result.returncode,
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
            name="terraform-init", status="pass" if passed else "fail", exitCode=result.returncode
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


def _verify_module(workspace: Path, stages: list[_Stage], blockers: list[_Blocker]) -> str:
    try:
        digest = installed_module_tree_digest(workspace)
    except (OSError, ValueError) as exc:
        stages.append(_Stage(name="terraform-module", status="fail"))
        blockers.append(
            _blocker(
                "TERRAFORM_MODULE_CONTENT_MISMATCH",
                str(exc),
                "Restore registry access to the exact approved module release and retry.",
            )
        )
        return ""
    stages.append(_Stage(name="terraform-module", status="pass", exitCode=0))
    return digest


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
            exitCode=result.returncode,
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
            name="terraform-plan", status="pass" if passed else "fail", exitCode=result.returncode
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
) -> tuple[dict[str, Any] | None, bytes]:
    result = _command([command, "show", "-json", str(plan_path)], workspace, environment)
    data = _json_mapping(result.stdout)
    passed = result.returncode == 0 and data is not None
    stages.append(
        _Stage(
            name="terraform-show", status="pass" if passed else "fail", exitCode=result.returncode
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
    return data, result.stdout.encode()


def _terraform_environment(workspace: Path) -> dict[str, str]:
    cli_config = workspace / "terraform-cli.tfrc"
    cli_config.write_text("disable_checkpoint = true\n")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("TF_")}
    environment.update(
        {
            "TF_IN_AUTOMATION": "1",
            "TF_CLI_CONFIG_FILE": str(cli_config),
            "CHECKPOINT_DISABLE": "1",
        }
    )
    return environment


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
        return {
            "replayManifestSha256": "unavailable",
            "bundleDigest": "unavailable",
            "sourceSha256": "unavailable",
        }
    try:
        manifest = load_bundle_yaml_mapping(bundle, "replay-manifest.yaml")
    except (BundleFileError, ValueError):
        return {
            "replayManifestSha256": sha256_file(replay),
            "bundleDigest": "unavailable",
            "sourceSha256": "unavailable",
        }
    artifacts = manifest.get("artifacts")
    files = artifacts.get("files") if isinstance(artifacts, dict) else []
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":"))
    return {
        "replayManifestSha256": sha256_file(replay),
        "bundleDigest": hashlib.sha256(encoded.encode()).hexdigest(),
        "sourceSha256": (
            str(manifest.get("source", {}).get("sha256", ""))
            if isinstance(manifest.get("source"), dict)
            else ""
        ),
    }


def _conformance_artifact_identities(bundle: Path) -> dict[str, str]:
    names = {
        "requirementGraphSha256": "requirement-graph.json",
        "decisionAuditSha256": "decision-audit.yaml",
        "policyGraphSha256": "policy-graph.yaml",
        "planManifestSha256": "plan-manifest.yaml",
        "decisionReportSha256": "decision-report.yaml",
        "moduleInputsSha256": "module-inputs.yaml",
    }
    identities: dict[str, str] = {}
    for key, name in names.items():
        try:
            identities[key] = _bundle_file_digest(bundle, name)
        except BundleFileError:
            identities[key] = "unavailable"
    return identities
