"""Standalone contract-validation artifact tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import ruamel.yaml

from intent_engine.core.contract_validation import (
    build_contract_validation,
    write_contract_validation,
)
from intent_engine.core.contracts import ArtifactContract, TargetContract
from intent_engine.core.patterns import GLOBAL_REGISTRY, Pattern
from intent_engine.core.requirements import Requirement, RequirementGraph


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    with path.open("w") as handle:
        yaml.dump(data, handle)


def _read_yaml(path: Path) -> dict[str, Any]:
    yaml = ruamel.yaml.YAML(typ="safe")
    data = yaml.load(path.read_text())
    assert isinstance(data, dict)
    return data


def _graph() -> RequirementGraph:
    graph = RequirementGraph()
    graph.add(
        Requirement(
            key="region",
            label="Region",
            question="Which region?",
            target_field="region",
        )
    )
    return graph


def _register_example_pattern() -> dict[str, Pattern]:
    original = dict(GLOBAL_REGISTRY._patterns)
    GLOBAL_REGISTRY.register(
        Pattern(
            name="contract-validation-example",
            description="Contract validation example",
            graph_factory=_graph,
            contracts=[
                TargetContract(
                    name="example-config",
                    kind="yaml-config",
                    source_url="https://example.com/config",
                    artifacts=[
                        ArtifactContract(name="config.yaml", required_paths=["region"]),
                    ],
                    required_decisions=["region"],
                )
            ],
        )
    )
    return original


def _write_ready_bundle(output_dir: Path, *, include_config: bool = True) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_yaml(
        output_dir / "decision-report.yaml",
        {
            "pattern": "contract-validation-example",
            "handoffReadiness": {
                "status": "ready",
                "handoffAllowed": True,
                "deploymentAllowed": True,
            },
            "deploymentReadiness": {
                "status": "ready",
                "handoffAllowed": True,
                "deploymentAllowed": True,
            },
        },
    )
    _write_yaml(
        output_dir / "handoff-plan.yaml",
        {
            "pattern": "contract-validation-example",
            "boundary": "handoff only",
            "allowedNextAction": "Review config.",
            "readiness": {"status": "ready", "handoffAllowed": True, "deploymentAllowed": True},
            "targetContracts": [
                {
                    "name": "example-config",
                    "kind": "yaml-config",
                    "requiredArtifacts": ["config.yaml"],
                }
            ],
            "steps": [
                {
                    "id": "review",
                    "title": "Review",
                    "owner": "Platform",
                    "dependsOn": [],
                    "manualGate": "approval",
                    "rollback": "re-run compile",
                }
            ],
            "manualGates": ["approval"],
            "rollback": ["re-run compile"],
        },
    )
    if include_config:
        _write_yaml(output_dir / "config.yaml", {"region": "eu-central-1"})


def _write_blocked_bundle(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    readiness = {
        "handoffAllowed": False,
        "deploymentAllowed": False,
        "status": "blocked",
        "summary": "Cannot hand off yet.",
        "blockers": [{"code": "REGION_REQUIRED", "message": "Region required."}],
        "missingDecisions": ["region"],
        "conflictingDecisions": [],
        "safeHandoffPath": ["Resolve region."],
    }
    _write_yaml(
        output_dir / "decision-report.yaml",
        {
            "pattern": "contract-validation-example",
            "handoffReadiness": readiness,
            "deploymentReadiness": readiness,
        },
    )
    _write_yaml(
        output_dir / "llm-trace-summary.yaml",
        {
            "pattern": "contract-validation-example",
            "provider": "none",
            "model": "none",
            "callCount": 0,
            "markdownDecisions": {},
            "markdownContradictions": [],
            "rawLlmDecisions": {},
            "acceptedDecisions": {},
            "appliedDecisions": {},
            "signalDecisions": {},
            "gaps": {"resolved": [], "blocking": [{"key": "region"}]},
            "contradictions": {"blocking": []},
            "handoffReadiness": {
                "handoffAllowed": False,
                "deploymentAllowed": False,
                "status": "blocked",
                "blockerCount": 1,
                "blockingGapCount": 1,
                "blockingContradictionCount": 0,
            },
            "deploymentReadiness": {
                "handoffAllowed": False,
                "deploymentAllowed": False,
                "status": "blocked",
                "blockerCount": 1,
                "blockingGapCount": 1,
                "blockingContradictionCount": 0,
            },
            "rawEvidence": {"path": "not-requested", "status": "not-requested"},
        },
    )
    _write_yaml(
        output_dir / "model-benchmark.yaml",
        {
            "schemaVersion": "intent-engine/model-benchmark/v1",
            "pattern": "contract-validation-example",
            "run": {"mode": "deterministic", "provider": "none", "model": "none", "callCount": 0},
            "readiness": {
                "status": "blocked",
                "handoffAllowed": False,
                "deploymentAllowed": False,
                "blockerCount": 1,
            },
            "latency": {"totalMs": 0, "averageMs": 0, "maxMs": 0},
            "tokens": {
                "status": "not-reported",
                "promptTokens": 0,
                "completionTokens": 0,
                "totalTokens": 0,
            },
            "quality": {
                "acceptedDecisionCount": 0,
                "rawLlmDecisionCount": 0,
                "rawLlmSignalDecisionCount": 0,
                "appliedDecisionCounts": {},
                "resolvedGapCount": 0,
                "blockingGapCount": 1,
                "rawGapCount": 1,
                "blockingContradictionCount": 0,
                "rawContradictionCount": 0,
                "parseErrorCount": 0,
            },
            "cost": {"status": "not-estimated"},
            "rawEvidence": {"path": "not-requested", "status": "not-requested"},
            "boundary": "artifact only",
            "calls": [],
        },
    )


def test_ready_bundle_validates_pattern_contracts_and_handoff_plan(tmp_path: Path):
    original = _register_example_pattern()
    try:
        _write_ready_bundle(tmp_path)

        result = build_contract_validation(tmp_path)

        assert result["summary"] == {
            "status": "pass",
            "contractCount": 2,
            "violationCount": 0,
        }
        assert [item["name"] for item in result["contracts"]] == [
            "example-config",
            "generic-handoff-plan",
        ]
    finally:
        GLOBAL_REGISTRY._patterns = original


def test_blocked_bundle_validates_blocked_assessment_only(tmp_path: Path):
    _write_blocked_bundle(tmp_path)

    result = build_contract_validation(tmp_path)

    assert result["summary"]["status"] == "pass"
    assert [item["name"] for item in result["contracts"]] == ["blocked-assessment-artifacts"]
    assert result["readiness"]["handoffAllowed"] is False
    assert result["readiness"]["deploymentAllowed"] is False


def test_unknown_ready_pattern_fails_without_guessing_contracts(tmp_path: Path):
    _write_yaml(
        tmp_path / "decision-report.yaml",
        {
            "pattern": "unknown-pattern",
            "handoffReadiness": {
                "status": "ready",
                "handoffAllowed": True,
                "deploymentAllowed": True,
            },
            "deploymentReadiness": {
                "status": "ready",
                "handoffAllowed": True,
                "deploymentAllowed": True,
            },
        },
    )
    _write_yaml(
        tmp_path / "handoff-plan.yaml",
        {"readiness": {"handoffAllowed": True, "deploymentAllowed": True}},
    )

    result = build_contract_validation(tmp_path)

    assert result["summary"] == {"status": "fail", "contractCount": 0, "violationCount": 0}
    assert result["contracts"] == []


def test_missing_required_artifact_produces_clear_violation(tmp_path: Path):
    original = _register_example_pattern()
    try:
        _write_ready_bundle(tmp_path, include_config=False)

        result = build_contract_validation(tmp_path)

        assert result["summary"]["status"] == "fail"
        example = result["contracts"][0]
        assert example["name"] == "example-config"
        assert example["violations"] == [
            {
                "code": "CONTRACT_REQUIRED_ARTIFACT_MISSING",
                "message": "Missing required file: config.yaml",
            }
        ]
    finally:
        GLOBAL_REGISTRY._patterns = original


def test_write_contract_validation_writes_stable_header_and_schema(tmp_path: Path):
    _write_blocked_bundle(tmp_path)

    path = write_contract_validation(tmp_path)

    text = path.read_text()
    assert text.startswith("# yaml-language-server: $schema=none\n")
    assert "validation artifact, not deployable configuration" in text
    assert _read_yaml(path)["schemaVersion"] == "intent-engine/contract-validation/v1"
