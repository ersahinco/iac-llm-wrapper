"""LZA-specific normalizer: applies deterministic defaults and guardrails.

Reads defaults from the LZA pattern's defaults.yaml to keep LZA-specific
values out of the core framework.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import ruamel.yaml

_DEFAULTS_FILE = Path(__file__).parent / "defaults.yaml"


def _load_guardrails() -> dict:
    with open(_DEFAULTS_FILE) as f:
        return ruamel.yaml.YAML(typ="safe").load(f) or {}


def _set_nested(obj: Any, dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        obj = getattr(obj, part)
    setattr(obj, parts[-1], value)


def _get_nested(obj: Any, dotted_path: str) -> Any:
    parts = dotted_path.split(".")
    for part in parts:
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def normalize_lza(intent: Any) -> Any:
    cfg = _load_guardrails()
    defaults = cfg.get("defaults", {})

    # Apply LZA-specific defaults
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

    # Guardrails for private CI/CD
    if (
        hasattr(intent, "cicd")
        and hasattr(intent.cicd, "mode")
        and hasattr(intent.cicd, "vpc_endpoints")
    ):
        mode_val = getattr(intent.cicd.mode, "value", str(intent.cicd.mode))
        if mode_val == "private":
            required_endpoints = cfg.get("guardrails", {}).get(
                "private_cicd_required_endpoints", []
            )
            for ep in required_endpoints:
                if ep not in intent.cicd.vpc_endpoints:
                    intent.cicd.vpc_endpoints.append(ep)
            intent.cicd.vpc_endpoints.sort()

    # Derive central network account from accounts list if hub-spoke
    if hasattr(intent, "topology") and hasattr(intent, "network") and hasattr(intent, "accounts"):
        topology = getattr(intent, "topology", None)
        is_hub_spoke = topology and getattr(topology, "value", str(topology)) == "hub-spoke"
        if (
            is_hub_spoke
            and hasattr(intent.network, "central_network_account")
            and not intent.network.central_network_account
        ):
            for acct in intent.accounts:
                if hasattr(acct, "name") and "network" in acct.name.lower():
                    intent.network.central_network_account = acct.name
                    break

    return intent
