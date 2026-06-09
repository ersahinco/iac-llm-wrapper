"""Standalone contract validation artifact helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import ruamel.yaml

from .contracts import (
    BLOCKED_ASSESSMENT_CONTRACT,
    CONTEXT_MANIFEST_CONTRACT,
    HANDOFF_PLAN_CONTRACT,
    PLAN_READY_BUNDLE_CONTRACT,
    ContractValidator,
)
from .patterns import GLOBAL_REGISTRY


def build_contract_validation(input_dir: Path) -> dict[str, Any]:
    """Validate generated artifacts against the contracts implied by the bundle."""
    report = _read_yaml(input_dir / "decision-report.yaml")
    handoff = _read_yaml(input_dir / "handoff-plan.yaml")
    readiness = _readiness(report, handoff)
    contracts = []

    if readiness.get("handoffAllowed", readiness.get("deploymentAllowed", False)):
        pattern = str(report.get("pattern", handoff.get("pattern", "")) or "")
        try:
            pattern_obj = GLOBAL_REGISTRY.get(pattern)
        except KeyError:
            pattern_obj = None
        if pattern_obj is not None:
            contracts.extend(pattern_obj.contracts)
            if pattern_obj.contracts:
                contracts.append(HANDOFF_PLAN_CONTRACT)
            contracts.append(CONTEXT_MANIFEST_CONTRACT)
            if pattern_obj.plan_ready:
                contracts.append(PLAN_READY_BUNDLE_CONTRACT)
    else:
        contracts.append(BLOCKED_ASSESSMENT_CONTRACT)

    results = []
    for contract in contracts:
        violations = ContractValidator(contract).validate_artifacts(input_dir)
        results.append(
            {
                "name": contract.name,
                "kind": contract.kind,
                "status": "pass" if not violations else "fail",
                "violationCount": len(violations),
                "violations": [
                    {"code": violation.code, "message": violation.message}
                    for violation in violations
                ],
            }
        )

    violation_count = 0
    for result in results:
        value = result.get("violationCount", 0)
        violation_count += value if isinstance(value, int) else 0

    return {
        "schemaVersion": "intent-engine/contract-validation/v1",
        "pattern": str(report.get("pattern", handoff.get("pattern", "unknown"))),
        "readiness": readiness,
        "contracts": results,
        "summary": {
            "status": "pass"
            if results and all(item["status"] == "pass" for item in results)
            else "fail",
            "contractCount": len(results),
            "violationCount": violation_count,
        },
    }


def write_contract_validation(input_dir: Path) -> Path:
    """Write contract-validation.yaml and return its path."""
    path = input_dir / "contract-validation.yaml"
    _write_yaml(path, build_contract_validation(input_dir))
    return path


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    yaml = ruamel.yaml.YAML(typ="safe")
    data = yaml.load(path.read_text())
    return data if isinstance(data, dict) else {}


def _readiness(report: dict[str, Any], handoff: dict[str, Any]) -> dict[str, Any]:
    report_readiness = report.get("handoffReadiness") or report.get("deploymentReadiness")
    if not isinstance(report_readiness, dict):
        report_readiness = {}
    handoff_readiness = handoff.get("readiness")
    if not isinstance(handoff_readiness, dict):
        handoff_readiness = {}
    if not report_readiness and not handoff_readiness:
        return {
            "status": "blocked",
            "handoffAllowed": False,
            "deploymentAllowed": False,
            "blockers": [
                {
                    "code": "READINESS_METADATA_MISSING",
                    "message": "Bundle is missing handoff readiness metadata.",
                }
            ],
        }
    allowed: bool | None = None
    for source in (report_readiness, handoff_readiness):
        for key in ("handoffAllowed", "deploymentAllowed"):
            if key in source:
                allowed = bool(source[key])
                break
        if allowed is not None:
            break
    blockers = report_readiness.get("blockers", handoff_readiness.get("blockers", []))
    if not isinstance(blockers, list):
        blockers = []
    status = str(report_readiness.get("status", handoff_readiness.get("status", ""))).lower()
    if allowed is None or not status:
        blockers = [
            *blockers,
            {
                "code": "READINESS_METADATA_INCOMPLETE",
                "message": (
                    "Bundle readiness metadata must explicitly include status and "
                    "handoffAllowed or deploymentAllowed."
                ),
            },
        ]
        return {
            "status": "blocked",
            "handoffAllowed": False,
            "deploymentAllowed": False,
            "blockers": blockers,
        }
    return {
        "status": status,
        "handoffAllowed": allowed,
        "deploymentAllowed": allowed,
        "blockers": blockers,
    }


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    path.write_text(_yaml_header() + _yaml_dump(yaml, data))


def _yaml_dump(yaml: ruamel.yaml.YAML, data: dict[str, Any]) -> str:
    from io import StringIO

    buf = StringIO()
    yaml.dump(data, buf)
    return "\n".join(line.rstrip() for line in buf.getvalue().splitlines()) + "\n"


def _yaml_header() -> str:
    return (
        "# yaml-language-server: $schema=none\n"
        "# Generated by intent-engine — validation artifact, not deployable configuration.\n"
    )
