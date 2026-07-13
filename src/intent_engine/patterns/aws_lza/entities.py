"""AWS LZA account and organizational-unit entity recovery."""

from __future__ import annotations

import re
from typing import Any

from .models import AwsLzaIntent, LzaAccount, LzaOrganizationalUnit

_SECTION_HEADINGS = {
    "organizational units": "ous",
    "accounts": "accounts",
}


def _find_section(text: str, heading: str) -> str:
    escaped = heading.replace(" ", r"\s+")
    flags = re.MULTILINE | re.DOTALL | re.IGNORECASE
    pattern = re.compile(rf"^##\s+{escaped}\s*$\n(.*?)(?=\n^##|\Z)", flags)
    match = pattern.search(text)
    if match:
        return match.group(1).strip()
    pattern = re.compile(rf"^###\s+{escaped}\s*$\n(.*?)(?=\n^#{{1,3}}\s|\Z)", flags)
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _parse_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for part in text.split(","):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _parse_ous(section: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for line in section.splitlines():
        match = re.match(r"[-*]\s+(.+?)\s*:\s*(.+)", line.strip())
        if match:
            items.append(
                {
                    "name": match.group(1).strip(),
                    "description": match.group(2).strip().lstrip(",").strip(),
                }
            )
    return items


def _parse_accounts(section: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for line in section.splitlines():
        match = re.match(r"[-*]\s+(.+?)\s*:\s*(.+)", line.strip())
        if not match:
            continue
        item = {"name": match.group(1).strip()}
        item.update(_parse_key_values(match.group(2)))
        items.append(item)
    return items


def extract_markdown_entities(text: str) -> dict[str, list[dict[str, Any]]]:
    """Recover explicitly structured AWS LZA accounts and OUs."""
    result: dict[str, list[dict[str, Any]]] = {"ous": [], "accounts": []}
    for heading, entity_type in _SECTION_HEADINGS.items():
        section = _find_section(text, heading)
        if not section:
            continue
        if entity_type == "ous":
            result[entity_type] = _parse_ous(section)
        else:
            result[entity_type] = _parse_accounts(section)
    return result


def apply_llm_entities(data: dict[str, Any], intent: AwsLzaIntent) -> None:
    """Apply AWS LZA entities from a structured model response."""
    intent.accounts.extend(
        LzaAccount.model_validate(item)
        for item in data.get("accounts", [])
        if isinstance(item, dict)
    )
    intent.ous.extend(
        LzaOrganizationalUnit.model_validate(item)
        for item in data.get("ous", [])
        if isinstance(item, dict)
    )


def _merge_named_entities(items: list[Any], values: list[Any], model: type[Any]) -> None:
    for value in values:
        if not isinstance(value, dict):
            continue
        candidate = model.model_validate(value)
        existing_index = next(
            (index for index, item in enumerate(items) if item.name == candidate.name),
            None,
        )
        if existing_index is None:
            items.append(candidate)
            continue

        existing = items[existing_index]
        updates = {
            field_name: getattr(candidate, field_name)
            for field_name in candidate.model_fields_set
            if field_name != "name"
            and (
                field_name not in existing.model_fields_set
                or getattr(existing, field_name) in (None, "", [], {})
            )
        }
        if updates:
            items[existing_index] = existing.model_copy(update=updates)


def merge_markdown_entities(data: dict[str, Any], intent: AwsLzaIntent) -> None:
    """Backfill deterministic AWS entities without overriding explicit LLM fields."""
    _merge_named_entities(intent.ous, data.get("ous", []), LzaOrganizationalUnit)
    _merge_named_entities(intent.accounts, data.get("accounts", []), LzaAccount)
