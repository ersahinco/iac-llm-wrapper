"""LLM-based intent extractor driven by the requirement graph.

The data model (RequirementGraph with target_field/target_type) generates the
prompt. The LLM traverses the graph and extracts structured JSON; the model
validates and coerces types.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .requirements import RequirementGraph, describe_expression

_JSON_FENCE = re.compile(
    r"\A```(?:json)?[ \t]*\r?\n(?P<body>.*)\r?\n```[ \t]*\Z",
    re.IGNORECASE | re.DOTALL,
)
_JSON_WRAPPER_CHARS = frozenset("{}[]")


class _GraphResponse(BaseModel):
    """Strict shape for the graph-aware model response boundary."""

    model_config = ConfigDict(extra="forbid", strict=True)

    decisions: dict[str, Any] = Field(default_factory=dict)
    signal_decisions: dict[str, Any] = Field(default_factory=dict)
    gaps: list[dict[str, Any]] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)


def _load_json_object(text: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"LLM response is not valid JSON: {exc.msg}"
    if not isinstance(parsed, dict):
        return None, "LLM response must be a JSON object"
    return parsed, None


def _is_non_json_prose(value: str) -> bool:
    text = value.strip()
    if not text:
        return True
    if any(char in text for char in _JSON_WRAPPER_CHARS):
        return False
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return any(char.isalpha() for char in text)
    return False


def _safe_json_parse(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse valid JSON while removing only harmless presentation wrappers."""
    text = raw.strip()
    if not text:
        return None, "LLM response is empty"

    if "```" in text:
        fence = _JSON_FENCE.fullmatch(text)
        if fence is None:
            return None, "LLM response contains an incomplete JSON code fence"
        return _load_json_object(fence.group("body").strip())

    parsed, error = _load_json_object(text)
    if parsed is not None:
        return parsed, None

    object_start = text.find("{")
    if object_start < 0:
        return None, error
    try:
        recovered, object_end = json.JSONDecoder().raw_decode(text[object_start:])
    except json.JSONDecodeError:
        return None, error
    prefix = text[:object_start]
    suffix = text[object_start + object_end :]
    if not _is_non_json_prose(prefix) or not _is_non_json_prose(suffix):
        return None, "LLM response contains additional JSON structure"
    if not isinstance(recovered, dict):
        return None, "LLM response must contain one JSON object"
    return recovered, None


@dataclass
class LLMGraphResult:
    """Structured result from LLM graph traversal."""

    decisions: dict[str, str] = field(default_factory=dict)
    signal_decisions: dict[str, str] = field(default_factory=dict)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    raw_response: str = ""
    parse_error: str | None = None

    def to_intent(self, extractor: Extractor) -> Any:
        """Convert the decision map to a type-safe intent model."""
        return extractor._decisions_to_intent(self.decisions)


