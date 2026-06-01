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
from datetime import UTC, datetime
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
    evidence_path: Path | None = None


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
    case: EvalCase,
    output_dir: Path,
    use_llm: bool,
    provider: str,
    model: str,
    evidence_path: Path | None,
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
    if use_llm and evidence_path is not None:
        cmd.extend(["--evidence-output", str(evidence_path)])

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


def _path_exists(data: Any, dotted_path: str) -> bool:
    current = data
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


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


def _compare_report(case: EvalCase, output_dir: Path, use_llm: bool) -> list[str]:
    failures: list[str] = []
    report_path = output_dir / "decision-report.yaml"
    if not report_path.exists():
        return ["missing artifact: decision-report.yaml"]

    report = _yaml_load(report_path)
    failures.extend(_compare_values(report, case.expected.get("values", {})))
    failures.extend(_compare_counts(report, case.expected.get("counts", {})))
    failures.extend(_compare_names(report, case.expected.get("names", {})))
    failures.extend(_compare_artifacts(output_dir, case.expected.get("artifacts", [])))
    failures.extend(_compare_trace(output_dir, case.expected.get("trace", {}), use_llm))
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


def _compare_trace(output_dir: Path, expected_trace: Any, use_llm: bool) -> list[str]:
    if not expected_trace:
        return []
    if not isinstance(expected_trace, dict):
        return ["expect.trace must be a mapping"]

    trace_path = output_dir / "llm-trace-summary.yaml"
    if not trace_path.exists():
        return ["missing artifact: llm-trace-summary.yaml"]

    trace = _yaml_load(trace_path)
    failures: list[str] = []
    required = expected_trace.get("required", [])
    if not isinstance(required, list):
        failures.append("expect.trace.required must be a list")
    else:
        for path in required:
            if not isinstance(path, str):
                failures.append("expect.trace.required entries must be strings")
            elif not _path_exists(trace, path):
                failures.append(f"trace missing required path: {path}")

    absent = expected_trace.get("absent", [])
    if not isinstance(absent, list):
        failures.append("expect.trace.absent must be a list")
    else:
        for path in absent:
            if not isinstance(path, str):
                failures.append("expect.trace.absent entries must be strings")
            elif _path_exists(trace, path):
                failures.append(f"trace path should be absent: {path}")

    failures.extend(_compare_values(trace, expected_trace.get("values", {})))
    mode_key = "llmValues" if use_llm else "deterministicValues"
    failures.extend(_compare_values(trace, expected_trace.get(mode_key, {})))
    return failures


def _compare_evidence(evidence_path: Path | None, model: str) -> list[str]:
    if evidence_path is None:
        return []
    if not evidence_path.exists():
        return [f"missing LLM evidence file: {evidence_path}"]

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
        if model and call.get("model") != model:
            failures.append(f"LLM model mismatch: expected {model}, got {call.get('model')}")
        if not call.get("prompt"):
            failures.append("LLM evidence missing prompt")
        if not call.get("response"):
            failures.append("LLM evidence missing response")
    return failures


def _compare_failure(
    case: EvalCase,
    output_dir: Path,
    proc: subprocess.CompletedProcess[str],
    use_llm: bool,
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
    failures.extend(_compare_trace(output_dir, case.expected.get("trace", {}), use_llm))
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
    evidence_dir: Path | None,
) -> EvalResult:
    expected_compile = case.expected.get("compile", "pass")
    if expected_compile not in {"pass", "fail"}:
        return EvalResult(case.name, case.pattern, "FAIL", ["expect.compile must be pass or fail"])

    evidence_path = evidence_dir / f"{case.name}.evidence.yaml" if evidence_dir else None

    if keep_output_root:
        output_dir = keep_output_root / case.name
        output_dir.mkdir(parents=True, exist_ok=True)
        proc = _compile_case(case, output_dir, use_llm, provider, model, evidence_path)
        cleanup = None
    else:
        cleanup = tempfile.TemporaryDirectory()
        output_dir = Path(cleanup.name)
        proc = _compile_case(case, output_dir, use_llm, provider, model, evidence_path)

    try:
        if expected_compile == "fail":
            if proc.returncode == 0:
                return EvalResult(
                    case.name,
                    case.pattern,
                    "FAIL",
                    ["expected compile failure"],
                    output_dir,
                    evidence_path,
                )
            failures = _compare_failure(case, output_dir, proc, use_llm)
            failures.extend(_compare_evidence(evidence_path, model))
            return EvalResult(
                case.name,
                case.pattern,
                "PASS" if not failures else "FAIL",
                failures,
                output_dir,
                evidence_path,
            )

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip().splitlines()
            failure = detail[-1] if detail else "compile failed"
            return EvalResult(case.name, case.pattern, "FAIL", [failure], output_dir, evidence_path)

        failures = _compare_report(case, output_dir, use_llm)
        failures.extend(_compare_evidence(evidence_path, model))
        return EvalResult(
            case.name,
            case.pattern,
            "PASS" if not failures else "FAIL",
            failures,
            output_dir,
            evidence_path,
        )
    finally:
        if cleanup is not None:
            cleanup.cleanup()


