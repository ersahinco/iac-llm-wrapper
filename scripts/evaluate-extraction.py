#!/usr/bin/env python3
"""Evaluate generated artifacts against expected extraction outcomes.

Default mode disables LLM use so the deterministic path is fast and repeatable.
Pass --llm to let normal provider/model auto-detection run.
"""

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

from intent_engine.core.contracts import GLOBAL_CONTRACT_REGISTRY, ContractValidator

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURES_DIR = REPO_ROOT / "fixtures" / "eval"


@dataclass(frozen=True)
class EvalCase:
    name: str
    input_path: Path
    pattern: str
    expected: dict[str, Any]


@dataclass
class EvalResult:
    name: str
    pattern: str
    status: str
    failures: list[str]
    output_dir: Path | None = None


def _yaml_load(path: Path) -> dict[str, Any]:
    yaml = ruamel.yaml.YAML(typ="safe")
    data = yaml.load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected mapping")
    return data


def _load_cases(fixtures_dir: Path, only: str | None) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for expected_path in sorted(fixtures_dir.glob("*.expected.yaml")):
        data = _yaml_load(expected_path)
        name = _expect_str(data, "name", expected_path)
        if only and name != only:
            continue
        input_name = _expect_str(data, "input", expected_path)
        pattern = _expect_str(data, "pattern", expected_path)
        expected = data.get("expect")
        if not isinstance(expected, dict):
            raise ValueError(f"{expected_path}: expect must be a mapping")
        input_path = fixtures_dir / input_name
        if not input_path.exists():
            raise ValueError(f"{expected_path}: missing input {input_name}")
        cases.append(EvalCase(name=name, input_path=input_path, pattern=pattern, expected=expected))
    if only and not cases:
        raise ValueError(f"No eval case named {only!r}")
    return cases


def _expect_str(data: dict[str, Any], key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path}: {key} must be a non-empty string")
    return value


def _compile_case(
    case: EvalCase, output_dir: Path, use_llm: bool, provider: str, model: str
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "-m",
        "intent_engine",
        "compile",
        "--input",
        str(case.input_path),
        "--output",
        str(output_dir),
        "--pattern",
        case.pattern,
    ]
    if provider:
        cmd.extend(["--provider", provider])
    if model:
        cmd.extend(["--model", model])

    env = os.environ.copy()
    if not use_llm:
        env["INTENT_ENGINE_DISABLE_LLM"] = "1"

    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )


