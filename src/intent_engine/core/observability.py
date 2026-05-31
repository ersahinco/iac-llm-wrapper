"""Artifact-first LLM observability helpers."""

from __future__ import annotations

from typing import Any


def build_model_benchmark(extraction_summary: dict[str, Any]) -> dict[str, Any]:
    """Build a lean model benchmark from the existing trace summary."""
    calls = _list_of_dicts(extraction_summary.get("calls"))
    latencies = [float(call.get("latencyMs", 0) or 0) for call in calls]
    total_latency = round(sum(latencies), 1)
    token_totals = _token_totals(calls)
    readiness = _dict(extraction_summary.get("deploymentReadiness"))
    gaps = _dict(extraction_summary.get("gaps"))
    contradictions = _dict(extraction_summary.get("contradictions"))
    raw_evidence = _dict(extraction_summary.get("rawEvidence"))
    accepted = _dict(extraction_summary.get("acceptedDecisions"))
    raw_decisions = _dict(extraction_summary.get("rawLlmDecisions"))
    signal_decisions = _dict(extraction_summary.get("rawLlmSignalDecisions"))
    applied = _dict(extraction_summary.get("appliedDecisions"))

    return {
        "schemaVersion": "intent-engine/model-benchmark/v1",
        "pattern": extraction_summary.get("pattern", "unknown"),
        "run": {
            "mode": "llm" if calls else "deterministic",
            "provider": extraction_summary.get("provider", "none"),
            "model": extraction_summary.get("model", "none"),
            "callCount": len(calls),
        },
        "readiness": {
            "status": readiness.get("status", "unknown"),
            "deploymentAllowed": readiness.get("deploymentAllowed", False),
            "blockerCount": readiness.get("blockerCount", 0),
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
            "appliedDecisionCounts": {
                key: len(value) if isinstance(value, list) else 0 for key, value in applied.items()
            },
            "resolvedGapCount": len(_coerce_list(gaps.get("resolved"))),
            "blockingGapCount": len(_coerce_list(gaps.get("blocking"))),
            "rawGapCount": len(_coerce_list(gaps.get("raw"))),
            "blockingContradictionCount": len(_coerce_list(contradictions.get("blocking"))),
            "rawContradictionCount": len(_coerce_list(contradictions.get("raw"))),
            "parseErrorCount": sum(1 for call in calls if call.get("parseError")),
        },
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


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _coerce_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
