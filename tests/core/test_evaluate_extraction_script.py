"""Extraction eval script artifact tests."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import ruamel.yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "evaluate-extraction.py"


def _yaml_load(path: Path) -> dict[str, Any]:
    yaml = ruamel.yaml.YAML(typ="safe")
    data = yaml.load(path.read_text())
    assert isinstance(data, dict)
    return data


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("evaluate_extraction_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_evaluate_extraction_writes_eval_results_artifact(tmp_path: Path):
    output_path = tmp_path / "eval-results.yaml"
    keep_output = tmp_path / "outputs"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--fixture",
            "cloudformation-parameters-handoff",
            "--keep-output",
            str(keep_output),
            "--output",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert f"Eval results: {output_path}" in result.stdout
    data = _yaml_load(output_path)
    assert data["schemaVersion"] == "intent-engine/eval-results/v1"
    assert data["mode"] == "deterministic"
    assert data["summary"] == {"caseCount": 1, "passed": 1, "failed": 0, "status": "pass"}
    assert data["cases"][0]["name"] == "cloudformation-parameters-handoff"
    assert data["cases"][0]["status"] == "pass"
    assert data["cases"][0]["outputDir"] == str(keep_output / "cloudformation-parameters-handoff")


def test_evaluate_extraction_flags_forbidden_artifacts(tmp_path: Path):
    script = _load_script()
    (tmp_path / "main.tf").write_text("resource null_resource example {}\n")

    failures = script._compare_forbidden_artifacts(tmp_path, ["main.tf", "template.yaml"])

    assert failures == ["forbidden artifact present: main.tf"]
