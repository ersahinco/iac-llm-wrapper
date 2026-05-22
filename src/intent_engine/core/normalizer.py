"""Normalize raw intent by applying deterministic defaults and guardrails.

All guardrail values come from defaults.yaml. No hardcoded fallbacks —
the Pydantic data model already provides its own defaults. This ensures
new use cases only need a new data model + defaults file, not code changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import ruamel.yaml

_DEFAULTS_FILE = Path(__file__).parent / "defaults.yaml"


def _load_guardrails() -> dict:
    with open(_DEFAULTS_FILE) as f:
        return ruamel.yaml.YAML(typ="safe").load(f)


def _set_nested(obj: Any, dotted_path: str, value: Any) -> None:
    """Set an attribute on a nested object by dotted path."""
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        obj = getattr(obj, part)
    setattr(obj, parts[-1], value)


def _get_nested(obj: Any, dotted_path: str) -> Any:
    """Get an attribute on a nested object by dotted path."""
    parts = dotted_path.split(".")
    for part in parts:
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def normalize(intent: Any) -> Any:
    cfg = _load_guardrails()
    defaults = cfg.get("defaults", {}) or {}

    # Apply defaults only when the field is still empty / zero
    # (Pydantic defaults already cover the base case)
    for key, value in defaults.items():
        if hasattr(intent, key):
            current = getattr(intent, key)
            if current is None or current == "" or current == 0:
                if not isinstance(current, bool):
                    setattr(intent, key, value)
        elif "." in key:
            current = _get_nested(intent, key)
            if current is None or current == "" or current == 0:
                if not isinstance(current, bool):
                    _set_nested(intent, key, value)

    return intent
