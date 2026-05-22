"""Tests for LZA-specific module mapping."""

from __future__ import annotations

from pathlib import Path

import ruamel.yaml

import intent_engine.patterns.kubernetes  # noqa: F401 — triggers mapper registration
import intent_engine.patterns.lza.generators  # noqa: F401 — triggers mapper registration
from intent_engine.core.generator import generate_all
from intent_engine.core.module_mapping import (
    DesignDocument,
    IaCIntentPayload,
    ModuleInputs,
    map_intent_to_modules,
)
from intent_engine.patterns.lza.models import RawIntent


class TestModuleMapperRegistry:
    def test_lza_mapper_registered(self):
        intent = RawIntent()
        intent.network.cidr = "10.0.0.0/16"
        modules = map_intent_to_modules(intent, "baseline")
        assert any(m.module_name == "lza-network" for m in modules)

    def test_k8s_mapper_registered(self):
        from intent_engine.patterns.kubernetes.models import K8sIntent

        intent = K8sIntent()
        intent.cluster_name = "test"
        intent.cluster_version = "1.30"
        modules = map_intent_to_modules(intent, "kubernetes-cluster")
        assert len(modules) == 1
        assert modules[0].module_name == "terraform-aws-eks"
        assert modules[0].variables["cluster_name"] == "test"

    def test_unknown_pattern_returns_empty(self):
        intent = RawIntent()
        modules = map_intent_to_modules(intent, "nonexistent-pattern")
        assert modules == []


class TestLzaModuleMapping:
    def test_maps_network_and_security(self):
        intent = RawIntent()
        intent.network.cidr = "10.0.0.0/16"
        intent.network.hub_cidr = "10.0.0.0/20"
        intent.security.audit_retention_days = 2555
        intent.security.s3_block_public_access = True

        modules = map_intent_to_modules(intent, "baseline")
        names = {m.module_name for m in modules}
        assert "lza-network" in names
        assert "lza-security-baseline" in names

        net = next(m for m in modules if m.module_name == "lza-network")
        assert net.variables["cidr"] == "10.0.0.0/16"
        assert net.variables["hub_cidr"] == "10.0.0.0/20"

        sec = next(m for m in modules if m.module_name == "lza-security-baseline")
        assert sec.variables["audit_retention_days"] == 2555
        assert sec.variables["block_public_access"] is True

    def test_no_network_skips_module(self):
        intent = RawIntent()
        modules = map_intent_to_modules(intent, "minimal")
        assert any(m.module_name == "lza-network" for m in modules)


class TestModuleInputGenerators:
    def test_design_doc_generator_skips_when_empty(self, tmp_path: Path):
        intent = RawIntent()
        payload = IaCIntentPayload(
            design_doc=DesignDocument(),
            module_inputs=[],
            intent=intent,
        )
        output_dir = tmp_path / "out"
        generate_all(payload, output_dir)
        assert not (output_dir / "design-doc.yaml").exists()

    def test_design_doc_generator_writes_when_present(self, tmp_path: Path):
        intent = RawIntent()
        dd = DesignDocument(
            project_name="acme-corp",
            business_justification="Need PCI-DSS compliant LZ",
            estimated_tier="Tier-1",
            compliance_tags=["pci-dss"],
        )
        payload = IaCIntentPayload(
            design_doc=dd,
            module_inputs=[],
            intent=intent,
        )
        output_dir = tmp_path / "out"
        generate_all(payload, output_dir)
        assert (output_dir / "design-doc.yaml").exists()
        data = ruamel.yaml.YAML(typ="safe").load((output_dir / "design-doc.yaml").read_text())
        assert data["projectName"] == "acme-corp"
        assert data["estimatedTier"] == "Tier-1"

    def test_module_inputs_generator_writes(self, tmp_path: Path):
        intent = RawIntent()
        mi = [
            ModuleInputs(
                module_name="lza-network",
                variables={"cidr": "10.0.0.0/16"},
            )
        ]
        payload = IaCIntentPayload(
            design_doc=DesignDocument(),
            module_inputs=mi,
            intent=intent,
        )
        output_dir = tmp_path / "out"
        generate_all(payload, output_dir)
        assert (output_dir / "module-inputs.yaml").exists()
        data = ruamel.yaml.YAML(typ="safe").load((output_dir / "module-inputs.yaml").read_text())
        assert data["moduleInputs"][0]["moduleName"] == "lza-network"
        assert data["moduleInputs"][0]["variables"]["cidr"] == "10.0.0.0/16"

    def test_plain_intent_auto_wraps(self, tmp_path: Path):
        """generate_all must auto-wrap plain intent for backward compat."""
        intent = RawIntent()
        intent.primary_region = "eu-central-1"
        output_dir = tmp_path / "out"
        generate_all(intent, output_dir)
        assert (output_dir / "decision-report.yaml").exists()
