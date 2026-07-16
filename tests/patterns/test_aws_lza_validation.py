from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
import ruamel.yaml
from typer.testing import CliRunner

from intent_engine.cli import app
from intent_engine.patterns.aws_lza.contracts import AWS_LZA_CONFIG_ARTIFACTS
from intent_engine.patterns.aws_lza.validation import (
    LZA_VALIDATION_EVIDENCE,
    LzaValidationError,
    summarize_lza_validation_output,
    validate_lza_config_bundle,
)

runner = CliRunner()


def _bundle(path: Path) -> Path:
    path.mkdir()
    for name in AWS_LZA_CONFIG_ARTIFACTS:
        (path / name).write_text(f"{name.replace('-', '_').removesuffix('.yaml')}: true\n")
    return path


def _lza_source(path: Path) -> Path:
    source = path / "source"
    source.mkdir(parents=True)
    (source / "package.json").write_text('{"version":"1.2.3"}\n')
    return path


def _fake_yarn(path: Path, *, exit_code: int = 0, output: str | None = None) -> Path:
    bin_dir = path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "yarn"
    line = output or "fake validate: $@"
    executable.write_text(f"#!/bin/sh\nprintf '%s\\n' '{line}'\nexit {exit_code}\n")
    executable.chmod(0o755)
    return bin_dir


def _fake_corepack(path: Path) -> Path:
    bin_dir = path / "corepack-bin"
    bin_dir.mkdir()
    executable = bin_dir / "corepack"
    executable.write_text('#!/bin/sh\nshift\necho "fake corepack yarn: $@"\n')
    executable.chmod(0o755)
    return bin_dir


def _read_yaml(path: Path) -> dict:
    yaml = ruamel.yaml.YAML(typ="safe")
    return yaml.load(path.read_text())


@pytest.mark.parametrize(
    ("exit_code", "stdout", "stderr", "category"),
    [
        (127, "", "yarn/corepack executable not found", "local-toolchain-missing"),
        (1, "Default email missing for Audit account", "", "owner-account-email-required"),
        (1, "network-config.yaml has 2 issues:", "", "schema-or-config-validation"),
        (9, "unexpected validator failure", "", "validator-failed"),
    ],
)
def test_summarize_lza_validation_output_classifies_common_blockers(
    exit_code: int,
    stdout: str,
    stderr: str,
    category: str,
):
    diagnostic = summarize_lza_validation_output(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
    )

    assert diagnostic["category"] == category
    assert diagnostic["summary"]
    assert diagnostic["nextAction"]


def test_summarize_lza_validation_output_prioritizes_default_email():
    diagnostic = summarize_lza_validation_output(
        exit_code=1,
        stdout=(
            "AccessDeniedException: account lookup permission denied in "
            "accounts-config.yaml config file\n"
            "accounts-config.yaml has 1 issues:\n"
            "Default email (audit@example.com) found."
        ),
        stderr="",
    )

    assert diagnostic["category"] == "owner-account-email-required"
    assert diagnostic["summary"] == "Default email (audit@example.com) found."


def test_validate_lza_config_bundle_rejects_symlinked_config(tmp_path: Path):
    bundle = _bundle(tmp_path / "bundle")
    config = bundle / AWS_LZA_CONFIG_ARTIFACTS[0]
    outside = tmp_path / "outside.yaml"
    config.replace(outside)
    config.symlink_to(outside)

    with pytest.raises(LzaValidationError, match="must not be a symlink"):
        validate_lza_config_bundle(bundle_dir=bundle, lza_source=tmp_path / "lza")


