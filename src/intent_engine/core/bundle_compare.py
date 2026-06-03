"""Compare generated handoff bundles for incremental review."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ruamel.yaml

from .sample_config import SampleConfig


@dataclass(frozen=True)
class _BundleSnapshot:
    path: Path
    pattern: str
    decisions: dict[str, Any]
    readiness: dict[str, Any]
    requirement_metrics: dict[str, Any]
    artifacts: dict[str, str]
    samples: list[dict[str, Any]]
    model: dict[str, Any]


def compare_handoff_bundles(before_dir: Path, after_dir: Path) -> dict[str, Any]:
    """Return a compact comparison report for two generated handoff bundles."""
    before = _load_bundle(before_dir)
    after = _load_bundle(after_dir)
    decision_delta = _decision_delta(before.decisions, after.decisions)
    requirement_delta = _requirement_delta(before, after)
    artifact_delta = _artifact_delta(before.artifacts, after.artifacts)
    sample_delta = _sample_delta(before.samples, after.samples)
    readiness_delta = _readiness_delta(before.readiness, after.readiness)
    model_delta = _model_delta(before.model, after.model)
    review_focus = _review_focus(
        decision_delta=decision_delta,
        requirement_delta=requirement_delta,
        artifact_delta=artifact_delta,
        sample_delta=sample_delta,
        readiness_delta=readiness_delta,
        model_delta=model_delta,
    )

    changed = any(
        [
            decision_delta["added"],
            decision_delta["removed"],
            decision_delta["changed"],
            requirement_delta["missingDecisionsAdded"],
            requirement_delta["missingDecisionsResolved"],
            requirement_delta["blockersAdded"],
            requirement_delta["blockersResolved"],
            artifact_delta["added"],
            artifact_delta["removed"],
            artifact_delta["changed"],
            sample_delta["added"],
            sample_delta["removed"],
            sample_delta["rankChanges"],
            sample_delta["scoreChanges"],
            readiness_delta["changed"],
            model_delta["changed"],
        ]
    )

    return {
        "schemaVersion": "intent-engine/handoff-comparison/v1",
        "summary": {
            "status": "changed" if changed else "unchanged",
            "before": str(before.path),
            "after": str(after.path),
            "patternBefore": before.pattern,
            "patternAfter": after.pattern,
            "decisionChangeCount": len(decision_delta["changed"]),
            "decisionAddedCount": len(decision_delta["added"]),
            "decisionRemovedCount": len(decision_delta["removed"]),
            "artifactChangedCount": len(artifact_delta["changed"]),
            "artifactAddedCount": len(artifact_delta["added"]),
            "artifactRemovedCount": len(artifact_delta["removed"]),
            "blockersAddedCount": len(requirement_delta["blockersAdded"]),
            "blockersResolvedCount": len(requirement_delta["blockersResolved"]),
            "sampleRankChangeCount": len(sample_delta["rankChanges"]),
            "reviewFocus": review_focus,
        },
        "readinessDelta": readiness_delta,
        "requirementDelta": requirement_delta,
        "decisionDelta": decision_delta,
        "artifactDelta": artifact_delta,
        "sampleRecommendationDelta": sample_delta,
        "modelDelta": model_delta,
    }


def write_bundle_comparison(report: dict[str, Any], output: Path) -> None:
    """Write a bundle comparison report as YAML."""
    output.parent.mkdir(parents=True, exist_ok=True)
    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    with output.open("w") as file:
        yaml.dump(report, file)


def render_bundle_comparison_text(report: dict[str, Any]) -> str:
    """Render a terse terminal summary for a bundle comparison report."""
    summary = _dict(report.get("summary"))
    decision_delta = _dict(report.get("decisionDelta"))
    requirement_delta = _dict(report.get("requirementDelta"))
    artifact_delta = _dict(report.get("artifactDelta"))
    sample_delta = _dict(report.get("sampleRecommendationDelta"))
    readiness_delta = _dict(report.get("readinessDelta"))
    lines = [
        "=== Handoff Bundle Comparison ===",
        "",
        f"Status: {summary.get('status', 'unknown')}",
        f"Before: {summary.get('before', '')}",
        f"After:  {summary.get('after', '')}",
        f"Pattern: {summary.get('patternBefore', '')} -> {summary.get('patternAfter', '')}",
        "",
        "Review focus:",
    ]
    focus = _coerce_list(summary.get("reviewFocus"))
    lines.extend(f"  - {item}" for item in focus) if focus else lines.append("  - No deltas found.")

    lines.extend(
        [
            "",
            "Readiness:",
            f"  status: {readiness_delta.get('statusBefore')} -> "
            f"{readiness_delta.get('statusAfter')}",
            f"  handoffAllowed: {readiness_delta.get('handoffAllowedBefore')} -> "
            f"{readiness_delta.get('handoffAllowedAfter')}",
            "",
            "Requirement completeness:",
            f"  accepted decisions: "
            f"{_nested(requirement_delta, 'before', 'acceptedDecisionCount')} -> "
            f"{_nested(requirement_delta, 'after', 'acceptedDecisionCount')}",
            f"  missing decisions: "
            f"{_nested(requirement_delta, 'before', 'missingDecisionCount')} -> "
            f"{_nested(requirement_delta, 'after', 'missingDecisionCount')}",
            f"  blockers: {_nested(requirement_delta, 'before', 'blockerCount')} -> "
            f"{_nested(requirement_delta, 'after', 'blockerCount')}",
            "",
            "Decision delta:",
            f"  added={len(_coerce_list(decision_delta.get('added')))} "
            f"removed={len(_coerce_list(decision_delta.get('removed')))} "
            f"changed={len(_coerce_list(decision_delta.get('changed')))}",
        ]
    )
    for item in _coerce_list(decision_delta.get("changed"))[:10]:
        if isinstance(item, dict):
            lines.append(f"  - {item.get('key')}: {item.get('before')} -> {item.get('after')}")

    lines.extend(
        [
            "",
            "Artifact delta:",
            f"  added={len(_coerce_list(artifact_delta.get('added')))} "
            f"removed={len(_coerce_list(artifact_delta.get('removed')))} "
            f"changed={len(_coerce_list(artifact_delta.get('changed')))}",
        ]
    )
    for name in _coerce_list(artifact_delta.get("changed"))[:12]:
        lines.append(f"  - {name}")

    lines.extend(
        [
            "",
            "Sample recommendation delta:",
            f"  top: {sample_delta.get('topBefore', 'none')} -> "
            f"{sample_delta.get('topAfter', 'none')}",
            f"  added={len(_coerce_list(sample_delta.get('added')))} "
            f"removed={len(_coerce_list(sample_delta.get('removed')))} "
            f"rankChanges={len(_coerce_list(sample_delta.get('rankChanges')))} "
            f"scoreChanges={len(_coerce_list(sample_delta.get('scoreChanges')))}",
        ]
    )
    return "\n".join(lines) + "\n"


def _load_bundle(path: Path) -> _BundleSnapshot:
    report = _read_yaml(path / "decision-report.yaml")
    trace = _read_yaml(path / "llm-trace-summary.yaml")
    benchmark = _read_yaml(path / "model-benchmark.yaml")
    handoff = _read_yaml(path / "handoff-plan.yaml")
    contract = _read_yaml(path / "contract-validation.yaml")
    samples = _coerce_list(_read_yaml(path / "sample-recommendations.yaml").get("recommendations"))
    readiness = _readiness(report, handoff, contract)
    decisions = _decisions(report, trace, path)
    metrics = _requirement_metrics(decisions, readiness, trace, benchmark)
    return _BundleSnapshot(
        path=path,
        pattern=str(
            report.get("pattern") or trace.get("pattern") or benchmark.get("pattern") or ""
        ),
        decisions=decisions,
        readiness=readiness,
        requirement_metrics=metrics,
        artifacts=_artifact_hashes(path),
        samples=[item for item in samples if isinstance(item, dict)],
        model=_model(benchmark),
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    yaml = ruamel.yaml.YAML(typ="safe")
    data = yaml.load(path.read_text())
    return data if isinstance(data, dict) else {}


def _readiness(
    report: dict[str, Any],
    handoff: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    report_readiness = _dict(report.get("handoffReadiness") or report.get("deploymentReadiness"))
    handoff_readiness = _dict(handoff.get("readiness"))
    contract_readiness = _dict(contract.get("readiness"))
    status = str(
        report_readiness.get(
            "status",
            handoff_readiness.get("status", contract_readiness.get("status", "unknown")),
        )
    )
    allowed = bool(
        report_readiness.get(
            "handoffAllowed",
            report_readiness.get(
                "deploymentAllowed",
                handoff_readiness.get(
                    "handoffAllowed",
                    handoff_readiness.get(
                        "deploymentAllowed",
                        contract_readiness.get("handoffAllowed", False),
                    ),
                ),
            ),
        )
    )
    return {
        "status": status,
        "handoffAllowed": allowed,
        "blockers": _coerce_list(report_readiness.get("blockers")),
        "missingDecisions": _coerce_list(report_readiness.get("missingDecisions")),
        "conflictingDecisions": _coerce_list(report_readiness.get("conflictingDecisions")),
    }


def _decisions(
    report: dict[str, Any],
    trace: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    accepted = _dict(trace.get("acceptedDecisions"))
    if accepted:
        return {key: _to_builtin(value) for key, value in accepted.items()}
    current = _dict(_read_yaml(path / "sample-recommendations.yaml").get("currentDecisions"))
    if current:
        return {key: _to_builtin(value) for key, value in current.items()}
    return _flatten_report_decisions(report)


def _flatten_report_decisions(report: dict[str, Any]) -> dict[str, Any]:
    ignored = {
        "pattern",
        "handoffReadiness",
        "deploymentReadiness",
        "schemaVersion",
        "boundary",
    }
    flat: dict[str, Any] = {}

    def visit(value: Any, prefix: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                next_key = f"{prefix}.{key}" if prefix else str(key)
                visit(item, next_key)
            return
        flat[prefix] = _to_builtin(value)

    for key, value in report.items():
        if key in ignored:
            continue
        visit(value, str(key))
    return flat


def _requirement_metrics(
    decisions: dict[str, Any],
    readiness: dict[str, Any],
    trace: dict[str, Any],
    benchmark: dict[str, Any],
) -> dict[str, Any]:
    quality = _dict(benchmark.get("quality"))
    missing = _coerce_list(readiness.get("missingDecisions"))
    blockers = _coerce_list(readiness.get("blockers"))
    return {
        "acceptedDecisionCount": int(quality.get("acceptedDecisionCount", len(decisions)) or 0),
        "missingDecisionCount": len(missing),
        "blockingGapCount": int(quality.get("blockingGapCount", _trace_count(trace, "gaps")) or 0),
        "blockingContradictionCount": int(
            quality.get("blockingContradictionCount", _trace_count(trace, "contradictions")) or 0
        ),
        "blockerCount": len(blockers),
        "missingDecisionKeys": _missing_keys(missing),
        "blockerCodes": _blocker_codes(blockers),
    }


def _model(benchmark: dict[str, Any]) -> dict[str, Any]:
    quality = _dict(benchmark.get("quality"))
    conformance = _dict(benchmark.get("conformance"))
    run = _dict(benchmark.get("run"))
    accepted = int(quality.get("acceptedDecisionCount", 0) or 0)
    covered = int(quality.get("rawLlmAcceptedCoverageCount", 0) or 0)
    return {
        "mode": run.get("mode", "unknown"),
        "provider": run.get("provider", "unknown"),
        "model": run.get("model", "unknown"),
        "conformance": conformance.get("status", "unknown"),
        "rawCoverage": f"{covered}/{accepted}",
        "parseErrorCount": int(quality.get("parseErrorCount", 0) or 0),
    }


def _artifact_hashes(path: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    if not path.exists():
        return hashes
    for item in sorted(path.iterdir()):
        if not item.is_file() or item.name.startswith("."):
            continue
        hashes[item.name] = hashlib.sha256(item.read_bytes()).hexdigest()
    return hashes


def _decision_delta(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    for key in sorted(set(before) | set(after)):
        if key not in before:
            added.append({"key": key, "value": after[key]})
        elif key not in after:
            removed.append({"key": key, "value": before[key]})
        elif not _values_match(before[key], after[key]):
            changed.append({"key": key, "before": before[key], "after": after[key]})
    return {"added": added, "removed": removed, "changed": changed}


def _requirement_delta(before: _BundleSnapshot, after: _BundleSnapshot) -> dict[str, Any]:
    before_missing = set(before.requirement_metrics.get("missingDecisionKeys", []))
    after_missing = set(after.requirement_metrics.get("missingDecisionKeys", []))
    before_blockers = set(before.requirement_metrics.get("blockerCodes", []))
    after_blockers = set(after.requirement_metrics.get("blockerCodes", []))
    return {
        "before": before.requirement_metrics,
        "after": after.requirement_metrics,
        "missingDecisionsAdded": sorted(after_missing - before_missing),
        "missingDecisionsResolved": sorted(before_missing - after_missing),
        "blockersAdded": sorted(after_blockers - before_blockers),
        "blockersResolved": sorted(before_blockers - after_blockers),
    }


def _artifact_delta(before: dict[str, str], after: dict[str, str]) -> dict[str, Any]:
    before_names = set(before)
    after_names = set(after)
    common = before_names & after_names
    changed = sorted(name for name in common if before[name] != after[name])
    return {
        "added": sorted(after_names - before_names),
        "removed": sorted(before_names - after_names),
        "changed": changed,
        "unchangedCount": len(common) - len(changed),
    }


def _sample_delta(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> dict[str, Any]:
    before_by_name = _sample_index(before)
    after_by_name = _sample_index(after)
    before_names = set(before_by_name)
    after_names = set(after_by_name)
    rank_changes: list[dict[str, Any]] = []
    score_changes: list[dict[str, Any]] = []
    for name in sorted(before_names & after_names):
        before_item = before_by_name[name]
        after_item = after_by_name[name]
        if before_item["rank"] != after_item["rank"]:
            rank_changes.append(
                {"name": name, "before": before_item["rank"], "after": after_item["rank"]}
            )
        before_score = _sample_score(before_item["item"])
        after_score = _sample_score(after_item["item"])
        if before_score != after_score:
            score_changes.append({"name": name, "before": before_score, "after": after_score})
    return {
        "topBefore": before[0].get("name") if before else None,
        "topAfter": after[0].get("name") if after else None,
        "added": sorted(after_names - before_names),
        "removed": sorted(before_names - after_names),
        "rankChanges": rank_changes,
        "scoreChanges": score_changes,
    }


def _readiness_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changed: list[str] = []
    if before.get("status") != after.get("status"):
        changed.append("status")
    if before.get("handoffAllowed") != after.get("handoffAllowed"):
        changed.append("handoffAllowed")
    return {
        "statusBefore": before.get("status", "unknown"),
        "statusAfter": after.get("status", "unknown"),
        "handoffAllowedBefore": before.get("handoffAllowed", False),
        "handoffAllowedAfter": after.get("handoffAllowed", False),
        "changed": changed,
    }


def _model_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changed = [
        key
        for key in sorted(set(before) | set(after))
        if before.get(key, "unknown") != after.get(key, "unknown")
    ]
    return {"before": before, "after": after, "changed": changed}


def _review_focus(
    *,
    decision_delta: dict[str, Any],
    requirement_delta: dict[str, Any],
    artifact_delta: dict[str, Any],
    sample_delta: dict[str, Any],
    readiness_delta: dict[str, Any],
    model_delta: dict[str, Any],
) -> list[str]:
    focus: list[str] = []
    if readiness_delta["changed"]:
        focus.append("Readiness changed; review blocker and handoff allowance deltas first.")
    if requirement_delta["blockersAdded"]:
        focus.append("New blockers appeared; do not hand off until they are resolved.")
    if requirement_delta["blockersResolved"]:
        focus.append("Blockers were resolved; confirm the updated source decisions.")
    decision_count = (
        len(decision_delta["added"])
        + len(decision_delta["removed"])
        + len(decision_delta["changed"])
    )
    if decision_count:
        focus.append(f"{decision_count} accepted decision delta(s) require reviewer attention.")
    artifact_count = (
        len(artifact_delta["added"])
        + len(artifact_delta["removed"])
        + len(artifact_delta["changed"])
    )
    if artifact_count:
        focus.append(f"{artifact_count} artifact file delta(s) were detected by hash.")
    if sample_delta["rankChanges"] or sample_delta["scoreChanges"]:
        focus.append("Sample recommendation ranking or match scores changed.")
    if model_delta["changed"]:
        focus.append("Model or extraction quality metrics changed.")
    if not focus:
        focus.append("No decision, requirement, artifact, model, or sample deltas detected.")
    return focus


def _sample_index(samples: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for rank, item in enumerate(samples, 1):
        name = str(item.get("name", ""))
        if name:
            index[name] = {"rank": rank, "item": item}
    return index


def _sample_score(item: dict[str, Any]) -> dict[str, int]:
    return {
        "same": int(item.get("sameDecisionCount", 0) or 0),
        "different": int(item.get("differentDecisionCount", 0) or 0),
        "missing": int(item.get("missingDecisionCount", 0) or 0),
        "total": int(item.get("totalSampleDecisions", 0) or 0),
    }


def _missing_keys(items: list[Any]) -> list[str]:
    keys: list[str] = []
    for item in items:
        if isinstance(item, dict) and item.get("key"):
            keys.append(str(item["key"]))
    return sorted(keys)


def _blocker_codes(items: list[Any]) -> list[str]:
    codes: list[str] = []
    for item in items:
        if isinstance(item, dict) and item.get("code"):
            codes.append(str(item["code"]))
    return sorted(codes)


def _trace_count(trace: dict[str, Any], section: str) -> int:
    values = _dict(trace.get(section))
    return len(_coerce_list(values.get("blocking")))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _nested(data: dict[str, Any], section: str, key: str) -> Any:
    return _dict(data.get(section)).get(key, "unknown")


def _to_builtin(value: Any) -> Any:
    return SampleConfig.to_builtin(value)


def _values_match(before: Any, after: Any) -> bool:
    return bool(SampleConfig._canonical_value(before) == SampleConfig._canonical_value(after))
