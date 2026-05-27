"""Tests for modular generator registry (generic core)."""

from __future__ import annotations

from pathlib import Path

from intent_engine.core.generator import GeneratorRegistry, _hcl_value, gen_tfvars
from intent_engine.core.module_mapping import IaCIntentPayload, ModuleInputs


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
            design_doc=None,  # type: ignore[arg-type]
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
