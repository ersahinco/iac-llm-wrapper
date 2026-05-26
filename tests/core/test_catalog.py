"""Tests for ConfigCatalog."""

from __future__ import annotations

from pathlib import Path

import pytest

from intent_engine.core.catalog import ConfigCatalog, get_catalog


class TestConfigCatalogBasics:
    def test_builtin_entries_loaded(self):
        cat = ConfigCatalog()
        assert "lza-minimal" in cat.list()
        assert "lza-baseline" in cat.list()
        assert "lza-hybrid-enterprise" in cat.list()

    def test_get_entry(self):
        cat = ConfigCatalog()
        entry = cat.get("lza-minimal")
        assert entry.name == "lza-minimal"
        assert entry.pattern == "minimal"
        assert "primary_region" in entry.decisions

    def test_unknown_entry_raises(self):
        cat = ConfigCatalog()
        with pytest.raises(KeyError, match="Unknown catalog entry"):
            cat.get("nonexistent")

    def test_list_by_pattern(self):
        cat = ConfigCatalog()
        minimal_entries = cat.list_by_pattern("minimal")
        assert len(minimal_entries) == 1
        assert minimal_entries[0].name == "lza-minimal"


class TestConfigCatalogDiff:
    def test_diff_same(self):
        cat = ConfigCatalog()
        current = {
            "primary_region": "eu-central-1",
            "topology": "single-vpc",
        }
        result = cat.diff("lza-minimal", current)
        assert result["entry"] == "lza-minimal"
        assert len(result["same"]) >= 2
        assert not result["different"]

    def test_diff_different(self):
        cat = ConfigCatalog()
        current = {
            "primary_region": "us-east-1",
            "topology": "single-vpc",
        }
        result = cat.diff("lza-minimal", current)
        assert "primary_region" in result["different"]
        assert result["different"]["primary_region"]["catalog"] == "eu-central-1"
        assert result["different"]["primary_region"]["current"] == "us-east-1"

    def test_diff_missing(self):
        cat = ConfigCatalog()
        current = {"primary_region": "eu-central-1"}
        result = cat.diff("lza-minimal", current)
        assert "topology" in result["missing_in_current"]
        assert "network_cidr" in result["missing_in_current"]

    def test_diff_extra(self):
        cat = ConfigCatalog()
        current = {
            "primary_region": "eu-central-1",
            "topology": "single-vpc",
            "network_cidr": "10.0.0.0/16",
            "audit_retention_days": "2555",
            "extra_field": "value",
        }
        result = cat.diff("lza-minimal", current)
        assert "extra_field" in result["extra_in_current"]


class TestConfigCatalogApply:
    def test_apply_fills_missing(self):
        cat = ConfigCatalog()
        current = {"primary_region": "us-east-1"}
        merged = cat.apply_as_defaults("lza-minimal", current)
        assert merged["primary_region"] == "us-east-1"  # current wins
        assert merged["topology"] == "single-vpc"  # filled from catalog
        assert merged["network_cidr"] == "10.0.0.0/16"

    def test_apply_preserves_current(self):
        cat = ConfigCatalog()
        current = {
            "primary_region": "us-east-1",
            "topology": "hub-spoke",
            "network_cidr": "172.16.0.0/16",
        }
        merged = cat.apply_as_defaults("lza-minimal", current)
        assert merged["primary_region"] == "us-east-1"
        assert merged["topology"] == "hub-spoke"
        assert merged["network_cidr"] == "172.16.0.0/16"


class TestConfigCatalogToIntent:
    def test_to_intent_minimal(self):
        cat = ConfigCatalog()
        intent = cat.to_intent("lza-minimal")
        assert intent.primary_region == "eu-central-1"
        assert intent.topology.value == "single-vpc"
        assert intent.network.cidr == "10.0.0.0/16"
        assert intent.security.audit_retention_days == 2555

    def test_to_intent_baseline(self):
        cat = ConfigCatalog()
        intent = cat.to_intent("lza-baseline")
        assert intent.primary_region == "eu-central-1"
        assert intent.topology.value == "hub-spoke"
        assert intent.network.central_network_account == "Network"
        assert intent.cicd.mode.value == "public"


class TestConfigCatalogPersistence:
    def test_load_from_dir(self, tmp_path: Path):
        catalog_dir = tmp_path / "catalog"
        catalog_dir.mkdir()
        custom_entry = {
            "name": "custom-pattern",
            "description": "A custom LZA config",
            "pattern": "baseline",
            "decisions": {"primary_region": "ap-southeast-1"},
            "tags": ["custom"],
        }
        import ruamel.yaml

        yaml = ruamel.yaml.YAML()
        yaml.default_flow_style = False
        with open(catalog_dir / "custom-pattern.yaml", "w") as f:
            yaml.dump(custom_entry, f)

        cat = ConfigCatalog(catalog_dir=catalog_dir)
        assert "custom-pattern" in cat.list()
        entry = cat.get("custom-pattern")
        assert entry.decisions["primary_region"] == "ap-southeast-1"

    def test_save_entry(self, tmp_path: Path):
        cat = ConfigCatalog()
        entry = cat.get("lza-minimal")
        catalog_dir = tmp_path / "catalog"
        cat.save_entry(entry, catalog_dir)
        assert (catalog_dir / "lza-minimal.yaml").exists()

    def test_save_and_load_roundtrip(self, tmp_path: Path):
        cat = ConfigCatalog()
        entry = cat.get("lza-baseline")
        catalog_dir = tmp_path / "catalog"
        cat.save_entry(entry, catalog_dir)

        cat2 = ConfigCatalog(catalog_dir=catalog_dir)
        loaded = cat2.get("lza-baseline")
        assert loaded.name == "lza-baseline"
        assert loaded.decisions["topology"] == "hub-spoke"


class TestCatalogMatch:
    def test_find_best_match_exact(self):
        from intent_engine.core.catalog_match import find_best_catalog_match

        decisions = {
            "primary_region": "eu-central-1",
            "topology": "hub-spoke",
        }
        match = find_best_catalog_match(decisions, "baseline")
        assert match is not None
        assert match["entry_name"] == "lza-baseline"
        assert match["score"] >= 0

    def test_find_best_match_no_match_for_unknown_pattern(self):
        from intent_engine.core.catalog_match import find_best_catalog_match

        decisions = {"primary_region": "eu-central-1"}
        match = find_best_catalog_match(decisions, "nonexistent-pattern")
        assert match is None

    def test_find_best_match_scores_differences(self):
        from intent_engine.core.catalog_match import find_best_catalog_match

        # Different topology should increase score
        decisions_wrong = {
            "primary_region": "eu-central-1",
            "topology": "single-vpc",
        }
        match_wrong = find_best_catalog_match(decisions_wrong, "baseline")

        decisions_correct = {
            "primary_region": "eu-central-1",
            "topology": "hub-spoke",
        }
        match_correct = find_best_catalog_match(decisions_correct, "baseline")

        assert match_wrong["score"] > match_correct["score"]


class TestGlobalCatalog:
    def test_singleton(self):
        cat1 = get_catalog()
        cat2 = get_catalog()
        assert cat1 is not cat2  # factory creates new instance each time
        assert cat1.list() == cat2.list()
