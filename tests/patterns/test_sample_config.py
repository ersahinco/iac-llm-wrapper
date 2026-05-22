"""Tests for cross-pattern versioned sample configurations."""

from __future__ import annotations

from pathlib import Path

import ruamel.yaml

from intent_engine.core.sample_config import GLOBAL_SAMPLE_REGISTRY

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


class TestK8sSampleConfigRegistered:
    def test_k8s_cluster_v1_registered(self):
        cfg = GLOBAL_SAMPLE_REGISTRY.get("k8s-cluster-v1")
        assert cfg.pattern == "kubernetes-cluster"
        assert cfg.version == "1.0.0"
        assert cfg.decisions["cluster_name"] == "prod-k8s"

    def test_k8s_v1_has_module_refs(self):
        cfg = GLOBAL_SAMPLE_REGISTRY.get("k8s-cluster-v1")
        module_names = {m.module_name for m in cfg.module_refs}
        assert "terraform-aws-eks" in module_names
        assert "terraform-aws-vpc" in module_names

    def test_k8s_v1_module_refs_have_versions(self):
        cfg = GLOBAL_SAMPLE_REGISTRY.get("k8s-cluster-v1")
        for ref in cfg.module_refs:
            assert ref.version
            assert ref.source


class TestK8sSampleConfigFixtures:
    def test_fixture_dir_exists(self):
        assert (FIXTURES / "kubernetes-v1").is_dir()

    def test_cluster_config_exists(self):
        path = FIXTURES / "kubernetes-v1" / "cluster-config.yaml"
        assert path.exists()
        data = ruamel.yaml.YAML(typ="safe").load(path.read_text())
        assert data["cluster"]["name"] == "prod-k8s"
        assert data["cluster"]["version"] == "1.30"

    def test_namespace_config_exists(self):
        path = FIXTURES / "kubernetes-v1" / "namespace-config.yaml"
        assert path.exists()
        data = ruamel.yaml.YAML(typ="safe").load(path.read_text())
        assert len(data["namespaces"]) >= 1
        assert data["namespaces"][0]["name"] == "production"

    def test_cluster_config_has_node_pools(self):
        path = FIXTURES / "kubernetes-v1" / "cluster-config.yaml"
        data = ruamel.yaml.YAML(typ="safe").load(path.read_text())
        pools = data["cluster"]["nodePools"]
        assert len(pools) == 1
        assert pools[0]["name"] == "primary"
        assert pools[0]["minSize"] == 2


class TestSampleConfigConsistency:
    def test_registered_samples_with_fixture_dirs(self):
        """Samples with fixture dirs should have valid directories."""
        for name in GLOBAL_SAMPLE_REGISTRY.list():
            expected_dir = FIXTURES / name
            if expected_dir.exists():
                assert expected_dir.is_dir(), f"{name} fixture path is not a directory"

    def test_all_samples_have_module_versions(self):
        """Every module ref should have a version and source."""
        for name in GLOBAL_SAMPLE_REGISTRY.list():
            cfg = GLOBAL_SAMPLE_REGISTRY.get(name)
            for ref in cfg.module_refs:
                assert ref.version, f"{name}/{ref.module_name} missing version"
                assert ref.source, f"{name}/{ref.module_name} missing source"
