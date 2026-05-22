"""Acceptance test: kubernetes-cluster pattern compiles end-to-end.

This test proves the framework is generic: we added a new use case
without modifying extractor.py, compiler.py, validator.py,
normalizer.py, interview.py, or cli.py.
"""

from __future__ import annotations

from pathlib import Path

import ruamel.yaml

import intent_engine.patterns.kubernetes  # noqa: F401 — triggers pattern registration
from intent_engine.core.compiler import compile_from_interview
from intent_engine.core.patterns import GLOBAL_REGISTRY


class TestKubernetesPattern:
    def test_pattern_is_registered(self):
        assert "kubernetes-cluster" in GLOBAL_REGISTRY.list()
        p = GLOBAL_REGISTRY.get("kubernetes-cluster")
        assert p.description
        assert p.intent_factory is not None

    def test_compile_from_interview_creates_artifacts(self, tmp_path: Path):
        decisions = {
            "cluster_name": "prod-k8s",
            "cluster_version": "1.30",
            "network_policy_enabled": "true",
            "pod_cidr": "10.244.0.0/16",
            "service_cidr": "10.96.0.0/12",
            "node_pool_name": "primary",
            "node_pool_instance_type": "t3.large",
            "node_pool_min_size": "2",
            "node_pool_max_size": "5",
            "namespace_name": "production",
        }
        output = tmp_path / "output"
        compile_from_interview(decisions, output, pattern="kubernetes-cluster")

        assert (output / "cluster-config.yaml").exists()
        assert (output / "namespace-config.yaml").exists()
        assert (output / "decision-report.yaml").exists()
        assert (output / "module-inputs.yaml").exists()

        # Verify module inputs content
        yaml = ruamel.yaml.YAML(typ="safe")
        with open(output / "module-inputs.yaml") as f:
            mi = yaml.load(f)
        assert len(mi["moduleInputs"]) == 1
        assert mi["moduleInputs"][0]["moduleName"] == "terraform-aws-eks"
        assert mi["moduleInputs"][0]["variables"]["cluster_name"] == "prod-k8s"

        # Verify cluster config content
        yaml = ruamel.yaml.YAML(typ="safe")
        with open(output / "cluster-config.yaml") as f:
            cluster = yaml.load(f)
        assert cluster["cluster"]["name"] == "prod-k8s"
        assert cluster["cluster"]["version"] == "1.30"
        assert cluster["cluster"]["network"]["podCidr"] == "10.244.0.0/16"
        assert cluster["cluster"]["network"]["networkPolicyEnabled"] is True
        pools = cluster["cluster"]["nodePools"]
        assert len(pools) == 1
        assert pools[0]["name"] == "primary"
        assert pools[0]["instanceType"] == "t3.large"
        assert pools[0]["minSize"] == 2
        assert pools[0]["maxSize"] == 5

        # Verify namespace config
        with open(output / "namespace-config.yaml") as f:
            ns = yaml.load(f)
        assert ns["namespaces"][0]["name"] == "production"

    def test_template_generation(self):
        from intent_engine.core.compiler import generate_template

        markdown = generate_template(pattern="kubernetes-cluster")
        assert "# Design Document — kubernetes-cluster pattern" in markdown
        assert "## Cluster" in markdown
        assert "## Network" in markdown
        assert "## Node Pools" in markdown
        assert "name: k8s-cluster" in markdown
        assert "pod_cidr: 10.244.0.0/16" in markdown

    def test_validate_command_passes(self, tmp_path: Path):
        from typer.testing import CliRunner

        from intent_engine.cli import app

        runner = CliRunner()
        output = tmp_path / "output"
        output.mkdir()
        # Create fake artifacts
        (output / "cluster-config.yaml").write_text("cluster:\n")
        (output / "namespace-config.yaml").write_text("namespaces:\n")
        (output / "decision-report.yaml").write_text("clusterName: prod\n")

        result = runner.invoke(
            app, ["validate", "--input", str(output), "--pattern", "kubernetes-cluster"]
        )
        assert result.exit_code == 0
        assert "Validation passed" in result.stdout

    def test_interview_engine_produces_intent(self):
        from intent_engine.core.interview import InterviewEngine

        engine = InterviewEngine(pattern="kubernetes-cluster")
        engine.run_from_decisions({"cluster_name": "test-cluster"})
        engine.apply_defaults_for_remaining()
        intent = engine.to_intent()

        assert intent.cluster_name == "test-cluster"
        assert intent.cluster_version == "1.29"
        assert intent.network_policy_enabled is True
        assert intent.node_pool_min_size == 1
