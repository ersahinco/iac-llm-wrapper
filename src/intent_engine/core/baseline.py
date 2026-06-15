"""Baseline bundle readers for incremental compile."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .yaml_utils import read_yaml_mapping


def without_locked_decisions(
    decisions: dict[str, Any],
    locked_keys: set[str],
) -> dict[str, Any]:
    return {key: value for key, value in decisions.items() if key not in locked_keys}


def baseline_decisions_from_bundle(bundle: Path) -> dict[str, Any]:
    trace = read_yaml_mapping(bundle / "llm-trace-summary.yaml")
    accepted = trace.get("acceptedDecisions")
    if isinstance(accepted, dict) and accepted:
        return accepted
    sample = read_yaml_mapping(bundle / "sample-recommendations.yaml")
    current = sample.get("currentDecisions")
    if isinstance(current, dict) and current:
        return current
    report = read_yaml_mapping(bundle / "decision-report.yaml")
    decisions = report.get("decisions")
    return decisions if isinstance(decisions, dict) else {}


def baseline_summary_from_bundle(bundle: Path) -> dict[str, Any]:
    report = read_yaml_mapping(bundle / "decision-report.yaml")
    trace = read_yaml_mapping(bundle / "llm-trace-summary.yaml")
    benchmark = read_yaml_mapping(bundle / "model-benchmark.yaml")
    readiness = report.get("handoffReadiness") or {}
    quality = benchmark.get("quality", {}) if isinstance(benchmark.get("quality"), dict) else {}
    return {
        "pattern": report.get("pattern", trace.get("pattern", benchmark.get("pattern", "unknown"))),
        "readiness": readiness,
        "acceptedDecisionCount": quality.get("acceptedDecisionCount"),
        "rawLlmCoverage": {
            "covered": quality.get("rawLlmAcceptedCoverageCount"),
            "accepted": quality.get("acceptedDecisionCount"),
        },
    }
