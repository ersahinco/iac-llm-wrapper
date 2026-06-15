"""Tests for module mapping layer (generic core)."""

from __future__ import annotations

from pydantic import BaseModel

from intent_engine.core.module_mapping import (
    DesignDocument,
    IaCIntentPayload,
    ModuleInputs,
)


class SampleIntent(BaseModel):
    __test__ = False
    name: str = "default"
    enabled: bool = True


class TestDesignDocument:
    def test_default_fields_empty(self):
        dd = DesignDocument()
        assert dd.project_name == ""
        assert dd.business_justification == ""
        assert dd.estimated_tier == ""
        assert dd.compliance_tags == []

    def test_populated_fields(self):
        dd = DesignDocument(
            project_name="my-project",
            business_justification="Need secure landing zone",
            estimated_tier="Tier-1",
            compliance_tags=["pci-dss"],
        )
        assert dd.project_name == "my-project"
        assert dd.business_justification == "Need secure landing zone"
        assert dd.estimated_tier == "Tier-1"
        assert dd.compliance_tags == ["pci-dss"]


class TestIaCIntentPayload:
    def test_proxy_to_intent(self):
        intent = SampleIntent(name="test-name")
        payload = IaCIntentPayload(
            design_doc=DesignDocument(),
            module_inputs=[],
            intent=intent,
        )
        assert payload.name == "test-name"

    def test_hasattr_on_proxy(self):
        intent = SampleIntent()
        payload = IaCIntentPayload(
            design_doc=DesignDocument(),
            module_inputs=[],
            intent=intent,
        )
        assert hasattr(payload, "name")
        assert hasattr(payload, "enabled")
        assert not hasattr(payload, "nonexistent_field")

    def test_access_own_fields(self):
        dd = DesignDocument(project_name="x")
        mi = [ModuleInputs(module_name="m", variables={})]
        payload = IaCIntentPayload(design_doc=dd, module_inputs=mi, intent=SampleIntent())
        assert payload.design_doc.project_name == "x"
        assert len(payload.module_inputs) == 1

    def test_access_pattern_and_decisions_fields(self):
        payload = IaCIntentPayload(
            design_doc=DesignDocument(),
            module_inputs=[],
            intent=SampleIntent(),
            pattern="aws-lza",
            decisions={"baseline": "standard"},
        )
        assert payload.pattern == "aws-lza"
        assert payload.decisions["baseline"] == "standard"

    def test_handoff_readiness_field(self):
        readiness = {"status": "ready", "handoffAllowed": True}
        payload = IaCIntentPayload(
            design_doc=DesignDocument(),
            module_inputs=[],
            intent=SampleIntent(),
            handoff_readiness=readiness,
        )

        assert payload.handoff_readiness is readiness
