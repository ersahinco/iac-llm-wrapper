#!/usr/bin/env python3
"""Role-based usability trials for architects, engineers, and BYOM module owners."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ruamel.yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures" / "usability"
EVAL_DIR = REPO_ROOT / "fixtures" / "eval"


@dataclass(frozen=True)
class TrialConfig:
    use_llm: bool
    provider: str
    model: str
    evidence_dir: Path | None = None

    @property
    def mode(self) -> str:
        return "llm" if self.use_llm else "deterministic"


@dataclass
class TrialResult:
    role: str
    name: str
    mode: str
    status: str
    failures: list[str]
    evidence_files: list[Path]


def _run(
    args: list[str],
    config: TrialConfig,
    evidence_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    cmd_args = list(args)
    if config.use_llm:
        llm_command = bool(args and args[0] in {"compile", "discover"})
        if config.provider:
            env["INTENT_ENGINE_PROVIDER"] = config.provider
            if llm_command:
                cmd_args.extend(["--provider", config.provider])
        if config.model:
            env["INTENT_ENGINE_MODEL"] = config.model
            if llm_command:
                cmd_args.extend(["--model", config.model])
        if llm_command and evidence_path is not None:
            cmd_args.extend(["--evidence-output", str(evidence_path)])
        env.pop("INTENT_ENGINE_DISABLE_LLM", None)
    else:
        env["INTENT_ENGINE_DISABLE_LLM"] = "1"

    cmd = [sys.executable, "-m", "intent_engine", *cmd_args]
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )


def _trial_evidence_path(config: TrialConfig, trial_name: str, temp_dir: Path) -> Path | None:
    if not config.use_llm:
        return None
    if config.evidence_dir is not None:
        config.evidence_dir.mkdir(parents=True, exist_ok=True)
        return config.evidence_dir / f"{trial_name}.evidence.yaml"
    return temp_dir / f"{trial_name}.evidence.yaml"


def _evidence_failures(config: TrialConfig, evidence_path: Path | None) -> list[str]:
    if not config.use_llm:
        return []
    if evidence_path is None or not evidence_path.exists():
        return ["missing LLM evidence file"]

    data = _yaml_load(evidence_path)
    calls = data.get("calls")
    if not isinstance(calls, list) or not calls:
        return ["LLM evidence has no calls"]

    failures: list[str] = []
    for call in calls:
        if not isinstance(call, dict):
            failures.append("LLM evidence call is not a mapping")
            continue
        if call.get("parse_error"):
            failures.append(f"LLM parse/call error: {call['parse_error']}")
        if config.model and call.get("model") != config.model:
            failures.append(f"LLM model mismatch: expected {config.model}, got {call.get('model')}")
        if not call.get("prompt"):
            failures.append("LLM evidence missing prompt")
        if not call.get("response"):
            failures.append("LLM evidence missing response")
    return failures


def _yaml_load(path: Path) -> dict[str, Any]:
    yaml = ruamel.yaml.YAML(typ="safe")
    data = yaml.load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected YAML mapping")
    return data


def _module_inputs(output_dir: Path) -> list[dict[str, Any]]:
    data = _yaml_load(output_dir / "module-inputs.yaml")
    items = data.get("moduleInputs", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _trial_architect_gap(config: TrialConfig) -> TrialResult:
    args = [
        "discover",
        "--input",
        str(FIXTURES_DIR / "architect-incomplete-lza.md"),
        "--pattern",
        "aws-lza",
    ]
    if not config.use_llm:
        args.append("--no-llm")

    failures: list[str] = []
    evidence_files: list[Path] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        evidence_path = _trial_evidence_path(config, "architect-gap-discovery", Path(temp_dir))
        proc = _run(args, config, evidence_path)
        if evidence_path is not None:
            evidence_files.append(evidence_path)
        output = proc.stdout + proc.stderr
        if proc.returncode != 0:
            failures.append("discover command failed")
        if "network_account" not in output:
            failures.append("missing network_account gap")
        if "Clarifying questions" not in output:
            failures.append("missing architect clarifying question section")
        failures.extend(_evidence_failures(config, evidence_path))
    return TrialResult(
        "architect",
        "gap-discovery",
        config.mode,
        "PASS" if not failures else "FAIL",
        failures,
        evidence_files,
    )


def _trial_engineer_handoff(config: TrialConfig) -> TrialResult:
    failures: list[str] = []
    evidence_files: list[Path] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        evidence_path = _trial_evidence_path(config, "engineer-handoff-artifacts", output_dir)
        compile_proc = _run(
            [
                "compile",
                "--input",
                str(FIXTURES_DIR / "engineer-handoff-lza.md"),
                "--output",
                str(output_dir),
                "--pattern",
                "aws-lza",
            ],
            config,
            evidence_path,
        )
        if evidence_path is not None:
            evidence_files.append(evidence_path)
        if compile_proc.returncode != 0:
            failures.append("compile command failed")
            failures.append((compile_proc.stderr or compile_proc.stdout).strip())
            return TrialResult(
                "engineer",
                "handoff-artifacts",
                config.mode,
                "FAIL",
                failures,
                evidence_files,
            )

        validate_proc = _run(
            ["validate", "--input", str(output_dir), "--pattern", "aws-lza"],
            config,
        )
        if validate_proc.returncode != 0:
            failures.append("validate command failed")

        for unexpected_file in ("module-inputs.yaml", "terraform.tfvars"):
            if (output_dir / unexpected_file).exists():
                failures.append(f"unexpected generated IaC handoff {unexpected_file}")

        expected_files = (
            "accounts-config.yaml",
            "global-config.yaml",
            "handoff-plan.yaml",
            "iam-config.yaml",
            "network-config.yaml",
            "organization-config.yaml",
            "security-config.yaml",
            "decision-report.yaml",
            "lineage-manifest.yaml",
            "deployment-runbook.md",
            "sample-recommendations.yaml",
        )
        for expected_file in expected_files:
            if not (output_dir / expected_file).exists():
                failures.append(f"missing artifact {expected_file}")
        failures.extend(_evidence_failures(config, evidence_path))

    return TrialResult(
        "engineer",
        "handoff-artifacts",
        config.mode,
        "PASS" if not failures else "FAIL",
        failures,
        evidence_files,
    )


def _trial_byom_terraform_vpc(config: TrialConfig) -> TrialResult:
    failures: list[str] = []
    evidence_files: list[Path] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        evidence_path = _trial_evidence_path(config, "byom-terraform-vpc-module", output_dir)
        compile_proc = _run(
            [
                "compile",
                "--input",
                str(FIXTURES_DIR / "byom-terraform-vpc.md"),
                "--output",
                str(output_dir),
                "--pattern",
                "terraform-vpc",
            ],
            config,
            evidence_path,
        )
        if evidence_path is not None:
            evidence_files.append(evidence_path)
        if compile_proc.returncode != 0:
            failures.append("compile command failed")
            failures.append((compile_proc.stderr or compile_proc.stdout).strip())
            return TrialResult(
                "byom",
                "terraform-vpc-module",
                config.mode,
                "FAIL",
                failures,
                evidence_files,
            )

        validate_proc = _run(
            ["validate", "--input", str(output_dir), "--pattern", "terraform-vpc"],
            config,
        )
        if validate_proc.returncode != 0:
            failures.append("validate command failed")

        inputs = _module_inputs(output_dir)
        variables = inputs[0].get("variables", {}) if inputs else {}
        if not inputs or inputs[0].get("moduleName") != "terraform-aws-vpc":
            failures.append("missing terraform-aws-vpc module input")
        expected_values = {
            "name": "orders-vpc",
            "cidr": "10.30.0.0/16",
            "azs": ["eu-central-1a", "eu-central-1b"],
            "public_subnets": ["10.30.0.0/24", "10.30.1.0/24"],
            "private_subnets": ["10.30.10.0/24", "10.30.11.0/24"],
            "enable_nat_gateway": True,
            "single_nat_gateway": False,
            "enable_dns_hostnames": True,
        }
        for key, expected in expected_values.items():
            if variables.get(key) != expected:
                failures.append(f"{key}: expected {expected!r}, got {variables.get(key)!r}")

        for expected_file in (
            "decision-report.yaml",
            "handoff-plan.yaml",
            "module-inputs.yaml",
            "sample-recommendations.yaml",
            "terraform.tfvars",
        ):
            if not (output_dir / expected_file).exists():
                failures.append(f"missing artifact {expected_file}")
        failures.extend(_evidence_failures(config, evidence_path))

    return TrialResult(
        "byom",
        "terraform-vpc-module",
        config.mode,
        "PASS" if not failures else "FAIL",
        failures,
        evidence_files,
    )


def _trial_existing_account_terraform_vpc(config: TrialConfig) -> TrialResult:
    failures: list[str] = []
    evidence_files: list[Path] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        evidence_path = _trial_evidence_path(
            config,
            "existing-account-terraform-vpc",
            output_dir,
        )
        compile_proc = _run(
            [
                "compile",
                "--input",
                str(FIXTURES_DIR / "byom-terraform-vpc-existing-account.md"),
                "--output",
                str(output_dir),
                "--pattern",
                "terraform-vpc",
            ],
            config,
            evidence_path,
        )
        if evidence_path is not None:
            evidence_files.append(evidence_path)
        if compile_proc.returncode != 0:
            failures.append("compile command failed")
            failures.append((compile_proc.stderr or compile_proc.stdout).strip())
            return TrialResult(
                "byom",
                "existing-account-terraform-vpc",
                config.mode,
                "FAIL",
                failures,
                evidence_files,
            )

        validate_proc = _run(
            ["validate", "--input", str(output_dir), "--pattern", "terraform-vpc"],
            config,
        )
        if validate_proc.returncode != 0:
            failures.append("validate command failed")

        review_proc = _run(
            [
                "review",
                "html",
                "--input",
                str(output_dir),
                "--output",
                str(output_dir / "handoff-review.html"),
            ],
            config,
        )
        if review_proc.returncode != 0:
            failures.append("review html command failed")

        checkov_evidence = output_dir / "shift-left-evidence.yaml"
        checkov_proc = _run(
            [
                "shift-left",
                "checkov",
                "--bundle",
                str(output_dir),
                "--scan-path",
                str(FIXTURES_DIR / "owner-terraform-vpc-module"),
                "--output",
                str(checkov_evidence),
            ],
            config,
        )
        if checkov_proc.returncode != 0:
            failures.append("checkov evidence command failed")
        if not checkov_evidence.exists():
            failures.append("missing Checkov shift-left evidence")
        else:
            evidence = _yaml_load(checkov_evidence)
            status = evidence.get("result", {}).get("status")
            if status == "invalid-input":
                failures.append("Checkov evidence scanned an invalid input")
            if "does not deploy" not in str(evidence.get("boundary", "")):
                failures.append("Checkov evidence missing no-deploy boundary")
            evidence_text = checkov_evidence.read_text().lower()
            for forbidden in ("terraform apply", "terragrunt apply", "kubectl apply"):
                if forbidden in evidence_text:
                    failures.append(f"Checkov evidence includes forbidden command: {forbidden}")

        report = _yaml_load(output_dir / "decision-report.yaml")
        delivery = report.get("delivery", {})
        if delivery.get("targetAccountId") != "444455556666":
            failures.append("delivery target account missing")
        if delivery.get("deploymentPipelineRef") != (
            "github://workload-networking/reporting-vpc-deploy"
        ):
            failures.append("delivery pipeline reference missing")
        inputs = _module_inputs(output_dir)
        variables = inputs[0].get("variables", {}) if inputs else {}
        if "target_account_id" in variables or "deployment_pipeline_ref" in variables:
            failures.append("delivery metadata leaked into module variables")
        for unexpected_file in ("main.tf", "terragrunt.hcl", "template.yaml", "stack.yaml"):
            if (output_dir / unexpected_file).exists():
                failures.append(f"unexpected deployable artifact {unexpected_file}")
        failures.extend(_evidence_failures(config, evidence_path))

    return TrialResult(
        "byom",
        "existing-account-terraform-vpc",
        config.mode,
        "PASS" if not failures else "FAIL",
        failures,
        evidence_files,
    )


def _trial_byom_cloudformation_parameters(config: TrialConfig) -> TrialResult:
    failures: list[str] = []
    evidence_files: list[Path] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        evidence_path = _trial_evidence_path(
            config,
            "byom-cloudformation-parameters",
            output_dir,
        )
        compile_proc = _run(
            [
                "compile",
                "--input",
                str(FIXTURES_DIR / "byom-cloudformation-parameters.md"),
                "--output",
                str(output_dir),
                "--pattern",
                "cloudformation-parameters",
            ],
            config,
            evidence_path,
        )
        if evidence_path is not None:
            evidence_files.append(evidence_path)
        if compile_proc.returncode != 0:
            failures.append("compile command failed")
            failures.append((compile_proc.stderr or compile_proc.stdout).strip())
            return TrialResult(
                "byom",
                "cloudformation-parameters",
                config.mode,
                "FAIL",
                failures,
                evidence_files,
            )

        validate_proc = _run(
            ["validate", "--input", str(output_dir), "--pattern", "cloudformation-parameters"],
            config,
        )
        if validate_proc.returncode != 0:
            failures.append("validate command failed")

        handoff = _yaml_load(output_dir / "cloudformation-parameters.yaml")
        if handoff.get("stackName") != "orders-service-prod":
            failures.append("wrong CloudFormation stack name")
        if handoff.get("templateUrl") != "s3://approved-templates/orders-service.yaml":
            failures.append("wrong CloudFormation template URL")
        parameters = handoff.get("parameters", [])
        if len(parameters) != 3:
            failures.append("expected three CloudFormation parameters")

        for unexpected_file in ("template.yaml", "stack.yaml", "main.tf", "terraform.tfvars"):
            if (output_dir / unexpected_file).exists():
                failures.append(f"unexpected generated deployable artifact {unexpected_file}")

        for expected_file in (
            "cloudformation-parameters.yaml",
            "decision-report.yaml",
            "handoff-plan.yaml",
        ):
            if not (output_dir / expected_file).exists():
                failures.append(f"missing artifact {expected_file}")
        failures.extend(_evidence_failures(config, evidence_path))

    return TrialResult(
        "byom",
        "cloudformation-parameters",
        config.mode,
        "PASS" if not failures else "FAIL",
        failures,
        evidence_files,
    )


def _trial_static_review_stakeholders(config: TrialConfig) -> TrialResult:
    failures: list[str] = []
    evidence_files: list[Path] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        evidence_path = _trial_evidence_path(config, "static-review-stakeholders", output_dir)
        compile_proc = _run(
            [
                "compile",
                "--input",
                str(EVAL_DIR / "aws-lza-customer-board-notes.md"),
                "--output",
                str(output_dir),
                "--pattern",
                "aws-lza",
            ],
            config,
            evidence_path,
        )
        if evidence_path is not None:
            evidence_files.append(evidence_path)
        if compile_proc.returncode != 0:
            failures.append("compile command failed")
            failures.append((compile_proc.stderr or compile_proc.stdout).strip())
            return TrialResult(
                "review",
                "static-review-stakeholders",
                config.mode,
                "FAIL",
                failures,
                evidence_files,
            )

        review_proc = _run(
            [
                "review",
                "html",
                "--input",
                str(output_dir),
                "--output",
                str(output_dir / "handoff-review.html"),
            ],
            config,
        )
        if review_proc.returncode != 0:
            failures.append("review html command failed")
            failures.append((review_proc.stderr or review_proc.stdout).strip())
            return TrialResult(
                "review",
                "static-review-stakeholders",
                config.mode,
                "FAIL",
                failures,
                evidence_files,
            )

        html = (output_dir / "handoff-review.html").read_text()
        role_signals = {
            "architect": [
                "Review Summary",
                "Readiness",
                "Contract status",
                "Allowed next action",
                "Handoff Readiness",
            ],
            "platform engineer": [
                "Target Artifacts",
                "accounts-config.yaml",
                "iam-config.yaml",
                "handoff-plan.yaml",
                "Pass the reviewed artifacts",
            ],
            "security reviewer": [
                "security-config.yaml",
                "identity_center_permission_sets",
                "Raw evidence",
                "Contract Validation",
            ],
            "model developer": [
                "Model Benchmark",
                "Model mode",
                "Raw LLM coverage",
                "Raw missing decisions",
                "Raw trace summary",
                "Raw model benchmark",
            ],
        }
        for role, signals in role_signals.items():
            for signal in signals:
                if signal not in html:
                    failures.append(f"{role} signal missing: {signal}")
        failures.extend(_evidence_failures(config, evidence_path))

    return TrialResult(
        "review",
        "static-review-stakeholders",
        config.mode,
        "PASS" if not failures else "FAIL",
        failures,
        evidence_files,
    )


def _trial_end_user_handoff_confidence(config: TrialConfig) -> TrialResult:
    failures: list[str] = []
    evidence_files: list[Path] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        compile_proc = _run(
            [
                "compile",
                "--input",
                str(EVAL_DIR / "aws-lza-customer-board-notes.md"),
                "--output",
                str(output_dir),
                "--pattern",
                "aws-lza",
                "--no-raw-evidence",
            ],
            config,
        )
        if compile_proc.returncode != 0:
            failures.append("compile command failed")
            failures.append((compile_proc.stderr or compile_proc.stdout).strip())
            return TrialResult(
                "stakeholder",
                "handoff-confidence",
                config.mode,
                "FAIL",
                failures,
                evidence_files,
            )

        review_proc = _run(
            [
                "review",
                "html",
                "--input",
                str(output_dir),
                "--output",
                str(output_dir / "handoff-review.html"),
            ],
            config,
        )
        if review_proc.returncode != 0:
            failures.append("review html command failed")
            failures.append((review_proc.stderr or review_proc.stdout).strip())
            return TrialResult(
                "stakeholder",
                "handoff-confidence",
                config.mode,
                "FAIL",
                failures,
                evidence_files,
            )

        html = (output_dir / "handoff-review.html").read_text()
        handoff_plan = _yaml_load(output_dir / "handoff-plan.yaml")
        trace = (output_dir / "llm-trace-summary.yaml").read_text()
        benchmark = (output_dir / "model-benchmark.yaml").read_text()
        expected_html_signals = [
            "Review Summary",
            "Handoff allowed",
            "True",
            "Allowed next action",
            "Pass the reviewed artifacts",
            "Contract status",
            "pass",
            "Target Artifacts",
            "accounts-config.yaml",
            "iam-config.yaml",
            "Model Benchmark",
        ]
        for signal in expected_html_signals:
            if signal not in html:
                failures.append(f"handoff confidence signal missing: {signal}")
        if handoff_plan.get("allowedNextAction") != (
            "Pass the reviewed artifacts to the existing target toolchain after manual gates."
        ):
            failures.append("handoff plan missing clear allowed next action")
        readiness = handoff_plan.get("readiness", {})
        if not isinstance(readiness, dict) or readiness.get("status") != "ready":
            failures.append("handoff plan is not ready")
        if not handoff_plan.get("targetContracts"):
            failures.append("handoff plan missing target contracts")
        if not handoff_plan.get("manualGates"):
            failures.append("handoff plan missing manual gates")
        if (output_dir / "raw-evidence.yaml").exists():
            failures.append("service-style handoff wrote raw evidence")
        if "status: not-requested" not in trace:
            failures.append("trace does not show raw evidence was not requested")
        if "conformance:" not in benchmark:
            failures.append("benchmark missing model conformance section")

    return TrialResult(
        "stakeholder",
        "handoff-confidence",
        config.mode,
        "PASS" if not failures else "FAIL",
        failures,
        evidence_files,
    )


def _trial_static_review_blocked(config: TrialConfig) -> TrialResult:
    failures: list[str] = []
    evidence_files: list[Path] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        evidence_path = _trial_evidence_path(config, "static-review-blocked", output_dir)
        compile_proc = _run(
            [
                "compile",
                "--input",
                str(EVAL_DIR / "aws-lza-enterprise-messy-blocked.md"),
                "--output",
                str(output_dir),
                "--pattern",
                "aws-lza",
            ],
            config,
            evidence_path,
        )
        if evidence_path is not None:
            evidence_files.append(evidence_path)
        if compile_proc.returncode == 0:
            failures.append("blocked compile unexpectedly passed")

        review_proc = _run(
            [
                "review",
                "html",
                "--input",
                str(output_dir),
                "--output",
                str(output_dir / "handoff-review.html"),
            ],
            config,
        )
        if review_proc.returncode != 0:
            failures.append("review html command failed")
            failures.append((review_proc.stderr or review_proc.stdout).strip())
            return TrialResult(
                "review",
                "static-review-blocked",
                config.mode,
                "FAIL",
                failures,
                evidence_files,
            )

        html = (output_dir / "handoff-review.html").read_text()
        required_signals = [
            "blocked",
            "Handoff allowed",
            "False",
            "Blocker count",
            "Blocking gap count",
            "Allowed next action",
            "Resolve blockers before passing artifacts to an implementation toolchain.",
            "AWS_LZA_NETWORK_ACCOUNT_REQUIRED",
            "AWS_LZA_IDENTITY_CENTER_PERMISSION_SETS_REQUIRED",
            "AWS_LZA_IDENTITY_CENTER_ASSIGNMENTS_REQUIRED",
            "AWS_LZA_HOME_REGION_NOT_ENABLED",
            "MARKDOWN_CONTRADICTION_NETWORK_CIDR",
            "Blocker Traceability",
            "Requirement key",
            "network_account",
            "Which account owns shared networking?",
            "identity_center_permission_sets",
            "Which IAM Identity Center permission sets are approved?",
            "identity_center_assignments",
            "Which IAM Identity Center assignments are approved?",
            "network_cidr",
            "Contract status",
            "blocked-assessment-artifacts",
            "Raw LLM coverage",
        ]
        for signal in required_signals:
            if signal not in html:
                failures.append(f"blocked review signal missing: {signal}")

        for unexpected_file in ("main.tf", "terraform.tfvars", "terragrunt.hcl"):
            if (output_dir / unexpected_file).exists():
                failures.append(f"unexpected deployable artifact {unexpected_file}")
        failures.extend(_evidence_failures(config, evidence_path))

    return TrialResult(
        "review",
        "static-review-blocked",
        config.mode,
        "PASS" if not failures else "FAIL",
        failures,
        evidence_files,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Use configured LLM extraction instead of deterministic mode.",
    )
    parser.add_argument("--provider", default="ollama", help="LLM provider when --llm is set.")
    parser.add_argument("--model", default="", help="LLM model when --llm is set.")
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        help="Directory to keep LLM evidence YAML files from --llm trials.",
    )
    args = parser.parse_args()

    config = TrialConfig(
        use_llm=args.llm,
        provider=args.provider,
        model=args.model,
        evidence_dir=args.evidence_dir,
    )
    trials = [
        _trial_architect_gap,
        _trial_engineer_handoff,
        _trial_byom_terraform_vpc,
        _trial_existing_account_terraform_vpc,
        _trial_byom_cloudformation_parameters,
        _trial_static_review_stakeholders,
        _trial_end_user_handoff_confidence,
        _trial_static_review_blocked,
    ]
    results = [trial(config) for trial in trials]

    print(f"{'Role':12s} {'Trial':24s} {'Mode':13s} Status")
    print("-" * 84)
    failures = 0
    for result in results:
        suffix = "" if not result.failures else " - " + "; ".join(result.failures[:3])
        print(f"{result.role:12s} {result.name:24s} {result.mode:13s} {result.status}{suffix}")
        if result.evidence_files and config.evidence_dir is not None:
            for evidence_file in result.evidence_files:
                print(f"{'':12s} {'evidence':24s} {'':13s} {evidence_file}")
        if result.status != "PASS":
            failures += 1
    print("-" * 84)
    print(f"Results: {len(results) - failures} passed, {failures} failed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
