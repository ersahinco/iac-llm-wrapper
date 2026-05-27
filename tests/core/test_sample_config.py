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
        assert cfg.description == ""
        assert cfg.source_contract is None
        assert cfg.upstream_variant is None
        assert cfg.tags == []
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

    def test_create_with_metadata(self):
        cfg = SampleConfig(
            name="test",
            pattern="aws-lza",
            description="Regulated sample",
            version="1.0.0",
            release_date="2026-05-27",
            source_url="https://example.com",
            source_contract="aws-lza-sample-configuration",
            upstream_variant="standard",
            tags=["regulated", "aws"],
        )
        assert cfg.description == "Regulated sample"
        assert cfg.source_contract == "aws-lza-sample-configuration"
        assert cfg.upstream_variant == "standard"
        assert cfg.tags == ["regulated", "aws"]

    def test_fixture_name_uses_override_when_present(self):
        cfg = SampleConfig(
            name="test",
            pattern="aws-lza",
            version="1.0.0",
            release_date="2026-05-27",
            source_url="https://example.com",
            fixture_dir="custom-fixture",
        )
        assert cfg.fixture_name == "custom-fixture"

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

    def test_find_by_contract(self):
        reg = SampleConfigRegistry()
        reg.register(
            SampleConfig(
                name="a",
                pattern="p1",
                version="1.0.0",
                release_date="2025-01-01",
                source_url="https://example.com",
                source_contract="contract-a",
            )
        )
        reg.register(
            SampleConfig(
                name="b",
                pattern="p1",
                version="1.0.0",
                release_date="2025-01-01",
                source_url="https://example.com",
                source_contract="contract-b",
            )
        )

        matches = reg.find_by_contract("contract-a")

        assert [sample.name for sample in matches] == ["a"]

    def test_find_by_tag(self):
        reg = SampleConfigRegistry()
        reg.register(
            SampleConfig(
                name="a",
                pattern="p1",
                version="1.0.0",
                release_date="2025-01-01",
                source_url="https://example.com",
                tags=["regulated", "aws"],
            )
        )
        reg.register(
            SampleConfig(
                name="b",
                pattern="p1",
                version="1.0.0",
                release_date="2025-01-01",
                source_url="https://example.com",
                tags=["kubernetes"],
            )
        )

        matches = reg.find_by_tag("AWS")

        assert [sample.name for sample in matches] == ["a"]

    def test_compare_to_normalizes_bool_and_list_shapes(self):
        cfg = SampleConfig(
            name="test",
            pattern="aws-lza",
            version="1.0.0",
            release_date="2026-05-27",
            source_url="https://example.com",
            decisions={
                "centralized_logging": "true",
                "enabled_regions": ["eu-central-1", "eu-west-1"],
            },
        )

        diff = cfg.compare_to(
            {
                "centralized_logging": True,
                "enabled_regions": "eu-central-1, eu-west-1",
                "extra": "value",
            }
        )

        assert set(diff["same"]) == {"centralized_logging", "enabled_regions"}
        assert diff["different"] == {}
        assert diff["missing_in_current"] == {}
        assert diff["extra_in_current"] == {"extra": "value"}

    def test_find_best_matches_prefers_more_exact_overlap(self):
        reg = SampleConfigRegistry()
        reg.register(
            SampleConfig(
                name="close",
                pattern="aws-lza",
                version="1.0.0",
                release_date="2026-05-27",
                source_url="https://example.com",
                decisions={"baseline": "standard", "centralized_logging": "true"},
            )
        )
        reg.register(
            SampleConfig(
                name="far",
                pattern="aws-lza",
                version="1.0.0",
                release_date="2026-05-27",
                source_url="https://example.com",
                decisions={"baseline": "healthcare", "centralized_logging": "false"},
            )
        )

        matches = reg.find_best_matches(
            {"baseline": "standard", "centralized_logging": True},
            pattern="aws-lza",
        )

        assert [match.sample.name for match in matches] == ["close", "far"]
        assert matches[0].same_count == 2
        assert matches[1].different_count == 2

    def test_global_registry_importable(self):
        from intent_engine.core.sample_config import GLOBAL_SAMPLE_REGISTRY

        assert GLOBAL_SAMPLE_REGISTRY is not None
