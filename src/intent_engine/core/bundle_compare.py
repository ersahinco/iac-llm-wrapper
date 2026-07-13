"""Compare generated handoff bundles for incremental review."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from .sample_config import SampleConfig
from .yaml_utils import read_yaml_mapping, write_yaml_artifact


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
    input_diff: dict[str, Any]
    lineage: list[dict[str, Any]]


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
    impacted_map = _impacted_requirement_map(
        decision_delta=decision_delta,
        requirement_delta=requirement_delta,
        artifact_delta=artifact_delta,
        sample_delta=sample_delta,
        after=after,
    )
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
        "inputDelta": _input_delta(before.input_diff, after.input_diff),
        "impactedRequirementMap": impacted_map,
        "artifactDelta": artifact_delta,
        "sampleRecommendationDelta": sample_delta,
        "modelDelta": model_delta,
    }


def write_bundle_comparison(report: dict[str, Any], output: Path) -> None:
    """Write a bundle comparison report as YAML."""
    write_yaml_artifact(output, report, "")


def write_bundle_comparison_html(report: dict[str, Any], output: Path) -> None:
    """Write a static HTML comparison page."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_bundle_comparison_html(report))


def render_bundle_comparison_html(report: dict[str, Any]) -> str:
    """Render a static HTML comparison page from a comparison report."""
    summary = _dict(report.get("summary"))
    readiness = _dict(report.get("readinessDelta"))
    decisions = _dict(report.get("decisionDelta"))
    artifacts = _dict(report.get("artifactDelta"))
    samples = _dict(report.get("sampleRecommendationDelta"))
    impacts = _coerce_list(report.get("impactedRequirementMap"))
    focus = _coerce_list(summary.get("reviewFocus"))
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>handoff comparison</title>",
            "<style>",
            _COMPARISON_CSS,
            "</style>",
            "</head>",
            "<body><main>",
            "<header><p>iac-llm-wrapper delta review</p><h1>handoff comparison</h1>"
            f"<strong>{escape(str(summary.get('status', 'unknown')))}</strong></header>",
            _html_section(
                "What Changed",
                [
                    _html_list(focus),
                    _html_kv("Before", str(summary.get("before", ""))),
                    _html_kv("After", str(summary.get("after", ""))),
                    _html_kv(
                        "Readiness",
                        f"{readiness.get('statusBefore')} -> {readiness.get('statusAfter')}",
                    ),
                    _html_kv(
                        "Handoff allowed",
                        f"{readiness.get('handoffAllowedBefore')} -> "
                        f"{readiness.get('handoffAllowedAfter')}",
                    ),
                ],
            ),
            _html_section(
                "What Must Be Reviewed",
                [
                    _html_list(_decision_review_lines(decisions)),
                    _html_named_list(
                        "Changed artifacts",
                        _coerce_list(artifacts.get("changed")),
                    ),
                    _html_table(
                        [
                            {
                                "requirement": item.get("requirementKey", ""),
                                "artifacts": ", ".join(
                                    str(name)
                                    for name in _coerce_list(item.get("changedDownstreamArtifacts"))
                                ),
                                "sampleImpact": str(item.get("sampleRecommendationImpact", "")),
                            }
                            for item in impacts
                            if isinstance(item, dict)
                        ]
                    ),
                ],
            ),
            _html_section(
                "What Stayed Stable",
                [
                    _html_kv("Artifact unchanged count", str(artifacts.get("unchangedCount", 0))),
                    _html_kv("Sample top before", str(samples.get("topBefore", "none"))),
                    _html_kv("Sample top after", str(samples.get("topAfter", "none"))),
                ],
            ),
            _html_section(
                "Artifact Delta",
                [
                    _html_named_list("Added", _coerce_list(artifacts.get("added"))),
                    _html_named_list("Changed", _coerce_list(artifacts.get("changed"))),
                    _html_named_list("Removed", _coerce_list(artifacts.get("removed"))),
                ],
            ),
            "</main></body></html>",
            "",
        ]
    )


