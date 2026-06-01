"""Pattern check helper tests."""

from __future__ import annotations

from pathlib import Path

from intent_engine.core.contracts import ArtifactContract, TargetContract
from intent_engine.core.pattern_check import check_pattern
from intent_engine.core.patterns import Pattern
from intent_engine.core.requirements import Requirement, RequirementGraph
from intent_engine.core.sample_config import GLOBAL_SAMPLE_REGISTRY, SampleConfig


def _graph(*requirements: Requirement) -> RequirementGraph:
    graph = RequirementGraph()
    for requirement in requirements:
        graph.add(requirement)
    return graph


def _requirement(
    key: str = "region",
    *,
    label: str = "Region",
    question: str = "Which region?",
    target_field: str | None = "region",
    depends_on: list[str] | None = None,
) -> Requirement:
    return Requirement(
        key=key,
        label=label,
        question=question,
        target_field=target_field,
        depends_on=depends_on or [],
    )


def test_check_pattern_passes_for_minimal_valid_pattern(tmp_path: Path):
    pattern = Pattern(
        name="valid-pattern",
        description="Valid pattern",
        graph_factory=lambda: _graph(_requirement()),
        contracts=[
            TargetContract(
                name="valid-contract",
                kind="yaml",
                source_url="https://example.com",
                artifacts=[ArtifactContract(name="config.yaml")],
                required_decisions=["region"],
            )
        ],
    )

    result = check_pattern(pattern, fixtures_root=tmp_path)

    assert result.passed
    assert result.requirements == 1
    assert result.contracts == 1
    assert result.expected_artifacts == 2
    assert result.samples == 0


def test_check_pattern_reports_graph_factory_failure(tmp_path: Path):
    def broken_graph() -> RequirementGraph:
        raise RuntimeError("boom")

    pattern = Pattern(name="broken", description="Broken", graph_factory=broken_graph)

    result = check_pattern(pattern, fixtures_root=tmp_path)

    assert not result.passed
    assert result.violations == ["graph factory failed: boom"]


def test_check_pattern_reports_requirement_metadata_and_dependency_failures(tmp_path: Path):
    pattern = Pattern(
        name="bad-graph",
        description="Bad graph",
        graph_factory=lambda: _graph(
            _requirement(
                key="network",
                label="",
                question="",
                target_field=None,
                depends_on=["missing"],
            )
        ),
    )

    result = check_pattern(pattern, fixtures_root=tmp_path)

    assert "network: missing label" in result.violations
    assert "network: missing question" in result.violations
    assert "network: missing target field" in result.violations
    assert "network: unknown dependency missing" in result.violations


def test_check_pattern_reports_contract_and_empty_artifact_failures(tmp_path: Path):
    pattern = Pattern(
        name="bad-contract",
        description="Bad contract",
        graph_factory=lambda: _graph(_requirement()),
        contracts=[
            TargetContract(
                name="bad-contract",
                kind="yaml",
                source_url="https://example.com",
                artifacts=[ArtifactContract(name="config.yaml"), ArtifactContract(name="")],
                required_decisions=["missing"],
            )
        ],
    )

    result = check_pattern(pattern, fixtures_root=tmp_path)

    assert (
        "bad-contract: Contract 'bad-contract' requires decision 'missing', "
        "but graph has no matching requirement."
    ) in result.violations
    assert "expected artifact list contains an empty name" in result.violations


def test_check_pattern_reports_missing_sample_fixture(tmp_path: Path):
    original_samples = dict(GLOBAL_SAMPLE_REGISTRY._samples)
    try:
        GLOBAL_SAMPLE_REGISTRY.register(
            SampleConfig(
                name="sample-missing-fixture",
                pattern="sample-pattern",
                version="1.0.0",
                release_date="2026-01-01",
                source_url="https://example.com",
                fixture_dir="missing-fixture",
                decisions={"region": "eu-central-1"},
            )
        )
        pattern = Pattern(
            name="sample-pattern",
            description="Sample pattern",
            graph_factory=lambda: _graph(_requirement()),
        )

        result = check_pattern(pattern, fixtures_root=tmp_path)

        assert result.samples == 1
        assert (
            f"sample-missing-fixture: missing fixture dir {tmp_path / 'missing-fixture'}"
            in result.violations
        )
    finally:
        GLOBAL_SAMPLE_REGISTRY._samples = original_samples
