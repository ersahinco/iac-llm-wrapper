"""Tests for versioned sample configuration system."""

from __future__ import annotations

from intent_engine.core.sample_config import (
    ModuleRef,
    SampleConfig,
    SampleConfigRegistry,
)


class TestSampleConfig:
    def test_create_minimal(self):
        cfg = SampleConfig(
            name="test",
            pattern="test-pattern",
            version="1.0.0",
            release_date="2025-01-01",
            source_url="https://example.com",
        )
        assert cfg.name == "test"
        assert cfg.pattern == "test-pattern"
        assert cfg.decisions == {}

    def test_create_with_decisions(self):
        cfg = SampleConfig(
            name="test",
            pattern="test-pattern",
            version="1.0.0",
            release_date="2025-01-01",
            source_url="https://example.com",
            decisions={"region": "eu-west-1"},
        )
        assert cfg.decisions["region"] == "eu-west-1"

    def test_create_with_module_refs(self):
        ref = ModuleRef(
            module_name="test-module",
            source="registry.example.com/module",
            version="~> 1.0",
            description="Test module",
        )
        cfg = SampleConfig(
            name="test",
            pattern="test-pattern",
            version="1.0.0",
            release_date="2025-01-01",
            source_url="https://example.com",
            module_refs=[ref],
        )
        assert len(cfg.module_refs) == 1
        assert cfg.module_refs[0].module_name == "test-module"
        assert cfg.module_refs[0].version == "~> 1.0"

    def test_diff_identical(self):
        cfg = SampleConfig(
            name="test",
            pattern="test-pattern",
            version="1.0.0",
            release_date="2025-01-01",
            source_url="https://example.com",
            decisions={"a": "x", "b": "y"},
        )
        changes = cfg.diff({"a": "x", "b": "y"})
        assert changes == {}

    def test_diff_different(self):
        cfg = SampleConfig(
            name="test",
            pattern="test-pattern",
            version="1.0.0",
            release_date="2025-01-01",
            source_url="https://example.com",
            decisions={"a": "x", "b": "y"},
        )
        changes = cfg.diff({"a": "z"})
        assert "a" in changes
        assert changes["a"]["sample"] == "x"
        assert changes["a"]["current"] == "z"
        assert "b" in changes
        assert changes["b"]["current"] is None

    def test_diff_missing_key(self):
        cfg = SampleConfig(
            name="test",
            pattern="test-pattern",
            version="1.0.0",
            release_date="2025-01-01",
            source_url="https://example.com",
            decisions={"a": "x"},
        )
        changes = cfg.diff({"b": "y"})
        assert "a" in changes
        assert changes["a"]["current"] is None


class TestSampleConfigRegistry:
    def test_register_and_get(self):
        reg = SampleConfigRegistry()
        cfg = SampleConfig(
            name="test",
            pattern="test-pattern",
            version="1.0.0",
            release_date="2025-01-01",
            source_url="https://example.com",
        )
        reg.register(cfg)
        assert reg.get("test").name == "test"

    def test_get_unknown_raises(self):
        reg = SampleConfigRegistry()
        import pytest

        with pytest.raises(KeyError):
            reg.get("nonexistent")

    def test_list(self):
        reg = SampleConfigRegistry()
        reg.register(
            SampleConfig(
                name="b",
                pattern="t1",
                version="1.0.0",
                release_date="2025-01-01",
                source_url="https://example.com",
            )
        )
        reg.register(
            SampleConfig(
                name="a",
                pattern="t2",
                version="1.0.0",
                release_date="2025-01-01",
                source_url="https://example.com",
            )
        )
        names = reg.list()
        assert names == ["a", "b"]

    def test_find_by_pattern(self):
        reg = SampleConfigRegistry()
        reg.register(
            SampleConfig(
                name="a",
                pattern="p1",
                version="1.0.0",
                release_date="2025-01-01",
                source_url="https://example.com",
            )
        )
        reg.register(
            SampleConfig(
                name="b",
                pattern="p1",
                version="2.0.0",
                release_date="2025-06-01",
                source_url="https://example.com",
            )
        )
        reg.register(
            SampleConfig(
                name="c",
                pattern="p2",
                version="1.0.0",
                release_date="2025-01-01",
                source_url="https://example.com",
            )
        )
        p1_samples = reg.find_by_pattern("p1")
        assert len(p1_samples) == 2
        assert p1_samples[0].name == "a"
        assert p1_samples[1].name == "b"

    def test_global_registry_importable(self):
        from intent_engine.core.sample_config import GLOBAL_SAMPLE_REGISTRY

        assert GLOBAL_SAMPLE_REGISTRY is not None