def render_bundle_comparison_text(report: dict[str, Any]) -> str:
    """Render a terse terminal summary for a bundle comparison report."""
    summary = _dict(report.get("summary"))
    decision_delta = _dict(report.get("decisionDelta"))
    requirement_delta = _dict(report.get("requirementDelta"))
    artifact_delta = _dict(report.get("artifactDelta"))
    sample_delta = _dict(report.get("sampleRecommendationDelta"))
    readiness_delta = _dict(report.get("readinessDelta"))
    input_delta = _dict(report.get("inputDelta"))
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
    lines.extend(_text_decision_list("Added", _coerce_list(decision_delta.get("added"))))
    lines.extend(_text_decision_list("Changed", _coerce_list(decision_delta.get("changed"))))
    lines.extend(_text_decision_list("Removed", _coerce_list(decision_delta.get("removed"))))

    if input_delta.get("available"):
        lines.extend(
            [
                "",
                "Input delta:",
                f"  mode: {input_delta.get('mode', 'unknown')}",
                f"  changed lines: {input_delta.get('changedLineCount', 0)}",
                "  changed headings: "
                + ", ".join(str(item) for item in _coerce_list(input_delta.get("changedHeadings"))),
            ]
        )

    lines.extend(
        [
            "",
            "Artifact delta:",
            f"  added={len(_coerce_list(artifact_delta.get('added')))} "
            f"removed={len(_coerce_list(artifact_delta.get('removed')))} "
            f"changed={len(_coerce_list(artifact_delta.get('changed')))}",
        ]
    )
    lines.extend(_text_named_list("Added", _coerce_list(artifact_delta.get("added"))))
    lines.extend(_text_named_list("Changed", _coerce_list(artifact_delta.get("changed"))))
    lines.extend(_text_named_list("Removed", _coerce_list(artifact_delta.get("removed"))))

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


def _text_named_list(title: str, values: list[Any]) -> list[str]:
    if not values:
        return []
    lines = [f"  {title}:"]
    lines.extend(f"    - {value}" for value in values[:12])
    if len(values) > 12:
        lines.append(f"    ... {len(values) - 12} more")
    return lines


def _text_decision_list(title: str, values: list[Any]) -> list[str]:
    if not values:
        return []
    lines = [f"  {title}:"]
    lines.extend(f"    - {_decision_summary(value)}" for value in values[:12])
    if len(values) > 12:
        lines.append(f"    ... {len(values) - 12} more")
    return lines


def _load_bundle(path: Path) -> _BundleSnapshot:
    report = _read_yaml(path / "decision-report.yaml")
    trace = _read_yaml(path / "llm-trace-summary.yaml")
    benchmark = _read_yaml(path / "model-benchmark.yaml")
    handoff = _read_yaml(path / "handoff-plan.yaml")
    contract = _read_yaml(path / "contract-validation.yaml")
    input_diff = _read_yaml(path / "input-diff-report.yaml")
    lineage = _coerce_list(_read_yaml(path / "lineage-manifest.yaml").get("lineage"))
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
        input_diff=input_diff,
        lineage=[item for item in lineage if isinstance(item, dict)],
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    return read_yaml_mapping(path)


