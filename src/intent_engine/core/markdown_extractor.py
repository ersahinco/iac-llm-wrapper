"""Deterministic Markdown pre-processor.

Extracts structured key-value pairs from Markdown design documents before
the LLM runs. This provides a reliable ground-truth layer for well-structured
docs and reduces hallucination by pre-filling known values.
"""

from __future__ import annotations

import re
from typing import Any

from .requirements import RequirementGraph


class MarkdownExtractor:
    """Deterministic extractor for structured Markdown design documents.

    Scans Markdown for sections and key-value pairs that match the
    requirement graph, producing a decision map without LLM involvement.
    """

    def __init__(self, graph: RequirementGraph) -> None:
        self.graph = graph

    def extract(self, text: str) -> dict[str, str]:
        """Extract decisions from Markdown text.

        Returns a flat dict of requirement_key → string_value.
        """
        decisions: dict[str, str] = {}

        # Build reverse lookup: field_name / target_field → requirement_key
        field_to_key: dict[str, str] = {}
        for key, req in self.graph._requirements.items():
            if req.target_field:
                # Map both the full dotted path and the last segment
                field_to_key[req.target_field] = key
                if "." in req.target_field:
                    field_to_key[req.target_field.split(".")[-1]] = key
            field_to_key[key] = key

        # Parse lines that look like key-value pairs
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Match "- key: value" or "- key = value" or "key: value"
            match = re.match(r"[-*]?\s*(\w[\w_]*(?:\.[\w_]+)?)\s*[:=]\s*(.+)", line)
            if not match:
                continue

            raw_key, raw_val = match.group(1).strip(), match.group(2).strip()

            # Clean value (remove trailing comments, markdown formatting)
            raw_val = raw_val.split("#")[0].strip()
            raw_val = raw_val.strip("`").strip('"').strip("'")

            # Try exact key match first, then field name match
            req_key = None
            if raw_key in field_to_key:
                req_key = field_to_key[raw_key]
            elif raw_key.lower().replace(" ", "_") in field_to_key:
                req_key = field_to_key[raw_key.lower().replace(" ", "_")]

            if req_key is None:
                continue

            # Validate against requirement options if available
            matched_req = self.graph._requirements.get(req_key)
            if matched_req and matched_req.options:
                val_lower = raw_val.lower()
                matched = next(
                    (opt for opt in matched_req.options if opt.lower() == val_lower),
                    None,
                )
                if matched:
                    raw_val = matched
                else:
                    # Value not in allowed options — skip or keep raw?
                    # Keep raw so the LLM / validator can flag it
                    pass

            decisions[req_key] = raw_val

        return decisions


def extract_from_markdown(text: str, graph: RequirementGraph) -> dict[str, str]:
    """Convenience function: extract decisions from Markdown using a graph."""
    extractor = MarkdownExtractor(graph)
    return extractor.extract(text)


# ---------------------------------------------------------------------------
# Deterministic entity extraction (accounts, OUs, workloads from Markdown)
# ---------------------------------------------------------------------------
# When no LLM is available, these functions parse structured sections like:
#   ## Accounts
#   - Network: ou=Infrastructure, description=Central networking
#
# The parsed format matches what the LLM would return in its JSON response,
# so downstream code (to_intent, generators) works identically.

_SECTION_HEADINGS = {
    "organizational units": "ous",
    "accounts": "accounts",
    "workloads": "workloads",
}


def _find_section(text: str, heading: str) -> str:
    """Return content under a '## <heading>' section.

    Heading is a plain string (not regex) — we handle escaping ourselves
    to avoid re.escape mangling spaces into \\ .
    """
    esc = heading.replace(" ", r"\s+")
    flags = re.MULTILINE | re.DOTALL | re.IGNORECASE
    pat = re.compile(rf"^##\s+{esc}\s*$\n(.*?)(?=\n^##|\Z)", flags)
    m = pat.search(text)
    if m:
        return m.group(1).strip()
    # Try ### level
    pat = re.compile(rf"^###\s+{esc}\s*$\n(.*?)(?=\n^#{1, 3}\s|\Z)", flags)
    m = pat.search(text)
    return m.group(1).strip() if m else ""


def _parse_kv_pairs(text: str) -> dict[str, str]:
    """Parse 'key=val, key2=val2' comma-separated pairs."""
    pairs: dict[str, str] = {}
    for part in text.split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            pairs[k.strip()] = v.strip()
    return pairs


def _parse_ou_items(section: str) -> list[dict[str, str]]:
    """Parse '- <name>: <description>' bullet items."""
    items: list[dict[str, str]] = []
    for line in section.splitlines():
        line = line.strip()
        m = re.match(r"[-*]\s+(.+?)\s*:\s*(.+)", line)
        if m:
            name = m.group(1).strip()
            desc = m.group(2).strip().lstrip(",").strip()
            items.append({"name": name, "description": desc})
    return items


def _parse_account_items(section: str) -> list[dict[str, str]]:
    """Parse '- <name>: ou=<ou>, description=<desc>' bullet items."""
    items: list[dict[str, str]] = []
    for line in section.splitlines():
        line = line.strip()
        m = re.match(r"[-*]\s+(.+?)\s*:\s*(.+)", line)
        if m:
            name = m.group(1).strip()
            rest = m.group(2).strip()
            item: dict[str, str] = {"name": name}
            item.update(_parse_kv_pairs(rest))
            items.append(item)
    return items


def _parse_workload_items(section: str) -> list[dict[str, Any]]:
    """Parse '- <name>: target_account=X, key=val, ...' bullet items.

    Coerces known types (bool, int) to match Pydantic model expectations.
    """
    _BOOL_FIELDS = {"public_ingress"}
    _INT_FIELDS = {"port", "cpu", "memory"}

    items: list[dict[str, Any]] = []
    for line in section.splitlines():
        line = line.strip()
        m = re.match(r"[-*]\s+(.+?)\s*:\s*(.+)", line)
        if m:
            name = m.group(1).strip()
            rest = m.group(2).strip()
            item: dict[str, Any] = {"name": name}
            item.update(_parse_kv_pairs(rest))
            # Type coercion
            for k in list(item):
                if k in _BOOL_FIELDS:
                    item[k] = str(item[k]).lower() in ("true", "yes", "1")
                elif k in _INT_FIELDS:
                    try:
                        item[k] = int(float(item[k]))
                    except (ValueError, TypeError):
                        pass
            items.append(item)
    return items


def extract_entities_from_markdown(text: str) -> dict[str, list[dict[str, Any]]]:
    """Extract accounts, OUs, and workloads from Markdown sections.

    Returns dict with keys 'ous', 'accounts', 'workloads', each a list of
    dicts matching the LLM JSON output format. Returns empty lists when
    no matching sections are found.
    """
    result: dict[str, list[dict[str, Any]]] = {"ous": [], "accounts": [], "workloads": []}
    for heading, entity_type in _SECTION_HEADINGS.items():
        section = _find_section(text, heading)
        if not section:
            continue
        if entity_type == "ous":
            result[entity_type] = _parse_ou_items(section)
        elif entity_type == "accounts":
            result[entity_type] = _parse_account_items(section)
        elif entity_type == "workloads":
            result[entity_type] = _parse_workload_items(section)
    return result
