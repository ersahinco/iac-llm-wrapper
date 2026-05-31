#!/usr/bin/env python3
"""Run repeatable local battle tests into ignored tests/results folders."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ruamel.yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = REPO_ROOT / "fixtures" / "eval"
RESULTS_DIR = REPO_ROOT / "tests" / "results"


@dataclass(frozen=True)
class BattleCase:
    name: str
    input_path: Path
    pattern: str


def _yaml_load(path: Path) -> dict[str, Any]:
    yaml = ruamel.yaml.YAML(typ="safe")
    data = yaml.load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected mapping")
    return data


def _load_case(name: str) -> BattleCase:
    for expected_path in sorted(EVAL_DIR.glob("*.expected.yaml")):
        data = _yaml_load(expected_path)
        if data.get("name") != name:
            continue
        input_name = data.get("input")
        pattern = data.get("pattern")
        if not isinstance(input_name, str) or not isinstance(pattern, str):
            raise ValueError(f"{expected_path}: input and pattern must be strings")
        return BattleCase(name=name, input_path=EVAL_DIR / input_name, pattern=pattern)
    raise ValueError(f"No eval fixture named {name!r}")


def _run(cmd: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )


def _result_dir(case: BattleCase, use_llm: bool, model: str, output: Path | None) -> Path:
    if output is not None:
        return output
    mode = "llm" if use_llm else "deterministic"
    suffix = _slug(model) if use_llm and model else "auto" if use_llm else "no-llm"
    return RESULTS_DIR / f"{case.name}-{mode}-{suffix}"


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value).strip("-").lower() or "model"


def _print_proc_failure(proc: subprocess.CompletedProcess[str]) -> None:
    output = (proc.stderr or proc.stdout).strip()
    if output:
        print(output, file=sys.stderr)


def _summary(output_dir: Path) -> dict[str, Any]:
    benchmark = _yaml_load(output_dir / "model-benchmark.yaml")
    validation_path = output_dir / "contract-validation.yaml"
    validation = _yaml_load(validation_path) if validation_path.exists() else {}
    run = benchmark.get("run", {}) if isinstance(benchmark.get("run"), dict) else {}
    latency = benchmark.get("latency", {}) if isinstance(benchmark.get("latency"), dict) else {}
    tokens = benchmark.get("tokens", {}) if isinstance(benchmark.get("tokens"), dict) else {}
    quality = benchmark.get("quality", {}) if isinstance(benchmark.get("quality"), dict) else {}
    readiness = (
        benchmark.get("readiness", {}) if isinstance(benchmark.get("readiness"), dict) else {}
    )
    validation_summary = (
        validation.get("summary", {}) if isinstance(validation.get("summary"), dict) else {}
    )
    return {
        "mode": run.get("mode", "unknown"),
        "provider": run.get("provider", "unknown"),
        "model": run.get("model", "unknown"),
        "readiness": readiness.get("status", "unknown"),
        "latencyMs": latency.get("totalMs", 0),
        "tokens": tokens.get("totalTokens", 0),
        "acceptedDecisions": quality.get("acceptedDecisionCount", 0),
        "parseErrors": quality.get("parseErrorCount", 0),
        "contractStatus": validation_summary.get("status", "unknown"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        default="aws-lza-complex-enterprise-handoff",
        help="Eval fixture case name",
    )
    parser.add_argument("--llm", action="store_true", help="Use configured LLM")
    parser.add_argument("--provider", default="", help="LLM provider for --llm")
    parser.add_argument("--model", default="", help="LLM model for --llm")
    parser.add_argument("--output", type=Path, help="Output directory")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep existing output directory contents instead of replacing them",
    )
    args = parser.parse_args()

    case = _load_case(args.fixture)
    output_dir = _result_dir(case, args.llm, args.model, args.output).resolve()
    if output_dir.exists() and not args.keep:
        if RESULTS_DIR not in output_dir.parents:
            raise RuntimeError(f"Refusing to delete non-results directory: {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    if not args.llm:
        env["INTENT_ENGINE_DISABLE_LLM"] = "1"
    else:
        env.pop("INTENT_ENGINE_DISABLE_LLM", None)

    compile_cmd = [
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
    if args.provider:
        compile_cmd.extend(["--provider", args.provider])
    if args.model:
        compile_cmd.extend(["--model", args.model])
    if args.llm:
        compile_cmd.extend(["--evidence-output", str(output_dir / "raw-evidence.yaml")])

    compile_proc = _run(compile_cmd, env=env)
    if compile_proc.returncode != 0:
        _print_proc_failure(compile_proc)
        return compile_proc.returncode

    review_proc = _run(
        [
            sys.executable,
            "-m",
            "intent_engine",
            "review",
            "html",
            "--input",
            str(output_dir),
            "--output",
            str(output_dir / "handoff-review.html"),
        ],
        env=env,
    )
    if review_proc.returncode != 0:
        _print_proc_failure(review_proc)
        return review_proc.returncode

    summary = _summary(output_dir)
    print(f"Output: {output_dir}")
    print(f"Review page: {output_dir / 'handoff-review.html'}")
    print(
        "Summary: "
        f"mode={summary['mode']} "
        f"provider={summary['provider']} "
        f"model={summary['model']} "
        f"readiness={summary['readiness']} "
        f"latencyMs={summary['latencyMs']} "
        f"tokens={summary['tokens']} "
        f"acceptedDecisions={summary['acceptedDecisions']} "
        f"parseErrors={summary['parseErrors']} "
        f"contractStatus={summary['contractStatus']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
