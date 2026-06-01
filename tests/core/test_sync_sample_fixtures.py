"""Sample fixture sync script tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from intent_engine.core.sample_config import SampleConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "sync-sample-fixtures.py"


@pytest.fixture(scope="module")
def sync_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sync_sample_fixtures_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sample(name: str = "sample-v1") -> SampleConfig:
    return SampleConfig(
        name=name,
        pattern="example-pattern",
        version="1.0.0",
        release_date="2026-01-01",
        source_url="https://example.com",
        decisions={"region": "eu-central-1"},
    )


def test_normalizes_decision_audit_timestamps(sync_script: ModuleType):
    first = "entries:\n  - timestamp: 2026-01-01T00:00:00Z\n    key: region\n"
    second = "entries:\n  - timestamp: 2026-02-01T00:00:00Z\n    key: region\n"

    assert sync_script._normalized_artifact_text("decision-audit.yaml", first) == (
        sync_script._normalized_artifact_text("decision-audit.yaml", second)
    )
    assert sync_script._normalized_artifact_text("config.yaml", "a: 1  \n") == "a: 1\n"


def test_drift_messages_report_missing_stale_and_changed_files(
    sync_script: ModuleType,
    tmp_path: Path,
):
    generated = tmp_path / "generated"
    fixture = tmp_path / "fixture"
    generated.mkdir()
    fixture.mkdir()
    (generated / "missing.yaml").write_text("missing: true\n")
    (generated / "changed.yaml").write_text("value: new\n")
    (fixture / "changed.yaml").write_text("value: old\n")
    (fixture / "stale.yaml").write_text("stale: true\n")
    (fixture / "README.md").write_text("kept\n")

    messages = sync_script._drift_messages(_sample(), generated, fixture)

    assert messages == [
        "sample-v1: missing missing.yaml",
        "sample-v1: stale stale.yaml",
        "sample-v1: changed changed.yaml",
    ]


def test_sync_sample_reports_missing_fixture_dir(sync_script: ModuleType, tmp_path: Path):
    sample = _sample()
    sync_script.FIXTURES_ROOT = tmp_path

    assert sync_script._sync_sample(sample, check=True) == [
        "sample-v1: fixture dir missing at sample-v1"
    ]


def test_sync_sample_check_mode_reports_drift_without_writing(
    sync_script: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    sample = _sample()
    fixture_dir = tmp_path / sample.fixture_name
    fixture_dir.mkdir()
    (fixture_dir / "config.yaml").write_text("region: old\n")
    sync_script.FIXTURES_ROOT = tmp_path

    def fake_compile(decisions: dict[str, Any], output_dir: Path, *, pattern: str) -> None:
        assert decisions == sample.decisions
        assert pattern == sample.pattern
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "config.yaml").write_text("region: eu-central-1\n")

    monkeypatch.setattr(sync_script, "compile_from_interview", fake_compile)

    messages = sync_script._sync_sample(sample, check=True)

    assert messages == ["sample-v1: changed config.yaml"]
    assert (fixture_dir / "config.yaml").read_text() == "region: old\n"
