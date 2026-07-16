"""Checkov shift-left evidence tests."""

from __future__ import annotations

from pathlib import Path

import ruamel.yaml
from typer.testing import CliRunner

from intent_engine.cli import app
from intent_engine.core.checkov_evidence import run_checkov_evidence

runner = CliRunner()


def _yaml_load(path: Path) -> dict:
    yaml = ruamel.yaml.YAML(typ="safe")
    return yaml.load(path.read_text())


def _write_checkov_stub(path: Path, *, output: str, exit_code: int = 0) -> None:
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import sys",
                "if '--version' in sys.argv:",
                "    print('3.2.0')",
                "    raise SystemExit(0)",
                f"print({output!r})",
                f"raise SystemExit({exit_code})",
            ]
        )
        + "\n"
    )
    path.chmod(0o755)


def test_checkov_evidence_handles_tool_unavailable(tmp_path: Path):
    evidence = run_checkov_evidence(
        bundle=tmp_path,
        scan_path=tmp_path,
        checkov_bin="definitely-missing-checkov-for-test",
    )

    assert evidence["result"]["status"] == "tool-unavailable"
    assert evidence["tool"]["available"] is False
    assert "does not deploy" in evidence["boundary"]


def test_shift_left_checkov_records_failed_findings_soft_fail(tmp_path: Path):
    bundle = tmp_path / "bundle"
    scan_path = tmp_path / "owner-module"
    bundle.mkdir()
    scan_path.mkdir()
    checkov = tmp_path / "checkov"
    _write_checkov_stub(
        checkov,
        output=(
            '{"summary":{"passed":1,"failed":1,"skipped":0,"parsing_errors":0,'
            '"resource_count":2},"results":{"failed_checks":[{"check_id":"CKV_AWS_1",'
            '"check_name":"example","file_path":"/main.tf","resource":"aws_s3_bucket.x",'
            '"guideline":"https://example.test"}]}}'
        ),
        exit_code=1,
    )
    evidence_path = bundle / "shift-left-evidence.yaml"

    result = runner.invoke(
        app,
        [
            "shift-left",
            "checkov",
            "--bundle",
            str(bundle),
            "--scan-path",
            str(scan_path),
            "--output",
            str(evidence_path),
            "--checkov-bin",
            str(checkov),
        ],
    )

    assert result.exit_code == 0, result.output
    evidence = _yaml_load(evidence_path)
    assert evidence["result"]["status"] == "fail"
    assert evidence["summary"]["failed"] == 1
    assert evidence["findings"][0]["checkId"] == "CKV_AWS_1"


def test_shift_left_checkov_require_pass_fails_on_findings(tmp_path: Path):
    bundle = tmp_path / "bundle"
    scan_path = tmp_path / "owner-module"
    bundle.mkdir()
    scan_path.mkdir()
    checkov = tmp_path / "checkov"
    _write_checkov_stub(
        checkov,
        output=(
            '{"summary":{"passed":0,"failed":1,"skipped":0,"parsing_errors":0,'
            '"resource_count":1},"results":{"failed_checks":[]}}'
        ),
        exit_code=1,
    )

    result = runner.invoke(
        app,
        [
            "shift-left",
            "checkov",
            "--bundle",
            str(bundle),
            "--scan-path",
            str(scan_path),
            "--checkov-bin",
            str(checkov),
            "--require-pass",
        ],
    )

    assert result.exit_code == 1
    assert (bundle / "shift-left-evidence.yaml").exists()


