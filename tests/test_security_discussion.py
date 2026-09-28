"""Scanner warnings stay actionable; exceptions never erase coverage limitations."""

import json
import subprocess

import pytest
from typer.testing import CliRunner

from intent_engine import scan
from intent_engine.cli import app
from intent_engine.scan import _parse_checkov, _parse_trivy


def test_checkov_retains_scoped_exception_reason():
    findings, assessed, exceptions = _parse_checkov(
        {
            "summary": {"passed": 1, "failed": 0, "skipped": 1, "parsing_errors": 0},
            "results": {
                "skipped_checks": [
                    {
                        "file_path": "/main.tf",
                        "resource": "aws_s3_bucket.public_assets",
                        "check_id": "CKV_AWS_18",
                        "check_result": {
                            "result": "SKIPPED",
                            "suppress_comment": "ARCH-42 approved exception",
                        },
                    }
                ]
            },
        }
    )
    assert findings == []
    assert assessed == 1
    assert exceptions == [
        "/main.tf: CKV_AWS_18 aws_s3_bucket.public_assets — ARCH-42 approved exception"
    ]


def test_trivy_retains_inline_and_ignorefile_exceptions():
    findings, assessed, exceptions = _parse_trivy(
        {
            "SchemaVersion": 2,
            "ArtifactType": "filesystem",
            "ArtifactName": "/iac",
            "Results": [
                {
                    "Target": "main.tf",
                    "MisconfSummary": {"Successes": 1, "Failures": 0},
                    "Misconfigurations": [
                        {"ID": "AWS-0089", "Status": "EXCEPTION", "Title": "Logging"}
                    ],
                    "ExperimentalModifiedFindings": [
                        {
                            "Type": "misconfiguration",
                            "Status": "ignored",
                            "Statement": "ARCH-42 accepted for test",
                            "Source": ".trivyignore.yaml",
                            "Finding": {"ID": "AWS-0090"},
                        }
                    ],
                }
            ],
        }
    )
    assert findings == []
    assert assessed == 1
    assert len(exceptions) == 2
    assert "ARCH-42" in exceptions[1]


def test_exceptions_alone_are_not_assessed():
    result = scan._result("checkov", [], 0, exceptions=["accepted exception"])
    assert result.status == "not-assessed"
    assert result.exceptions == ["accepted exception"]
    assert result.blocking


@pytest.mark.parametrize("strict,exit_code", [(False, 0), (True, 1)])
def test_security_warnings_are_advisory_unless_strict(monkeypatch, tmp_path, strict, exit_code):
    monkeypatch.setattr(
        "intent_engine.cli.scan_bundle",
        lambda *args: [
            scan.ToolResult(
                "checkov",
                "findings",
                "one assessed warning",
                ["main.tf: missing encryption"],
                ["main.tf: ARCH-42 recorded exception"],
            ),
        ],
    )
    command = ["scan", str(tmp_path)] + (["--strict"] if strict else [])
    result = CliRunner().invoke(app, command)
    assert result.exit_code == exit_code
    assert "checkov: warning" in result.stdout
    assert "missing encryption" in result.stdout
    assert "exception (still review)" in result.stdout


def test_schema_errors_are_not_softened_to_security_warnings(monkeypatch, tmp_path):
    assert "schema error(s)" in scan._result("lza-schema", ["missing field"]).detail
    monkeypatch.setattr(
        "intent_engine.cli.scan_bundle",
        lambda *args: [
            scan.ToolResult("lza-schema", "findings", "invalid shape", ["missing field"]),
        ],
    )
    assert CliRunner().invoke(app, ["scan", str(tmp_path)]).exit_code == 1


def test_iac_scan_uses_native_scanners_without_requiring_lza_files(monkeypatch, tmp_path):
    monkeypatch.setattr(scan, "run_checkov", lambda path: scan.ToolResult("checkov", "passed"))
    monkeypatch.setattr(scan, "run_trivy", lambda path: scan.ToolResult("trivy", "passed"))
    assert [r.tool for r in scan.scan_bundle(tmp_path)] == ["checkov", "trivy"]
    with pytest.raises(scan.ScanError, match="expects an LZA bundle"):
        scan.scan_bundle(tmp_path, tmp_path / "custom.rego")
    (tmp_path / "network-config.yaml").write_text("{}")
    with pytest.raises(scan.ScanError, match="expected bundle file"):
        scan.scan_bundle(tmp_path)


def test_native_scan_arguments_and_exception_file(monkeypatch, tmp_path):
    commands = []
    monkeypatch.setattr(scan.shutil, "which", lambda _: "/scanner")
    (tmp_path / ".trivyignore.yaml").write_text("misconfigurations: []")

    def run(command):
        commands.append(command)
        report = {"SchemaVersion": 2, "ArtifactType": "filesystem", "ArtifactName": "/iac"}
        return subprocess.CompletedProcess(command, 0, json.dumps(report), "")

    monkeypatch.setattr(scan, "_run", run)
    scan.run_trivy(tmp_path)
    command = commands[0]
    assert "--include-non-failures" in command
    assert "--show-suppressed" in command
    assert command[command.index("--ignorefile") + 1] == str(tmp_path / ".trivyignore.yaml")


@pytest.mark.parametrize(
    "payload",
    [
        {"summary": {"passed": 0, "failed": 0, "skipped": 1, "parsing_errors": 0}},
        {
            "summary": {"passed": 0, "failed": 0, "parsing_errors": 0},
            "results": {"skipped_checks": [{"check_id": "CKV_1"}]},
        },
    ],
)
def test_malformed_exception_report_is_not_a_pass(payload):
    with pytest.raises(scan.ScanError):
        _parse_checkov(payload)
