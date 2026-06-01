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


def _run(*paths: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(path) for path in paths)],
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
    assert "identity_center_permission_sets, identity_center_assignments" in result.stdout
    assert str(benchmark) in result.stdout


def test_compare_model_benchmarks_fails_for_missing_file(tmp_path: Path):
    missing = tmp_path / "missing.yaml"

    result = _run(missing)

    assert result.returncode == 1
    assert f"Missing benchmark file(s): {missing}" in result.stderr
