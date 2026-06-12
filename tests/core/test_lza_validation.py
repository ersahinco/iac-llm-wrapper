from __future__ import annotations

import os
from pathlib import Path

import ruamel.yaml
from typer.testing import CliRunner

from intent_engine.cli import app
from intent_engine.core.lza_validation import validate_lza_config_bundle
from intent_engine.patterns.aws_lza.contracts import AWS_LZA_CONFIG_ARTIFACTS

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


def _fake_yarn(path: Path, *, exit_code: int = 0) -> Path:
    bin_dir = path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "yarn"
    executable.write_text(
        "#!/bin/sh\n"
        'echo "fake validate: $@"\n'
        'case "$*" in\n'
        "  validate-config*) ;;\n"
        '  *) echo "unexpected command" >&2; exit 9 ;;\n'
        "esac\n"
        f"exit {exit_code}\n"
    )
    executable.chmod(0o755)
    return bin_dir


def _read_yaml(path: Path) -> dict:
    yaml = ruamel.yaml.YAML(typ="safe")
    return yaml.load(path.read_text())


def test_validate_lza_config_bundle_writes_validation_only_evidence(
    tmp_path: Path,
    monkeypatch,
):
    bundle = _bundle(tmp_path / "bundle")
    source = _lza_source(tmp_path / "lza")
    bin_dir = _fake_yarn(tmp_path)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    evidence = validate_lza_config_bundle(bundle_dir=bundle, lza_source=source)

    evidence_path = bundle / "lza-validation-evidence.yaml"
    assert evidence_path.exists()
    assert evidence["status"] == "pass"
    assert evidence["boundary"]["mode"] == "validation-only"
    assert evidence["boundary"]["noDeploy"] is True
    assert evidence["boundary"]["noAwsMutation"] is True
    assert evidence["command"]["argv"][0:2] == ["yarn", "validate-config"]
    assert evidence["command"]["exitCode"] == 0
    assert evidence["lzaSource"]["packageVersion"] == "1.2.3"
    assert _read_yaml(evidence_path)["schemaVersion"].endswith("aws-lza-validation-evidence/v1")


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
    evidence = _read_yaml(bundle / "lza-validation-evidence.yaml")
    assert evidence["status"] == "fail"
    assert evidence["command"]["exitCode"] == 7


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
