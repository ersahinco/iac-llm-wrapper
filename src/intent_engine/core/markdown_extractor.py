"""Deterministic Markdown pre-processor.

Extracts structured key-value pairs from Markdown design documents before
the LLM runs. This provides a reliable ground-truth layer for well-structured
docs and reduces hallucination by pre-filling known values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .requirements import RequirementGraph


@dataclass
class MarkdownExtractionResult:
    decisions: dict[str, str]
    contradictions: list[dict[str, Any]]


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
        return self.extract_with_diagnostics(text).decisions

    def extract_with_diagnostics(self, text: str) -> MarkdownExtractionResult:
        """Extract decisions and structured duplicate-key contradictions."""
        decisions: dict[str, str] = {}
        contradictions: list[dict[str, Any]] = []

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

            previous = decisions.get(req_key)
            if previous is not None and previous != raw_val:
                contradictions.append(
                    {
                        "key": req_key,
                        "reason": "conflicting structured Markdown values",
                        "details": f"{req_key} was set to {previous!r} and later {raw_val!r}",
                        "source": "markdown",
                    }
                )
            decisions[req_key] = raw_val

        return MarkdownExtractionResult(decisions=decisions, contradictions=contradictions)


def extract_from_markdown(text: str, graph: RequirementGraph) -> dict[str, str]:
    """Convenience function: extract decisions from Markdown using a graph."""
    extractor = MarkdownExtractor(graph)
    return extractor.extract(text)


def extract_from_markdown_with_diagnostics(
    text: str,
    graph: RequirementGraph,
) -> MarkdownExtractionResult:
    """Extract decisions and deterministic structured contradictions."""
    extractor = MarkdownExtractor(graph)
    return extractor.extract_with_diagnostics(text)
