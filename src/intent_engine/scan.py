"""Policy and security checks over an emitted bundle.

Three external tools, three separate verdicts:

    opa      the landing-zone policy the organization agreed to
    checkov  misconfiguration and secret checks on the emitted files
    trivy    independent secret and misconfiguration scan

A missing tool, a tool that failed to run, and a tool that found something are
three different results. None of them is silently treated as a pass.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from ruamel.yaml import YAML, YAMLError

ToolStatus = Literal["passed", "findings", "not-installed", "error"]

_BUNDLE_INPUTS = {
    "organization": "organization-config.yaml",
    "accounts": "accounts-config.yaml",
    "global": "global-config.yaml",
    "iam": "iam-config.yaml",
    "network": "network-config.yaml",
    "security": "security-config.yaml",
}
_TIMEOUT = 300


class ScanError(Exception):
    """The bundle could not be prepared for scanning."""


@dataclass
class ToolResult:
    tool: str
    status: ToolStatus
    detail: str = ""
    findings: list[str] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        return self.status in {"findings", "error"}


def bundle_input(bundle_dir: Path) -> dict[str, Any]:
    """Merge the emitted config files into a single OPA input document."""
    yaml = YAML(typ="safe")
    document: dict[str, Any] = {}
    for key, name in _BUNDLE_INPUTS.items():
        path = bundle_dir / name
        if not path.is_file():
            raise ScanError(f"{path}: expected bundle file is missing")
        try:
            loaded = yaml.load(path.read_text("utf-8"))
        except (YAMLError, OSError) as exc:
            raise ScanError(f"{path}: could not be read as YAML: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ScanError(f"{path}: expected a YAML mapping")
        document[key] = loaded
    return document


def default_policy() -> Path:
    return Path(str(resources.files("intent_engine").joinpath("policy/lza.rego")))


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argument list, no shell
        command, capture_output=True, text=True, timeout=_TIMEOUT, check=False
    )


def run_opa(bundle_dir: Path, policy: Path | None = None) -> ToolResult:
    if shutil.which("opa") is None:
        return ToolResult("opa", "not-installed", "opa is not on PATH")
    policy_path = policy or default_policy()
    if not policy_path.is_file():
        return ToolResult("opa", "error", f"{policy_path}: policy file not found")

    document = bundle_input(bundle_dir)
    with tempfile.TemporaryDirectory() as workspace:
        input_path = Path(workspace) / "input.json"
        input_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
        completed = _run(
            [
                "opa",
                "eval",
                "--format",
                "json",
                "--data",
                str(policy_path),
                "--input",
                str(input_path),
                "data.lza.deny",
            ]
        )

    if completed.returncode != 0:
        return ToolResult("opa", "error", completed.stderr.strip() or "opa eval failed")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return ToolResult("opa", "error", "opa returned output that is not JSON")
    try:
        return _result("opa", _parse_opa(payload))
    except ScanError as exc:
        return ToolResult("opa", "error", str(exc))


def _parse_opa(payload: Any) -> list[str]:
    """Read the deny set.

    An undefined rule and an empty deny set look alike in a summary and are not
    the same thing: one means the policy said nothing was wrong, the other means
    no policy ran. Only the second is silent, so only the second is an error.
    """
    results = payload.get("result") if isinstance(payload, dict) else None
    if not results:
        raise ScanError(
            "data.lza.deny is undefined: no rule by that name loaded from the policy. "
            "An undefined policy is not a passing policy."
        )
    expressions = results[0].get("expressions") or []
    value = expressions[0].get("value") if expressions else None
    if not isinstance(value, list):
        raise ScanError(
            f"data.lza.deny evaluated to {type(value).__name__}, expected a set of messages"
        )
    return sorted(str(item) for item in value)


def run_checkov(bundle_dir: Path) -> ToolResult:
    if shutil.which("checkov") is None:
        return ToolResult("checkov", "not-installed", "checkov is not on PATH")
    completed = _run(
        [
            "checkov",
            "--directory",
            str(bundle_dir),
            "--framework",
            "secrets",
            "--output",
            "json",
            "--quiet",
            "--compact",
        ]
    )
    if not completed.stdout.strip():
        detail = completed.stderr.strip() or "checkov produced no output"
        return ToolResult("checkov", "error", detail)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return ToolResult("checkov", "error", "checkov returned output that is not JSON")
    return _result("checkov", _parse_checkov(payload))


def _parse_checkov(payload: Any) -> list[str]:
    reports = payload if isinstance(payload, list) else [payload]
    findings: list[str] = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        failed = (report.get("results") or {}).get("failed_checks") or []
        for check in failed:
            findings.append(
                f"{check.get('file_path', '?')}: {check.get('check_id', '?')} "
                f"{check.get('check_name', '')}".strip()
            )
    return sorted(findings)


def run_trivy(bundle_dir: Path) -> ToolResult:
    if shutil.which("trivy") is None:
        return ToolResult("trivy", "not-installed", "trivy is not on PATH")
    completed = _run(
        [
            "trivy",
            "fs",
            "--scanners",
            "secret,misconfig",
            "--format",
            "json",
            "--quiet",
            str(bundle_dir),
        ]
    )
    if completed.returncode != 0 and not completed.stdout.strip():
        return ToolResult("trivy", "error", completed.stderr.strip() or "trivy failed")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return ToolResult("trivy", "error", "trivy returned output that is not JSON")
    return _result("trivy", _parse_trivy(payload))


def _parse_trivy(payload: Any) -> list[str]:
    results = payload.get("Results") if isinstance(payload, dict) else None
    findings: list[str] = []
    for result in results or []:
        target = result.get("Target", "?")
        for secret in result.get("Secrets") or []:
            findings.append(f"{target}: secret {secret.get('RuleID', '?')}")
        for misconfig in result.get("Misconfigurations") or []:
            findings.append(f"{target}: {misconfig.get('ID', '?')} {misconfig.get('Title', '')}")
    return sorted(findings)


def _result(tool: str, findings: list[str]) -> ToolResult:
    if findings:
        return ToolResult(tool, "findings", f"{len(findings)} finding(s)", findings)
    return ToolResult(tool, "passed", "no findings")


def scan_bundle(bundle_dir: Path, policy: Path | None = None) -> list[ToolResult]:
    if not bundle_dir.is_dir():
        raise ScanError(f"{bundle_dir}: bundle directory not found")
    return [run_opa(bundle_dir, policy), run_checkov(bundle_dir), run_trivy(bundle_dir)]
