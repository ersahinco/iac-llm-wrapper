#!/usr/bin/env python3
"""Evaluate the canonical customer-doc to reviewed-handoff journey."""

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
READY_FIXTURE = REPO_ROOT / "fixtures" / "eval" / "aws-lza-customer-board-notes.md"
BLOCKED_FIXTURE = REPO_ROOT / "fixtures" / "eval" / "aws-lza-enterprise-messy-blocked.md"
DEFAULT_PATTERN = "aws-lza"
EXPECTED_ALLOWED_NEXT_ACTION = (
    "Pass the reviewed artifacts to the existing target toolchain after manual gates."
)
EXPECTED_BLOCKED_ALLOWED_NEXT_ACTION = (
    "Resolve blockers before passing artifacts to an implementation toolchain."
)
EXPECTED_TARGET_ARTIFACTS = (
    "accounts-config.yaml",
    "global-config.yaml",
    "iam-config.yaml",
    "network-config.yaml",
    "organization-config.yaml",
    "security-config.yaml",
    "decision-report.yaml",
    "lineage-manifest.yaml",
    "deployment-runbook.md",
)
EXPECTED_REVIEW_ARTIFACTS = (
    "handoff-plan.yaml",
    "sample-recommendations.yaml",
    "llm-trace-summary.yaml",
    "model-benchmark.yaml",
    "handoff-review.html",
    "contract-validation.yaml",
    "requirement-graph.json",
    "requirement-graph.mmd",
)
FORBIDDEN_ARTIFACTS = (
    "raw-evidence.yaml",
    "main.tf",
    "terraform.tfvars",
    "terragrunt.hcl",
    "template.yaml",
    "stack.yaml",
)
BLOCKED_SAFE_ARTIFACTS = (
    "decision-report.yaml",
    "llm-trace-summary.yaml",
    "model-benchmark.yaml",
    "handoff-review.html",
    "contract-validation.yaml",
    "requirement-graph.json",
    "requirement-graph.mmd",
)
BLOCKED_FORBIDDEN_ARTIFACTS = (
    "accounts-config.yaml",
    "global-config.yaml",
    "iam-config.yaml",
    "network-config.yaml",
    "organization-config.yaml",
    "security-config.yaml",
    "lineage-manifest.yaml",
    "deployment-runbook.md",
    "handoff-plan.yaml",
    "sample-recommendations.yaml",
    *FORBIDDEN_ARTIFACTS,
)
BLOCKED_REVIEW_SIGNALS = (
    "blocked",
    "Deployment allowed",
    "False",
    "Allowed next action",
    EXPECTED_BLOCKED_ALLOWED_NEXT_ACTION,
    "Blocker Traceability",
    "Requirement key",
    "AWS_LZA_NETWORK_ACCOUNT_REQUIRED",
    "AWS_LZA_IDENTITY_CENTER_PERMISSION_SETS_REQUIRED",
    "AWS_LZA_IDENTITY_CENTER_ASSIGNMENTS_REQUIRED",
    "MARKDOWN_CONTRADICTION_NETWORK_CIDR",
    "network_account",
    "Which account owns shared networking?",
    "identity_center_permission_sets",
    "Which IAM Identity Center permission sets are approved?",
    "identity_center_assignments",
    "Which IAM Identity Center assignments are approved?",
    "network_cidr",
    "blocked-assessment-artifacts",
    "Model Benchmark",
    "Model conformance",
)


@dataclass(frozen=True)
class JourneyConfig:
    scenario: str
    fixture: Path
    pattern: str
    use_llm: bool
    provider: str
    model: str
    require_conformant: bool

    @property
    def mode(self) -> str:
        return "llm" if self.use_llm else "deterministic"


@dataclass
class JourneyResult:
    status: str
    failures: list[str]
    output_dir: Path
    benchmark_summary: dict[str, Any]


def _yaml_load(path: Path) -> dict[str, Any]:
    yaml = ruamel.yaml.YAML(typ="safe")
    data = yaml.load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected YAML mapping")
    return data


