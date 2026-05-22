"""Tests for modular generator registry (generic core)."""

from __future__ import annotations

from pathlib import Path

from intent_engine.core.generator import GeneratorRegistry


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
