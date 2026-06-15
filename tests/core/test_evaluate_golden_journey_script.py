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


def test_evaluate_golden_journey_passes_blocked_service_style_path(tmp_path: Path):
    output_dir = tmp_path / "blocked"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--scenario",
            "blocked",
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
    assert "Scenario: blocked" in result.stdout
    assert "Readiness: blocked" in result.stdout
    assert (
        "Validated: blocked readiness, safe assessment artifacts, blocker traceability"
        in result.stdout
    )
    assert "Validated: no deployable or target handoff artifacts" in result.stdout
    assert (output_dir / "decision-report.yaml").exists()
    assert (output_dir / "handoff-review.html").exists()
    assert not (output_dir / "contract-validation.yaml").exists()
    assert not (output_dir / "network-config.yaml").exists()
    assert not (output_dir / "handoff-plan.yaml").exists()
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


def test_evaluate_golden_journey_writes_ready_result_artifact(tmp_path: Path):
    output_dir = tmp_path / "golden"
    result_path = tmp_path / "golden-results.yaml"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--scenario",
            "ready",
            "--keep-output",
            str(output_dir),
            "--output",
            str(result_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    data = _yaml_load(result_path)
    assert data["schemaVersion"] == "intent-engine/golden-journey-results/v1"
    assert data["summary"] == {
        "scenarioCount": 1,
        "passed": 1,
        "failed": 0,
        "status": "pass",
    }
    assert data["scenarios"][0]["scenario"] == "ready"
    assert data["scenarios"][0]["status"] == "pass"
    assert data["scenarios"][0]["outputDir"] == str(output_dir)
    assert data["scenarios"][0]["readiness"] == "ready"
    assert data["scenarios"][0]["contractStatus"] == "pass"
    assert data["scenarios"][0]["rawEvidenceStatus"] == "not-requested"
    assert "target-artifacts" in data["scenarios"][0]["validatedChecks"]


def test_evaluate_golden_journey_writes_blocked_result_artifact(tmp_path: Path):
    output_dir = tmp_path / "blocked"
    result_path = tmp_path / "blocked-results.yaml"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--scenario",
            "blocked",
            "--keep-output",
            str(output_dir),
            "--output",
            str(result_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    data = _yaml_load(result_path)
    assert data["summary"]["status"] == "pass"
    assert data["scenarios"][0]["scenario"] == "blocked"
    assert data["scenarios"][0]["readiness"] == "blocked"
    assert data["scenarios"][0]["blockerCount"] > 0
    assert data["scenarios"][0]["contractStatus"] == "pass"
    assert "no-deployable-or-target-handoff-artifacts" in data["scenarios"][0]["validatedChecks"]


def test_evaluate_golden_journey_writes_combined_result_artifact(tmp_path: Path):
    output_dir = tmp_path / "all"
    result_path = tmp_path / "all-results.yaml"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--scenario",
            "all",
            "--keep-output",
            str(output_dir),
            "--output",
            str(result_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    data = _yaml_load(result_path)
    assert data["summary"] == {
        "scenarioCount": 2,
        "passed": 2,
        "failed": 0,
        "status": "pass",
    }
    scenarios = {item["scenario"]: item for item in data["scenarios"]}
    assert set(scenarios) == {"ready", "blocked"}
    assert scenarios["ready"]["outputDir"] == str(output_dir / "ready")
    assert scenarios["blocked"]["outputDir"] == str(output_dir / "blocked")


def test_golden_journey_result_artifact_records_failures(tmp_path: Path):
    script = _load_script()
    config: Any = script.JourneyConfig(
        scenario="blocked",
        fixture=SCRIPT,
        pattern="aws-lza",
        use_llm=False,
        provider="ollama",
        model="",
        require_conformant=False,
    )
    result: Any = script.JourneyResult(
        status="FAIL",
        failures=["blocked review html missing signal: Blocker Traceability"],
        output_dir=tmp_path,
        benchmark_summary={"readiness": "blocked", "conformance": "not-applicable"},
    )

    data: dict[str, Any] = script._results_artifact([(config, result)], keep_output=False)

    assert data["summary"]["status"] == "fail"
    assert data["scenarios"][0]["outputDir"] == ""
    assert data["scenarios"][0]["failures"] == [
        "blocked review html missing signal: Blocker Traceability"
    ]


def test_golden_journey_validation_flags_raw_evidence(tmp_path: Path):
    script = _load_script()
    output_dir = tmp_path / "golden"
    output_dir.mkdir()
    (output_dir / "raw-evidence.yaml").write_text("calls: []\n")

    failures: list[str] = script._validate_files(output_dir)

    assert "forbidden artifact present: raw-evidence.yaml" in failures


def test_golden_blocked_journey_flags_deployable_or_handoff_artifacts(tmp_path: Path):
    script = _load_script()
    output_dir = tmp_path / "blocked"
    output_dir.mkdir()
    (output_dir / "network-config.yaml").write_text("homeRegion: eu-central-1\n")
    (output_dir / "main.tf").write_text("resource null_resource example {}\n")

    failures: list[str] = script._validate_blocked_files(output_dir)

    assert "forbidden blocked artifact present: network-config.yaml" in failures
    assert "forbidden blocked artifact present: main.tf" in failures


def test_golden_blocked_journey_requires_blocker_traceability():
    script = _load_script()

    failures: list[str] = script._validate_blocked_review_html(
        "<html><body>blocked AWS_LZA_NETWORK_ACCOUNT_REQUIRED</body></html>"
    )

    assert "blocked review html missing signal: Blocker Traceability" in failures
    assert "blocked review html missing signal: network_account" in failures
    assert (
        "blocked review html missing signal: Which IAM Identity Center assignments are approved?"
        in failures
    )


def test_golden_journey_benchmark_requires_conformance(tmp_path: Path):
    script = _load_script()
    config: Any = script.JourneyConfig(
        scenario="ready",
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
        scenario="ready",
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
        scenario="ready",
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