def _write_eval_results(
    path: Path,
    *,
    results: list[EvalResult],
    use_llm: bool,
    provider: str,
    model: str,
) -> None:
    failures = [result for result in results if result.status != "PASS"]
    data = {
        "schemaVersion": "intent-engine/eval-results/v1",
        "generatedAt": datetime.now(UTC).isoformat(),
        "mode": "llm" if use_llm else "deterministic",
        "provider": provider if use_llm and provider else "auto" if use_llm else "none",
        "model": model if use_llm and model else "auto" if use_llm else "none",
        "summary": {
            "caseCount": len(results),
            "passed": len(results) - len(failures),
            "failed": len(failures),
            "status": "pass" if not failures else "fail",
        },
        "cases": [
            {
                "name": result.name,
                "pattern": result.pattern,
                "status": result.status.lower(),
                "failures": result.failures,
                "outputDir": (
                    str(result.output_dir)
                    if result.output_dir is not None and result.output_dir.exists()
                    else None
                ),
                "evidencePath": (
                    str(result.evidence_path)
                    if result.evidence_path is not None and result.evidence_path.exists()
                    else None
                ),
            }
            for result in results
        ],
    }
    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_yaml_header() + _yaml_dump(yaml, data))


def _yaml_dump(yaml: ruamel.yaml.YAML, data: dict[str, Any]) -> str:
    from io import StringIO

    buf = StringIO()
    yaml.dump(data, buf)
    return "\n".join(line.rstrip() for line in buf.getvalue().splitlines()) + "\n"


def _yaml_header() -> str:
    return (
        "# yaml-language-server: $schema=none\n"
        "# Generated by intent-engine - eval results artifact.\n"
    )


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
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        help="Directory to keep LLM evidence YAML files from --llm evals.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write machine-readable eval-results.yaml artifact.",
    )
    args = parser.parse_args()

    cases = _load_cases(args.fixtures_dir, args.fixture)
    keep_output = args.keep_output.resolve() if args.keep_output else None
    if keep_output:
        keep_output.mkdir(parents=True, exist_ok=True)
    evidence_dir = args.evidence_dir.resolve() if args.evidence_dir else None
    if evidence_dir:
        evidence_dir.mkdir(parents=True, exist_ok=True)

    print(f"{'Case':28s} {'Pattern':20s} {'Mode':13s} Status")
    print("-" * 78)

    failures = 0
    results: list[EvalResult] = []
    for case in cases:
        result = _evaluate_case(
            case,
            args.llm,
            args.provider,
            args.model,
            keep_output,
            evidence_dir,
        )
        results.append(result)
        mode = "llm" if args.llm else "deterministic"
        suffix = "" if not result.failures else " - " + "; ".join(result.failures[:3])
        print(f"{result.name:28s} {result.pattern:20s} {mode:13s} {result.status}{suffix}")
        if result.evidence_path is not None:
            print(f"{'':28s} {'evidence':20s} {'':13s} {result.evidence_path}")
        if result.status != "PASS":
            failures += 1

    print("-" * 78)
    print(f"Results: {len(cases) - failures} passed, {failures} failed")
    if args.output:
        _write_eval_results(
            args.output.resolve(),
            results=results,
            use_llm=args.llm,
            provider=args.provider,
            model=args.model,
        )
        print(f"Eval results: {args.output.resolve()}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
