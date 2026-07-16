"""Focused tests for usability-evaluation evidence checks."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from intent_engine.core.yaml_utils import write_yaml_artifact

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "evaluate-usability.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("evaluate_usability_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_regulated_vpc_checkov_evidence_accepts_owner_boundary(tmp_path: Path):
    script = _load_script()
    evidence_path = tmp_path / "shift-left-evidence.yaml"
    write_yaml_artifact(
        evidence_path,
        {
            "boundary": "This evidence does not deploy owner infrastructure.",
            "input": {
                "iacKind": "terraform",
                "policyPacks": [{"name": "regulated-vpc-baseline-v1"}],
                "ownerPolicyPaths": ["owner/checks"],
            },
            "result": {"status": "pass"},
        },
        "",
    )

    assert script._regulated_vpc_checkov_failures(evidence_path) == []


def test_regulated_vpc_checkov_evidence_rejects_missing_or_unsafe_evidence(tmp_path: Path):
    script = _load_script()
    missing_path = tmp_path / "missing.yaml"
    assert script._regulated_vpc_checkov_failures(missing_path) == [
        "missing Checkov shift-left evidence"
    ]

    evidence_path = tmp_path / "shift-left-evidence.yaml"
    write_yaml_artifact(
        evidence_path,
        {
            "boundary": "Runs terraform apply",
            "input": {"iacKind": "terraform", "policyPacks": [], "ownerPolicyPaths": []},
            "result": {"status": "invalid-input"},
        },
        "",
    )

    failures = script._regulated_vpc_checkov_failures(evidence_path)
    assert "Checkov evidence scanned an invalid input" in failures
    assert "Checkov evidence missing no-deploy boundary" in failures
    assert "Checkov evidence missing regulated VPC policy pack" in failures
    assert "Checkov evidence missing owner custom-policy path" in failures
    assert "Checkov evidence includes forbidden command: terraform apply" in failures
