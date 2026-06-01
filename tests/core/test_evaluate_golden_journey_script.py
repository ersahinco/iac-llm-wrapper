"""Golden journey script tests."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "evaluate-golden-journey.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("evaluate_golden_journey_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_evaluate_golden_journey_passes_service_style_path(tmp_path: Path):
    output_dir = tmp_path / "golden"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--keep-output",
            str(output_dir),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Golden journey: PASS" in result.stdout
    assert "Validated: readiness" in result.stdout
    assert (output_dir / "handoff-review.html").exists()
    assert (output_dir / "model-benchmark.yaml").exists()
    assert not (output_dir / "raw-evidence.yaml").exists()


def test_golden_journey_validation_flags_raw_evidence(tmp_path: Path):
    script = _load_script()
    output_dir = tmp_path / "golden"
    output_dir.mkdir()
    (output_dir / "raw-evidence.yaml").write_text("calls: []\n")

    failures: list[str] = script._validate_files(output_dir)

    assert "forbidden artifact present: raw-evidence.yaml" in failures


def test_golden_journey_benchmark_requires_conformance(tmp_path: Path):
    script = _load_script()
    config: Any = script.JourneyConfig(
        fixture=SCRIPT,
        pattern="aws-lza",
        use_llm=False,
        provider="ollama",
        model="",
    )

    failures: list[str] = script._validate_benchmark(
        config,
        {
            "schemaVersion": "intent-engine/model-benchmark/v1",
            "run": {"mode": "deterministic"},
            "readiness": {"status": "ready"},
            "quality": {"acceptedDecisionCount": 1},
            "rawEvidence": {"status": "not-requested"},
        },
    )

    assert "benchmark missing valid conformance status" in failures