def test_validate_lza_config_bundle_writes_validation_only_evidence(
    tmp_path: Path,
    monkeypatch,
):
    bundle = _bundle(tmp_path / "bundle")
    source = _lza_source(tmp_path / "lza")
    bin_dir = _fake_yarn(tmp_path)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    evidence = validate_lza_config_bundle(bundle_dir=bundle, lza_source=source)

    evidence_path = bundle / LZA_VALIDATION_EVIDENCE
    assert evidence_path.exists()
    assert evidence["status"] == "pass"
    assert evidence["boundary"]["mode"] == "validation-only"
    assert evidence["boundary"]["noDeploy"] is True
    assert evidence["boundary"]["noAwsMutation"] is True
    assert evidence["boundary"]["readOnlyAwsAccountLookupMayOccur"] is True
    assert "read-only account lookup" in evidence["boundary"]["awsAccountLookupBoundary"]
    assert evidence["input"]["stagedConfigRetained"] is False
    assert "temporary copy is removed" in evidence["input"]["stagingBoundary"]
    assert evidence["command"]["replayable"] is False
    assert "source bundle to reproduce" in evidence["command"]["replayBoundary"]
    assert evidence["command"]["argv"][0:2] == ["yarn", "validate-config"]
    assert evidence["command"]["exitCode"] == 0
    assert evidence["lzaSource"]["packageVersion"] == "1.2.3"
    assert evidence["diagnostic"]["category"] == "passed"
    digests = {item["name"]: item["sha256"] for item in evidence["input"]["configFileDigests"]}
    assert set(digests) == set(AWS_LZA_CONFIG_ARTIFACTS)
    assert (
        digests["network-config.yaml"]
        == hashlib.sha256((bundle / "network-config.yaml").read_bytes()).hexdigest()
    )
    assert _read_yaml(evidence_path)["schemaVersion"].endswith("aws-lza-validation-evidence/v1")


def test_validate_lza_config_bundle_uses_corepack_when_yarn_is_missing(
    tmp_path: Path,
    monkeypatch,
):
    bundle = _bundle(tmp_path / "bundle")
    source = _lza_source(tmp_path / "lza")
    bin_dir = _fake_corepack(tmp_path)
    monkeypatch.setenv("PATH", str(bin_dir))

    evidence = validate_lza_config_bundle(bundle_dir=bundle, lza_source=source)

    assert evidence["status"] == "pass"
    assert evidence["command"]["argv"][0:3] == ["corepack", "yarn", "validate-config"]
    assert "fake corepack yarn" in evidence["command"]["stdout"]


def test_validate_lza_config_bundle_records_failed_validator(
    tmp_path: Path,
    monkeypatch,
):
    bundle = _bundle(tmp_path / "bundle")
    source = _lza_source(tmp_path / "lza")
    bin_dir = _fake_yarn(tmp_path, exit_code=7)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    result = runner.invoke(
        app,
        ["lza", "validate", "--bundle", str(bundle), "--lza-source", str(source)],
    )

    assert result.exit_code == 1
    assert "AWS LZA config validation failed." in result.output
    assert "Diagnostic: validator-failed" in result.output
    evidence = _read_yaml(bundle / LZA_VALIDATION_EVIDENCE)
    assert evidence["status"] == "fail"
    assert evidence["command"]["exitCode"] == 7
    assert evidence["diagnostic"]["category"] == "validator-failed"


def test_validate_lza_config_bundle_classifies_account_lookup_permission_failure(
    tmp_path: Path,
    monkeypatch,
):
    bundle = _bundle(tmp_path / "bundle")
    source = _lza_source(tmp_path / "lza")
    bin_dir = _fake_yarn(
        tmp_path,
        exit_code=1,
        output=(
            "AccessDeniedException: account lookup permission denied in "
            "accounts-config.yaml config file"
        ),
    )
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    with pytest.raises(LzaValidationError) as exc:
        validate_lza_config_bundle(bundle_dir=bundle, lza_source=source)

    evidence = exc.value.evidence
    assert evidence is not None
    assert evidence["diagnostic"] == {
        "category": "aws-account-lookup-permission",
        "summary": (
            "AccessDeniedException: account lookup permission denied in "
            "accounts-config.yaml config file"
        ),
        "nextAction": (
            "Run with an AWS/LZA validation context that can perform the official "
            "account lookup, or send this failure to the downstream owner."
        ),
    }
    assert _read_yaml(bundle / LZA_VALIDATION_EVIDENCE)["diagnostic"] == evidence["diagnostic"]


def test_lza_validate_cli_passes_with_fake_validator(tmp_path: Path, monkeypatch):
    bundle = _bundle(tmp_path / "bundle")
    source = _lza_source(tmp_path / "lza")
    bin_dir = _fake_yarn(tmp_path)
    output = tmp_path / "evidence.yaml"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    result = runner.invoke(
        app,
        [
            "lza",
            "validate",
            "--bundle",
            str(bundle),
            "--lza-source",
            str(source),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "AWS LZA config validation passed." in result.output
    assert output.exists()
