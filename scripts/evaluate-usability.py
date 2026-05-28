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


@dataclass(frozen=True)
class TrialConfig:
    use_llm: bool
    provider: str
    model: str

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


def _run(args: list[str], config: TrialConfig) -> subprocess.CompletedProcess[str]:
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
        "baseline",
    ]
    if not config.use_llm:
        args.append("--no-llm")

    proc = _run(args, config)
    failures: list[str] = []
    output = proc.stdout + proc.stderr
    if proc.returncode != 0:
        failures.append("discover command failed")
    if "central_network_account" not in output:
        failures.append("missing central_network_account gap")
    if "Clarifying questions" not in output:
        failures.append("missing architect clarifying question section")
    return TrialResult(
        "architect",
        "gap-discovery",
        config.mode,
        "PASS" if not failures else "FAIL",
        failures,
    )


def _trial_engineer_handoff(config: TrialConfig) -> TrialResult:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        compile_proc = _run(
            [
                "compile",
                "--input",
                str(FIXTURES_DIR / "engineer-handoff-lza.md"),
                "--output",
                str(output_dir),
                "--pattern",
                "baseline",
            ],
            config,
        )
        if compile_proc.returncode != 0:
            failures.append("compile command failed")
            return TrialResult(
                "engineer",
                "handoff-artifacts",
                config.mode,
                "FAIL",
                failures,
            )

        validate_proc = _run(
            ["validate", "--input", str(output_dir), "--pattern", "baseline"],
            config,
        )
        if validate_proc.returncode != 0:
            failures.append("validate command failed")

        module_names = [str(item.get("moduleName", "")) for item in _module_inputs(output_dir)]
        for expected in ("lza-network", "lza-security-baseline", "lza-workload"):
            if expected not in module_names:
                failures.append(f"missing module input {expected}")

        for expected_file in ("decision-report.yaml", "module-inputs.yaml", "terraform.tfvars"):
            if not (output_dir / expected_file).exists():
                failures.append(f"missing artifact {expected_file}")

    return TrialResult(
        "engineer",
        "handoff-artifacts",
        config.mode,
        "PASS" if not failures else "FAIL",
        failures,
    )


def _trial_byom_terraform_vpc(config: TrialConfig) -> TrialResult:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
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
        )
        if compile_proc.returncode != 0:
            failures.append("compile command failed")
            failures.append((compile_proc.stderr or compile_proc.stdout).strip())
            return TrialResult(
                "byom",
                "terraform-vpc-module",
                config.mode,
                "FAIL",
                failures,
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
            "module-inputs.yaml",
            "sample-recommendations.yaml",
            "terraform.tfvars",
        ):
            if not (output_dir / expected_file).exists():
                failures.append(f"missing artifact {expected_file}")

    return TrialResult(
        "byom",
        "terraform-vpc-module",
        config.mode,
        "PASS" if not failures else "FAIL",
        failures,
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
    args = parser.parse_args()

    config = TrialConfig(use_llm=args.llm, provider=args.provider, model=args.model)
    trials = [_trial_architect_gap, _trial_engineer_handoff, _trial_byom_terraform_vpc]
    results = [trial(config) for trial in trials]

    print(f"{'Role':12s} {'Trial':24s} {'Mode':13s} Status")
    print("-" * 84)
    failures = 0
    for result in results:
        suffix = "" if not result.failures else " - " + "; ".join(result.failures[:3])
        print(f"{result.role:12s} {result.name:24s} {result.mode:13s} {result.status}{suffix}")
        if result.status != "PASS":
            failures += 1
    print("-" * 84)
    print(f"Results: {len(results) - failures} passed, {failures} failed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