class Extractor:
    """LLM extractor that auto-generates prompts from a RequirementGraph.

    New decisions added to the graph automatically appear in the LLM prompt
    without code changes. The data model guides extraction — no regex needed.

    The LLM is prompted to *traverse the graph*: read prose, skip nodes that
    don't apply based on applies_if/applies_when gates, flag contradictions, detect
    signals. It returns structured JSON with decisions, signals, gaps, and
    contradictions.
    """

    def __init__(self, graph=None, pattern: str = "aws-lza") -> None:
        if graph is None:
            from .patterns import GLOBAL_REGISTRY

            graph = GLOBAL_REGISTRY.get(pattern).create_graph()
        self.graph = graph
        self.pattern = pattern
        self._intent_model = self._resolve_intent_model()

    def _resolve_intent_model(self) -> type[BaseModel]:
        """Resolve the intent model for this pattern."""
        graph_model = getattr(self.graph, "_intent_model", None)
        if isinstance(graph_model, type) and issubclass(graph_model, BaseModel):
            return graph_model
        from .patterns import GLOBAL_REGISTRY

        model = GLOBAL_REGISTRY.get(self.pattern).intent_factory
        if isinstance(model, type) and issubclass(model, BaseModel):
            return model
        raise TypeError(f"Pattern '{self.pattern}' must register a Pydantic intent model.")

    def _build_schema(self) -> dict[str, Any]:
        """Generate a flat JSON schema from the requirement graph."""
        schema: dict[str, Any] = {}
        for key, req in self.graph._requirements.items():
            if req.options:
                schema[key] = {
                    "type": "string",
                    "enum": req.options,
                    "description": req.question,
                }
            else:
                schema[key] = {"type": "string", "description": req.question}
        return schema

    def _build_graph_context(self) -> str:
        """Serialize the requirement graph for the LLM to reason over."""
        lines: list[str] = []
        for key, req in self.graph._requirements.items():
            lines.append(f"\n[{key}] {req.label}")
            lines.append(f"  Question: {req.question}")
            if req.options:
                lines.append(f"  Options: {', '.join(req.options)}")
            if req.default:
                lines.append(f"  Default: {req.default}")
            if req.applies_if:
                for cond_key, cond_vals in req.applies_if.items():
                    lines.append(
                        f"  Applies only when {cond_key} is one of: {', '.join(cond_vals)}"
                    )
            if req.applies_when:
                lines.append(f"  Applies when: {describe_expression(req.applies_when)}")
            if req.depends_on:
                lines.append(f"  Depends on: {', '.join(req.depends_on)}")
            if req.blocked_if:
                for cond_key, cond_vals in req.blocked_if.items():
                    lines.append(f"  Blocked when {cond_key} is one of: {', '.join(cond_vals)}")
            if req.blocked_when:
                lines.append(f"  Blocked when: {describe_expression(req.blocked_when)}")
            if req.signals:
                lines.append(f"  Migration/compliance signals: {', '.join(req.signals)}")
            if req.tradeoffs:
                lines.append("  Tradeoffs:")
                for t in req.tradeoffs:
                    lines.append(f"    - {t}")
        return "\n".join(lines)

    def _build_signal_context(self) -> str:
        """Auto-generate signal detection rules from graph metadata."""
        lines: list[str] = []
        signals_map: dict[str, list[str]] = {}
        for key, req in self.graph._requirements.items():
            if req.signals:
                for sig in req.signals:
                    signals_map.setdefault(sig, []).append(key)
        lines.append("3. Detect migration/compliance SIGNALS from natural language:")
        if signals_map:
            for sig, keys in sorted(signals_map.items()):
                lines.append(f"   - '{sig}' → {', '.join(keys)} may apply")
        else:
            lines.append("   (no specific signals defined for this pattern)")
        return "\n".join(lines)

    def build_prompt(self, text: str) -> str:
        """Build a graph-traversal prompt for the LLM."""
        schema = self._build_schema()
        schema_lines = []
        for key, meta in schema.items():
            desc = meta["description"]
            if "enum" in meta:
                vals = " | ".join(meta["enum"])
                schema_lines.append(f"  {key}: {desc} (one of: {vals})")
            else:
                schema_lines.append(f"  {key}: {desc}")

        schema_block = "\n".join(schema_lines)
        graph_context = self._build_graph_context()
        signal_context = self._build_signal_context()

        # Optional domain context from pattern metadata
        from .patterns import GLOBAL_REGISTRY

        domain_ctx = ""
        pattern_obj = GLOBAL_REGISTRY.get(self.pattern)
        if pattern_obj.prompt_context:
            domain_ctx = f"\n=== DOMAIN CONTEXT ===\n{pattern_obj.prompt_context}\n"

        return (
            "You are an architecture intent extractor.\n"
            "Your job is to READ the design document, TRAVERSE the requirement graph,\n"
            "and return structured JSON with your analysis.\n"
            f"{domain_ctx}\n"
            "=== REQUIREMENT GRAPH ===\n"
            f"{graph_context}\n\n"
            "=== EXTRACTION RULES ===\n"
            "1. Map each sentence in the document to relevant graph nodes.\n"
            "2. Skip nodes whose applies_if or applies_when gate is NOT satisfied by "
            "earlier decisions.\n"
            f"{signal_context}\n"
            "4. Flag CONTRADICTIONS between prose and graph constraints.\n"
            "5. Identify GAPS: applicable requirements that are not mentioned.\n"
            "6. Boolean values must be strings: 'true' or 'false'.\n"
            "7. Integer values must be strings (e.g., '2555', not 2555).\n"
            "8. If the document contains explicit 'schema_key: value' bullets or lines "
            "where schema_key appears in the SCHEMA, copy those keys into decisions "
            "exactly unless the value is contradicted later.\n"
            "9. Use only SCHEMA keys for decisions, signal_decisions, gaps, and "
            "contradictions. Do not report gaps for metadata outside SCHEMA.\n\n"
            "=== OUTPUT FORMAT ===\n"
            "Return ONLY valid JSON (no markdown fences) with this exact structure:\n"
            "{\n"
            '  "decisions": { ...key: value from document... },\n'
            '  "signal_decisions": { ...key: value inferred from signals... },\n'
            '  "gaps": [\n'
            '    {"key": "requirement_key", "reason": "why it is missing", '
            '"suggestion": "what to ask"}\n'
            "  ],\n"
            '  "contradictions": [\n'
            '    {"key": "requirement_key", "reason": "why it contradicts", "details": "..."}\n'
            "  ]\n"
            "}\n\n"
            "If the document does not mention a field, omit it from 'decisions'.\n"
            "Do NOT hallucinate values. If unsure about a SCHEMA key, omit the decision "
            "and list that SCHEMA key in 'gaps'.\n\n"
            f"=== SCHEMA (flat field map) ===\n{schema_block}\n\n"
            "=== DESIGN DOCUMENT ===\n"
            f"{text}"
        )

    def parse_response(self, response: str) -> LLMGraphResult:
        """Parse LLM response into structured LLMGraphResult.

        Supports graph-aware format (with decisions/signals/gaps) and flat
        decision maps from simpler backends.
        """
        result = LLMGraphResult(raw_response=response)
        data, result.parse_error = _safe_json_parse(response)
        if data is None:
            return result

        # Graph-aware format
        reserved_fields = {"decisions", "signal_decisions", "gaps", "contradictions"}
        if reserved_fields.intersection(data):
            try:
                graph_response = _GraphResponse.model_validate(data)
            except ValidationError as exc:
                result.parse_error = f"Invalid graph response shape: {exc.errors()[0]['msg']}"
                return result
            result.decisions = self._stringify_decisions(graph_response.decisions)
            result.signal_decisions = self._stringify_decisions(graph_response.signal_decisions)
            result.gaps = graph_response.gaps
            result.contradictions = graph_response.contradictions
            return result

        # Flat format: treat entire response as decisions.
        result.decisions = self._stringify_decisions(data)
        return result

    def _stringify_decisions(self, data: dict[str, Any]) -> dict[str, str]:
        """Serialize decisions without duplicating graph-owned type coercion."""
        serialized: dict[str, str] = {}
        for key, raw_val in data.items():
            if raw_val is None:
                continue
            req = self.graph._requirements.get(key)
            target_type = req.target_type if req is not None else "string"
            serialized[key] = self.graph.stringify_decision_value(raw_val, target_type)
        return serialized

    def _decisions_to_intent(self, decisions: dict[str, str]) -> Any:
        """Apply a flat decision map to an intent model with type coercion.

        Uses the pattern's intent_factory to create the model instance,
        then coerces values generically from Pydantic field annotations.
        """

        model = self._intent_model
        intent: Any = model()

        for key, req in self.graph._requirements.items():
            if req.target_field is None or key not in decisions:
                continue
            raw_val = decisions[key]
            if raw_val is None:
                continue

            parsed_val = self.graph._convert_value(
                raw_val,
                req.target_type,
                req.target_field,
            )

            if parsed_val is not None:
                RequirementGraph._set_nested(intent, req.target_field, parsed_val)

        return intent

    def extract(self, llm_response: str | None = None) -> Any:
        if llm_response is not None:
            result = self.parse_response(llm_response)
            intent = result.to_intent(self)
            return intent
        # No LLM response: return the model defaults.

        g = self.graph
        g.apply_defaults_for_remaining()
        intent = self._create_default_intent()
        g.apply_to_intent(intent)
        return intent

    def _create_default_intent(self) -> Any:
        """Create a default intent instance from the pattern's intent_factory."""
        return self._intent_model()
