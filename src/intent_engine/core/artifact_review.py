"""Static handoff review page orchestration."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from intent_engine.patterns.aws_lza.validation import (
    LZA_VALIDATION_EVIDENCE,
    summarize_lza_validation_output,
)

from .contract_validation import build_contract_validation
from .patterns import GLOBAL_REGISTRY
from .review_renderer import render_review_html as render_review_html_context
from .yaml_utils import read_yaml_mapping

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def write_review_html(input_dir: Path, output: Path) -> None:
    """Write a portable static HTML review page for a generated handoff bundle."""
    output.parent.mkdir(parents=True, exist_ok=True)
    contract_validation_path = _existing_contract_validation(input_dir)
    context = build_review_context(
        input_dir,
        link_base_dir=output.parent,
        graph_exports=_relative_graph_exports(
            input_dir,
            output.parent,
            _existing_graph_exports(input_dir),
        ),
        contract_validation_path=contract_validation_path,
    )
    output.write_text(render_review_html_context(context))


def render_review_html(
    input_dir: Path,
    graph_exports: dict[str, str] | None = None,
    link_base_dir: Path | None = None,
) -> str:
    """Render a static HTML review page from generated handoff artifacts."""
    context = build_review_context(
        input_dir,
        link_base_dir=link_base_dir or input_dir,
        graph_exports=graph_exports or _existing_graph_exports(input_dir),
        contract_validation_path=_existing_contract_validation(input_dir),
    )
    return render_review_html_context(context)


def build_review_context(
    input_dir: Path,
    *,
    link_base_dir: Path,
    graph_exports: dict[str, str],
    contract_validation_path: Path | None,
) -> dict[str, Any]:
    """Read generated artifacts and return renderer-ready review context."""
    report = _read_yaml(input_dir / "decision-report.yaml")
    trace = _read_yaml(input_dir / "llm-trace-summary.yaml")
    benchmark = _read_yaml(input_dir / "model-benchmark.yaml")
    handoff = _read_yaml(input_dir / "handoff-plan.yaml")
    lineage = _read_yaml(input_dir / "lineage-manifest.yaml")
    policy_graph = _read_yaml(input_dir / "policy-graph.yaml")
    shift_left_evidence = _read_yaml(input_dir / "shift-left-evidence.yaml")
    target_capabilities = _read_yaml(input_dir / "target-capability-graph.yaml")
    if not target_capabilities:
        target_capabilities = _dict(
            report.get("targetCapabilities")
            or trace.get("targetCapabilities")
            or handoff.get("targetCapabilities")
        )
    readiness = _readiness(report, handoff)
    contract_validation = (
        _read_yaml(contract_validation_path)
        if contract_validation_path is not None
        else build_contract_validation(input_dir)
    )
    model_quality = _model_quality(benchmark, trace)
    contract_status = _contract_status(contract_validation)
    blocking_gaps = _trace_list(trace, "gaps", "blocking")
    blocking_contradictions = _trace_list(trace, "contradictions", "blocking")
    artifacts = _artifact_rows(input_dir, _artifact_names(input_dir, handoff, lineage))
    raw_evidence = _raw_evidence(trace)
    lza_validation_evidence = _read_yaml(input_dir / LZA_VALIDATION_EVIDENCE)
    lza_validation_summary = _lza_validation_summary(lza_validation_evidence)
    policy_evidence_summary = _policy_evidence_summary(policy_graph, shift_left_evidence)

    return {
        "pattern": str(report.get("pattern", handoff.get("pattern", "handoff"))),
        "readiness": readiness,
        "reviewSummary": {
            "readiness": readiness.get("status", "unknown"),
            "handoffAllowed": readiness.get("handoffAllowed", False),
            "blockerCount": len(_coerce_list(readiness.get("blockers"))),
            "missingDecisionCount": len(_coerce_list(readiness.get("missingDecisions"))),
            "conflictingDecisionCount": len(_coerce_list(readiness.get("conflictingDecisions"))),
            "blockingGapCount": len(blocking_gaps),
            "blockingContradictionCount": len(blocking_contradictions),
            "contractStatus": contract_status,
            "allowedNextAction": readiness.get("allowedNextAction", ""),
            "modelQuality": model_quality,
            "modelParseErrorCount": model_quality.get("parseErrorCount", 0),
            "lzaValidationStatus": lza_validation_summary.get("status", "not-run"),
            "lzaValidationFailure": lza_validation_summary.get("failureExcerpt", ""),
            "policyPackCount": policy_evidence_summary.get("policyPackCount", 0),
            "policyEvidenceStatus": policy_evidence_summary.get("status", "not-run"),
            "failedPolicyControlCount": policy_evidence_summary.get("failedPolicyControlCount", 0),
            "unmappedCheckovFindingCount": policy_evidence_summary.get("unmappedFindingCount", 0),
            "selectedTargetPath": target_capabilities.get("selectedTargetPath", []),
            "unsupportedTargetGapCount": len(
                _coerce_list(target_capabilities.get("unsupportedGaps"))
            ),
        },
        "modelQuality": model_quality,
        "graphExports": graph_exports,
        "acceptedDecisions": _dict(trace.get("acceptedDecisions")),
        "graphDecisions": _graph_decisions(report),
        "blockingGaps": blocking_gaps,
        "resolvedGaps": _trace_list(trace, "gaps", "resolved"),
        "blockingContradictions": blocking_contradictions,
        "blockerRows": _blocker_rows(str(report.get("pattern", "")), readiness),
        "contractValidation": _coerce_list(contract_validation.get("contracts")),
        "contractValidationArtifact": contract_validation,
        "contractStatus": contract_status,
        "lzaValidationEvidence": lza_validation_evidence,
        "lzaValidationSummary": lza_validation_summary,
        "policyGraph": policy_graph,
        "shiftLeftEvidence": shift_left_evidence,
        "policyEvidenceSummary": policy_evidence_summary,
        "targetCapabilities": target_capabilities,
        "reviewerNextActions": _reviewer_next_actions(
            readiness=readiness,
            contract_status=contract_status,
            raw_evidence=raw_evidence,
            artifacts=artifacts,
            model_quality=model_quality,
            lza_validation_summary=lza_validation_summary,
            policy_evidence_summary=policy_evidence_summary,
        ),
        "artifacts": artifacts,
        "handoff": handoff,
        "trace": trace,
        "benchmark": benchmark,
        "rawEvidence": raw_evidence,
        "links": {
            "llmTrace": _artifact_href(input_dir, link_base_dir, "llm-trace-summary.yaml"),
            "rawEvidence": _raw_evidence_href(link_base_dir, trace),
            "modelBenchmark": _artifact_href(input_dir, link_base_dir, "model-benchmark.yaml"),
            "contractValidation": _href(link_base_dir, contract_validation_path)
            if contract_validation_path is not None
            else None,
            "lzaValidation": _artifact_href(input_dir, link_base_dir, LZA_VALIDATION_EVIDENCE),
            "policyGraph": _artifact_href(input_dir, link_base_dir, "policy-graph.yaml"),
            "shiftLeftEvidence": _artifact_href(
                input_dir,
                link_base_dir,
                "shift-left-evidence.yaml",
            ),
            "targetCapabilities": _artifact_href(
                input_dir,
                link_base_dir,
                "target-capability-graph.yaml",
            ),
        },
    }


def _existing_graph_exports(input_dir: Path) -> dict[str, str]:
    exports: dict[str, str] = {}
    if (input_dir / "requirement-graph.json").exists():
        exports["json"] = "requirement-graph.json"
    if (input_dir / "requirement-graph.mmd").exists():
        exports["mermaid"] = "requirement-graph.mmd"
    for key, name in {
        "bundleGraph": "bundle-graph.yaml",
        "graphRoots": "graph-roots.yaml",
        "impactReport": "impact-report.yaml",
        "graphImpactMatrix": "graph-impact-matrix.yaml",
        "graphFind": "graph-find.yaml",
        "graphPath": "graph-path.yaml",
        "graphNeighborhood": "graph-neighborhood.yaml",
        "graphDiff": "graph-diff.yaml",
    }.items():
        if (input_dir / name).exists():
            exports[key] = name
    return exports


def _relative_graph_exports(
    input_dir: Path,
    link_base_dir: Path,
    graph_exports: dict[str, str],
) -> dict[str, str]:
    return {
        key: _href_required(link_base_dir, input_dir / value)
        for key, value in graph_exports.items()
        if value
    }


def _existing_contract_validation(input_dir: Path) -> Path | None:
    path = input_dir / "contract-validation.yaml"
    return path if path.exists() else None


def _read_yaml(path: Path | None) -> dict[str, Any]:
    return read_yaml_mapping(path) if path is not None else {}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _readiness(report: dict[str, Any], handoff: dict[str, Any]) -> dict[str, Any]:
    report_readiness = _dict(report.get("handoffReadiness"))
    handoff_readiness = _dict(handoff.get("readiness"))
    allowed = bool(
        report_readiness.get(
            "handoffAllowed",
            handoff_readiness.get("handoffAllowed", True),
        )
    )
    status = str(report_readiness.get("status", handoff_readiness.get("status", "ready"))).lower()
    default_action = (
        "Resolve blockers before passing artifacts to an implementation toolchain."
        if status == "blocked"
        else "Review generated artifacts with the owning teams before handoff."
    )
    return {
        "status": status,
        "handoffAllowed": allowed,
        "allowedNextAction": str(
            handoff.get(
                "allowedNextAction",
                default_action,
            )
        ),
        "blockers": _coerce_list(
            report_readiness.get("blockers", handoff_readiness.get("blockers", []))
        ),
        "missingDecisions": _coerce_list(report_readiness.get("missingDecisions")),
        "conflictingDecisions": _coerce_list(report_readiness.get("conflictingDecisions")),
        "safeHandoffPath": _coerce_list(report_readiness.get("safeHandoffPath")),
    }


def _graph_decisions(report: dict[str, Any]) -> dict[str, Any]:
    ignored = {"handoffReadiness"}
    return {key: value for key, value in report.items() if key not in ignored}


def _blocker_rows(pattern: str, readiness: dict[str, Any]) -> list[dict[str, str]]:
    requirements_by_code, requirements_by_key = _requirement_indexes(pattern)
    missing_by_reason = {
        str(item.get("reason", "")): item
        for item in _coerce_list(readiness.get("missingDecisions"))
        if isinstance(item, dict)
    }
    conflicting_codes = {
        str(item.get("code", ""))
        for item in _coerce_list(readiness.get("conflictingDecisions"))
        if isinstance(item, dict)
    }
    rows: list[dict[str, str]] = []
    for blocker in _coerce_list(readiness.get("blockers")):
        if not isinstance(blocker, dict):
            continue
        code = str(blocker.get("code", "unknown"))
        message = str(blocker.get("message", ""))
        requirement = requirements_by_code.get(code)
        missing = missing_by_reason.get(message)
        key = str(missing.get("key", "")) if isinstance(missing, dict) else ""
        if not key and requirement is not None:
            key = requirement.key
        if not key:
            key = _markdown_contradiction_key(code, message)
        if not key:
            key = _validator_code_key(pattern, code)
        if requirement is None and key:
            requirement = requirements_by_key.get(key)
        rows.append(
            {
                "code": code,
                "message": message,
                "requirementKey": key or "unknown",
                "label": str(missing.get("label", "") if isinstance(missing, dict) else "")
                or (requirement.label if requirement is not None else "unknown"),
                "question": str(missing.get("question", "") if isinstance(missing, dict) else "")
                or (requirement.question if requirement is not None else "unknown"),
                "resolutionType": _resolution_type(code, key, conflicting_codes),
            }
        )
    return rows


def _requirement_indexes(pattern: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if not pattern:
        return {}, {}
    try:
        graph = GLOBAL_REGISTRY.get(pattern).create_graph()
    except KeyError:
        return {}, {}
    by_code = {
        req.violation_code: req
        for req in graph._requirements.values()
        if req.violation_code is not None
    }
    by_key = {req.key: req for req in graph._requirements.values()}
    return by_code, by_key


def _markdown_contradiction_key(code: str, message: str) -> str:
    if code.startswith("MARKDOWN_CONTRADICTION_"):
        return code.removeprefix("MARKDOWN_CONTRADICTION_").lower()
    marker = "decision '"
    if marker not in message:
        return ""
    return message.split(marker, 1)[1].split("'", 1)[0]


def _validator_code_key(pattern: str, code: str) -> str:
    pattern_codes = {
        "aws-lza": {
            "AWS_LZA_SECURITY_OU_REQUIRED": "organizational_units",
            "AWS_LZA_INFRASTRUCTURE_OU_REQUIRED": "organizational_units",
            "AWS_LZA_WORKLOADS_OU_REQUIRED": "organizational_units",
            "AWS_LZA_LOG_ARCHIVE_ACCOUNT_REQUIRED": "log_archive_account",
            "AWS_LZA_AUDIT_ACCOUNT_REQUIRED": "audit_account",
            "AWS_LZA_SECURITY_TOOLING_ACCOUNT_REQUIRED": "security_tooling_account",
            "AWS_LZA_IDENTITY_CENTER_ADMIN_UNKNOWN": ("identity_center_delegated_admin_account"),
            "AWS_LZA_IDENTITY_CENTER_ASSIGNMENT_FORMAT_INVALID": ("identity_center_assignments"),
            "AWS_LZA_IDENTITY_CENTER_ASSIGNMENT_PERMISSION_SET_UNKNOWN": (
                "identity_center_assignments"
            ),
            "AWS_LZA_IDENTITY_CENTER_ASSIGNMENT_ACCOUNT_UNKNOWN": ("identity_center_assignments"),
            "AWS_LZA_HOME_REGION_NOT_ENABLED": "enabled_regions",
        }
    }
    return pattern_codes.get(pattern, {}).get(code, "")


def _resolution_type(code: str, key: str, conflicting_codes: set[str]) -> str:
    if code in conflicting_codes or code.startswith("MARKDOWN_CONTRADICTION_"):
        return "conflicting"
    if key and key != "unknown":
        return "missing"
    return "blocker"


def _trace_list(trace: dict[str, Any], section: str, key: str) -> list[Any]:
    value = trace.get(section)
    if not isinstance(value, dict):
        return []
    return _coerce_list(value.get(key, []))


def _contract_status(contract_validation: dict[str, Any]) -> str:
    summary = contract_validation.get("summary")
    if isinstance(summary, dict):
        return str(summary.get("status", "unknown"))
    contracts = _coerce_list(contract_validation.get("contracts"))
    if not contracts:
        return "unknown"
    return "fail" if any(_dict(item).get("status") == "fail" for item in contracts) else "pass"


def _model_quality(benchmark: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    quality = _dict(benchmark.get("quality"))
    run = _dict(benchmark.get("run"))
    conformance = _dict(benchmark.get("conformance"))
    applied = _dict(trace.get("appliedDecisions"))
    mode = str(run.get("mode", "unknown"))
    accepted = int(quality.get("acceptedDecisionCount", 0) or 0)
    raw_coverage = int(quality.get("rawLlmAcceptedCoverageCount", 0) or 0)
    raw_missing = int(quality.get("rawLlmMissingAcceptedDecisionCount", 0) or 0)
    missing_keys = [
        str(item) for item in _coerce_list(quality.get("rawLlmMissingAcceptedDecisions"))
    ]
    llm_applied = _coerce_list(applied.get("llm"))
    markdown_applied = _coerce_list(applied.get("markdown"))
    parse_error_count = int(quality.get("parseErrorCount", 0) or 0)
    warnings: list[str] = []
    if parse_error_count:
        warnings.append(
            "LLM extraction recorded parse or backend errors; deterministic extraction may "
            "have carried the run."
        )
    if mode != "llm":
        raw_missing = 0
        missing_keys = []
    if mode == "llm" and raw_missing:
        warnings.append("Raw LLM missed accepted decisions: " + ", ".join(missing_keys) + ".")
    if mode == "llm" and markdown_applied and not llm_applied:
        warnings.append("Structured Markdown carried the handoff; LLM added no accepted decisions.")
    return {
        "mode": mode,
        "model": str(run.get("model", "unknown")),
        "acceptedDecisionCount": accepted,
        "rawCoverage": (f"{raw_coverage}/{accepted}" if mode == "llm" and accepted else "not-run"),
        "rawMissingCount": raw_missing,
        "missingKeys": missing_keys,
        "conformanceStatus": str(conformance.get("status", "unknown")),
        "conformanceReason": str(conformance.get("reason", "")),
        "expectedWeaknesses": warnings,
        "parseErrorCount": parse_error_count,
    }


def _artifact_names(input_dir: Path, handoff: dict[str, Any], lineage: dict[str, Any]) -> list[str]:
    names: list[str] = []
    contracts = handoff.get("targetContracts")
    if isinstance(contracts, list):
        for contract in contracts:
            if isinstance(contract, dict):
                names.extend(
                    str(item) for item in _coerce_list(contract.get("requiredArtifacts", []))
                )
    artifacts = lineage.get("artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if isinstance(artifact, dict) and artifact.get("required", True):
                names.append(str(artifact.get("name", "")))
    names.extend(path.name for path in sorted(input_dir.iterdir()) if path.is_file())
    return sorted(dict.fromkeys(name for name in names if name))


def _artifact_rows(input_dir: Path, artifacts: list[str]) -> list[dict[str, str]]:
    return [
        {
            "name": artifact,
            "status": "present" if (input_dir / artifact).exists() else "missing",
        }
        for artifact in artifacts
    ]


def _raw_evidence(trace: dict[str, Any]) -> str:
    raw = trace.get("rawEvidence")
    if not isinstance(raw, dict):
        return "unknown"
    status = raw.get("status", "unknown")
    path = raw.get("path")
    return f"{status} ({path})" if path else str(status)


def _lza_validation_summary(evidence: dict[str, Any]) -> dict[str, Any]:
    if not evidence:
        return {"status": "not-run", "configFileDigests": []}
    command = _dict(evidence.get("command"))
    source = _dict(evidence.get("lzaSource"))
    input_block = _dict(evidence.get("input"))
    boundary = _dict(evidence.get("boundary"))
    status = str(evidence.get("status", "unknown"))
    exit_code = _exit_code(command.get("exitCode"), status=status)
    diagnostic = _dict(evidence.get("diagnostic")) or summarize_lza_validation_output(
        exit_code=exit_code,
        stdout=str(command.get("stdout", "") or ""),
        stderr=str(command.get("stderr", "") or ""),
    )
    argv = command.get("argv")
    command_text = " ".join(str(item) for item in argv) if isinstance(argv, list) else ""
    failure_excerpt = (
        str(diagnostic.get("summary") or _lza_validation_failure_excerpt(command))
        if status != "pass"
        else ""
    )
    return {
        "status": status,
        "exitCode": str(command.get("exitCode", "unknown")),
        "command": command_text,
        "sourcePath": str(source.get("requestedPath", "")),
        "sourceCwd": str(source.get("commandWorkingDirectory", "")),
        "packageVersion": str(source.get("packageVersion", "unknown")),
        "gitCommit": str(source.get("gitCommit") or "unknown"),
        "awsLookupBoundary": _aws_lookup_boundary(boundary),
        "stagingBoundary": str(input_block.get("stagingBoundary", "")),
        "commandReplayable": command.get("replayable", "unknown"),
        "commandReplayBoundary": str(command.get("replayBoundary", "")),
        "diagnosticCategory": str(diagnostic.get("category", "")),
        "diagnosticNextAction": str(diagnostic.get("nextAction", "")),
        "failureExcerpt": failure_excerpt,
        "configFileDigests": _coerce_list(input_block.get("configFileDigests")),
    }


def _policy_evidence_summary(
    policy_graph: dict[str, Any],
    shift_left_evidence: dict[str, Any],
) -> dict[str, Any]:
    packs = _coerce_list(policy_graph.get("policyPacks"))
    frameworks = sorted(
        {
            str(framework)
            for pack in packs
            if isinstance(pack, dict)
            for framework in _coerce_list(pack.get("frameworks"))
        }
    )
    controls = [
        control
        for pack in packs
        if isinstance(pack, dict)
        for control in _coerce_list(pack.get("controls"))
        if isinstance(control, dict)
    ]
    evidence_result = _dict(shift_left_evidence.get("result"))
    evidence_input = _dict(shift_left_evidence.get("input"))
    status = str(evidence_result.get("status", "not-run")) if shift_left_evidence else "not-run"
    mapped_controls = _coerce_list(shift_left_evidence.get("mappedControls"))
    unmapped_findings = _coerce_list(shift_left_evidence.get("unmappedFindings"))
    failed_control_ids = sorted(
        {
            str(item.get("controlId", ""))
            for item in mapped_controls
            if isinstance(item, dict) and item.get("controlId")
        }
    )
    return {
        "status": status,
        "policyPackCount": len(packs),
        "policyPacks": [
            {
                "name": str(pack.get("name", "")),
                "version": str(pack.get("version", "")),
                "frameworks": _coerce_list(pack.get("frameworks")),
                "controlCount": len(_coerce_list(pack.get("controls"))),
            }
            for pack in packs
            if isinstance(pack, dict)
        ],
        "frameworks": frameworks,
        "controlCount": len(controls),
        "failedPolicyControlCount": len(failed_control_ids),
        "failedPolicyControls": failed_control_ids,
        "unmappedFindingCount": len(unmapped_findings),
        "ownerPolicyPaths": _coerce_list(evidence_input.get("ownerPolicyPaths")),
        "iacKind": str(evidence_input.get("iacKind", "")),
        "checkovFramework": str(evidence_input.get("checkovFramework", "")),
        "summary": _dict(shift_left_evidence.get("summary")),
        "boundary": str(shift_left_evidence.get("boundary", "")),
    }


def _aws_lookup_boundary(boundary: dict[str, Any]) -> str:
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


def _lza_validation_failure_excerpt(command: dict[str, Any]) -> str:
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
    for line in lines:
        clean = _ANSI_ESCAPE_RE.sub("", line).strip()
        if "Config file validation failed" in clean:
            return "Config file validation failed."
    return ""


def _reviewer_next_actions(
    *,
    readiness: dict[str, Any],
    contract_status: str,
    raw_evidence: str,
    artifacts: list[dict[str, str]],
    model_quality: dict[str, Any],
    lza_validation_summary: dict[str, Any],
    policy_evidence_summary: dict[str, Any],
) -> list[str]:
    status = str(readiness.get("status", "unknown"))
    handoff_allowed = bool(readiness.get("handoffAllowed", False))
    if status == "blocked" or not handoff_allowed:
        actions = [
            "Do not pass target artifacts to the provisioning toolchain yet.",
            "Resolve the blocker traceability rows with the listed requirement questions.",
            "Update the source Markdown, re-run compile, then regenerate this review page.",
        ]
    else:
        missing_artifacts = [row["name"] for row in artifacts if row.get("status") == "missing"]
        actions = [
            "Review handoff-plan.yaml for owners, manual gates, and the allowed next action.",
            (
                "Review the target artifact files listed below with the owning "
                "implementation, platform, security, or network reviewers."
            ),
            "Pass only reviewed artifacts to the existing target toolchain after manual gates.",
        ]
        if contract_status != "pass":
            actions.insert(0, "Resolve contract-validation.yaml before handoff.")
        if missing_artifacts:
            actions.insert(
                0,
                "Resolve missing required artifacts before handoff: "
                + ", ".join(missing_artifacts)
                + ".",
            )
    if str(lza_validation_summary.get("status", "not-run")) == "fail":
        actions.insert(
            0,
            "Do not claim downstream AWS LZA validation until lza-validation-evidence.yaml "
            "failures are resolved.",
        )
    policy_status = str(policy_evidence_summary.get("status", "not-run"))
    if int(policy_evidence_summary.get("policyPackCount", 0) or 0):
        if policy_status == "not-run":
            actions.append(
                "Policy packs are declared; capture shift-left Checkov evidence before "
                "owner-controlled pipeline gates require it."
            )
        elif policy_status != "pass":
            actions.append(
                "Treat shift-left Checkov findings as owner-pipeline evidence, not "
                "compliance attestation or deployment approval; resolve failed mapped "
                "controls or document owner acceptance."
            )
        else:
            actions.append(
                "Use shift-left-evidence.yaml as input to owner-controlled CI/CD gates; "
                "it is not compliance attestation by itself."
            )
    raw_evidence_status = _raw_evidence_status_label(raw_evidence)
    if raw_evidence_status in {"captured", "requested"}:
        actions.append(
            "Treat raw-evidence.yaml as local debug material; do not share it as "
            "a service artifact."
        )
    elif raw_evidence_status == "requested-empty":
        actions.append(
            "Raw evidence was requested, but no LLM calls were recorded; confirm LLM setup "
            "if that was unexpected."
        )
    elif raw_evidence_status == "not-requested":
        actions.append(
            "Raw prompt/response evidence was omitted; use trace and benchmark "
            "summaries for review."
        )
    if int(model_quality.get("parseErrorCount", 0) or 0):
        actions.append(
            "LLM extraction recorded parse or backend errors; review llm-trace-summary.yaml "
            "and model-benchmark.yaml before trusting model contribution."
        )
    return actions


def _raw_evidence_status_label(raw_evidence: str) -> str:
    return raw_evidence.split(" ", 1)[0].strip()


def _artifact_href(input_dir: Path, link_base_dir: Path, artifact_name: str) -> str | None:
    path = input_dir / artifact_name
    if not path.exists():
        return None
    return _href(link_base_dir, path)


def _raw_evidence_href(link_base_dir: Path, trace: dict[str, Any]) -> str | None:
    raw = trace.get("rawEvidence")
    if not isinstance(raw, dict):
        return None
    path = str(raw.get("path", ""))
    if not path or path == "not-requested":
        return None
    evidence_path = Path(path)
    return _href(link_base_dir, evidence_path) if evidence_path.exists() else path


def _href(link_base_dir: Path, target: Path | None) -> str | None:
    if target is None:
        return None
    return _href_required(link_base_dir, target)


def _href_required(link_base_dir: Path, target: Path) -> str:
    return Path(os.path.relpath(target, link_base_dir)).as_posix()


def _coerce_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
