"""AWS LZA review evidence shaping."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from intent_engine.core.yaml_utils import read_yaml_mapping

from .validation import LZA_VALIDATION_EVIDENCE, summarize_lza_validation_output

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def load_lza_review_evidence(input_dir: Path) -> dict[str, Any]:
    evidence_path = input_dir / LZA_VALIDATION_EVIDENCE
    evidence = read_yaml_mapping(evidence_path) if evidence_path.exists() else {}
    return {
        "label": "LZA validation",
        "sectionTitle": "LZA Validation Evidence",
        "artifactName": LZA_VALIDATION_EVIDENCE,
        "evidence": evidence,
        "summary": _validation_summary(evidence),
    }


def _validation_summary(evidence: dict[str, Any]) -> dict[str, Any]:
    if not evidence:
        return {"status": "not-run", "configFileDigests": []}
    command = _dict(evidence.get("command"))
    source = _dict(evidence.get("lzaSource"))
    input_block = _dict(evidence.get("input"))
    boundary = _dict(evidence.get("boundary"))
    status = str(evidence.get("status", "unknown"))
    diagnostic = _dict(evidence.get("diagnostic")) or summarize_lza_validation_output(
        exit_code=_exit_code(command.get("exitCode"), status=status),
        stdout=str(command.get("stdout", "") or ""),
        stderr=str(command.get("stderr", "") or ""),
    )
    argv = command.get("argv")
    command_text = " ".join(str(item) for item in argv) if isinstance(argv, list) else ""
    failure_excerpt = (
        str(diagnostic.get("summary") or _failure_excerpt(command)) if status != "pass" else ""
    )
    return {
        "status": status,
        "exitCode": str(command.get("exitCode", "unknown")),
        "command": command_text,
        "sourcePath": str(source.get("requestedPath", "")),
        "sourceCwd": str(source.get("commandWorkingDirectory", "")),
        "packageVersion": str(source.get("packageVersion", "unknown")),
        "gitCommit": str(source.get("gitCommit") or "unknown"),
        "lookupBoundary": _lookup_boundary(boundary),
        "stagingBoundary": str(input_block.get("stagingBoundary", "")),
        "commandReplayable": command.get("replayable", "unknown"),
        "commandReplayBoundary": str(command.get("replayBoundary", "")),
        "diagnosticCategory": str(diagnostic.get("category", "")),
        "diagnosticNextAction": str(diagnostic.get("nextAction", "")),
        "failureExcerpt": failure_excerpt,
        "configFileDigests": _list(input_block.get("configFileDigests")),
        "failureAction": (
            "Do not claim downstream AWS LZA validation until "
            "lza-validation-evidence.yaml failures are resolved."
        ),
    }


def _lookup_boundary(boundary: dict[str, Any]) -> str:
    explicit = boundary.get("awsAccountLookupBoundary")
    if explicit:
        return str(explicit)
    if boundary.get("readOnlyAwsAccountLookupMayOccur") is True:
        return (
            "The official AWS LZA validator may perform read-only account lookup "
            "through the provided AWS/LZA context."
        )
    return ""


def _exit_code(value: Any, *, status: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0 if status == "pass" else 1


def _failure_excerpt(command: dict[str, Any]) -> str:
    text = "\n".join(str(command.get(key, "") or "") for key in ("stdout", "stderr"))
    lines = [_ANSI_ESCAPE_RE.sub("", line).strip() for line in text.splitlines()]
    for line in lines:
        if "Default email" in line:
            return line[line.find("Default email") :]
    for line in lines:
        if "AccessDeniedException" in line:
            return line[line.find("AccessDeniedException") :]
    for line in lines:
        if " has " in line and " issues:" in line:
            return line.rsplit("|", 1)[-1].strip()
    if any("Config file validation failed" in line for line in lines):
        return "Config file validation failed."
    return ""


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
