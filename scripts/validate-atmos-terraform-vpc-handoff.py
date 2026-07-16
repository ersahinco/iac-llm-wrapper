"""Validate the generated Terraform VPC handoff with pinned Atmos and Terraform."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from intent_engine.core.compiler import compile_from_interview
from intent_engine.core.yaml_utils import load_bundle_yaml_mapping, write_yaml_artifact
from intent_engine.patterns.terraform_vpc.atmos import ATMOS_VERSION
from intent_engine.patterns.terraform_vpc.target import (
    MODULE_TREE_SHA256,
    TERRAFORM_VERSION,
    installed_module_tree_digest,
)

_DECISIONS = {
    "vpc_name": "atmos-contract-vpc",
    "primary_region": "eu-central-1",
    "cidr": "10.30.0.0/16",
    "az_count": "2",
    "public_subnet_cidrs": "10.30.0.0/24,10.30.1.0/24",
    "private_subnet_cidrs": "10.30.10.0/24,10.30.11.0/24",
    "enable_nat_gateway": "true",
    "single_nat_gateway": "false",
    "enable_dns_hostnames": "true",
    "target_account_id": "111122223333",
    "deployment_pipeline_ref": "github://owner/networking",
}
_COMPONENT = "terraform-vpc-contract"
_STACK = "test"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--atmos-command", default="atmos")
    parser.add_argument("--terraform-command", default="terraform")
    args = parser.parse_args()
    validate_handoff(args.atmos_command, args.terraform_command)
    print("Atmos Terraform VPC handoff: schema, provenance, init, and validate passed")


def validate_handoff(atmos_command: str, terraform_command: str) -> None:
    """Compile and validate one credential-free synthetic Atmos handoff."""
    with tempfile.TemporaryDirectory(prefix="intent-engine-atmos-vpc-") as tmp:
        root = Path(tmp)
        bundle = root / "bundle"
        project = root / "project"
        compile_from_interview(_DECISIONS, bundle, pattern="terraform-vpc")
        shutil.copytree(bundle / "atmos", project)
        _write_project_config(project)
        environment = _environment(root, atmos_command, terraform_command)
        _assert_versions(atmos_command, terraform_command, project, environment)
        _run([atmos_command, "validate", "stacks"], project, environment)
        described = _describe(atmos_command, project, environment)
        expected = _expected_variables(bundle)
        if described.get("vars") != expected:
            raise RuntimeError(
                "Atmos resolved variables differ from the compiled module inputs: "
                f"expected {expected!r}, received {described.get('vars')!r}."
            )
        _run(
            [
                atmos_command,
                "describe",
                "component",
                _COMPONENT,
                "-s",
                _STACK,
                "--provenance",
                "--format",
                "json",
            ],
            project,
            environment,
        )
        _run(
            [
                atmos_command,
                "terraform",
                "init",
                _COMPONENT,
                "-s",
                _STACK,
                "-backend=false",
                "-input=false",
                "-lockfile=readonly",
            ],
            project,
            environment,
        )
        component_root = project / "components" / "terraform" / "terraform-vpc"
        if installed_module_tree_digest(component_root) != MODULE_TREE_SHA256:
            raise RuntimeError("Atmos initialized an unapproved Terraform module tree.")
        try:
            _run(
                [
                    atmos_command,
                    "terraform",
                    "validate",
                    _COMPONENT,
                    "-s",
                    _STACK,
                ],
                project,
                environment,
            )
        except RuntimeError as exc:
            diagnostic = subprocess.run(
                [terraform_command, "validate", "-no-color"],
                cwd=component_root,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            output = "\n".join(
                part.strip() for part in (diagnostic.stdout, diagnostic.stderr) if part.strip()
            )
            raise RuntimeError(f"{exc}\nUnderlying Terraform diagnostic:\n{output[:2000]}") from exc
        if list(project.rglob("terraform.tfstate*")):
            raise RuntimeError("Credential-free Atmos validation retained Terraform state.")


def _write_project_config(project: Path) -> None:
    write_yaml_artifact(
        project / "atmos.yaml",
        {
            "base_path": ".",
            "components": {
                "terraform": {
                    "base_path": "components/terraform",
                    "auto_generate_backend_file": False,
                    "workspaces_enabled": False,
                }
            },
            "stacks": {
                "base_path": "stacks",
                "included_paths": ["**/*"],
                "excluded_paths": [],
                "name_pattern": _STACK,
            },
            "settings": {"telemetry": {"enabled": False}},
        },
        "",
    )
    write_yaml_artifact(
        project / "stacks" / f"{_STACK}.yaml",
        {
            "import": ["catalog/terraform-vpc-intent"],
            "components": {
                "terraform": {
                    _COMPONENT: {
                        "metadata": {
                            "component": "terraform-vpc",
                            "inherits": ["terraform-vpc/intent-defaults"],
                        }
                    }
                }
            },
        },
        "",
    )


def _environment(root: Path, atmos_command: str, terraform_command: str) -> dict[str, str]:
    blocked_prefixes = ("AWS_", "ATMOS_", "TF_")
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith(blocked_prefixes)
    }
    tool_dirs = {
        str(Path(command).resolve().parent)
        for command in (atmos_command, terraform_command)
        if Path(command).parent != Path(".")
    }
    path = environment.get("PATH", "")
    if tool_dirs:
        path = os.pathsep.join([*sorted(tool_dirs), path])
    cache = root / "cache"
    config = root / "config"
    data = root / "data"
    home = root / "home"
    for directory in (cache, config, data, home):
        directory.mkdir()
    cli_config = config / "terraform.tfrc"
    cli_config.write_text("disable_checkpoint = true\n")
    environment.update(
        {
            "PATH": path,
            "HOME": str(home),
            "ATMOS_TELEMETRY_ENABLED": "false",
            "ATMOS_VERSION_CHECK_ENABLED": "false",
            "ATMOS_IDENTITY": "false",
            "ATMOS_UPLOAD_STATUS": "false",
            "ATMOS_EXPERIMENTAL": "disable",
            "ATMOS_XDG_CACHE_HOME": str(cache),
            "ATMOS_XDG_CONFIG_HOME": str(config),
            "ATMOS_XDG_DATA_HOME": str(data),
            "CHECKPOINT_DISABLE": "1",
            "TF_IN_AUTOMATION": "1",
            "TF_CLI_CONFIG_FILE": str(cli_config),
        }
    )
    return environment


def _assert_versions(
    atmos_command: str,
    terraform_command: str,
    project: Path,
    environment: dict[str, str],
) -> None:
    atmos = _run([atmos_command, "version"], project, environment)
    if re.search(rf"\b{re.escape(ATMOS_VERSION)}\b", atmos.stdout) is None:
        raise RuntimeError(f"Atmos {ATMOS_VERSION} is required.")
    terraform = _run([terraform_command, "version", "-json"], project, environment)
    try:
        version = json.loads(terraform.stdout)["terraform_version"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError("Terraform returned malformed version JSON.") from exc
    if version != TERRAFORM_VERSION:
        raise RuntimeError(f"Terraform {TERRAFORM_VERSION} is required.")


def _describe(
    atmos_command: str,
    project: Path,
    environment: dict[str, str],
) -> dict[str, Any]:
    result = _run(
        [
            atmos_command,
            "describe",
            "component",
            _COMPONENT,
            "-s",
            _STACK,
            "--format",
            "json",
        ],
        project,
        environment,
    )
    return _decode_component(result.stdout, "Atmos returned malformed component JSON.")


def _decode_component(value: str, message: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(message) from exc
    value = decoded
    if not isinstance(value, dict):
        raise RuntimeError("Atmos component description must be a mapping.")
    return value


def _expected_variables(bundle: Path) -> dict[str, Any]:
    inputs = load_bundle_yaml_mapping(bundle, "module-inputs.yaml")
    modules = inputs.get("moduleInputs")
    if not isinstance(modules, list) or len(modules) != 1 or not isinstance(modules[0], dict):
        raise RuntimeError("Compiled module inputs are malformed.")
    variables = modules[0].get("variables")
    if not isinstance(variables, dict):
        raise RuntimeError("Compiled module variables are malformed.")
    report = load_bundle_yaml_mapping(bundle, "decision-report.yaml")
    vpc = report.get("vpc")
    if not isinstance(vpc, dict) or not isinstance(vpc.get("region"), str):
        raise RuntimeError("Compiled VPC region is malformed.")
    return {"region": vpc["region"], **variables}


def _run(
    argv: list[str],
    cwd: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        raise RuntimeError(f"Command failed ({result.returncode}): {argv[1]}\n{output[-5000:]}")
    return result


if __name__ == "__main__":
    main()
