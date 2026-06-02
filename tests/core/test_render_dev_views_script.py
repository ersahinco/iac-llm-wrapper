"""Tests for the local developer visualization script."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import ruamel.yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_yaml(path: Path, data: dict) -> None:
    yaml = ruamel.yaml.YAML()
    with path.open("w") as handle:
        yaml.dump(data, handle)


def test_render_dev_views_writes_graph_model_dependency_and_result_views(tmp_path: Path):
    results_dir = tmp_path / "results"
    output_dir = tmp_path / "dev-views"
    benchmark_dir = results_dir / "golden-bedrock" / "ready"
    benchmark_dir.mkdir(parents=True)
    _write_yaml(
        results_dir / "golden-journey-bedrock.yaml",
        {
            "provider": "bedrock",
            "model": "eu.amazon.nova-2-lite-v1:0",
            "summary": {"status": "pass"},
            "scenarios": [
                {
                    "scenario": "ready",
                    "status": "pass",
                    "readiness": "ready",
                    "rawCoverage": "20/20",
                    "conformance": "pass",
                }
            ],
        },
    )
    _write_yaml(
        benchmark_dir / "model-benchmark.yaml",
        {
            "run": {"provider": "bedrock", "model": "eu.amazon.nova-2-lite-v1:0"},
            "readiness": {"status": "ready"},
            "latency": {"totalMs": 123.4},
            "tokens": {"totalTokens": 42},
            "quality": {
                "acceptedDecisionCount": 2,
                "rawLlmAcceptedCoverageCount": 2,
                "rawLlmMissingAcceptedDecisionCount": 0,
            },
            "conformance": {"status": "pass"},
        },
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/render-dev-views.py",
            "--pattern",
            "aws-lza",
            "--results-dir",
            str(results_dir),
            "--output",
            str(output_dir),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "index.html").exists()
    assert (output_dir / "graphs" / "aws-lza-requirement-graph.mmd").exists()
    assert (output_dir / "graphs" / "aws-lza-requirement-graph.json").exists()
    assert (output_dir / "models" / "aws-lza-intent-model.mmd").exists()
    assert (output_dir / "code" / "module-dependencies.mmd").exists()
    golden = (output_dir / "results" / "golden-journeys.md").read_text()
    benchmark = (output_dir / "results" / "model-benchmarks.md").read_text()
    assert "eu.amazon.nova-2-lite-v1:0" in golden
    assert "20/20" in golden
    assert "2/2" in benchmark
