"""Tests for cross-pattern versioned sample configurations."""

from __future__ import annotations

from pathlib import Path

import ruamel.yaml

import intent_engine.patterns.aws_lza  # noqa: F401 — triggers sample registration
import intent_engine.patterns.kubernetes  # noqa: F401 — triggers sample registration
from intent_engine.core.compiler import compile_from_interview
from intent_engine.core.sample_config import GLOBAL_SAMPLE_REGISTRY

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


class TestAwsLzaSampleConfigRegistered:
    def test_aws_lza_standard_v1_registered(self):
        cfg = GLOBAL_SAMPLE_REGISTRY.get("aws-lza-standard-v1")
        assert cfg.pattern == "aws-lza"
        assert cfg.version == "1.0.0"
        assert cfg.source_contract == "aws-lza-sample-configuration"
        assert cfg.upstream_variant == "standard"
        assert "hub-spoke" in cfg.tags
        assert cfg.decisions["baseline"] == "standard"
        assert cfg.source_url.startswith("https://awslabs.github.io/")

    def test_aws_lza_regulated_v1_registered(self):
        cfg = GLOBAL_SAMPLE_REGISTRY.get("aws-lza-regulated-v1")
        assert cfg.pattern == "aws-lza"
        assert cfg.decisions["compliance_overlay"] == "regulated"
        assert cfg.upstream_variant == "standard"
        assert "regulated" in cfg.tags

    def test_aws_lza_healthcare_v1_registered(self):
        cfg = GLOBAL_SAMPLE_REGISTRY.get("aws-lza-healthcare-v1")
        assert cfg.pattern == "aws-lza"
        assert cfg.decisions["baseline"] == "healthcare"
        assert cfg.decisions["compliance_overlay"] == "healthcare"
        assert cfg.upstream_variant == "healthcare"
        assert "hipaa" in cfg.tags


class TestAwsLzaSampleConfigFixtures:
    def test_aws_lza_registered_sample_decisions_compile(self, tmp_path: Path):
        cfg = GLOBAL_SAMPLE_REGISTRY.get("aws-lza-regulated-v1")

        compile_from_interview(cfg.decisions, tmp_path / "regulated", pattern="aws-lza")

        assert (tmp_path / "regulated" / "security-config.yaml").exists()

    def test_aws_lza_standard_fixture_has_readme(self):
        path = FIXTURES / "aws-lza-standard-v1" / "README.md"
        assert path.exists()
        assert "aws-lza-standard-v1" in path.read_text()

    def test_aws_lza_regulated_fixture_has_readme(self):
        path = FIXTURES / "aws-lza-regulated-v1" / "README.md"
        assert path.exists()
        text = path.read_text()
        assert "regulated" in text
        assert "Security Hub" in text

    def test_aws_lza_healthcare_fixture_has_readme(self):
        path = FIXTURES / "aws-lza-healthcare-v1" / "README.md"
        assert path.exists()
        text = path.read_text()
        assert "healthcare" in text
        assert "HIPAA" in text

    def test_aws_lza_regulated_fixture_security_overlay(self):
        path = FIXTURES / "aws-lza-regulated-v1" / "security-config.yaml"
        data = ruamel.yaml.YAML(typ="safe").load(path.read_text())
        standards = data["centralSecurityServices"]["securityHub"]["standards"]
        names = {item["name"] for item in standards}
        assert "AWS Foundational Security Best Practices v1.0.0" in names
        assert "NIST Special Publication 800-53 Revision 5" in names

    def test_aws_lza_healthcare_fixture_security_overlay(self):
        path = FIXTURES / "aws-lza-healthcare-v1" / "security-config.yaml"
        data = ruamel.yaml.YAML(typ="safe").load(path.read_text())
        standards = data["centralSecurityServices"]["securityHub"]["standards"]
        names = {item["name"] for item in standards}
        assert "AWS Foundational Security Best Practices v1.0.0" in names
        assert "NIST Special Publication 800-53 Revision 5" in names


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

    def test_all_samples_with_contract_metadata_have_source_url(self):
        for name in GLOBAL_SAMPLE_REGISTRY.list():
            cfg = GLOBAL_SAMPLE_REGISTRY.get(name)
            if cfg.source_contract:
                assert cfg.source_url, f"{name} missing source_url"
                assert cfg.upstream_variant, f"{name} missing upstream_variant"