def test_shift_left_checkov_rejects_tfvars_only_scan(tmp_path: Path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    tfvars = bundle / "terraform.tfvars"
    tfvars.write_text('name = "example"\n')

    result = runner.invoke(
        app,
        [
            "shift-left",
            "checkov",
            "--bundle",
            str(bundle),
            "--scan-path",
            str(tfvars),
        ],
    )

    assert result.exit_code == 1
    evidence = _yaml_load(bundle / "shift-left-evidence.yaml")
    assert evidence["result"]["status"] == "invalid-input"


def test_checkov_evidence_handles_malformed_json(tmp_path: Path):
    bundle = tmp_path / "bundle"
    scan_path = tmp_path / "owner-module"
    bundle.mkdir()
    scan_path.mkdir()
    checkov = tmp_path / "checkov"
    _write_checkov_stub(checkov, output="not json", exit_code=0)

    evidence = run_checkov_evidence(bundle=bundle, scan_path=scan_path, checkov_bin=str(checkov))

    assert evidence["result"]["status"] == "parse-error"
    assert "rawOutput" in evidence


def test_checkov_evidence_uses_file_flag_for_iac_file(tmp_path: Path):
    scan_path = tmp_path / "main.tf"
    scan_path.write_text('resource "aws_vpc" "main" {}\n')
    checkov = tmp_path / "checkov"
    _write_checkov_stub(
        checkov,
        output=(
            '{"summary":{"passed":1,"failed":0,"skipped":0,"parsing_errors":0,'
            '"resource_count":1},"results":{"failed_checks":[]}}'
        ),
    )

    evidence = run_checkov_evidence(
        bundle=tmp_path,
        scan_path=scan_path,
        checkov_bin=str(checkov),
    )

    assert evidence["result"]["status"] == "pass"
    assert evidence["command"]["argv"][1:3] == ["-f", str(scan_path)]


def test_checkov_evidence_fails_on_parsing_errors(tmp_path: Path):
    scan_path = tmp_path / "owner-module"
    scan_path.mkdir()
    checkov = tmp_path / "checkov"
    _write_checkov_stub(
        checkov,
        output=(
            '{"summary":{"passed":0,"failed":0,"skipped":0,"parsing_errors":1,'
            '"resource_count":0},"results":{"failed_checks":[]}}'
        ),
    )

    evidence = run_checkov_evidence(
        bundle=tmp_path,
        scan_path=scan_path,
        checkov_bin=str(checkov),
    )

    assert evidence["result"]["status"] == "fail"
    assert evidence["summary"]["parsingErrors"] == 1


def test_checkov_evidence_rejects_structurally_invalid_json(tmp_path: Path):
    scan_path = tmp_path / "owner-module"
    scan_path.mkdir()
    checkov = tmp_path / "checkov"
    _write_checkov_stub(checkov, output="{}")

    evidence = run_checkov_evidence(
        bundle=tmp_path,
        scan_path=scan_path,
        checkov_bin=str(checkov),
    )

    assert evidence["result"]["status"] == "invalid-output"
    assert "rawOutput" in evidence


def test_checkov_evidence_rejects_incomplete_summary(tmp_path: Path):
    scan_path = tmp_path / "owner-module"
    scan_path.mkdir()
    checkov = tmp_path / "checkov"
    _write_checkov_stub(
        checkov,
        output='{"summary":{"passed":1,"failed":0},"results":{"failed_checks":[]}}',
    )

    evidence = run_checkov_evidence(
        bundle=tmp_path,
        scan_path=scan_path,
        checkov_bin=str(checkov),
    )

    assert evidence["result"]["status"] == "invalid-output"


def test_shift_left_checkov_maps_registered_policy_pack_and_owner_checks(tmp_path: Path):
    bundle = tmp_path / "bundle"
    scan_path = tmp_path / "owner-module"
    custom_checks = tmp_path / "custom-checks"
    bundle.mkdir()
    scan_path.mkdir()
    custom_checks.mkdir()
    (bundle / "decision-report.yaml").write_text("pattern: terraform-vpc\n")
    checkov = tmp_path / "checkov"
    _write_checkov_stub(
        checkov,
        output=(
            '{"summary":{"passed":0,"failed":2,"skipped":0,"parsing_errors":0,'
            '"resource_count":2},"results":{"failed_checks":['
            '{"check_id":"CKV_CUSTOM_VPC_001","check_name":"CIDR policy",'
            '"file_path":"/main.tf","resource":"module.vpc"},'
            '{"check_id":"CKV_OTHER","check_name":"Other policy",'
            '"file_path":"/main.tf","resource":"module.other"}]}}'
        ),
        exit_code=1,
    )

    result = runner.invoke(
        app,
        [
            "shift-left",
            "checkov",
            "--bundle",
            str(bundle),
            "--scan-path",
            str(scan_path),
            "--policy-pack",
            "regulated-vpc-baseline-v1",
            "--external-checks-dir",
            str(custom_checks),
            "--iac-kind",
            "terraform",
            "--checkov-framework",
            "terraform",
            "--checkov-bin",
            str(checkov),
        ],
    )

    assert result.exit_code == 0, result.output
    evidence = _yaml_load(bundle / "shift-left-evidence.yaml")
    assert evidence["input"]["iacKind"] == "terraform"
    assert evidence["input"]["policyPacks"][0]["name"] == "regulated-vpc-baseline-v1"
    assert evidence["input"]["ownerPolicyPaths"] == [str(custom_checks)]
    assert "--external-checks-dir" in evidence["command"]["argv"]
    assert "--framework" in evidence["command"]["argv"]
    assert evidence["mappedControls"][0]["controlId"] == "VPC-NETWORK-001"
    assert evidence["unmappedFindings"][0]["checkId"] == "CKV_OTHER"
