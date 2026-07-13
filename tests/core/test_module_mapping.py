"""Tests for module mapping layer (generic core)."""

from __future__ import annotations

from pydantic import BaseModel

from intent_engine.core.module_mapping import (
    IaCIntentPayload,
    ModuleInputs,
)


class SampleIntent(BaseModel):
    __test__ = False
    name: str = "default"
    enabled: bool = True


class TestIaCIntentPayload:
    def test_access_own_fields(self):
        mi = [ModuleInputs(module_name="m", variables={})]
        payload = IaCIntentPayload(module_inputs=mi, intent=SampleIntent())
        assert len(payload.module_inputs) == 1

    def test_access_pattern_and_decisions_fields(self):
        payload = IaCIntentPayload(
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
            module_inputs=[],
            intent=SampleIntent(),
            handoff_readiness=readiness,
        )

        assert payload.handoff_readiness is readiness
