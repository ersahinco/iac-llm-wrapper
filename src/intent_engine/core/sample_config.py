"""Versioned sample configurations for intent patterns.

Each SampleConfig represents a known-good, version-pinned reference
configuration that engineers can diff against or apply as defaults.
The version metadata lets consumers detect stale references and upgrade
safely when module sources are updated.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ModuleRef(BaseModel):
    """Pinned reference to an external IaC module."""

    module_name: str
    source: str = Field(description="Module source URL or Terraform registry reference")
    version: str = Field(description="Semver constraint, e.g. ~> 5.0")
    description: str = ""


class SampleConfig(BaseModel):
    """A version-pinned sample configuration for a specific pattern."""

    name: str
    pattern: str
    version: str = Field(description="Sample config version (semver)")
    release_date: str = Field(description="ISO-8601 release date")
    source_url: str = Field(description="URL to upstream source of these config files")
    decisions: dict[str, Any] = Field(default_factory=dict)
    module_refs: list[ModuleRef] = Field(default_factory=list)
    requires: list[str] = Field(
        default_factory=list,
        description="Other sample config names this depends on",
    )

    def diff(self, other_decisions: dict[str, Any]) -> dict[str, Any]:
        """Compare another decision set against this sample."""
        changes: dict[str, Any] = {}
        for k, v in self.decisions.items():
            if k in other_decisions:
                if other_decisions[k] != v:
                    changes[k] = {"sample": v, "current": other_decisions[k]}
            else:
                changes[k] = {"sample": v, "current": None}
        return changes


class SampleConfigRegistry:
    """Registry of version-pinned sample configurations."""

    def __init__(self) -> None:
        self._samples: dict[str, SampleConfig] = {}

    def register(self, config: SampleConfig) -> None:
        self._samples[config.name] = config

    def get(self, name: str) -> SampleConfig:
        if name not in self._samples:
            raise KeyError(f"Unknown sample config: {name}")
        return self._samples[name]

    def list(self) -> list[str]:
        return sorted(self._samples.keys())

    def find_by_pattern(self, pattern: str) -> list[SampleConfig]:
        return [s for s in self._samples.values() if s.pattern == pattern]


GLOBAL_SAMPLE_REGISTRY = SampleConfigRegistry()
