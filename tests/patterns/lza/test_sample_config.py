"""Tests for LZA versioned sample configurations."""

from __future__ import annotations

from pathlib import Path

import ruamel.yaml

from intent_engine.core.sample_config import GLOBAL_SAMPLE_REGISTRY

FIXTURES = Path(__file__).parent.parent.parent.parent / "fixtures"


class TestLZASampleConfigRegistered:
    def test_lza_baseline_v1_registered(self):
        cfg = GLOBAL_SAMPLE_REGISTRY.get("lza-baseline-v1")
        assert cfg.pattern == "baseline"
        assert cfg.version == "1.0.0"
        assert len(cfg.module_refs) == 2

    def test_lza_minimal_v1_registered(self):
        cfg = GLOBAL_SAMPLE_REGISTRY.get("lza-minimal-v1")
        assert cfg.pattern == "minimal"
        assert len(cfg.module_refs) == 1

    def test_baseline_v1_has_module_refs(self):
        cfg = GLOBAL_SAMPLE_REGISTRY.get("lza-baseline-v1")
        module_names = {m.module_name for m in cfg.module_refs}
        assert "lza-network" in module_names
        assert "lza-security-baseline" in module_names

    def test_baseline_v1_module_refs_have_versions(self):
        cfg = GLOBAL_SAMPLE_REGISTRY.get("lza-baseline-v1")
        for ref in cfg.module_refs:
            assert ref.version
            assert ref.source


class TestLZASampleConfigFixtures:
    """Verify the actual fixture YAML files exist and are valid."""

    def test_fixture_dir_exists(self):
        assert (FIXTURES / "lza-baseline-v1").is_dir()

    def test_organization_config_exists(self):
        path = FIXTURES / "lza-baseline-v1" / "organization-config.yaml"
        assert path.exists()
        data = ruamel.yaml.YAML(typ="safe").load(path.read_text())
        assert "organization" in data
        assert "organizationalUnits" in data

    def test_accounts_config_exists(self):
        path = FIXTURES / "lza-baseline-v1" / "accounts-config.yaml"
        assert path.exists()
        data = ruamel.yaml.YAML(typ="safe").load(path.read_text())
        assert "accounts" in data
        assert len(data["accounts"]) >= 4

    def test_global_config_exists(self):
        path = FIXTURES / "lza-baseline-v1" / "global-config.yaml"
        assert path.exists()
        data = ruamel.yaml.YAML(typ="safe").load(path.read_text())
        assert data["global"]["cloudtrail"]["organizationTrail"] is True

    def test_iam_config_exists(self):
        path = FIXTURES / "lza-baseline-v1" / "iam-config.yaml"
        assert path.exists()
        data = ruamel.yaml.YAML(typ="safe").load(path.read_text())
        assert data["permissionBoundary"] == "enabled"

    def test_security_config_exists(self):
        path = FIXTURES / "lza-baseline-v1" / "security-config.yaml"
        assert path.exists()
        data = ruamel.yaml.YAML(typ="safe").load(path.read_text())
        assert data["security"]["audit"]["retentionDays"] == 2555

    def test_network_config_exists(self):
        path = FIXTURES / "lza-baseline-v1" / "network-config.yaml"
        assert path.exists()
        data = ruamel.yaml.YAML(typ="safe").load(path.read_text())
        assert data["network"]["topology"] == "hub-spoke"
