"""Versioned sample configurations for intent patterns.

Each SampleConfig represents a known-good, version-pinned reference
configuration that engineers can diff against or apply as defaults.
The version metadata lets consumers detect stale references and upgrade
safely when module sources are updated.
"""

from __future__ import annotations

import builtins
from dataclasses import dataclass
from enum import Enum
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
    description: str = Field(default="", description="Short human-readable summary")
    version: str = Field(description="Sample config version (semver)")
    release_date: str = Field(description="ISO-8601 release date")
    source_url: str = Field(description="URL to upstream source of these config files")
    source_contract: str | None = Field(
        default=None,
        description="Registered target contract or upstream schema family this sample follows",
    )
    upstream_variant: str | None = Field(
        default=None,
        description="Named upstream variant or baseline used to derive this sample",
    )
    tags: list[str] = Field(default_factory=list, description="Searchable metadata labels")
    fixture_dir: str | None = Field(
        default=None,
        description=(
            "Optional fixture directory name when repo fixture path differs from sample name"
        ),
    )
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

    @property
    def fixture_name(self) -> str:
        return self.fixture_dir or self.name

    @staticmethod
    def _canonical_value(value: Any) -> Any:
        if isinstance(value, Enum):
            return SampleConfig._canonical_value(value.value)
        if isinstance(value, bool):
            return value
        if isinstance(value, list):
            return tuple(SampleConfig._canonical_value(item) for item in value)
        if isinstance(value, dict):
            return tuple(
                sorted((key, SampleConfig._canonical_value(item)) for key, item in value.items())
            )
        if isinstance(value, str):
            normalized = value.strip()
            lowered = normalized.lower()
            if lowered == "true":
                return True
            if lowered == "false":
                return False
            return normalized
        return value

    @staticmethod
    def _coerce_list_like(value: Any) -> Any:
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",") if part.strip()]
            if len(parts) > 1:
                return parts
        return value

    @staticmethod
    def to_builtin(value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, list):
            return [SampleConfig.to_builtin(item) for item in value]
        if isinstance(value, dict):
            return {key: SampleConfig.to_builtin(item) for key, item in value.items()}
        return value

    @classmethod
    def _values_match(cls, current_value: Any, sample_value: Any) -> bool:
        if isinstance(current_value, list) or isinstance(sample_value, list):
            current_value = cls._coerce_list_like(current_value)
            sample_value = cls._coerce_list_like(sample_value)
        return bool(cls._canonical_value(current_value) == cls._canonical_value(sample_value))

    def compare_to(self, other_decisions: dict[str, Any]) -> dict[str, Any]:
        same: dict[str, Any] = {}
        different: dict[str, Any] = {}
        missing_in_current: dict[str, Any] = {}
        extra_in_current: dict[str, Any] = {}

        for key, sample_value in self.decisions.items():
            if key not in other_decisions:
                missing_in_current[key] = sample_value
                continue
            current_value = other_decisions[key]
            if self._values_match(current_value, sample_value):
                same[key] = sample_value
            else:
                different[key] = {"sample": sample_value, "current": current_value}

        for key, current_value in other_decisions.items():
            if key not in self.decisions:
                extra_in_current[key] = current_value

        return {
            "same": same,
            "different": different,
            "missing_in_current": missing_in_current,
            "extra_in_current": extra_in_current,
        }


@dataclass(frozen=True)
class SampleMatch:
    sample: SampleConfig
    same_count: int
    different_count: int
    missing_count: int
    total_sample_decisions: int
    diff: dict[str, Any]


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

    def list(self) -> builtins.list[str]:
        return sorted(self._samples.keys())

    def find_by_pattern(self, pattern: str) -> builtins.list[SampleConfig]:
        return self.find(pattern=pattern)

    def find_by_contract(self, contract: str) -> builtins.list[SampleConfig]:
        return self.find(contract=contract)

    def find_by_tag(self, tag: str) -> builtins.list[SampleConfig]:
        return self.find(tag=tag)

    def find(
        self,
        *,
        pattern: str | None = None,
        contract: str | None = None,
        tag: str | None = None,
    ) -> builtins.list[SampleConfig]:
        samples = list(self._samples.values())
        if pattern is not None:
            samples = [sample for sample in samples if sample.pattern == pattern]
        if contract is not None:
            samples = [sample for sample in samples if sample.source_contract == contract]
        if tag is not None:
            needle = tag.lower()
            samples = [
                sample
                for sample in samples
                if any(candidate.lower() == needle for candidate in sample.tags)
            ]
        return sorted(samples, key=lambda sample: sample.name)

    def find_best_matches(
        self,
        current_decisions: dict[str, Any],
        *,
        pattern: str | None = None,
        contract: str | None = None,
        tag: str | None = None,
        limit: int = 3,
    ) -> builtins.list[SampleMatch]:
        ranked: builtins.list[SampleMatch] = []
        for sample in self.find(pattern=pattern, contract=contract, tag=tag):
            diff = sample.compare_to(current_decisions)
            ranked.append(
                SampleMatch(
                    sample=sample,
                    same_count=len(diff["same"]),
                    different_count=len(diff["different"]),
                    missing_count=len(diff["missing_in_current"]),
                    total_sample_decisions=len(sample.decisions),
                    diff=diff,
                )
            )
        ranked.sort(
            key=lambda match: (
                -match.same_count,
                match.different_count,
                match.missing_count,
                match.sample.name,
            )
        )
        return ranked[:limit]


GLOBAL_SAMPLE_REGISTRY = SampleConfigRegistry()
