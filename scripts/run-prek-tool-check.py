"""Run optional native tools from prek hooks.

The repository's default hooks should stay useful on a fresh workstation. These
wrappers skip missing external tools by default and fail when
PREK_REQUIRE_EXTERNAL_TOOLS=1 is set by a stricter local or CI environment.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]

FileMode = Literal["args", "none", "terraform-dirs", "terraform-docs-dirs"]


@dataclass(frozen=True)
class ToolCheck:
    executable: str
    args: tuple[str, ...]
    alternatives: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()
    mode: FileMode = "args"
    config_files: tuple[str, ...] = ()


CHECKS: dict[str, ToolCheck] = {
    "actionlint": ToolCheck(
        executable="actionlint",
        args=(),
        patterns=(r"^\.github/workflows/.*\.ya?ml$",),
    ),
    "commitlint": ToolCheck(
        executable="commitlint",
        args=("--edit",),
        config_files=(
            ".commitlintrc",
            ".commitlintrc.json",
            ".commitlintrc.yaml",
            ".commitlintrc.yml",
            ".commitlintrc.js",
            ".commitlintrc.cjs",
            "commitlint.config.js",
            "commitlint.config.cjs",
            "commitlint.config.mjs",
        ),
    ),
    "shellcheck": ToolCheck(
        executable="shellcheck",
        args=(),
        patterns=(r"\.(bash|bats|sh)$",),
    ),
    "shfmt": ToolCheck(
        executable="shfmt",
        args=("-w",),
        patterns=(r"\.(bash|bats|sh)$",),
    ),
    "hadolint": ToolCheck(
        executable="hadolint",
        args=(),
        patterns=(r"(^|/)Dockerfile[^/]*$", r"\.dockerfile$"),
    ),
    "markdownlint": ToolCheck(
        executable="markdownlint-cli2",
        alternatives=("markdownlint",),
        args=(),
        patterns=(r"\.md$",),
    ),
    "typos": ToolCheck(
        executable="typos",
        args=("--format", "brief"),
        patterns=(r"\.(hcl|json|md|py|sh|tf|tfvars|toml|txt|ya?ml)$",),
    ),
    "terraform-fmt": ToolCheck(
        executable="terraform",
        args=("fmt", "-check"),
        patterns=(r"\.(hcl|tf|tfvars)$",),
    ),
    "opentofu-fmt": ToolCheck(
        executable="tofu",
        args=("fmt", "-check"),
        patterns=(r"\.(hcl|tf|tfvars)$",),
    ),
    "terraform-validate": ToolCheck(
        executable="terraform",
        args=("validate",),
        patterns=(r"\.tf$",),
        mode="terraform-dirs",
    ),
    "opentofu-validate": ToolCheck(
        executable="tofu",
        args=("validate",),
        patterns=(r"\.tf$",),
        mode="terraform-dirs",
    ),
    "terraform-docs": ToolCheck(
        executable="terraform-docs",
        args=("markdown", "table", "--output-check"),
        patterns=(r"\.tf$",),
        mode="terraform-docs-dirs",
    ),
    "tflint": ToolCheck(
        executable="tflint",
        args=("--recursive", "--minimum-failure-severity=error"),
        patterns=(r"\.tf$",),
        mode="none",
    ),
    "tfupdate": ToolCheck(
        executable="tfupdate",
        args=("--version",),
        patterns=(r"\.tf$",),
        mode="none",
    ),
    "checkov": ToolCheck(
        executable="checkov",
        args=("-d", ".", "--quiet", "--skip-path", "fixtures", "--skip-path", "tests/results"),
        mode="none",
    ),
    "trivy-fs": ToolCheck(
        executable="trivy",
        args=("fs", "--quiet", "--scanners", "vuln,secret,config", "."),
        mode="none",
    ),
    "grype-fs": ToolCheck(
        executable="grype",
        args=("dir:.",),
        mode="none",
    ),
    "gitleaks": ToolCheck(
        executable="gitleaks",
        args=("detect", "--source", ".", "--redact", "--no-banner"),
        mode="none",
    ),
    "deepfence-secretscanner": ToolCheck(
        executable="SecretScanner",
        args=("-path", ".", "-mask"),
        mode="none",
    ),
    "owasp-dependency-check": ToolCheck(
        executable="dependency-check",
        args=("--scan", ".", "--format", "JSON", "--out", "tests/results/dependency-check"),
        mode="none",
    ),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check", choices=sorted(CHECKS))
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)

    check = CHECKS[args.check]
    if check.config_files and not any(
        (ROOT / config_file).exists() for config_file in check.config_files
    ):
        print(f"{args.check}: no config file found")
        return 0

    executable = _resolve_executable(check)
    if executable is None:
        return _handle_missing_tool((check.executable, *check.alternatives))

    files = _matching_files(args.files, check.patterns)
    if check.patterns and not files:
        print(f"{args.check}: no matching files")
        return 0

    if check.mode == "args":
        return _run((executable, *check.args, *files), args.check)
    if check.mode == "none":
        return _run((executable, *check.args), args.check)
    if check.mode == "terraform-dirs":
        return _run_for_dirs(executable, check.args, _terraform_dirs(files), args.check)
    if check.mode == "terraform-docs-dirs":
        return _run_for_dirs(executable, check.args, _terraform_docs_dirs(files), args.check)

    raise AssertionError(f"unsupported check mode: {check.mode}")


def _resolve_executable(check: ToolCheck) -> str | None:
    for executable in (check.executable, *check.alternatives):
        resolved = shutil.which(executable)
        if resolved:
            return resolved
    return None


def _handle_missing_tool(executables: tuple[str, ...]) -> int:
    names = " or ".join(repr(executable) for executable in executables)
    message = f"{names} is not installed; skipping optional external prek hook"
    if os.environ.get("PREK_REQUIRE_EXTERNAL_TOOLS") == "1":
        print(message, file=sys.stderr)
        return 1
    print(message)
    return 0


def _matching_files(files: list[str], patterns: tuple[str, ...]) -> list[str]:
    if not patterns:
        return files
    compiled = [re.compile(pattern, flags=re.IGNORECASE) for pattern in patterns]
    return [file for file in files if any(pattern.search(file) for pattern in compiled)]


def _terraform_dirs(files: list[str]) -> list[Path]:
    dirs = {Path(file).parent for file in files if Path(file).suffix == ".tf"}
    return sorted(dirs)


def _terraform_docs_dirs(files: list[str]) -> list[Path]:
    dirs = []
    for directory in _terraform_dirs(files):
        if (directory / ".terraform-docs.yml").exists() or (
            directory / ".terraform-docs.yaml"
        ).exists():
            dirs.append(directory)
        else:
            print(f"terraform-docs: skipping {directory}; no .terraform-docs config")
    return dirs


def _run_for_dirs(executable: str, base_args: tuple[str, ...], dirs: list[Path], name: str) -> int:
    if not dirs:
        print(f"{name}: no Terraform module directories")
        return 0

    exit_code = 0
    for directory in dirs:
        if name.endswith("validate"):
            if _requires_terraform_init(directory) and not (directory / ".terraform").exists():
                print(f"{name}: skipping {directory}; run terraform init first")
                continue
            command = (executable, f"-chdir={directory}", *base_args)
        else:
            command = (executable, *base_args, str(directory))
        exit_code = max(exit_code, _run(command, name))
    return exit_code


def _requires_terraform_init(directory: Path) -> bool:
    for path in directory.glob("*.tf"):
        try:
            if re.search(r'^\s*module\s+"[^"]+"\s*\{', path.read_text(), flags=re.MULTILINE):
                return True
        except OSError:
            continue
    return False


def _run(command: tuple[str, ...], name: str) -> int:
    print(f"{name}: {' '.join(command)}")
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
