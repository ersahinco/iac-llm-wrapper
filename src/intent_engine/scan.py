"""Advisory security checks over LZA output or owner-supplied IaC.

Three external tools, three separate verdicts:

    opa      LZA artifact advice (or an explicit --policy file)
    checkov  supported IaC and secret checks
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

from .contract import CONFIG_FILES, LZA_VERSION, validate_configs

ToolStatus = Literal["passed", "findings", "not-installed", "not-assessed", "error"]

_BUNDLE_INPUTS = {name.removesuffix("-config.yaml"): name for name in CONFIG_FILES}
_TIMEOUT = 300


class ScanError(Exception):
    """The bundle could not be prepared for scanning."""


@dataclass
class ToolResult:
    tool: str
    status: ToolStatus
    detail: str = ""
    findings: list[str] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        return self.status in {"not-installed", "not-assessed", "error"} or (
            self.tool == "lza-schema" and self.status == "findings"
        )


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
    try:
        return subprocess.run(  # noqa: S603 - fixed argument list, no shell
            command, capture_output=True, text=True, timeout=_TIMEOUT, check=False
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(command, 2, "", f"timed out after {_TIMEOUT}s")
    except OSError as exc:
        return subprocess.CompletedProcess(command, 2, "", f"could not run: {exc}")


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
    results = _objects(results, "OPA result")
    expressions = _objects(results[0].get("expressions"), "OPA expressions")
    value = expressions[0].get("value") if expressions else None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
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
            "terraform",
            "cloudformation",
            "kubernetes",
            "dockerfile",
            "secrets",
            "--skip-download",
            "--skip-results-upload",
            "--download-external-modules",
            "false",
            "--include-all-checkov-policies",
            "--output",
            "json",
            "--compact",
        ]
    )
    if completed.returncode not in {0, 1}:
        return ToolResult("checkov", "error", completed.stderr.strip() or "checkov failed")
    try:
        findings, assessed, exceptions = _parse_checkov(json.loads(completed.stdout))
    except (json.JSONDecodeError, ScanError) as exc:
        return ToolResult("checkov", "error", str(exc))
    if completed.returncode == 1 and not findings:
        return ToolResult("checkov", "error", "exit code 1 without reported findings")
    return _result(
        "checkov",
        findings,
        assessed,
        "supported IaC and secrets; LZA semantics not assessed",
        exceptions,
    )


def _objects(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ScanError(f"{label}: expected an array of objects")
    return value


def _count(report: dict[str, Any], key: str) -> int:
    value = report.get(key)
    if type(value) is not int or value < 0:
        raise ScanError(f"{key}: expected a nonnegative integer")
    return value


def _parse_checkov(payload: Any) -> tuple[list[str], int, list[str]]:
    reports = _objects(payload if isinstance(payload, list) else [payload], "Checkov reports")
    if not reports:
        raise ScanError("Checkov returned no report")
    findings: list[str] = []
    exceptions: list[str] = []
    assessed = 0
    for report in reports:
        # With no checks, Checkov returns the summary alone (no results wrapper).
        summary = report.get("summary", report)
        if not isinstance(summary, dict):
            raise ScanError("Checkov summary: expected an object")
        passed, failed = _count(summary, "passed"), _count(summary, "failed")
        if _count(summary, "parsing_errors"):
            raise ScanError("Checkov reported parsing errors")
        results = report.get("results", {})
        if not isinstance(results, dict):
            raise ScanError("Checkov results: expected an object")
        checks = _objects(results.get("failed_checks", []), "Checkov failed_checks")
        if failed != len(checks):
            raise ScanError("Checkov failed count does not match reported findings")
        for check in checks:
            if not check.get("file_path") or not check.get("check_id"):
                raise ScanError("Checkov finding is missing file_path or check_id")
            findings.append(
                f"{check['file_path']}: {check['check_id']} {check.get('check_name', '')}".strip()
            )
        exceptions.extend(_checkov_exceptions(results, summary))
        assessed += passed + failed
    return sorted(findings), assessed, sorted(exceptions)


def _checkov_exceptions(results: dict[str, Any], summary: dict[str, Any]) -> list[str]:
    exceptions = []
    skipped = _objects(results.get("skipped_checks", []), "Checkov skipped_checks")
    if _count({"skipped": len(skipped)} | summary, "skipped") != len(skipped):
        raise ScanError("Checkov skipped count does not match reported exceptions")
    for check in skipped:
        if not check.get("file_path") or not check.get("check_id"):
            raise ScanError("Checkov exception is missing file_path or check_id")
        result = check.get("check_result", {})
        if not isinstance(result, dict):
            raise ScanError("Checkov exception check_result must be an object")
        exceptions.append(
            f"{check['file_path']}: {check['check_id']} "
            f"{check.get('resource', '')} — "
            f"{result.get('suppress_comment') or 'no reason reported'}"
        )
    return exceptions


def run_trivy(bundle_dir: Path) -> ToolResult:
    if shutil.which("trivy") is None:
        return ToolResult("trivy", "not-installed", "trivy is not on PATH")
    command = [
        "trivy",
        "fs",
        "--scanners",
        "secret,misconfig",
        "--include-non-failures",
        "--show-suppressed",
        "--skip-check-update",
        "--skip-version-check",
        "--disable-telemetry",
        "--offline-scan",
        "--exit-code",
        "0",
        "--format",
        "json",
        "--quiet",
        str(bundle_dir),
    ]
    for name in (".trivyignore.yaml", ".trivyignore"):
        ignorefile = bundle_dir / name
        if ignorefile.is_file():
            command.extend(["--ignorefile", str(ignorefile)])
            break
    completed = _run(command)
    # Trivy's default findings exit code is zero; any nonzero code is a failure.
    if completed.returncode != 0:
        return ToolResult("trivy", "error", completed.stderr.strip() or "trivy failed")
    try:
        findings, assessed, exceptions = _parse_trivy(json.loads(completed.stdout))
    except (json.JSONDecodeError, ScanError) as exc:
        return ToolResult("trivy", "error", str(exc))
    return _result(
        "trivy",
        findings,
        assessed,
        "reported secret/misconfiguration checks; no LZA schema validation",
        exceptions,
    )


def _parse_trivy(payload: Any) -> tuple[list[str], int, list[str]]:
    if not isinstance(payload, dict) or payload.get("SchemaVersion") != 2:
        raise ScanError("Trivy report: expected SchemaVersion 2")
    if payload.get("ArtifactType") != "filesystem" or not payload.get("ArtifactName"):
        raise ScanError("Trivy report: expected a filesystem artifact")
    results = _objects(payload.get("Results", []), "Trivy Results")
    findings: list[str] = []
    exceptions: list[str] = []
    assessed = 0
    for result in results:
        target = result.get("Target")
        if not isinstance(target, str) or not target:
            raise ScanError("Trivy result is missing Target")
        secrets = _objects(result.get("Secrets", []), "Trivy Secrets")
        for secret in secrets:
            if not secret.get("RuleID"):
                raise ScanError("Trivy secret is missing RuleID")
            findings.append(f"{target}: secret {secret['RuleID']}")
        assessed += len(secrets)
        messages, checked, skipped = _trivy_misconfigurations(result, target)
        findings.extend(messages)
        assessed += checked
        exceptions.extend(skipped)
        exceptions.extend(_trivy_suppressions(result, target))
    return sorted(findings), assessed, sorted(exceptions)


def _trivy_suppressions(result: dict[str, Any], target: str) -> list[str]:
    exceptions = []
    for item in _objects(result.get("ExperimentalModifiedFindings", []), "Trivy suppressions"):
        finding = item.get("Finding")
        if not isinstance(finding, dict) or item.get("Status") != "ignored":
            raise ScanError("Trivy suppression needs an ignored finding")
        identifier = finding.get("ID") or finding.get("RuleID")
        if not identifier:
            raise ScanError("Trivy suppression is missing a check ID")
        exceptions.append(
            f"{target}: {identifier} — {item.get('Statement') or 'no reason reported'} "
            f"({item.get('Source') or 'native scanner suppression'})"
        )
    return exceptions


def _trivy_misconfigurations(
    result: dict[str, Any], target: str
) -> tuple[list[str], int, list[str]]:
    findings: list[str] = []
    exceptions: list[str] = []
    misconfigs = _objects(result.get("Misconfigurations", []), "Trivy Misconfigurations")
    failures = 0
    for misconfig in misconfigs:
        if not misconfig.get("ID") or misconfig.get("Status") not in ("FAIL", "PASS", "EXCEPTION"):
            raise ScanError("Trivy misconfiguration is missing ID or a valid Status")
        if misconfig["Status"] == "FAIL":
            failures += 1
            findings.append(f"{target}: {misconfig['ID']} {misconfig.get('Title', '')}".strip())
        elif misconfig["Status"] == "EXCEPTION":
            exceptions.append(
                f"{target}: {misconfig['ID']} {misconfig.get('Title', '')} — "
                f"{misconfig.get('Message') or 'native scanner exception'}"
            )
    summary = result.get("MisconfSummary")
    if summary is not None:
        if not isinstance(summary, dict):
            raise ScanError("Trivy MisconfSummary: expected an object")
        if _count(summary, "Failures") != failures:
            raise ScanError("Trivy failure count does not match reported findings")
        assessed = _count(summary, "Successes") + failures
    else:
        assessed = sum(item["Status"] != "EXCEPTION" for item in misconfigs)
    return findings, assessed, exceptions


def _result(
    tool: str,
    findings: list[str],
    assessed: int = 1,
    scope: str = "LZA artifact advice",
    exceptions: list[str] | None = None,
) -> ToolResult:
    exceptions = exceptions or []
    if findings:
        label = "schema error(s)" if tool == "lza-schema" else "warning(s)"
        return ToolResult(
            tool, "findings", f"{len(findings)} {label}; {scope}", findings, exceptions
        )
    if not assessed:
        return ToolResult(
            tool, "not-assessed", f"no assessed checks reported; {scope}", exceptions=exceptions
        )
    return ToolResult(
        tool,
        "passed",
        f"{assessed} assessed checks; no open findings; {scope}",
        exceptions=exceptions,
    )


def scan_bundle(bundle_dir: Path, policy: Path | None = None) -> list[ToolResult]:
    if not bundle_dir.is_dir():
        raise ScanError(f"{bundle_dir}: bundle directory not found")
    results = []
    if any((bundle_dir / name).exists() for name in CONFIG_FILES):
        documents = bundle_input(bundle_dir)
        errors = validate_configs({_BUNDLE_INPUTS[key]: value for key, value in documents.items()})
        results = [
            _result("lza-schema", errors, scope=f"LZA {LZA_VERSION} configuration shape only"),
            run_opa(bundle_dir, policy),
        ]
    elif policy:
        raise ScanError("--policy expects an LZA bundle with all six configuration files")
    return [*results, run_checkov(bundle_dir), run_trivy(bundle_dir)]