def _get_path(data: Any, dotted_path: str) -> Any:
    current = data
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _names(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    names: list[str] = []
    for item in items:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
    return names


def _compare_report(case: EvalCase, output_dir: Path) -> list[str]:
    failures: list[str] = []
    report_path = output_dir / "decision-report.yaml"
    if not report_path.exists():
        return ["missing artifact: decision-report.yaml"]

    report = _yaml_load(report_path)
    failures.extend(_compare_values(report, case.expected.get("values", {})))
    failures.extend(_compare_counts(report, case.expected.get("counts", {})))
    failures.extend(_compare_names(report, case.expected.get("names", {})))
    failures.extend(_compare_artifacts(output_dir, case.expected.get("artifacts", [])))
    return failures


def _compare_values(report: dict[str, Any], expected_values: Any) -> list[str]:
    if not isinstance(expected_values, dict):
        return ["expect.values must be a mapping"]
    failures: list[str] = []
    for path, expected in expected_values.items():
        if not isinstance(path, str):
            failures.append("expect.values keys must be strings")
            continue
        actual = _get_path(report, path)
        if actual != expected:
            failures.append(f"{path}: expected {expected!r}, got {actual!r}")
    return failures


def _compare_counts(report: dict[str, Any], expected_counts: Any) -> list[str]:
    if not isinstance(expected_counts, dict):
        return ["expect.counts must be a mapping"]
    failures: list[str] = []
    for key, expected in expected_counts.items():
        items = report.get(key)
        actual = len(items) if isinstance(items, list) else 0
        if actual != expected:
            failures.append(f"{key} count: expected {expected}, got {actual}")
    return failures


def _compare_names(report: dict[str, Any], expected_names: Any) -> list[str]:
    if not isinstance(expected_names, dict):
        return ["expect.names must be a mapping"]
    failures: list[str] = []
    for key, expected in expected_names.items():
        if not isinstance(expected, list):
            failures.append(f"{key} names: expected list in gold file")
            continue
        missing = [name for name in expected if name not in _names(report.get(key))]
        if missing:
            failures.append(f"{key} names missing: {', '.join(str(name) for name in missing)}")
    return failures


def _compare_artifacts(output_dir: Path, expected_artifacts: Any) -> list[str]:
    if not isinstance(expected_artifacts, list):
        return ["expect.artifacts must be a list"]
    failures: list[str] = []
    for artifact in expected_artifacts:
        if not isinstance(artifact, str):
            failures.append("expect.artifacts entries must be strings")
        elif not (output_dir / artifact).exists():
            failures.append(f"missing artifact: {artifact}")
    return failures


def _compare_contracts(output_dir: Path, expected_contracts: Any) -> list[str]:
    if not isinstance(expected_contracts, list):
        return ["expect.contracts must be a list"]
    failures: list[str] = []
    for contract_name in expected_contracts:
        if not isinstance(contract_name, str):
            failures.append("expect.contracts entries must be strings")
            continue
        try:
            contract = GLOBAL_CONTRACT_REGISTRY.get(contract_name)
        except KeyError as exc:
            failures.append(str(exc))
            continue
        failures.extend(
            f"{contract_name}: {violation.message}"
            for violation in ContractValidator(contract).validate_artifacts(output_dir)
        )
    return failures


def _compare_failure(
    case: EvalCase,
    output_dir: Path,
    proc: subprocess.CompletedProcess[str],
) -> list[str]:
    failures: list[str] = []
    expected_violations = case.expected.get("violations", [])
    if not isinstance(expected_violations, list):
        failures.append("expect.violations must be a list")
    else:
        combined_output = f"{proc.stdout}\n{proc.stderr}"
        for violation in expected_violations:
            if not isinstance(violation, str):
                failures.append("expect.violations entries must be strings")
            elif violation not in combined_output:
                failures.append(f"missing violation in output: {violation}")

    failures.extend(_compare_artifacts(output_dir, case.expected.get("artifacts", [])))
    failures.extend(_compare_contracts(output_dir, case.expected.get("contracts", [])))
    report_path = output_dir / "decision-report.yaml"
    if report_path.exists():
        report = _yaml_load(report_path)
        failures.extend(_compare_values(report, case.expected.get("values", {})))
    elif case.expected.get("values"):
        failures.append("missing artifact: decision-report.yaml")
    return failures


def _evaluate_case(
    case: EvalCase,
    use_llm: bool,
    provider: str,
    model: str,
    keep_output_root: Path | None,
) -> EvalResult:
    expected_compile = case.expected.get("compile", "pass")
    if expected_compile not in {"pass", "fail"}:
        return EvalResult(case.name, case.pattern, "FAIL", ["expect.compile must be pass or fail"])

    if keep_output_root:
        output_dir = keep_output_root / case.name
        output_dir.mkdir(parents=True, exist_ok=True)
        proc = _compile_case(case, output_dir, use_llm, provider, model)
        cleanup = None
    else:
        cleanup = tempfile.TemporaryDirectory()
        output_dir = Path(cleanup.name)
        proc = _compile_case(case, output_dir, use_llm, provider, model)

    try:
        if expected_compile == "fail":
            if proc.returncode == 0:
                return EvalResult(
                    case.name, case.pattern, "FAIL", ["expected compile failure"], output_dir
                )
            failures = _compare_failure(case, output_dir, proc)
            return EvalResult(
                case.name,
                case.pattern,
                "PASS" if not failures else "FAIL",
                failures,
                output_dir,
            )

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip().splitlines()
            failure = detail[-1] if detail else "compile failed"
            return EvalResult(case.name, case.pattern, "FAIL", [failure], output_dir)

        failures = _compare_report(case, output_dir)
        return EvalResult(
            case.name,
            case.pattern,
            "PASS" if not failures else "FAIL",
            failures,
            output_dir,
        )
    finally:
        if cleanup is not None:
            cleanup.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate extraction against gold artifacts")
    parser.add_argument("--fixtures-dir", type=Path, default=DEFAULT_FIXTURES_DIR)
    parser.add_argument("--fixture", help="Run one eval case by name")
    parser.add_argument(
        "--llm", action="store_true", help="Use configured LLM instead of deterministic mode"
    )
    parser.add_argument("--provider", default="", help="LLM provider when --llm is set")
    parser.add_argument("--model", default="", help="LLM model when --llm is set")
    parser.add_argument(
        "--keep-output", type=Path, help="Keep generated outputs under this directory"
    )
    args = parser.parse_args()

    cases = _load_cases(args.fixtures_dir, args.fixture)
    keep_output = args.keep_output.resolve() if args.keep_output else None
    if keep_output:
        keep_output.mkdir(parents=True, exist_ok=True)

    print(f"{'Case':28s} {'Pattern':20s} {'Mode':13s} Status")
    print("-" * 78)

    failures = 0
    for case in cases:
        result = _evaluate_case(case, args.llm, args.provider, args.model, keep_output)
        mode = "llm" if args.llm else "deterministic"
        suffix = "" if not result.failures else " - " + "; ".join(result.failures[:3])
        print(f"{result.name:28s} {result.pattern:20s} {mode:13s} {result.status}{suffix}")
        if result.status != "PASS":
            failures += 1

    print("-" * 78)
    print(f"Results: {len(cases) - failures} passed, {failures} failed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
