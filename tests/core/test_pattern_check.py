"""Pattern check helper tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from intent_engine.core.contracts import ArtifactContract, TargetContract
from intent_engine.core.pattern_check import check_pattern, validate_pattern_references
from intent_engine.core.patterns import Pattern, PatternGenerator, PatternRegistry
from intent_engine.core.policy import PolicyControl, PolicyPack, PolicyRequirementMapping
from intent_engine.core.requirements import Requirement, RequirementGraph
from intent_engine.core.sample_config import SampleConfig


class _TestIntent(BaseModel):
    region: str = ""
    network: str = ""
    mode: str = ""
    a: str = ""
    b: str = ""
    c: str = ""


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
    default: str | None = None,
    depends_on: list[str] | None = None,
    applies_when: dict[str, object] | None = None,
    blocked_when: dict[str, object] | None = None,
    violation_code: str | None = "REGION_REQUIRED",
    violation_message: str | None = "Region is required.",
) -> Requirement:
    return Requirement(
        key=key,
        label=label,
        question=question,
        target_field=target_field,
        default=default,
        depends_on=depends_on or [],
        applies_when=applies_when,
        blocked_when=blocked_when,
        violation_code=violation_code,
        violation_message=violation_message,
    )


def _noop_generator(_payload: object, _output_dir: Path) -> None:
    return None


def test_check_pattern_passes_for_minimal_valid_pattern(tmp_path: Path):
    pattern = Pattern(
        name="valid-pattern",
        description="Valid pattern",
        graph_factory=lambda: _graph(_requirement()),
        intent_factory=_TestIntent,
        prompt_context=(
            "This pattern captures approved region handoff context only. "
            "Extract the region decision for an existing target contract."
        ),
        contracts=[
            TargetContract(
                name="valid-contract",
                kind="yaml",
                source_url="https://example.com",
                artifacts=[ArtifactContract(name="config.yaml")],
                required_decisions=["region"],
            )
        ],
        generators=[PatternGenerator("config", _noop_generator, outputs=("config.yaml",))],
    )

    result = check_pattern(pattern, fixtures_root=tmp_path)

    assert result.passed
    assert result.requirements == 1
    assert result.contracts == 1
    assert result.expected_artifacts == 4
    assert result.samples == 0
    assert result.policy_packs == 0
    assert result.context_rules == 3


def test_check_pattern_reports_graph_factory_failure(tmp_path: Path):
    def broken_graph() -> RequirementGraph:
        raise RuntimeError("boom")

    pattern = Pattern(
        name="broken",
        description="Broken",
        graph_factory=broken_graph,
        intent_factory=_TestIntent,
    )

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
                violation_code=None,
                violation_message=None,
            )
        ),
        intent_factory=_TestIntent,
    )

    result = check_pattern(pattern, fixtures_root=tmp_path)

    assert "network: missing label" in result.violations
    assert "network: missing question" in result.violations
    assert "network: missing category" not in result.violations
    assert "network: missing target field" in result.violations
    assert (
        "network: required open requirement must define violation code and message"
        in result.violations
    )
    assert "network: unknown dependency missing" in result.violations


def test_check_pattern_reports_invalid_requirement_expressions(tmp_path: Path):
    pattern = Pattern(
        name="bad-expression",
        description="Bad expression",
        graph_factory=lambda: _graph(
            _requirement(key="mode"),
            _requirement(
                key="network",
                applies_when={"all": []},
                blocked_when={"bogus": {"decision": "mode"}},
            ),
        ),
        intent_factory=_TestIntent,
        prompt_context=(
            "This pattern captures approved region handoff context only. "
            "Extract the region decision for an existing target contract."
        ),
    )

    result = check_pattern(pattern, fixtures_root=tmp_path)

    assert "network: network.applies_when.all: must be a non-empty list" in result.violations
    assert "network: network.blocked_when: unsupported operator bogus" in result.violations
    assert (
        "network: network.blocked_when: expression must define exactly one operator"
        in result.violations
    )


def test_check_pattern_reports_requirement_cycles(tmp_path: Path):
    pattern = Pattern(
        name="cycle",
        description="Cycle",
        graph_factory=lambda: _graph(
            _requirement(key="a", depends_on=["c"]),
            _requirement(key="b", depends_on=["a"]),
            _requirement(key="c", depends_on=["b"]),
        ),
        intent_factory=_TestIntent,
        prompt_context=(
            "This pattern captures approved region handoff context only. "
            "Extract the region decision for an existing target contract."
        ),
    )

    result = check_pattern(pattern, fixtures_root=tmp_path)

    assert "requirement graph has a cycle: [('a', 'b'), ('b', 'c'), ('c', 'a')]" in (
        result.violations
    )


def test_check_pattern_reports_missing_or_vague_context(tmp_path: Path):
    missing_context = Pattern(
        name="missing-context",
        description="Missing context",
        graph_factory=lambda: _graph(_requirement()),
        intent_factory=_TestIntent,
    )

    missing_result = check_pattern(missing_context, fixtures_root=tmp_path)

    assert "prompt context is missing" in missing_result.violations
    assert missing_result.context_rules == 0

    vague_context = Pattern(
        name="vague-context",
        description="Vague context",
        graph_factory=lambda: _graph(_requirement()),
        intent_factory=_TestIntent,
        prompt_context="Use the document intelligently and make a good architecture plan.",
    )

    vague_result = check_pattern(vague_context, fixtures_root=tmp_path)

    assert "prompt context is too short to define extraction scope" in vague_result.violations
    assert "prompt context must say what the LLM extracts or captures" in vague_result.violations
    assert "prompt context must state a handoff, contract, or target boundary" in (
        vague_result.violations
    )
    assert vague_result.context_rules == 3


def test_check_pattern_reports_contract_and_empty_artifact_failures(tmp_path: Path):
    pattern = Pattern(
        name="bad-contract",
        description="Bad contract",
        graph_factory=lambda: _graph(_requirement()),
        intent_factory=_TestIntent,
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
    pattern = Pattern(
        name="sample-pattern",
        description="Sample pattern",
        graph_factory=lambda: _graph(_requirement()),
        intent_factory=_TestIntent,
        samples=[
            SampleConfig(
                name="sample-missing-fixture",
                pattern="sample-pattern",
                version="1.0.0",
                release_date="2026-01-01",
                source_url="https://example.com",
                fixture_dir="missing-fixture",
                decisions={"region": "eu-central-1"},
            )
        ],
    )

    result = check_pattern(pattern, fixtures_root=tmp_path)

    assert result.samples == 1
    assert (
        f"sample-missing-fixture: missing fixture dir {tmp_path / 'missing-fixture'}"
        in result.violations
    )


def test_check_pattern_reports_policy_mapping_failures(tmp_path: Path):
    pattern = Pattern(
        name="policy-pattern",
        description="Policy pattern",
        graph_factory=lambda: _graph(_requirement()),
        intent_factory=_TestIntent,
        prompt_context=(
            "This pattern captures approved region handoff context only. "
            "Extract the region decision for an existing target contract."
        ),
        contracts=[
            TargetContract(
                name="valid-contract",
                kind="yaml",
                source_url="https://example.com",
                artifacts=[ArtifactContract(name="config.yaml")],
                required_decisions=["region"],
            )
        ],
        policy_packs=[
            PolicyPack(
                name="regulated-test-v1",
                version="1.0.0",
                frameworks=["SOC2"],
                controls=[
                    PolicyControl(
                        id="CTRL-001",
                        title="Invalid mapping",
                        mapping=PolicyRequirementMapping(
                            requirement_keys=["missing"],
                            target_contracts=["missing-contract"],
                        ),
                    )
                ],
            )
        ],
    )

    result = check_pattern(pattern, fixtures_root=tmp_path)

    assert result.policy_packs == 1
    assert "regulated-test-v1:CTRL-001: unknown requirement missing" in result.violations
    assert (
        "regulated-test-v1:CTRL-001: unknown target contract missing-contract" in result.violations
    )


def test_registry_and_pattern_check_share_reference_validation(tmp_path: Path):
    pattern = Pattern(
        name="invalid-reference",
        description="Invalid reference pattern",
        graph_factory=lambda: _graph(_requirement()),
        intent_factory=_TestIntent,
        prompt_context=(
            "This pattern captures approved region handoff context only. "
            "Extract the region decision for an existing target contract."
        ),
        contracts=[
            TargetContract(
                name="invalid-contract",
                kind="yaml",
                source_url="https://example.com",
                artifacts=[ArtifactContract(name="config.yaml")],
                required_decisions=["missing"],
            )
        ],
        generators=[PatternGenerator("config", _noop_generator, outputs=("config.yaml",))],
    )
    graph = pattern.create_graph()
    references = validate_pattern_references(pattern, graph)

    assert len(references) == 1
    assert references[0].check_message in check_pattern(pattern, fixtures_root=tmp_path).violations
    with pytest.raises(ValueError, match="requires decision 'missing'"):
        PatternRegistry().register(pattern)


def test_registry_and_pattern_check_reject_unsafe_paths_consistently(tmp_path: Path):
    pattern = Pattern(
        name="unsafe-paths",
        description="Unsafe path references",
        graph_factory=lambda: _graph(_requirement()),
        intent_factory=_TestIntent,
        contracts=[
            TargetContract(
                name="valid-contract",
                kind="yaml",
                source_url="https://example.com",
                artifacts=[ArtifactContract(name="config.yaml")],
                required_decisions=["region"],
            )
        ],
        samples=[
            SampleConfig(
                name="unsafe-sample",
                pattern="unsafe-paths",
                version="1.0.0",
                release_date="2026-01-01",
                source_url="https://example.com",
                fixture_dir="../outside",
                decisions={"region": "eu-central-1"},
            )
        ],
        artifact_review_owners={"../review.yaml": "owner"},
        forbidden_artifacts=("/tmp/main.tf",),
    )

    result = check_pattern(pattern, fixtures_root=tmp_path)

    assert any("invalid fixture path ../outside" in item for item in result.violations)
    assert any("invalid artifact owner path ../review.yaml" in item for item in result.violations)
    assert any("invalid forbidden artifact path /tmp/main.tf" in item for item in result.violations)
    with pytest.raises(ValueError, match="invalid path"):
        PatternRegistry().register(pattern)


def test_pattern_generators_must_own_safe_unique_outputs(tmp_path: Path):
    pattern = Pattern(
        name="invalid-generators",
        description="Invalid generator ownership",
        graph_factory=lambda: _graph(_requirement()),
        intent_factory=_TestIntent,
        prompt_context=(
            "This pattern captures approved region handoff context only. "
            "Extract the region decision for an existing target contract."
        ),
        generators=[
            PatternGenerator("missing", _noop_generator),
            PatternGenerator("duplicate-a", _noop_generator, outputs=("config.yaml",)),
            PatternGenerator("duplicate-b", _noop_generator, outputs=("config.yaml",)),
            PatternGenerator("unsafe", _noop_generator, outputs=("../outside.yaml",)),
            PatternGenerator(
                "context-manifest",
                _noop_generator,
                outputs=("context-manifest.yaml",),
            ),
        ],
    )

    violations = check_pattern(pattern, fixtures_root=tmp_path).violations

    assert "generator missing: no declared outputs" in violations
    assert "artifact config.yaml has multiple generators: duplicate-a, duplicate-b" in violations
    assert any("invalid output path ../outside.yaml" in item for item in violations)
    assert "duplicate generator name context-manifest" in violations
    assert "generator context-manifest: output context-manifest.yaml is owned by core" in violations


def test_required_contract_artifact_must_have_a_generator(tmp_path: Path):
    pattern = Pattern(
        name="missing-generator",
        description="Missing contract artifact generator",
        graph_factory=lambda: _graph(_requirement()),
        intent_factory=_TestIntent,
        prompt_context=(
            "This pattern captures approved region handoff context only. "
            "Extract the region decision for an existing target contract."
        ),
        contracts=[
            TargetContract(
                name="missing-generator-contract",
                kind="yaml",
                source_url="https://example.com",
                artifacts=[ArtifactContract(name="config.yaml")],
                required_decisions=["region"],
            )
        ],
    )

    result = check_pattern(pattern, fixtures_root=tmp_path)

    assert (
        "missing-generator-contract: required artifact config.yaml has no generator"
        in result.violations
    )
    with pytest.raises(ValueError, match="required artifact 'config.yaml' has no generator"):
        PatternRegistry().register(pattern)


def test_core_generator_can_satisfy_required_contract_artifact(tmp_path: Path):
    pattern = Pattern(
        name="core-generated-contract",
        description="Core generated contract artifact",
        graph_factory=lambda: _graph(_requirement()),
        intent_factory=_TestIntent,
        prompt_context=(
            "This pattern captures approved region handoff context only. "
            "Extract the region decision for an existing target contract."
        ),
        contracts=[
            TargetContract(
                name="core-generated",
                kind="yaml",
                source_url="https://example.com",
                artifacts=[ArtifactContract(name="module-inputs.yaml")],
                required_decisions=["region"],
            )
        ],
    )

    assert check_pattern(pattern, fixtures_root=tmp_path).passed
