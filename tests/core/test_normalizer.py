"""Tests for the deterministic default normalizer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from intent_engine.core.normalizer import normalize


@dataclass
class SimpleIntent:
    region: str | None = None
    retention_days: int = 0
    enabled: bool = False
    name: str = ""


@dataclass
class NestedIntent:
    class Network:
        cidr: str = ""
        dns: str = ""

    network: Network = field(default_factory=Network)
    region: str | None = None


def test_normalize_empty_intent(tmp_path: Path):
    """When no defaults file matches, normalize is a no-op."""
    intent = SimpleIntent()
    result = normalize(intent)
    assert result.region is None
    assert result.retention_days == 0
    assert result.enabled is False


def test_normalize_none_field_remains_none():
    intent = SimpleIntent(region=None, retention_days=0, enabled=False, name="")
    result = normalize(intent)
    assert result.name == ""


def test_normalize_nonzero_retention_preserved():
    intent = SimpleIntent(retention_days=365, enabled=False, name="test")
    result = normalize(intent)
    assert result.retention_days == 365


def test_normalize_boolean_false_preserved():
    """False is a valid decision — don't overwrite with a default."""
    intent = SimpleIntent(enabled=False, retention_days=2555, name="test")
    result = normalize(intent)
    assert result.enabled is False


def test_normalize_string_empty_is_overwritten():
    """Empty strings are treated as unset and filled by defaults."""
    intent = SimpleIntent(name="", retention_days=2555, enabled=True)
    result = normalize(intent)
    # No defaults file registered, so empty stays empty
    assert result.name == ""


def test_normalize_no_crash_on_missing_attr():
    class Bare:
        pass

    intent = Bare()
    result = normalize(intent)
    assert result is intent
