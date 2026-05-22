"""LZA-specific discovery handlers.

Legacy consistency checks and signal detection for LZA patterns.
"""

from __future__ import annotations

from typing import Any

from intent_engine.core.discovery import DetectedSignal, DiscoveryResult, Inconsistency


def check_lza_legacy_consistency(intent: Any, result: DiscoveryResult) -> None:
    """Legacy consistency checks for LZA-specific models (duck-typed)."""
    # Workload consistency: private mode + public ingress
    if hasattr(intent, "workloads"):
        for w in intent.workloads:
            if (
                hasattr(w, "network_mode")
                and hasattr(w, "public_ingress")
                and getattr(w.network_mode, "value", str(w.network_mode)) == "private"
                and w.public_ingress
            ):
                result.inconsistent.append(
                    Inconsistency(
                        key_a=f"workload:{w.name}:network_mode",
                        key_b=f"workload:{w.name}:public_ingress",
                        reason=f"Workload {w.name} is private but allows public ingress.",
                    )
                )


def detect_lza_legacy_signals(intent: Any, text_lower: str, result: DiscoveryResult) -> None:
    """Legacy signal detection for LZA-specific keywords."""
    # Account count signal
    if hasattr(intent, "accounts") and hasattr(intent, "topology"):
        topo_val = getattr(intent.topology, "value", str(intent.topology))
        if len(intent.accounts) >= 5 and topo_val != "hub-spoke":
            result.signals.append(
                DetectedSignal(
                    signal="5+-accounts",
                    triggered_requirements=["topology"],
                    context=(f"{len(intent.accounts)} accounts but not hub-spoke. Try hub-spoke."),
                )
            )
