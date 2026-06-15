"""Target capability semantic fact tests."""

from __future__ import annotations

from intent_engine.patterns.aws_lza.target_capabilities import (
    TargetCapability,
    TargetCapabilityType,
    UnsupportedAskFact,
    UnsupportedRequest,
    build_target_capability_report,
    extract_unsupported_ask_facts,
)


def _capabilities() -> list[TargetCapability]:
    return [
        TargetCapability(
            key="landing-zone",
            label="Landing zone",
            capability_type=TargetCapabilityType.ACCELERATOR,
            description="Landing-zone handoff",
            handled_decisions=("baseline",),
            unsupported_requests=(
                UnsupportedRequest(
                    key="workload-infrastructure",
                    label="Workload infrastructure",
                    keywords=("application stack", "rds"),
                    recommended_target=TargetCapabilityType.MODULE_COMPOSITION,
                    reason="Workload resources need a separate target.",
                ),
            ),
        ),
        TargetCapability(
            key="workload-modules",
            label="Workload modules",
            capability_type=TargetCapabilityType.MODULE_COMPOSITION,
            description="Approved workload modules",
            depends_on=("landing-zone",),
            manual_gates=("Select approved workload module.",),
        ),
    ]


def test_extracts_unsupported_ask_fact_with_evidence_span():
    facts = extract_unsupported_ask_facts(
        _capabilities(),
        "Landing zone first.\nNeeds an application stack with RDS later.",
    )

    assert facts == [
        UnsupportedAskFact(
            kind="workload-infrastructure",
            label="Workload infrastructure",
            evidence_span="Needs an application stack with RDS later.",
            recommended_target=TargetCapabilityType.MODULE_COMPOSITION,
            owned_by_pattern=False,
            detected_by="landing-zone",
            reason="Workload resources need a separate target.",
        )
    ]


def test_negated_unsupported_ask_does_not_create_fact():
    facts = extract_unsupported_ask_facts(
        _capabilities(),
        "Do not generate an application stack from this packet.",
    )

    assert facts == []


def test_capability_routing_uses_semantic_facts_not_raw_text():
    fact = UnsupportedAskFact(
        kind="workload-infrastructure",
        label="Workload infrastructure",
        evidence_span="Needs RDS later.",
        recommended_target=TargetCapabilityType.MODULE_COMPOSITION,
        owned_by_pattern=False,
        detected_by="landing-zone",
        reason="Workload resources need a separate target.",
    )

    report = build_target_capability_report(
        _capabilities(),
        {"baseline": "standard"},
        source_text="",
        unsupported_ask_facts=[fact],
    )

    assert report["selectedTargetPath"] == ["accelerator", "module-composition"]
    assert report["semanticFacts"]["unsupportedAsks"] == [fact.to_dict()]
    assert report["unsupportedGaps"] == [
        {
            "key": "workload-infrastructure",
            "label": "Workload infrastructure",
            "detectedBy": "landing-zone",
            "recommendedTarget": "module-composition",
            "reason": "Workload resources need a separate target.",
            "evidenceSpan": "Needs RDS later.",
            "ownedByPattern": False,
            "source": "deterministic-text",
        }
    ]
    assert "Select approved workload module." in report["manualGates"]
