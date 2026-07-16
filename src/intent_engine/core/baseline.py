"""Baseline bundle readers for incremental compile."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .yaml_utils import load_bundle_yaml_mapping


@dataclass(frozen=True)
class BaselineBundle:
    """Trusted fields read once from a generated incremental baseline."""

    pattern: str
    decisions: dict[str, Any]
    summary: dict[str, Any]


def without_locked_decisions(
    decisions: dict[str, Any],
    locked_keys: set[str],
) -> dict[str, Any]:
    return {key: value for key, value in decisions.items() if key not in locked_keys}


def load_baseline_bundle(bundle: Path) -> BaselineBundle:
    """Load the required baseline reports without silent shape fallback."""
    report = load_bundle_yaml_mapping(bundle, "decision-report.yaml")
    trace = load_bundle_yaml_mapping(bundle, "llm-trace-summary.yaml")
    benchmark = load_bundle_yaml_mapping(bundle, "model-benchmark.yaml")

    accepted = trace.get("acceptedDecisions")
    if isinstance(accepted, dict) and accepted:
        decisions = accepted
    else:
        report_decisions = report.get("decisions")
        decisions = report_decisions if isinstance(report_decisions, dict) else {}

    readiness = report.get("handoffReadiness") or {}
    quality = benchmark.get("quality", {}) if isinstance(benchmark.get("quality"), dict) else {}
    pattern = str(report.get("pattern") or "")
    other_patterns = [
        str(value) for value in (trace.get("pattern"), benchmark.get("pattern")) if value
    ]
    if pattern and any(value != pattern for value in other_patterns):
        raise ValueError("incremental baseline reports declare different patterns")
    return BaselineBundle(
        pattern=pattern,
        decisions=decisions,
        summary={
            "pattern": pattern,
            "readiness": readiness,
            "acceptedDecisionCount": quality.get("acceptedDecisionCount"),
            "rawLlmCoverage": {
                "covered": quality.get("rawLlmAcceptedCoverageCount"),
                "accepted": quality.get("acceptedDecisionCount"),
            },
        },
    )
