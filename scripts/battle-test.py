#!/usr/bin/env python3
"""Run repeatable local battle tests into ignored tests/results folders."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import ruamel.yaml

from intent_engine.core.battle_summary import (
    BattleCaseInput,
    BattleCompileResult,
    build_battle_summary,
    summarize_battle_artifacts,
    write_battle_summary,
)
from intent_engine.core.contract_validation import write_contract_validation

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = REPO_ROOT / "fixtures" / "eval"
RESULTS_DIR = REPO_ROOT / "tests" / "results"


def _yaml_load(path: Path) -> dict[str, Any]:
    yaml = ruamel.yaml.YAML(typ="safe")
    data = yaml.load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected mapping")
    return data


def _load_case(name: str) -> BattleCaseInput:
    for expected_path in sorted(EVAL_DIR.glob("*.expected.yaml")):
        data = _yaml_load(expected_path)
        if data.get("name") != name:
            continue
        input_name = data.get("input")
        pattern = data.get("pattern")
        expected = data.get("expect", {})
        if not isinstance(input_name, str) or not isinstance(pattern, str):
            raise ValueError(f"{expected_path}: input and pattern must be strings")
        if not isinstance(expected, dict):
            raise ValueError(f"{expected_path}: expect must be a mapping")
        artifacts = expected.get("artifacts", [])
        violations = expected.get("violations", [])
        return BattleCaseInput(
            name=name,
            input_path=EVAL_DIR / input_name,
            pattern=pattern,
            expected_compile=str(expected.get("compile", "pass")),
            expected_artifacts=tuple(str(item) for item in artifacts if isinstance(item, str)),
            expected_violations=tuple(str(item) for item in violations if isinstance(item, str)),
        )
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


def _result_dir(case: BattleCaseInput, use_llm: bool, model: str, output: Path | None) -> Path:
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


def _git_sha() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


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
    if compile_proc.returncode != 0 and case.expected_compile != "fail":
        _print_proc_failure(compile_proc)
        return compile_proc.returncode

    write_contract_validation(output_dir)

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

    battle_summary = build_battle_summary(
        case=case,
        output_dir=output_dir,
        command=[Path(sys.executable).name, *sys.argv],
        use_llm=args.llm,
        compile_result=BattleCompileResult(
            returncode=compile_proc.returncode,
            stdout=compile_proc.stdout,
            stderr=compile_proc.stderr,
        ),
        repo_root=REPO_ROOT,
        git_commit=_git_sha(),
    )
    write_battle_summary(output_dir / "battle-summary.yaml", battle_summary)
    summary = summarize_battle_artifacts(output_dir)
    print(f"Output: {output_dir}")
    print(f"Review page: {output_dir / 'handoff-review.html'}")
    print(f"Battle summary: {output_dir / 'battle-summary.yaml'}")
    print(
        "Summary: "
        f"verdict={battle_summary['verdict']} "
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
    return 0 if battle_summary["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
