from __future__ import annotations

from pathlib import Path

from intent_engine.core.bundle_compare import (
    compare_handoff_bundles,
    render_bundle_comparison_html,
    render_bundle_comparison_text,
)


def test_compare_handoff_bundles_reports_blocker_and_sample_deltas(tmp_path: Path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir()
    after.mkdir()

    _write_bundle(
        before,
        status="blocked",
        handoff_allowed=False,
        blockers=["OLD_BLOCKER"],
        missing=["network_account"],
        decisions={"network_account": None, "home_region": "eu-central-1"},
        samples=[
            {"name": "sample-a", "sameDecisionCount": 8, "differentDecisionCount": 1},
            {"name": "sample-b", "sameDecisionCount": 7, "differentDecisionCount": 2},
        ],
        artifact_body="before",
    )
    _write_bundle(
        after,
        status="ready",
        handoff_allowed=True,
        blockers=[],
        missing=[],
        decisions={"network_account": "Network", "home_region": "eu-central-1"},
        samples=[
            {"name": "sample-b", "sameDecisionCount": 9, "differentDecisionCount": 0},
            {"name": "sample-a", "sameDecisionCount": 8, "differentDecisionCount": 1},
        ],
        artifact_body="after",
    )
    after.joinpath("incremental-compile-report.yaml").write_text("schemaVersion: test\n")

    report = compare_handoff_bundles(before, after)

    assert report["summary"]["status"] == "changed"
    assert report["readinessDelta"]["statusBefore"] == "blocked"
    assert report["readinessDelta"]["statusAfter"] == "ready"
    assert report["requirementDelta"]["blockersResolved"] == ["OLD_BLOCKER"]
    assert report["requirementDelta"]["missingDecisionsResolved"] == ["network_account"]
    assert report["decisionDelta"]["changed"] == [
        {"key": "network_account", "before": None, "after": "Network"}
    ]
    assert "target.yaml" in report["artifactDelta"]["changed"]
    assert report["sampleRecommendationDelta"]["topBefore"] == "sample-a"
    assert report["sampleRecommendationDelta"]["topAfter"] == "sample-b"
    assert report["sampleRecommendationDelta"]["rankChanges"]

    rendered = render_bundle_comparison_text(report)
    assert "Handoff Bundle Comparison" in rendered
    assert "OLD_BLOCKER" not in rendered
    assert "network_account" in rendered
    html = render_bundle_comparison_html(report)
    assert "Artifact Delta" in html
    assert "Added" in html
    assert "incremental-compile-report.yaml" in html
    assert "target.yaml" in html


def _write_bundle(
    path: Path,
    *,
    status: str,
    handoff_allowed: bool,
    blockers: list[str],
    missing: list[str],
    decisions: dict[str, object],
    samples: list[dict[str, object]],
    artifact_body: str,
) -> None:
    blocker_lines = (
        ["  blockers:"] + [f"    - code: {code}\n      message: {code}" for code in blockers]
        if blockers
        else ["  blockers: []"]
    )
    missing_lines = (
        ["  missingDecisions:"]
        + [f"    - key: {key}\n      label: {key}\n      reason: missing {key}" for key in missing]
        if missing
        else ["  missingDecisions: []"]
    )
    path.joinpath("decision-report.yaml").write_text(
        "\n".join(
            [
                "pattern: test-pattern",
                "handoffReadiness:",
                f"  handoffAllowed: {str(handoff_allowed).lower()}",
                f"  status: {status}",
                *blocker_lines,
                *missing_lines,
                "  conflictingDecisions: []",
                "",
            ]
        )
    )
    accepted = "\n".join(f"  {key}: {_yaml_scalar(value)}" for key, value in decisions.items())
    path.joinpath("llm-trace-summary.yaml").write_text(
        "\n".join(["pattern: test-pattern", "acceptedDecisions:", accepted, ""])
    )
    path.joinpath("model-benchmark.yaml").write_text(
        "\n".join(
            [
                "pattern: test-pattern",
                "quality:",
                f"  acceptedDecisionCount: {len(decisions)}",
                f"  blockingGapCount: {len(missing)}",
                "  blockingContradictionCount: 0",
                "  parseErrorCount: 0",
                "conformance:",
                "  status: not-applicable",
                "run:",
                "  mode: deterministic",
                "  provider: none",
                "  model: none",
                "",
            ]
        )
    )
    path.joinpath("sample-recommendations.yaml").write_text(
        "recommendations:\n"
        + "\n".join(
            "\n".join(
                [
                    f"  - name: {sample['name']}",
                    f"    sameDecisionCount: {sample['sameDecisionCount']}",
                    f"    differentDecisionCount: {sample['differentDecisionCount']}",
                    "    missingDecisionCount: 0",
                    "    totalSampleDecisions: 10",
                ]
            )
            for sample in samples
        )
        + "\n"
    )
    path.joinpath("target.yaml").write_text(artifact_body)


def _yaml_scalar(value: object) -> object:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    return value
