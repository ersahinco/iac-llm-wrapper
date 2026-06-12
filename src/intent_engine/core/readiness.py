"""Readiness shaping for handoff-oriented compile results."""

from __future__ import annotations

from typing import Any

from .validator import Violation


def gap_is_resolved(graph, gap: Any) -> bool:
    key = finding_key(gap)
    if key is None:
        return False
    value = graph.get(key)
    return value is not None and str(value).strip() != ""


def blocking_gaps(graph, gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        gap
        for gap in gaps
        if isinstance(gap, dict)
        and finding_targets_requirement(graph, gap)
        and not gap_is_resolved(graph, gap)
    ]


def finding_key(finding: Any) -> str | None:
    if not isinstance(finding, dict):
        return None
    key = finding.get("key")
    if not isinstance(key, str) or not key:
        return None
    return key


def finding_targets_requirement(graph, finding: Any) -> bool:
    key = finding_key(finding)
    if key is None or not graph_has_requirement(graph, key):
        return False
    is_applicable = getattr(graph, "is_applicable", None)
    if callable(is_applicable) and not is_applicable(key):
        return False
    is_blocked = getattr(graph, "is_blocked", None)
    if callable(is_blocked) and is_blocked(key):
        return False
    return True


def graph_has_requirement(graph, key: str) -> bool:
    has_requirement = getattr(graph, "has_requirement", None)
    if callable(has_requirement):
        return bool(has_requirement(key))
    requirements = getattr(graph, "_requirements", {})
    return key in requirements


def blocking_contradictions(
    graph,
    contradictions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        contradiction
        for contradiction in contradictions
        if isinstance(contradiction, dict) and finding_targets_requirement(graph, contradiction)
    ]


def graph_missing_decisions(graph) -> list[dict[str, Any]]:
    from .requirements import RequirementStatus

    missing: list[dict[str, Any]] = []
    for key, req in graph._requirements.items():
        if not req.required_when_applicable:
            continue
        if not graph.is_applicable(key) or graph.is_blocked(key):
            continue
        status = graph.status(key)
        value = graph.get(key)
        if (
            status in (RequirementStatus.DECIDED, RequirementStatus.DEFAULTED)
            and str(value or "").strip()
        ):
            continue
        missing.append(
            {
                "key": key,
                "label": req.label,
                "reason": req.violation_message or f"{req.label} is required when applicable.",
                "question": req.question,
            }
        )
    return missing


def violation_conflicts(violations: list[Violation]) -> list[dict[str, str]]:
    conflicts: list[dict[str, str]] = []
    for violation in violations:
        if violation.code.endswith("_REQUIRED") or "REQUIRED" in violation.code:
            continue
        if violation.code.startswith("LLM_GAP_"):
            continue
        if violation.code.startswith("LLM_CONTRADICTION_"):
            continue
        conflicts.append({"code": violation.code, "reason": violation.message})
    return conflicts


def build_handoff_readiness(
    graph,
    violations: list[Violation],
    llm_result: Any,
    target_capability_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    missing = graph_missing_decisions(graph)
    conflicts = violation_conflicts(violations)
    llm_gaps = blocking_gaps(graph, llm_result.gaps)
    llm_contradictions = blocking_contradictions(graph, llm_result.contradictions)
    blockers = [{"code": v.code, "message": v.message} for v in violations]
    handoff_allowed = not blockers
    config_ready_status = "ready" if handoff_allowed else "blocked"
    plan_ready_status = "not-declared" if handoff_allowed else "blocked"
    allowed_next_action = (
        "Pass the reviewed artifacts to the existing target toolchain after manual gates."
        if handoff_allowed
        else "Resolve blockers and re-run compile before any downstream handoff."
    )
    unsupported_gaps: list[dict[str, Any]] = []
    if target_capability_report:
        unsupported_gaps = target_capability_report.get("unsupportedGaps", []) or []
    safe_handoff_path = (
        [
            "Review handoff-plan.yaml for owners, manual gates, and allowed next action.",
            "Validate target contracts and artifact owner approvals before downstream use.",
            "Pass only reviewed artifacts to the existing target toolchain.",
            *(
                [
                    "Route unsupported workload-specific requests through a separate "
                    "approved target path."
                ]
                if unsupported_gaps
                else []
            ),
        ]
        if handoff_allowed
        else [
            "Do not mutate downstream systems from this output while status is blocked.",
            "Resolve missing and conflicting decisions with the owning architect/platform team.",
            "Re-run compile and preserve decision-report.yaml plus lineage artifacts for handoff.",
            "Use the existing target toolchain only after handoff readiness is ready.",
        ]
    )
    readiness: dict[str, Any] = {
        "handoffAllowed": handoff_allowed,
        # Backward-compatible alias for existing artifact consumers.
        "deploymentAllowed": handoff_allowed,
        "status": "ready" if handoff_allowed else "blocked",
        "allowedNextAction": allowed_next_action,
        "summary": (
            "Ready for handoff."
            if handoff_allowed
            else "Cannot hand off yet; missing or conflicting decisions must be resolved."
        ),
        "configReady": {
            "status": config_ready_status,
            "allowed": handoff_allowed,
            "summary": (
                "Validated target configuration artifacts are ready for owner review."
                if handoff_allowed
                else "Target configuration artifacts are blocked until required decisions pass."
            ),
            "blockers": blockers,
        },
        "planReady": {
            "status": plan_ready_status,
            "planAllowed": False,
            "summary": (
                "No registered plan-ready bundle is declared for this target."
                if handoff_allowed
                else "Plan readiness is blocked until configuration readiness is clean."
            ),
            "blockers": [] if handoff_allowed else blockers,
        },
        "blockers": blockers,
        "missingDecisions": missing + llm_gaps,
        "conflictingDecisions": conflicts + llm_contradictions,
        "safeHandoffPath": safe_handoff_path,
    }
    if target_capability_report:
        readiness["targetCapabilities"] = {
            "selectedTargetPath": target_capability_report.get("selectedTargetPath", []),
            "unsupportedGapCount": len(unsupported_gaps),
            "unsupportedGaps": unsupported_gaps,
        }
    return readiness
