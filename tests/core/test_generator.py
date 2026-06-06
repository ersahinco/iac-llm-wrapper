"""Tests for modular generator registry (generic core)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import ruamel.yaml

from intent_engine.core.contracts import ArtifactContract, TargetContract
from intent_engine.core.generator import (
    GeneratorRegistry,
    _hcl_value,
    gen_context_manifest,
    gen_handoff_plan,
    gen_sample_recommendations,
    gen_tfvars,
    generate_all,
)
from intent_engine.core.module_mapping import DesignDocument, IaCIntentPayload, ModuleInputs
from intent_engine.core.patterns import GLOBAL_REGISTRY, Pattern
from intent_engine.core.requirements import Requirement, RequirementGraph
from intent_engine.core.sample_config import GLOBAL_SAMPLE_REGISTRY, SampleConfig


def _yaml_load(path: Path) -> dict:
    yaml = ruamel.yaml.YAML(typ="safe")
    data = yaml.load(path.read_text())
    assert isinstance(data, dict)
    return data


def _handoff_graph() -> RequirementGraph:
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


def _register_handoff_pattern() -> dict[str, Pattern]:
    original = dict(GLOBAL_REGISTRY._patterns)
    GLOBAL_REGISTRY.register(
        Pattern(
            name="handoff-semantic-test",
            description="Handoff semantic test",
            graph_factory=_handoff_graph,
            prompt_context=(
                "This pattern captures approved region handoff context only. "
                "Extract the region decision for an existing target contract."
            ),
            contracts=[
                TargetContract(
                    name="handoff-test-contract",
                    kind="yaml-config",
                    source_url="https://example.com/contract",
                    artifacts=[
                        ArtifactContract(name="network-config.yaml"),
                        ArtifactContract(name="security-config.yaml"),
                    ],
                    required_decisions=["region"],
                )
            ],
        )
    )
    return original


class TestGeneratorRegistry:
    def test_register_and_list(self):
        reg = GeneratorRegistry()

        def fake_gen(intent: object, output_dir: Path) -> None:
            pass

        reg.register("fake", fake_gen, priority=10, category="test")
        assert "fake" in reg.list()

    def test_priority_ordering(self):
        reg = GeneratorRegistry()
        order: list[str] = []

        def gen_a(intent: object, output_dir: Path) -> None:
            order.append("a")

        def gen_b(intent: object, output_dir: Path) -> None:
            order.append("b")

        reg.register("b", gen_b, priority=20)
        reg.register("a", gen_a, priority=10)
        reg.generate(object(), Path("/tmp"))
        assert order == ["a", "b"]

    def test_registries_are_independent(self):
        reg1 = GeneratorRegistry()
        reg2 = GeneratorRegistry()

        def fake_gen(intent: object, output_dir: Path) -> None:
            pass

        reg1.register("a", fake_gen)
        assert "a" in reg1.list()
        assert "a" not in reg2.list()

    def test_register_with_category(self):
        reg = GeneratorRegistry()

        def fake_gen(intent: object, output_dir: Path) -> None:
            pass

        reg.register("cat_gen", fake_gen, category="custom")
        assert "cat_gen" in reg.list()

    def test_scoped_generator_runs_only_for_matching_pattern(self):
        reg = GeneratorRegistry()
        called: list[str] = []

        def scoped_gen(intent: object, output_dir: Path) -> None:
            called.append("scoped")

        def shared_gen(intent: object, output_dir: Path) -> None:
            called.append("shared")

        reg.register("shared", shared_gen)
        reg.register("scoped", scoped_gen, applies_to={"aws-lza"})

        reg.generate(object(), Path("/tmp"), pattern="kubernetes-cluster")

        assert called == ["shared"]

    def test_scoped_generator_runs_for_matching_pattern(self):
        reg = GeneratorRegistry()
        called: list[str] = []

        def scoped_gen(intent: object, output_dir: Path) -> None:
            called.append("scoped")

        reg.register("scoped", scoped_gen, applies_to={"aws-lza"})

        reg.generate(object(), Path("/tmp"), pattern="aws-lza")

        assert called == ["scoped"]


class TestHCLValue:
    def test_string(self):
        assert _hcl_value("hello") == '"hello"'

    def test_bool_true(self):
        assert _hcl_value(True) == "true"

    def test_bool_false(self):
        assert _hcl_value(False) == "false"

    def test_int(self):
        assert _hcl_value(42) == "42"

    def test_float(self):
        assert _hcl_value(3.14) == "3.14"

    def test_list(self):
        assert _hcl_value(["a", "b"]) == '["a", "b"]'

    def test_nested_list(self):
        assert _hcl_value([1, True, "x"]) == '[1, true, "x"]'

    def test_empty_list(self):
        assert _hcl_value([]) == "[]"


class TestGenTFVars:
    def test_writes_file(self, tmp_path: Path):
        payload = IaCIntentPayload(
            design_doc=DesignDocument(),
            module_inputs=[
                ModuleInputs(
                    module_name="lza-network",
                    variables={"cidr": "10.0.0.0/16", "enable_logs": True},
                )
            ],
            intent=None,
        )
        gen_tfvars(payload, tmp_path)
        tfvars = tmp_path / "terraform.tfvars"
        assert tfvars.exists()
        content = tfvars.read_text()
        assert "lza-network" in content
        assert 'cidr = "10.0.0.0/16"' in content
        assert "enable_logs = true" in content

    def test_no_module_inputs_skips(self, tmp_path: Path):
        payload = IaCIntentPayload(
            design_doc=None,  # type: ignore[arg-type]
            module_inputs=[],
            intent=None,
        )
        gen_tfvars(payload, tmp_path)
        assert not (tmp_path / "terraform.tfvars").exists()

    def test_multiple_modules(self, tmp_path: Path):
        payload = IaCIntentPayload(
            design_doc=None,  # type: ignore[arg-type]
            module_inputs=[
                ModuleInputs(
                    module_name="mod-a",
                    variables={"x": 1},
                ),
                ModuleInputs(
                    module_name="mod-b",
                    variables={"y": False},
                ),
            ],
            intent=None,
        )
        gen_tfvars(payload, tmp_path)
        content = (tmp_path / "terraform.tfvars").read_text()
        assert "# Module: mod-a" in content
        assert "# Module: mod-b" in content
        assert "x = 1" in content
        assert "y = false" in content

    def test_global_generation_scopes_tfvars_to_explicit_terraform_patterns(
        self,
        tmp_path: Path,
    ):
        original = dict(GLOBAL_REGISTRY._patterns)
        try:
            GLOBAL_REGISTRY.register(
                Pattern(
                    name="future-non-terraform-pattern",
                    description="Future non-Terraform module handoff",
                    graph_factory=_handoff_graph,
                )
            )
            payload = IaCIntentPayload(
                design_doc=DesignDocument(),
                module_inputs=[
                    ModuleInputs(
                        module_name="future-module",
                        variables={"name": "example"},
                    )
                ],
                intent=None,
                pattern="future-non-terraform-pattern",
            )

            generate_all(payload, tmp_path)

            assert (tmp_path / "module-inputs.yaml").exists()
            assert not (tmp_path / "terraform.tfvars").exists()
        finally:
            GLOBAL_REGISTRY._patterns = original


class TestGenHandoffPlan:
    def test_ready_handoff_requires_review_before_toolchain_action(self, tmp_path: Path):
        original = _register_handoff_pattern()
        try:
            payload = SimpleNamespace(
                pattern="handoff-semantic-test",
                deployment_readiness={"status": "ready", "deploymentAllowed": True},
            )

            gen_handoff_plan(payload, tmp_path)

            plan = _yaml_load(tmp_path / "handoff-plan.yaml")
            assert plan["allowedNextAction"] == (
                "Pass the reviewed artifacts to the existing target toolchain after manual gates."
            )
            assert plan["readiness"]["handoffAllowed"] is True
            assert "downstream generation, execution" in plan["boundary"]
            steps = {step["id"]: step for step in plan["steps"]}
            assert steps["approve-handoff"]["dependsOn"] == [
                "review-network-config-yaml",
                "review-security-config-yaml",
            ]
            assert steps["validate-target-contracts"]["dependsOn"] == ["resolve-decisions"]
            for step in plan["steps"]:
                assert step["owner"]
                assert step["manualGate"] is True
                assert step["rollback"]
        finally:
            GLOBAL_REGISTRY._patterns = original

    def test_blocked_handoff_allows_only_resolution_action(self, tmp_path: Path):
        original = _register_handoff_pattern()
        try:
            payload = SimpleNamespace(
                pattern="handoff-semantic-test",
                deployment_readiness={
                    "status": "blocked",
                    "deploymentAllowed": False,
                    "blockers": [{"code": "REGION_REQUIRED", "message": "Region required."}],
                },
            )

            gen_handoff_plan(payload, tmp_path)

            plan = _yaml_load(tmp_path / "handoff-plan.yaml")
            assert plan["allowedNextAction"] == (
                "Resolve blockers and re-run compile before any downstream handoff."
            )
            assert plan["readiness"]["status"] == "blocked"
            assert plan["readiness"]["handoffAllowed"] is False
            assert plan["readiness"]["deploymentAllowed"] is False
            assert plan["readiness"]["blockers"] == [
                {"code": "REGION_REQUIRED", "message": "Region required."}
            ]
            assert "Do not mutate downstream systems from this plan." in plan["rollback"]
        finally:
            GLOBAL_REGISTRY._patterns = original


class TestGenContextManifest:
    def test_writes_code_owned_context_inventory(self, tmp_path: Path):
        original = _register_handoff_pattern()
        try:
            payload = IaCIntentPayload(
                design_doc=DesignDocument(),
                module_inputs=[ModuleInputs(module_name="example", variables={"region": "eu"})],
                intent=None,
                pattern="handoff-semantic-test",
                decisions={"region": "eu-central-1"},
                extraction_summary={
                    "provider": "ollama",
                    "model": "qwen2.5:7b",
                    "callCount": 1,
                    "rawEvidence": {"path": "not-requested", "status": "not-requested"},
                },
            )

            gen_context_manifest(payload, tmp_path)

            manifest = _yaml_load(tmp_path / "context-manifest.yaml")
            assert manifest["schemaVersion"] == "intent-engine/context-manifest/v1"
            assert manifest["pattern"] == "handoff-semantic-test"
            assert manifest["contextInventory"]["promptContext"]["present"] is True
            assert manifest["contextInventory"]["promptContext"]["wordCount"] >= 12
            assert manifest["contextInventory"]["requirementGraph"]["nodeCount"] == 1
            assert manifest["contextInventory"]["targetContracts"][0]["name"] == (
                "handoff-test-contract"
            )
            assert manifest["runtimeContext"]["acceptedDecisionCount"] == 1
            assert manifest["runtimeContext"]["moduleInputCount"] == 1
            assert manifest["runtimeContext"]["unsupportedAskFactCount"] == 0
            assert manifest["runtimeContext"]["llm"]["provider"] == "ollama"
            assert "context-manifest.yaml" in manifest["outputs"]["expectedArtifacts"]
            assert (
                "LLM output is never authoritative without graph acceptance."
                in (manifest["guardrails"])
            )
        finally:
            GLOBAL_REGISTRY._patterns = original


class TestGenSampleRecommendations:
    def test_writes_file_when_pattern_has_sample_matches(self, tmp_path: Path):
        GLOBAL_SAMPLE_REGISTRY.register(
            SampleConfig(
                name="test-sample-rec-v1",
                pattern="test-pattern-rec",
                version="1.0.0",
                release_date="2026-05-27",
                source_url="https://example.com",
                decisions={"region": "eu-central-1", "enabled": "true"},
            )
        )
        payload = IaCIntentPayload(
            design_doc=None,  # type: ignore[arg-type]
            module_inputs=[],
            intent=None,
            pattern="test-pattern-rec",
            decisions={"region": "eu-central-1", "enabled": True},
        )

        gen_sample_recommendations(payload, tmp_path)

        out = tmp_path / "sample-recommendations.yaml"
        assert out.exists()
        content = out.read_text()
        assert "test-sample-rec-v1" in content
        assert "sameDecisionCount: 2" in content

    def test_skips_without_pattern_decisions(self, tmp_path: Path):
        payload = IaCIntentPayload(
            design_doc=None,  # type: ignore[arg-type]
            module_inputs=[],
            intent=None,
        )

        gen_sample_recommendations(payload, tmp_path)

        assert not (tmp_path / "sample-recommendations.yaml").exists()
