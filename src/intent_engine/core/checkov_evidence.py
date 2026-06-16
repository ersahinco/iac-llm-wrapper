"""Checkov shift-left evidence capture."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

BOUNDARY = (
    "Checkov evidence is a shift-left policy scan for an owner-provided IaC, "
    "module, or pipeline path. iac-llm-wrapper does not deploy, mutate cloud "
    "resources, install modules, clone repositories, or run apply commands."
)


def scan_path_is_tfvars_only(scan_path: Path) -> bool:
    return scan_path.is_file() and scan_path.suffix.lower() == ".tfvars"


def build_invalid_scan_path_evidence(*, bundle: Path, scan_path: Path) -> dict[str, Any]:
    return {
        "schemaVersion": "intent-engine/shift-left-checkov/v1",
        "tool": {"name": "checkov", "available": False, "version": ""},
        "input": {"bundle": str(bundle), "scanPath": str(scan_path)},
        "boundary": BOUNDARY,
        "result": {
            "status": "invalid-input",
            "exitCode": None,
            "message": (
                "Do not scan generated terraform.tfvars alone; provide owner IaC/module path."
            ),
        },
        "summary": _empty_summary(),
        "findings": [],
    }


def run_checkov_evidence(
    *,
    bundle: Path,
    scan_path: Path,
    checkov_bin: str = "checkov",
) -> dict[str, Any]:
    executable = shutil.which(checkov_bin)
    evidence: dict[str, Any] = {
        "schemaVersion": "intent-engine/shift-left-checkov/v1",
        "tool": {"name": "checkov", "available": bool(executable), "version": ""},
        "input": {"bundle": str(bundle), "scanPath": str(scan_path)},
        "boundary": BOUNDARY,
        "summary": _empty_summary(),
        "findings": [],
    }
    if executable is None:
        evidence["result"] = {
            "status": "tool-unavailable",
            "exitCode": None,
            "message": "checkov executable was not found on PATH.",
        }
        return evidence

    version_proc = subprocess.run(
        [executable, "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    evidence["tool"]["version"] = (version_proc.stdout or version_proc.stderr).strip()

    argv = [executable, "-d", str(scan_path), "-o", "json"]
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
    )
    evidence["command"] = {"argv": argv, "replayable": True}
    evidence["result"] = {"status": "error", "exitCode": proc.returncode}

    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        evidence["result"].update(
            {
                "status": "parse-error",
                "message": f"checkov JSON output could not be parsed: {exc.msg}",
            }
        )
        evidence["rawOutput"] = {
            "stdout": proc.stdout[:4000],
            "stderr": proc.stderr[:4000],
        }
        return evidence

    summary, findings = _extract_checkov_payload(payload)
    status = "pass" if summary["failed"] == 0 and proc.returncode == 0 else "fail"
    evidence["result"]["status"] = status
    evidence["summary"] = summary
    evidence["findings"] = findings
    if proc.stderr.strip():
        evidence["stderr"] = proc.stderr[:4000]
    return evidence


def checkov_status_is_failure(evidence: dict[str, Any]) -> bool:
    result = evidence.get("result")
    if not isinstance(result, dict):
        return True
    return str(result.get("status")) != "pass"


def _empty_summary() -> dict[str, int]:
    return {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "parsingErrors": 0,
        "resourceCount": 0,
    }


def _extract_checkov_payload(payload: Any) -> tuple[dict[str, int], list[dict[str, Any]]]:
    reports = payload if isinstance(payload, list) else [payload]
    summary = _empty_summary()
    findings: list[dict[str, Any]] = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        report_summary = report.get("summary")
        if isinstance(report_summary, dict):
            summary["passed"] += _int(report_summary.get("passed"))
            summary["failed"] += _int(report_summary.get("failed"))
            summary["skipped"] += _int(report_summary.get("skipped"))
            summary["parsingErrors"] += _int(report_summary.get("parsing_errors"))
            summary["resourceCount"] += _int(report_summary.get("resource_count"))
        results = report.get("results")
        if not isinstance(results, dict):
            continue
        failed_checks = results.get("failed_checks")
        if not isinstance(failed_checks, list):
            continue
        for check in failed_checks:
            if not isinstance(check, dict):
                continue
            findings.append(
                {
                    "checkId": check.get("check_id", ""),
                    "checkName": check.get("check_name", ""),
                    "filePath": check.get("file_path", ""),
                    "resource": check.get("resource", ""),
                    "guideline": check.get("guideline", ""),
                }
            )
    return summary, findings[:50]


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