def _readiness(
    report: dict[str, Any],
    handoff: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    report_readiness = _dict(report.get("handoffReadiness"))
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
            handoff_readiness.get(
                "handoffAllowed",
                contract_readiness.get("handoffAllowed", False),
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


def _input_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    if not before and not after:
        return {
            "available": False,
            "changedHeadings": [],
            "changedStructuredDecisionLines": [],
            "likelyImpactedRequirements": [],
        }
    return {
        "available": bool(after),
        "changedHeadings": _coerce_list(after.get("changedHeadings")),
        "changedStructuredDecisionLines": _coerce_list(after.get("changedStructuredDecisionLines")),
        "likelyImpactedRequirements": _coerce_list(after.get("likelyImpactedRequirements")),
        "changedLineCount": after.get("changedLineCount", 0),
        "mode": _dict(after.get("source")).get("mode", "unknown"),
    }


def _impacted_requirement_map(
    *,
    decision_delta: dict[str, Any],
    requirement_delta: dict[str, Any],
    artifact_delta: dict[str, Any],
    sample_delta: dict[str, Any],
    after: _BundleSnapshot,
) -> list[dict[str, Any]]:
    lineage_by_decision: dict[str, list[dict[str, Any]]] = {}
    for item in after.lineage:
        decision = str(item.get("decision", ""))
        if decision:
            lineage_by_decision.setdefault(decision, []).append(item)
    changed_artifacts = set(_coerce_list(artifact_delta.get("changed")))
    sample_changed = bool(
        sample_delta.get("rankChanges")
        or sample_delta.get("scoreChanges")
        or sample_delta.get("added")
        or sample_delta.get("removed")
    )
    missing_added = set(_coerce_list(requirement_delta.get("missingDecisionsAdded")))
    missing_resolved = set(_coerce_list(requirement_delta.get("missingDecisionsResolved")))
    rows: list[dict[str, Any]] = []
    for item in _coerce_list(decision_delta.get("changed")):
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", ""))
        lineage = lineage_by_decision.get(key, [])
        artifacts = sorted(
            {str(entry.get("artifact", "")) for entry in lineage if entry.get("artifact")}
        )
        rows.append(
            {
                "requirementKey": key,
                "decisionBefore": item.get("before"),
                "decisionAfter": item.get("after"),
                "downstreamArtifacts": artifacts,
                "changedDownstreamArtifacts": [
                    artifact for artifact in artifacts if artifact in changed_artifacts
                ],
                "lineagePaths": [
                    {
                        "artifact": entry.get("artifact"),
                        "path": entry.get("path"),
                    }
                    for entry in lineage
                ],
                "sampleRecommendationImpact": sample_changed,
                "blockerImpact": {
                    "missingAdded": key in missing_added,
                    "missingResolved": key in missing_resolved,
                },
            }
        )
    return rows


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


def _decision_review_lines(decisions: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for title, key in (
        ("Added", "added"),
        ("Changed", "changed"),
        ("Removed", "removed"),
    ):
        for item in _coerce_list(decisions.get(key)):
            lines.append(f"{title}: {_decision_summary(item)}")
    return lines


def _decision_summary(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    key = item.get("key", "unknown")
    if "before" in item or "after" in item:
        return f"{key}: {item.get('before')} -> {item.get('after')}"
    return f"{key}: {item.get('value')}"


def _html_section(title: str, body: list[str]) -> str:
    return "\n".join(["<section>", f"<h2>{escape(title)}</h2>", *body, "</section>"])


def _html_kv(label: str, value: str) -> str:
    return f"<p><span>{escape(label)}</span><strong>{escape(value)}</strong></p>"


def _html_list(items: list[Any]) -> str:
    if not items:
        return '<p class="muted">None</p>'
    return "<ul>" + "".join(f"<li>{escape(str(item))}</li>" for item in items) + "</ul>"


def _html_named_list(title: str, items: list[Any]) -> str:
    return f"<h3>{escape(title)}</h3>{_html_list(items)}"


def _html_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="muted">None</p>'
    rendered = [
        "<table><tr><th>Requirement</th><th>Changed Artifacts</th><th>Sample Impact</th></tr>"
    ]
    for row in rows:
        rendered.append(
            "<tr>"
            f"<td>{escape(str(row.get('requirement', '')))}</td>"
            f"<td>{escape(str(row.get('artifacts', '')))}</td>"
            f"<td>{escape(str(row.get('sampleImpact', '')))}</td>"
            "</tr>"
        )
    rendered.append("</table>")
    return "".join(rendered)


_COMPARISON_CSS = """
:root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
body { margin: 0; background: #f7f7f5; color: #171717; }
main { max-width: 1040px; margin: 0 auto; padding: 32px 20px 56px; }
header { border-bottom: 1px solid #d8d8d2; margin-bottom: 24px; padding-bottom: 18px; }
header p { margin: 0 0 8px; color: #666; font-size: 13px; text-transform: uppercase; }
h1 { margin: 0 0 10px; font-size: 34px; letter-spacing: 0; }
h2 { margin: 0 0 14px; font-size: 20px; }
section { border-top: 1px solid #d8d8d2; padding: 22px 0; }
p { display: flex; gap: 16px; justify-content: space-between; margin: 8px 0; }
p span { color: #666; }
p strong { text-align: right; }
ul { margin: 0; padding-left: 20px; }
li { margin: 7px 0; }
table { border-collapse: collapse; width: 100%; background: white; }
th, td { border: 1px solid #d8d8d2; padding: 8px 10px; text-align: left; vertical-align: top; }
th { background: #eeeeea; }
.muted { display: block; color: #777; }
"""
