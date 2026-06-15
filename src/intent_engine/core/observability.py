"""Artifact-first LLM observability helpers."""

from __future__ import annotations

from typing import Any


def build_model_benchmark(extraction_summary: dict[str, Any]) -> dict[str, Any]:
    """Build a lean model benchmark from the existing trace summary."""
    calls = _list_of_dicts(extraction_summary.get("calls"))
    latencies = [float(call.get("latencyMs", 0) or 0) for call in calls]
    total_latency = round(sum(latencies), 1)
    token_totals = _token_totals(calls)
    readiness = _dict(extraction_summary.get("handoffReadiness"))
    gaps = _dict(extraction_summary.get("gaps"))
    contradictions = _dict(extraction_summary.get("contradictions"))
    raw_evidence = _dict(extraction_summary.get("rawEvidence"))
    accepted = _dict(extraction_summary.get("acceptedDecisions"))
    raw_decisions = _dict(extraction_summary.get("rawLlmDecisions"))
    signal_decisions = _dict(extraction_summary.get("rawLlmSignalDecisions"))
    applied = _dict(extraction_summary.get("appliedDecisions"))
    raw_llm_keys = set(raw_decisions) | set(signal_decisions)
    missing_from_raw_llm = sorted(set(accepted) - raw_llm_keys)
    unaccepted_raw_llm = sorted(raw_llm_keys - set(accepted))
    mode = "llm" if calls else "deterministic"
    parse_error_count = sum(1 for call in calls if call.get("parseError"))
    blocker_count = int(readiness.get("blockerCount", 0) or 0)

    return {
        "schemaVersion": "intent-engine/model-benchmark/v1",
        "pattern": extraction_summary.get("pattern", "unknown"),
        "run": {
            "mode": mode,
            "provider": extraction_summary.get("provider", "none"),
            "model": extraction_summary.get("model", "none"),
            "callCount": len(calls),
        },
        "readiness": {
            "status": readiness.get("status", "unknown"),
            "handoffAllowed": readiness.get("handoffAllowed", False),
            "blockerCount": blocker_count,
        },
        "latency": {
            "totalMs": total_latency,
            "averageMs": round(total_latency / len(latencies), 1) if latencies else 0.0,
            "maxMs": round(max(latencies), 1) if latencies else 0.0,
        },
        "tokens": {
            "status": "captured" if any(token_totals.values()) else "not-reported",
            **token_totals,
        },
        "quality": {
            "acceptedDecisionCount": len(accepted),
            "rawLlmDecisionCount": len(raw_decisions),
            "rawLlmSignalDecisionCount": len(signal_decisions),
            "rawLlmAcceptedCoverageCount": len(set(accepted) & raw_llm_keys),
            "rawLlmMissingAcceptedDecisionCount": len(missing_from_raw_llm),
            "rawLlmMissingAcceptedDecisions": missing_from_raw_llm,
            "rawLlmUnacceptedDecisionCount": len(unaccepted_raw_llm),
            "appliedDecisionCounts": {
                key: len(value) if isinstance(value, list) else 0 for key, value in applied.items()
            },
            "resolvedGapCount": len(_coerce_list(gaps.get("resolved"))),
            "blockingGapCount": len(_coerce_list(gaps.get("blocking"))),
            "rawGapCount": len(_coerce_list(gaps.get("raw"))),
            "blockingContradictionCount": len(_coerce_list(contradictions.get("blocking"))),
            "rawContradictionCount": len(_coerce_list(contradictions.get("raw"))),
            "parseErrorCount": parse_error_count,
        },
        "conformance": _model_conformance(
            mode=mode,
            readiness_status=str(readiness.get("status", "unknown")),
            blocker_count=blocker_count,
            accepted_count=len(accepted),
            missing_count=len(missing_from_raw_llm),
            parse_error_count=parse_error_count,
        ),
        "cost": {
            "status": "not-estimated",
            "reason": "No provider pricing table is configured in iac-llm-wrapper.",
        },
        "rawEvidence": {
            "path": raw_evidence.get("path", "not-requested"),
            "status": raw_evidence.get("status", "not-requested"),
        },
        "boundary": (
            "This artifact summarizes LLM behavior for evaluation and review; "
            "external observability tools may visualize it, but readiness remains "
            "owned by requirement graph and target contract checks."
        ),
        "calls": [
            {
                "provider": call.get("provider", "unknown"),
                "model": call.get("model", "unknown"),
                "latencyMs": call.get("latencyMs", 0.0),
                "tokenUsage": _dict(call.get("tokenUsage")),
                "parseError": call.get("parseError"),
            }
            for call in calls
        ],
    }


def _token_totals(calls: list[dict[str, Any]]) -> dict[str, int]:
    totals = {"promptTokens": 0, "completionTokens": 0, "totalTokens": 0}
    for call in calls:
        usage = _dict(call.get("tokenUsage"))
        totals["promptTokens"] += int(usage.get("prompt_tokens", usage.get("promptTokens", 0)) or 0)
        totals["completionTokens"] += int(
            usage.get("completion_tokens", usage.get("completionTokens", 0)) or 0
        )
        totals["totalTokens"] += int(usage.get("total_tokens", usage.get("totalTokens", 0)) or 0)
    return totals


def _model_conformance(
    *,
    mode: str,
    readiness_status: str,
    blocker_count: int,
    accepted_count: int,
    missing_count: int,
    parse_error_count: int,
) -> dict[str, Any]:
    reasons: list[str] = []
    if mode != "llm":
        return {
            "status": "not-applicable",
            "reason": "Deterministic runs do not measure model extraction quality.",
            "reasons": [],
        }
    if readiness_status != "ready" or blocker_count:
        reasons.append("handoff is not ready")
    if parse_error_count:
        reasons.append("LLM calls had parse errors")
    if missing_count:
        reasons.append("raw LLM missed accepted decisions")
    if not accepted_count:
        reasons.append("no accepted decisions to score")
    if not reasons:
        return {
            "status": "pass",
            "reason": "LLM run was ready with full raw coverage and no parse errors.",
            "reasons": [],
        }
    status = (
        "fail" if readiness_status != "ready" or blocker_count or parse_error_count else "review"
    )
    return {
        "status": status,
        "reason": "; ".join(reasons),
        "reasons": reasons,
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _coerce_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
