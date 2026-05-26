"""Catalog matching utilities."""

from __future__ import annotations

from typing import Any

from .catalog import get_catalog


def find_best_catalog_match(decisions: dict[str, Any], pattern: str) -> dict[str, Any] | None:
    """Find the catalog entry that best matches the given decisions.

    Returns the entry with the fewest differences, along with the diff
    result. Returns None if no entries match the pattern.
    """
    cat = get_catalog()
    best_match: dict[str, Any] | None = None
    best_score = float("inf")

    for entry_name in cat.list():
        entry = cat.get(entry_name)
        if entry.pattern != pattern:
            continue
        diff = cat.diff(entry_name, decisions)
        # Score = number of differences + missing + extra (lower is better)
        score = (
            len(diff["different"]) + len(diff["missing_in_current"]) + len(diff["extra_in_current"])
        )
        if score < best_score:
            best_score = score
            best_match = {
                "entry_name": entry_name,
                "entry": entry,
                "diff": diff,
                "score": score,
            }

    return best_match
