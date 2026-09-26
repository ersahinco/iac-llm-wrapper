"""Load and validate the architecture decision catalog."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from ruamel.yaml import YAML, YAMLError

from .models import Decision

_CATALOG_FILE = "decisions.yaml"


class CatalogError(Exception):
    """The decision catalog itself is wrong. Not a document problem."""


def _read_yaml(text: str, origin: str) -> Any:
    try:
        return YAML(typ="safe").load(text)
    except YAMLError as exc:
        raise CatalogError(f"{origin}: not valid YAML: {exc}") from exc


def load_catalog(path: Path | None = None) -> dict[str, Decision]:
    """Return decisions by key. Raises CatalogError on a malformed catalog."""
    if path is None:
        origin = f"packaged {_CATALOG_FILE}"
        text = resources.files("intent_engine").joinpath(_CATALOG_FILE).read_text("utf-8")
    else:
        origin = str(path)
        if not path.is_file():
            raise CatalogError(f"{origin}: catalog file not found")
        text = path.read_text("utf-8")

    raw = _read_yaml(text, origin)
    if not isinstance(raw, list) or not raw:
        raise CatalogError(f"{origin}: expected a non-empty list of decisions")

    catalog: dict[str, Decision] = {}
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise CatalogError(f"{origin}: entry {index} is not a mapping")
        try:
            decision = Decision.model_validate(entry)
        except ValidationError as exc:
            raise CatalogError(f"{origin}: entry {index} is invalid: {exc}") from exc
        if decision.key in catalog:
            raise CatalogError(f"{origin}: duplicate decision key '{decision.key}'")
        catalog[decision.key] = decision

    _check_references(catalog, origin)
    return catalog


def _check_references(catalog: dict[str, Decision], origin: str) -> None:
    for decision in catalog.values():
        for required in decision.requires:
            if required not in catalog:
                raise CatalogError(
                    f"{origin}: '{decision.key}' requires unknown decision '{required}'"
                )
        gate = decision.gate
        if gate is None:
            continue
        parent = catalog.get(gate.decision)
        if parent is None:
            raise CatalogError(f"{origin}: '{decision.key}' is gated by unknown '{gate.decision}'")
        if parent.options and gate.equals not in parent.options:
            raise CatalogError(
                f"{origin}: '{decision.key}' gate value '{gate.equals}' is not an option of "
                f"'{parent.key}' ({', '.join(parent.options)})"
            )
        if decision.type == "enum" and not decision.options:
            raise CatalogError(f"{origin}: enum decision '{decision.key}' declares no options")


def coerce(decision: Decision, raw: str) -> Any:
    """Turn a document string into the typed value the target config needs."""
    value = raw.strip()
    if not value:
        raise ValueError(f"{decision.key}: empty value")

    if decision.type == "bool":
        lowered = value.lower()
        if lowered in {"true", "yes", "enabled"}:
            return True
        if lowered in {"false", "no", "disabled"}:
            return False
        raise ValueError(f"{decision.key}: '{value}' is not a boolean (expected true or false)")

    if decision.type == "string_list":
        items = [part.strip() for part in value.split(",") if part.strip()]
        if not items:
            raise ValueError(f"{decision.key}: list value contains no entries")
        return items

    if decision.options and value not in decision.options:
        raise ValueError(
            f"{decision.key}: '{value}' is not an approved option "
            f"({', '.join(decision.options)})"
        )
    return value
