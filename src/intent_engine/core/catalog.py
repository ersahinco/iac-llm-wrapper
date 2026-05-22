"""ConfigCatalog: known-good reference decision sets.

Provides pre-built decisions that represent proven, validated patterns.
Architects can use these as starting points. Engineers can diff their
current intent against a catalog entry to understand gaps.

Each catalog entry is a YAML file with:
  name: "baseline"
  description: "Standard enterprise with hub-spoke, security, CI/CD"
  pattern: "baseline"
  decisions:
    primary_region: "eu-central-1"
    topology: "hub-spoke"
    ...
  notes:
    architect: "Suitable for enterprises with 5+ accounts"
    engineer: "Produces 10 YAML files + workload skeletons"
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import ruamel.yaml

from .patterns import GLOBAL_REGISTRY


@dataclass
class CatalogEntry:
    """A known-good decision set reference."""

    name: str
    description: str
    pattern: str
    decisions: dict[str, Any] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    # optional: reference to a fixture or example markdown doc
    example_doc: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConfigCatalog:
    """Registry of known-good decision sets."""

    _builtin_entries: list[CatalogEntry] = []

    def __init__(self, catalog_dir: Path | None = None) -> None:
        self._entries: dict[str, CatalogEntry] = {}
        self._catalog_dir = catalog_dir
        for entry in self._builtin_entries:
            self._entries[entry.name] = entry
        if catalog_dir:
            self._load_from_dir(catalog_dir)

    @classmethod
    def register_builtin(cls, entry: CatalogEntry) -> None:
        cls._builtin_entries.append(entry)

    def register(self, entry: CatalogEntry) -> None:
        self._entries[entry.name] = entry

    def _load_from_dir(self, catalog_dir: Path) -> None:
        yaml = ruamel.yaml.YAML(typ="safe")
        for f in sorted(catalog_dir.glob("*.yaml")):
            data = yaml.load(f.read_text())
            entry = CatalogEntry(
                name=data["name"],
                description=data.get("description", ""),
                pattern=data.get("pattern", "baseline"),
                decisions=data.get("decisions", {}),
                notes=data.get("notes", {}),
                tags=data.get("tags", []),
                example_doc=data.get("example_doc"),
            )
            self._entries[entry.name] = entry

    def get(self, name: str) -> CatalogEntry:
        if name not in self._entries:
            available = ", ".join(sorted(self._entries.keys()))
            raise KeyError(f"Unknown catalog entry '{name}'. Available: {available}")
        return self._entries[name]

    def list(self) -> list[str]:
        return sorted(self._entries.keys())

    def list_by_pattern(self, pattern: str) -> list[CatalogEntry]:
        return [e for e in self._entries.values() if e.pattern == pattern]

    def diff(self, entry_name: str, current_decisions: dict[str, Any]) -> dict[str, Any]:
        """Compare current decisions against a catalog entry.

        Returns:
            Dict with 'same', 'different', 'missing_in_current', 'extra_in_current'
        """
        entry = self.get(entry_name)
        entry_decisions = entry.decisions

        same = {}
        different = {}
        missing_in_current = {}
        extra_in_current = {}

        for key, val in entry_decisions.items():
            if key in current_decisions:
                if str(current_decisions[key]).lower() == str(val).lower():
                    same[key] = val
                else:
                    different[key] = {
                        "catalog": val,
                        "current": current_decisions[key],
                    }
            else:
                missing_in_current[key] = val

        for key, val in current_decisions.items():
            if key not in entry_decisions:
                extra_in_current[key] = val

        return {
            "entry": entry_name,
            "same": same,
            "different": different,
            "missing_in_current": missing_in_current,
            "extra_in_current": extra_in_current,
        }

    def apply_as_defaults(
        self,
        entry_name: str,
        current_decisions: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge catalog entry decisions into current decisions.

        Current decisions take precedence. Missing fields are filled from catalog.
        """
        entry = self.get(entry_name)
        merged = dict(entry.decisions)
        merged.update(current_decisions)
        return merged

    def to_intent(self, entry_name: str) -> Any:
        """Convert a catalog entry to an intent model for validation/testing."""
        from .interview import InterviewEngine

        entry = self.get(entry_name)
        graph = GLOBAL_REGISTRY.get(entry.pattern).create_graph()
        engine = InterviewEngine(graph)
        engine.run_from_decisions(entry.decisions)
        engine.apply_defaults_for_remaining()
        return engine.to_intent()

    def save_entry(self, entry: CatalogEntry, catalog_dir: Path) -> None:
        """Save a catalog entry to disk as YAML."""
        catalog_dir.mkdir(parents=True, exist_ok=True)
        yaml = ruamel.yaml.YAML()
        yaml.default_flow_style = False
        path = catalog_dir / f"{entry.name}.yaml"
        with open(path, "w") as f:
            yaml.dump(entry.to_dict(), f)


def get_catalog(catalog_dir: Path | None = None) -> ConfigCatalog:
    return ConfigCatalog(catalog_dir=catalog_dir)
