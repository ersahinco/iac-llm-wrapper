"""Tests for graph-driven discovery."""

from __future__ import annotations

from pydantic import BaseModel

from intent_engine.core.discovery import DiscoveryEngine
from intent_engine.core.requirements import Requirement, RequirementGraph


class RegionIntent(BaseModel):
    region: str = "us-east-1"


def test_discovery_returns_synced_keys_without_requiring_second_sync():
    graph = RequirementGraph()
    graph.add(
        Requirement(
            key="region",
            target_field="region",
            target_type="string",
            label="Region",
            question="Which region?",
        )
    )

    result = DiscoveryEngine(graph).discover(RegionIntent(region="eu-central-1"))

    assert result.synced == ["region"]
    assert graph.get("region") == "eu-central-1"
    assert [entry["key"] for entry in graph.audit_log()] == ["region"]