def _run_cli(
    args: list[str],
    config: JourneyConfig,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    cmd_args = list(args)
    if config.use_llm:
        if config.provider:
            env["INTENT_ENGINE_PROVIDER"] = config.provider
            if args and args[0] == "compile":
                cmd_args.extend(["--provider", config.provider])
        if config.model:
            env["INTENT_ENGINE_MODEL"] = config.model
            if args and args[0] == "compile":
                cmd_args.extend(["--model", config.model])
        env.pop("INTENT_ENGINE_DISABLE_LLM", None)
    else:
        env["INTENT_ENGINE_DISABLE_LLM"] = "1"

    return subprocess.run(
        [sys.executable, "-m", "intent_engine", *cmd_args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )


def _evaluate(config: JourneyConfig, output_dir: Path) -> JourneyResult:
    failures: list[str] = []
    compile_proc = _run_cli(
        [
            "compile",
            "--input",
            str(config.fixture),
            "--output",
            str(output_dir),
            "--pattern",
            config.pattern,
            "--no-raw-evidence",
        ],
        config,
    )
    if config.scenario == "ready" and compile_proc.returncode != 0:
        failures.append("compile command failed")
        failures.append((compile_proc.stderr or compile_proc.stdout).strip())
        return JourneyResult("FAIL", failures, output_dir, {})
    if config.scenario == "blocked" and compile_proc.returncode == 0:
        failures.append("blocked compile unexpectedly passed")

    review_proc = _run_cli(
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
        return JourneyResult("FAIL", failures, output_dir, {})

    if config.scenario == "ready":
        failures.extend(_validate_ready_output(config, output_dir))
    else:
        failures.extend(_validate_blocked_output(config, output_dir))
    benchmark_summary = _benchmark_summary(output_dir / "model-benchmark.yaml")
    failures.extend(_required_conformance_failures(config, benchmark_summary))
    return JourneyResult(
        "PASS" if not failures else "FAIL",
        failures,
        output_dir,
        benchmark_summary,
    )


def _validate_ready_output(config: JourneyConfig, output_dir: Path) -> list[str]:
    failures: list[str] = []
    failures.extend(_validate_files(output_dir))

    if not (output_dir / "decision-report.yaml").exists():
        return failures + ["missing decision-report.yaml"]
    if not (output_dir / "handoff-plan.yaml").exists():
        return failures + ["missing handoff-plan.yaml"]
    if not (output_dir / "llm-trace-summary.yaml").exists():
        return failures + ["missing llm-trace-summary.yaml"]
    if not (output_dir / "model-benchmark.yaml").exists():
        return failures + ["missing model-benchmark.yaml"]
    if not (output_dir / "contract-validation.yaml").exists():
        return failures + ["missing contract-validation.yaml"]
    if not (output_dir / "handoff-review.html").exists():
        return failures + ["missing handoff-review.html"]

    report = _yaml_load(output_dir / "decision-report.yaml")
    handoff_plan = _yaml_load(output_dir / "handoff-plan.yaml")
    trace = _yaml_load(output_dir / "llm-trace-summary.yaml")
    benchmark = _yaml_load(output_dir / "model-benchmark.yaml")
    contract_validation = _yaml_load(output_dir / "contract-validation.yaml")
    html = (output_dir / "handoff-review.html").read_text()

    failures.extend(_validate_readiness(report, handoff_plan))
    failures.extend(_validate_handoff_plan(handoff_plan))
    failures.extend(_validate_contracts(contract_validation))
    failures.extend(_validate_trace(trace))
    failures.extend(_validate_benchmark(config, benchmark))
    failures.extend(_validate_review_html(html))
    return failures


def _validate_blocked_output(config: JourneyConfig, output_dir: Path) -> list[str]:
    failures: list[str] = []
    failures.extend(_validate_blocked_files(output_dir))

    if not (output_dir / "decision-report.yaml").exists():
        return failures + ["missing decision-report.yaml"]
    if not (output_dir / "llm-trace-summary.yaml").exists():
        return failures + ["missing llm-trace-summary.yaml"]
    if not (output_dir / "model-benchmark.yaml").exists():
        return failures + ["missing model-benchmark.yaml"]
    if not (output_dir / "contract-validation.yaml").exists():
        return failures + ["missing contract-validation.yaml"]
    if not (output_dir / "handoff-review.html").exists():
        return failures + ["missing handoff-review.html"]

    report = _yaml_load(output_dir / "decision-report.yaml")
    trace = _yaml_load(output_dir / "llm-trace-summary.yaml")
    benchmark = _yaml_load(output_dir / "model-benchmark.yaml")
    contract_validation = _yaml_load(output_dir / "contract-validation.yaml")
    html = (output_dir / "handoff-review.html").read_text()

    failures.extend(_validate_blocked_readiness(report))
    failures.extend(_validate_blocked_contracts(contract_validation))
    failures.extend(_validate_trace(trace))
    failures.extend(_validate_blocked_benchmark(config, benchmark))
    failures.extend(_validate_blocked_review_html(html))
    return failures


def _validate_files(output_dir: Path) -> list[str]:
    failures: list[str] = []
    for artifact in (*EXPECTED_TARGET_ARTIFACTS, *EXPECTED_REVIEW_ARTIFACTS):
        if not (output_dir / artifact).exists():
            failures.append(f"missing artifact: {artifact}")
    for artifact in FORBIDDEN_ARTIFACTS:
        if (output_dir / artifact).exists():
            failures.append(f"forbidden artifact present: {artifact}")
    return failures


def _validate_blocked_files(output_dir: Path) -> list[str]:
    failures: list[str] = []
    for artifact in BLOCKED_SAFE_ARTIFACTS:
        if not (output_dir / artifact).exists():
            failures.append(f"missing blocked artifact: {artifact}")
    for artifact in BLOCKED_FORBIDDEN_ARTIFACTS:
        if (output_dir / artifact).exists():
            failures.append(f"forbidden blocked artifact present: {artifact}")
    return failures


def _validate_readiness(report: dict[str, Any], handoff_plan: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    report_readiness = _dict(report.get("handoffReadiness") or report.get("deploymentReadiness"))
    plan_readiness = _dict(handoff_plan.get("readiness"))
    if report_readiness.get("status") != "ready":
        failures.append("decision report is not ready")
    if report_readiness.get("deploymentAllowed") is not True:
        failures.append("decision report does not allow handoff")
    if plan_readiness.get("status") != "ready":
        failures.append("handoff plan is not ready")
    if plan_readiness.get("deploymentAllowed") is not True:
        failures.append("handoff plan does not allow handoff")
    if handoff_plan.get("allowedNextAction") != EXPECTED_ALLOWED_NEXT_ACTION:
        failures.append("handoff plan missing clear allowed next action")
    return failures


def _validate_blocked_readiness(report: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    readiness = _dict(report.get("handoffReadiness") or report.get("deploymentReadiness"))
    if readiness.get("status") != "blocked":
        failures.append("decision report is not blocked")
    if readiness.get("deploymentAllowed") is not False:
        failures.append("blocked decision report allows handoff")
    if not _coerce_list(readiness.get("blockers")):
        failures.append("blocked decision report has no blockers")
    missing_keys = {
        str(item.get("key", "")) for item in _list_of_dicts(readiness.get("missingDecisions"))
    }
    for key in (
        "network_account",
        "identity_center_permission_sets",
        "identity_center_assignments",
    ):
        if key not in missing_keys:
            failures.append(f"blocked decision report missing decision {key}")
    conflicting_codes = {
        str(item.get("code", "")) for item in _list_of_dicts(readiness.get("conflictingDecisions"))
    }
    if "MARKDOWN_CONTRADICTION_NETWORK_CIDR" not in conflicting_codes:
        failures.append("blocked decision report missing network CIDR contradiction")
    return failures


def _validate_handoff_plan(handoff_plan: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    contracts = _list_of_dicts(handoff_plan.get("targetContracts"))
    contract_names = {str(contract.get("name", "")) for contract in contracts}
    if "aws-lza-sample-configuration" not in contract_names:
        failures.append("handoff plan missing AWS LZA target contract")
    required_artifacts = {
        str(artifact)
        for contract in contracts
        for artifact in _coerce_list(contract.get("requiredArtifacts"))
    }
    for artifact in EXPECTED_TARGET_ARTIFACTS:
        if artifact not in required_artifacts:
            failures.append(f"handoff plan target contract missing {artifact}")
    manual_gates = _coerce_list(handoff_plan.get("manualGates"))
    if not manual_gates:
        failures.append("handoff plan missing manual gates")
    steps = _list_of_dicts(handoff_plan.get("steps"))
    if "approve-handoff" not in {str(step.get("id", "")) for step in steps}:
        failures.append("handoff plan missing approve-handoff step")
    return failures


def _validate_contracts(contract_validation: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    summary = _dict(contract_validation.get("summary"))
    if summary.get("status") != "pass":
        failures.append("contract validation did not pass")
    contract_names = {
        str(contract.get("name", ""))
        for contract in _list_of_dicts(contract_validation.get("contracts"))
    }
    for expected in ("aws-lza-sample-configuration", "generic-handoff-plan"):
        if expected not in contract_names:
            failures.append(f"contract validation missing {expected}")
    return failures


def _validate_blocked_contracts(contract_validation: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    summary = _dict(contract_validation.get("summary"))
    if summary.get("status") != "pass":
        failures.append("blocked contract validation did not pass")
    contract_names = {
        str(contract.get("name", ""))
        for contract in _list_of_dicts(contract_validation.get("contracts"))
    }
    if "blocked-assessment-artifacts" not in contract_names:
        failures.append("contract validation missing blocked-assessment-artifacts")
    return failures


def _validate_trace(trace: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    raw_evidence = _dict(trace.get("rawEvidence"))
    if raw_evidence.get("status") != "not-requested":
        failures.append("trace does not show raw evidence was intentionally omitted")
    if not _dict(trace.get("acceptedDecisions")):
        failures.append("trace missing accepted decisions")
    if "rawLlmDecisions" not in trace:
        failures.append("trace missing raw LLM decision section")
    return failures


def _validate_benchmark(config: JourneyConfig, benchmark: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if benchmark.get("schemaVersion") != "intent-engine/model-benchmark/v1":
        failures.append("benchmark has wrong schema version")
    run = _dict(benchmark.get("run"))
    if run.get("mode") != config.mode:
        failures.append(f"benchmark mode mismatch: expected {config.mode}, got {run.get('mode')}")
    readiness = _dict(benchmark.get("readiness"))
    if readiness.get("status") != "ready":
        failures.append("benchmark readiness is not ready")
    conformance = _dict(benchmark.get("conformance"))
    conformance_status = str(conformance.get("status", ""))
    if conformance_status not in {"pass", "review", "fail", "not-applicable"}:
        failures.append("benchmark missing valid conformance status")
    if config.mode == "deterministic" and conformance_status != "not-applicable":
        failures.append("deterministic benchmark should mark conformance not-applicable")
    quality = _dict(benchmark.get("quality"))
    if int(quality.get("acceptedDecisionCount", 0) or 0) <= 0:
        failures.append("benchmark missing accepted decisions")
    raw_evidence = _dict(benchmark.get("rawEvidence"))
    if raw_evidence.get("status") != "not-requested":
        failures.append("benchmark does not show raw evidence was intentionally omitted")
    return failures


def _validate_blocked_benchmark(config: JourneyConfig, benchmark: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if benchmark.get("schemaVersion") != "intent-engine/model-benchmark/v1":
        failures.append("benchmark has wrong schema version")
    run = _dict(benchmark.get("run"))
    if run.get("mode") != config.mode:
        failures.append(f"benchmark mode mismatch: expected {config.mode}, got {run.get('mode')}")
    readiness = _dict(benchmark.get("readiness"))
    if readiness.get("status") != "blocked":
        failures.append("blocked benchmark readiness is not blocked")
    if int(readiness.get("blockerCount", 0) or 0) <= 0:
        failures.append("blocked benchmark has no blockers")
    conformance = _dict(benchmark.get("conformance"))
    conformance_status = str(conformance.get("status", ""))
    if conformance_status not in {"pass", "review", "fail", "not-applicable"}:
        failures.append("benchmark missing valid conformance status")
    if config.mode == "deterministic" and conformance_status != "not-applicable":
        failures.append("deterministic benchmark should mark conformance not-applicable")
    raw_evidence = _dict(benchmark.get("rawEvidence"))
    if raw_evidence.get("status") != "not-requested":
        failures.append("benchmark does not show raw evidence was intentionally omitted")
    return failures


def _benchmark_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    benchmark = _yaml_load(path)
    run = _dict(benchmark.get("run"))
    readiness = _dict(benchmark.get("readiness"))
    quality = _dict(benchmark.get("quality"))
    conformance = _dict(benchmark.get("conformance"))
    accepted = int(quality.get("acceptedDecisionCount", 0) or 0)
    raw_coverage = int(quality.get("rawLlmAcceptedCoverageCount", 0) or 0)
    raw_missing = int(quality.get("rawLlmMissingAcceptedDecisionCount", 0) or 0)
    return {
        "mode": str(run.get("mode", "unknown")),
        "provider": str(run.get("provider", "unknown")),
        "model": str(run.get("model", "unknown")),
        "readiness": str(readiness.get("status", "unknown")),
        "conformance": str(conformance.get("status", "unknown")),
        "conformanceReason": str(conformance.get("reason", "")),
        "accepted": accepted,
        "rawCoverage": f"{raw_coverage}/{accepted}" if accepted else "0/0",
        "rawMissing": raw_missing,
        "missingKeys": [
            str(item) for item in _coerce_list(quality.get("rawLlmMissingAcceptedDecisions"))
        ],
        "parseErrors": int(quality.get("parseErrorCount", 0) or 0),
    }


def _required_conformance_failures(
    config: JourneyConfig,
    benchmark_summary: dict[str, Any],
) -> list[str]:
    if not config.require_conformant or not config.use_llm:
        return []
    conformance = str(benchmark_summary.get("conformance", "unknown"))
    if conformance == "pass":
        return []
    return [f"LLM golden journey is not conformant: {conformance}"]


def _validate_review_html(html: str) -> list[str]:
    failures: list[str] = []
    signals = [
        "Review Summary",
        "Handoff ready",
        "True",
        "Allowed next action",
        "Pass the reviewed artifacts",
        "Contract status",
        "pass",
        "Target Artifacts",
        "accounts-config.yaml",
        "iam-config.yaml",
        "Trace Summary",
        "Raw evidence",
        "Model Benchmark",
        "Model conformance",
        "Conformance",
        "Requirement Graph",
    ]
    for signal in signals:
        if signal not in html:
            failures.append(f"review html missing signal: {signal}")
    return failures


def _validate_blocked_review_html(html: str) -> list[str]:
    failures: list[str] = []
    for signal in BLOCKED_REVIEW_SIGNALS:
        if signal not in html:
            failures.append(f"blocked review html missing signal: {signal}")
    return failures


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _default_fixture(scenario: str) -> Path:
    return BLOCKED_FIXTURE if scenario == "blocked" else READY_FIXTURE


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=("ready", "blocked"),
        default="ready",
        help="Golden journey scenario to evaluate.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="Customer-style design fixture to compile.",
    )
    parser.add_argument("--pattern", default=DEFAULT_PATTERN, help="Pattern to compile.")
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Use configured LLM extraction instead of deterministic mode.",
    )
    parser.add_argument("--provider", default="ollama", help="LLM provider when --llm is set.")
    parser.add_argument("--model", default="", help="LLM model when --llm is set.")
    parser.add_argument(
        "--require-conformant",
        action="store_true",
        help="Exit non-zero unless an LLM golden journey has conformance=pass.",
    )
    parser.add_argument(
        "--benchmark-output",
        type=Path,
        help="Optional path to write a compact golden journey benchmark summary.",
    )
    parser.add_argument(
        "--keep-output",
        type=Path,
        help="Directory to keep the generated golden journey bundle.",
    )
    args = parser.parse_args()

    config = JourneyConfig(
        scenario=args.scenario,
        fixture=args.fixture or _default_fixture(args.scenario),
        pattern=args.pattern,
        use_llm=args.llm,
        provider=args.provider,
        model=args.model,
        require_conformant=args.require_conformant,
    )
    if not config.fixture.exists():
        print(f"Missing fixture: {config.fixture}", file=sys.stderr)
        return 1

    if args.keep_output is not None:
        args.keep_output.mkdir(parents=True, exist_ok=True)
        result = _evaluate(config, args.keep_output)
    else:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = _evaluate(config, Path(temp_dir))
            _write_benchmark_summary(args.benchmark_output, result.benchmark_summary)
            return _print_result(result, config)
    _write_benchmark_summary(args.benchmark_output, result.benchmark_summary)
    return _print_result(result, config)


def _write_benchmark_summary(path: Path | None, summary: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    with path.open("w") as handle:
        yaml.dump(
            {
                "schemaVersion": "intent-engine/golden-journey-benchmark/v1",
                **summary,
            },
            handle,
        )


def _print_result(result: JourneyResult, config: JourneyConfig) -> int:
    print(f"Golden journey: {result.status}")
    print(f"Scenario: {config.scenario}")
    print(f"Mode: {config.mode}")
    print(f"Fixture: {config.fixture}")
    print(f"Output: {result.output_dir}")
    if result.benchmark_summary:
        print(f"Readiness: {result.benchmark_summary.get('readiness', 'unknown')}")
        print(f"Model: {result.benchmark_summary.get('model', 'unknown')}")
        print(f"Raw coverage: {result.benchmark_summary.get('rawCoverage', '0/0')}")
        print(f"Raw missing: {result.benchmark_summary.get('rawMissing', 0)}")
        print(f"Conformance: {result.benchmark_summary.get('conformance', 'unknown')}")
    if result.failures:
        print("Failures:")
        for failure in result.failures:
            print(f"  - {failure}")
        return 1
    if config.scenario == "blocked":
        print("Validated: blocked readiness, safe assessment artifacts, blocker traceability")
        print("Validated: trace summary, model benchmark conformance, review HTML, no raw evidence")
        print("Validated: no deployable or target handoff artifacts")
        return 0
    print("Validated: readiness, allowed next action, contracts, manual gates, target artifacts")
    print("Validated: trace summary, model benchmark conformance, review HTML, no raw evidence")
    return 0


if __name__ == "__main__":
    sys.exit(main())
