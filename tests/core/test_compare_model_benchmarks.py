"""Model benchmark comparison script tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import ruamel.yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "compare-model-benchmarks.py"


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    with path.open("w") as handle:
        yaml.dump(data, handle)


def _run(*paths: Path, require_conformant: bool = False) -> subprocess.CompletedProcess[str]:
    args = ["--require-conformant"] if require_conformant else []
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, *(str(path) for path in paths)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_compare_model_benchmarks_prints_table(tmp_path: Path):
    benchmark = tmp_path / "model-benchmark.yaml"
    _write_yaml(
        benchmark,
        {
            "run": {
                "mode": "llm",
                "provider": "openai-compatible",
                "model": "llama3.2:3b",
            },
            "readiness": {"status": "ready", "blockerCount": 0},
            "latency": {"totalMs": 123.4},
            "tokens": {"totalTokens": 4321},
            "quality": {
                "acceptedDecisionCount": 20,
                "rawLlmAcceptedCoverageCount": 18,
                "rawLlmMissingAcceptedDecisionCount": 2,
                "rawLlmMissingAcceptedDecisions": [
                    "identity_center_permission_sets",
                    "identity_center_assignments",
                ],
                "parseErrorCount": 0,
            },
            "conformance": {
                "status": "review",
                "reason": "raw LLM missed accepted decisions",
            },
        },
    )

    result = _run(benchmark)

    assert result.returncode == 0, result.stderr
    assert "provider" in result.stdout
    assert "openai-compatible" in result.stdout
    assert "llama3.2:3b" in result.stdout
    assert "123.4" in result.stdout
    assert "4321" in result.stdout
    assert "rawCoverage" in result.stdout
    assert "18/20" in result.stdout
    assert "rawMissing" in result.stdout
    assert "conformance" in result.stdout
    assert "review" in result.stdout
    assert "identity_center_permission_sets, identity_center_assignments" in result.stdout
    assert str(benchmark) in result.stdout


def test_compare_model_benchmarks_can_require_conformance(tmp_path: Path):
    passing = tmp_path / "pass.yaml"
    review = tmp_path / "review.yaml"
    base = {
        "run": {"mode": "llm", "provider": "ollama", "model": "qwen2.5:7b"},
        "readiness": {"status": "ready", "blockerCount": 0},
        "latency": {"totalMs": 100},
        "tokens": {"totalTokens": 0},
        "quality": {
            "acceptedDecisionCount": 2,
            "rawLlmAcceptedCoverageCount": 2,
            "rawLlmMissingAcceptedDecisionCount": 0,
            "rawLlmMissingAcceptedDecisions": [],
            "parseErrorCount": 0,
        },
    }
    _write_yaml(passing, {**base, "conformance": {"status": "pass"}})
    _write_yaml(
        review,
        {
            **base,
            "quality": {
                **base["quality"],
                "rawLlmAcceptedCoverageCount": 1,
                "rawLlmMissingAcceptedDecisionCount": 1,
                "rawLlmMissingAcceptedDecisions": ["network_account"],
            },
            "conformance": {"status": "review"},
        },
    )

    pass_result = _run(passing, require_conformant=True)
    review_result = _run(review, require_conformant=True)

    assert pass_result.returncode == 0, pass_result.stderr
    assert review_result.returncode == 1
    assert f"Non-conformant LLM benchmark(s): {review}" in review_result.stderr


def test_compare_model_benchmarks_fails_for_missing_file(tmp_path: Path):
    missing = tmp_path / "missing.yaml"

    result = _run(missing)

    assert result.returncode == 1
    assert f"Missing benchmark file(s): {missing}" in result.stderr
