"""Golden journey script tests."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import ruamel.yaml

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


def _yaml_load(path: Path) -> dict[str, Any]:
    yaml = ruamel.yaml.YAML(typ="safe")
    data = yaml.load(path.read_text())
    assert isinstance(data, dict)
    return data


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


def test_evaluate_golden_journey_writes_benchmark_summary(tmp_path: Path):
    output_dir = tmp_path / "golden"
    benchmark_output = tmp_path / "golden-benchmark.yaml"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--keep-output",
            str(output_dir),
            "--benchmark-output",
            str(benchmark_output),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Readiness: ready" in result.stdout
    assert "Conformance: not-applicable" in result.stdout
    data = _yaml_load(benchmark_output)
    assert data["schemaVersion"] == "intent-engine/golden-journey-benchmark/v1"
    assert data["mode"] == "deterministic"
    assert data["readiness"] == "ready"
    assert data["conformance"] == "not-applicable"
    assert data["rawCoverage"] == "0/20"


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
        require_conformant=False,
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


def test_golden_journey_require_conformant_ignores_deterministic(tmp_path: Path):
    script = _load_script()
    config: Any = script.JourneyConfig(
        fixture=SCRIPT,
        pattern="aws-lza",
        use_llm=False,
        provider="ollama",
        model="",
        require_conformant=True,
    )

    failures: list[str] = script._required_conformance_failures(
        config,
        {"conformance": "not-applicable"},
    )

    assert failures == []


def test_golden_journey_require_conformant_fails_llm_review_or_fail(tmp_path: Path):
    script = _load_script()
    config: Any = script.JourneyConfig(
        fixture=SCRIPT,
        pattern="aws-lza",
        use_llm=True,
        provider="ollama",
        model="qwen2.5:7b",
        require_conformant=True,
    )

    for conformance in ("review", "fail"):
        failures: list[str] = script._required_conformance_failures(
            config,
            {"conformance": conformance},
        )
        result = script.JourneyResult(
            status="FAIL",
            failures=failures,
            output_dir=tmp_path,
            benchmark_summary={
                "readiness": "ready",
                "model": "qwen2.5:7b",
                "rawCoverage": "18/20",
                "rawMissing": 2,
                "conformance": conformance,
            },
        )

        assert failures == [f"LLM golden journey is not conformant: {conformance}"]
        assert script._print_result(result, config) == 1
