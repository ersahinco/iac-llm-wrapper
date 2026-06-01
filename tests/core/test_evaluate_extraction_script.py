"""Extraction eval script artifact tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import ruamel.yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "evaluate-extraction.py"


def _yaml_load(path: Path) -> dict[str, Any]:
    yaml = ruamel.yaml.YAML(typ="safe")
    data = yaml.load(path.read_text())
    assert isinstance(data, dict)
    return data


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
