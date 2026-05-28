"""LLM-based intent extractor driven by the requirement graph.

The data model (RequirementGraph with target_field/target_type) generates the
prompt. The LLM traverses the graph, detects signals, and extracts structured
JSON; the model validates and coerces types.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from .model_introspection import coerce_value, resolve_field_info
from .requirements import RequirementGraph


def _str(v: Any) -> str | None:
    if v is None:
        return None
    return str(v)


def _bool(v: Any) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("true", "yes", "1")


def _safe_json_parse(raw: str) -> dict[str, Any] | None:
    """Parse JSON with recovery for common LLM malformations.

    Handles markdown fences, trailing commas, and extra closing braces
    that small LLMs occasionally produce.
    """
    text = raw.strip()
    # Strip markdown fences
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2:
            text = "\n".join(lines[1:-1]).strip()
    if text.startswith("json"):
        text = text[4:].strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
    # Try full parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    # Brace-matching recovery: find outermost {…} pair
    brace_matches = list(re.finditer(r"\{.*\}", text, re.DOTALL))
    if brace_matches:
        last_brace = brace_matches[-1].group()
        try:
            parsed = json.loads(last_brace)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    # Comma-insertion recovery: LLMs often miss commas between top-level keys.
    # Insert commas after } or ] when followed by whitespace + " (a new key).
    fixed = re.sub(r'([}\]])[\t\n ]+(?=")', r"\1, ", text)
    try:
        parsed = json.loads(fixed)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    # Progressive truncation: try stripping trailing content after each }
    for i in range(len(text) - 1, 0, -1):
        if text[i] == "}":
            try:
                parsed = json.loads(text[: i + 1])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
    return None


def _int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


@dataclass
class LLMGraphResult:
    """Structured result from LLM graph traversal."""

    decisions: dict[str, str] = field(default_factory=dict)
    design_doc: dict[str, Any] = field(default_factory=dict)
    signal_decisions: dict[str, str] = field(default_factory=dict)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    raw_response: str = ""

    def to_intent(self, extractor: Extractor) -> Any:
        """Convert the decision map to a type-safe intent model."""
        intent = extractor._decisions_to_intent(self.decisions)
        parsed = _safe_json_parse(self.raw_response)
        if isinstance(parsed, dict):
            extractor._parse_workloads(parsed, intent)
            extractor._parse_accounts(parsed, intent)
            extractor._parse_ous(parsed, intent)
        return intent


class Extractor:
    """LLM extractor that auto-generates prompts from a RequirementGraph.

    New decisions added to the graph automatically appear in the LLM prompt
    without code changes. The data model guides extraction — no regex needed.

    The LLM is prompted to *traverse the graph*: read prose, skip nodes that
    don't apply based on applies_if gates, flag contradictions, detect
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

    def _resolve_intent_model(self) -> type[BaseModel] | None:
        """Resolve the intent model for this pattern."""
        graph_model = getattr(self.graph, "_intent_model", None)
        if isinstance(graph_model, type) and issubclass(graph_model, BaseModel):
            return graph_model
        try:
            from .patterns import GLOBAL_REGISTRY

            pattern_obj = GLOBAL_REGISTRY.get(self.pattern)
            model = pattern_obj.intent_factory
            if isinstance(model, type) and issubclass(model, BaseModel):
                return model
        except Exception:
            pass
        return None

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
            if req.depends_on:
                lines.append(f"  Depends on: {', '.join(req.depends_on)}")
            if req.blocked_if:
                for cond_key, cond_vals in req.blocked_if.items():
                    lines.append(f"  Blocked when {cond_key} is one of: {', '.join(cond_vals)}")
            if req.signals:
                lines.append(f"  Migration/compliance signals: {', '.join(req.signals)}")
            if req.tradeoffs:
                lines.append("  Tradeoffs:")
                for t in req.tradeoffs:
                    lines.append(f"    - {t}")
            if req.consequences:
                lines.append("  Consequences:")
                for c in req.consequences:
                    lines.append(f"    - {c}")
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
        domain_ctx = ""
        try:
            from .patterns import GLOBAL_REGISTRY

            pattern_obj = GLOBAL_REGISTRY.get(self.pattern)
            if pattern_obj.prompt_context:
                domain_ctx = f"\n=== DOMAIN CONTEXT ===\n{pattern_obj.prompt_context}\n"
        except Exception:
            pass

        return (
            "You are an architecture intent extractor.\n"
            "Your job is to READ the design document, TRAVERSE the requirement graph,\n"
            "and return structured JSON with your analysis.\n"
            f"{domain_ctx}\n"
            "=== REQUIREMENT GRAPH ===\n"
            f"{graph_context}\n\n"
            "=== EXTRACTION RULES ===\n"
            "1. Map each sentence in the document to relevant graph nodes.\n"
            "2. Skip nodes whose 'applies_if' gate is NOT satisfied by earlier decisions.\n"
            f"{signal_context}\n"
            "4. Flag CONTRADICTIONS between prose and graph constraints.\n"
            "5. Identify GAPS: applicable requirements that are not mentioned.\n"
            "6. Boolean values must be strings: 'true' or 'false'.\n"
            "7. Integer values must be strings (e.g., '2555', not 2555).\n"
            "8. If the document mentions accounts, workloads, or OUs, include them as "
            "top-level JSON arrays in the output.\n"
            '9. Account format: {"name": "...", "ou": "...", "description": "..."}\n'
            '10. Workload format: {"name": "...", "target_account": "...", '
            '"network_mode": "private" (or "public"), '
            '"runtime": "ecs-fargate" (or "ec2" or "eks"), '
            '"public_ingress": false, "port": 8080, "cpu": 256, "memory": 512}\n'
            '11. OU format: {"name": "...", "description": "..."}\n\n'
            "=== EXAMPLE OUTPUT ===\n"
            "For a document with region=eu-central-1, topology=hub-spoke, "
            "an OU 'Infrastructure', and one account 'prod' under it:\n"
            "{\n"
            '  "decisions": {\n'
            '    "primary_region": "eu-central-1",\n'
            '    "topology": "hub-spoke"\n'
            "  },\n"
            '  "accounts": [{"name": "prod", "ou": "Infrastructure", '
            '"description": "Production account"}],\n'
            '  "ous": [{"name": "Infrastructure", '
            '"description": "Shared services OU"}],\n'
            '  "design_doc": {},\n'
            '  "signal_decisions": {},\n'
            '  "gaps": [],\n'
            '  "contradictions": []\n'
            "}\n\n"
            "=== OUTPUT FORMAT ===\n"
            "Return ONLY valid JSON (no markdown fences) with this exact structure:\n"
            "{\n"
            '  "decisions": { ...key: value from document... },\n'
            '  "accounts": [{"name": "...", "ou": "...", "description": "..."}, ...],\n'
            '  "ous": [{"name": "...", "description": "..."}, ...],\n'
            '  "workloads": [{"name": "...", "target_account": "...", '
            '"network_mode": "private", "runtime": "ecs-fargate", '
            '"public_ingress": false, "port": 8080, "cpu": 256, "memory": 512}, ...],\n'
            '  "design_doc": {\n'
            '    "project_name": "...",\n'
            '    "business_justification": "...",\n'
            '    "estimated_tier": "...",\n'
            '    "compliance_tags": ["..."]\n'
            "  },\n"
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
            "Do NOT hallucinate values. If unsure, omit the key and list it in 'gaps'.\n\n"
            f"=== SCHEMA (flat field map) ===\n{schema_block}\n\n"
            "=== DESIGN DOCUMENT ===\n"
            f"{text}"
        )

    def parse_response(self, response: str) -> LLMGraphResult:
        """Parse LLM response into structured LLMGraphResult.

        Supports graph-aware format (with decisions/signals/gaps) and flat
        decision maps from simpler backends.
        """
        data: dict[str, Any] = _safe_json_parse(response) or {}
        result = LLMGraphResult(raw_response=response)

        # Graph-aware format
        if "decisions" in data or "signal_decisions" in data:
            result.decisions = self._coerce_decisions(data.get("decisions", {}))
            result.design_doc = data.get("design_doc", {})
            result.signal_decisions = self._coerce_decisions(data.get("signal_decisions", {}))
            result.gaps = data.get("gaps", [])
            result.contradictions = data.get("contradictions", [])
            return result

        # Flat format: treat entire response as decisions.
        result.decisions = self._coerce_decisions(data)
        return result

    def _coerce_decisions(self, data: dict[str, Any]) -> dict[str, str]:
        """Coerce decision values to strings using graph target_type metadata."""
        coerced: dict[str, str] = {}
        for key, raw_val in data.items():
            if raw_val is None:
                continue
            req = self.graph._requirements.get(key)
            if req is None:
                # Unknown key — keep as string
                coerced[key] = str(raw_val)
                continue
            target_type = req.target_type
            if target_type == "bool":
                if isinstance(raw_val, bool):
                    coerced[key] = "true" if raw_val else "false"
                else:
                    coerced[key] = (
                        "true" if str(raw_val).lower() in ("true", "yes", "1") else "false"
                    )
            elif target_type == "int":
                try:
                    coerced[key] = str(int(float(raw_val)))
                except (ValueError, TypeError):
                    coerced[key] = str(raw_val)
            elif target_type in ("cidr_list", "string_list"):
                if isinstance(raw_val, list):
                    coerced[key] = ",".join(str(c) for c in raw_val)
                else:
                    coerced[key] = str(raw_val)
            else:
                coerced[key] = str(raw_val)
        return coerced

    def _decisions_to_intent(self, decisions: dict[str, str]) -> Any:
        """Apply a flat decision map to an intent model with type coercion.

        Uses the pattern's intent_factory to create the model instance,
        then coerces values generically from Pydantic field annotations.
        """

        model = self._intent_model
        if model is None:
            # Fallback: create a plain object when no model is known
            class _FallbackIntent:
                pass

            intent: Any = _FallbackIntent()
        else:
            intent = model()

        for key, req in self.graph._requirements.items():
            if req.target_field is None or key not in decisions:
                continue
            raw_val = decisions[key]
            if raw_val is None:
                continue

            parsed_val: Any = None
            if model is not None:
                try:
                    _, annotation = resolve_field_info(model, req.target_field)
                    parsed_val = coerce_value(raw_val, annotation)
                except Exception:
                    # Fall back to target_type string match.
                    pass

            if parsed_val is None:
                # Fallback for string-based target_type metadata.
                target_type = req.target_type
                if target_type == "string":
                    parsed_val = _str(raw_val)
                elif target_type == "int":
                    parsed_val = _int(raw_val)
                elif target_type == "bool":
                    parsed_val = _bool(raw_val)
                elif target_type in ("cidr_list", "string_list"):
                    if isinstance(raw_val, str):
                        parsed_val = [c.strip() for c in raw_val.split(",") if c.strip()]
                    elif isinstance(raw_val, list):
                        parsed_val = [str(c) for c in raw_val]
                else:
                    # Try to find the type by name in the intent model's module
                    try:
                        enum_cls = getattr(model, target_type, None)
                        if enum_cls is None:
                            import importlib

                            mod = importlib.import_module(model.__module__)
                            enum_cls = getattr(mod, target_type, None)
                        if enum_cls is not None and isinstance(enum_cls, type):
                            s = _str(raw_val)
                            if s:
                                parsed_val = enum_cls(s)
                    except Exception:
                        pass

            if parsed_val is not None:
                RequirementGraph._set_nested(intent, req.target_field, parsed_val)

        return intent

    def _parse_workloads(self, data: dict[str, Any], intent: Any) -> None:
        if not hasattr(intent, "workloads"):
            return
        from .model_introspection import append_to_list_field

        for wl_data in data.get("workloads", []):
            if isinstance(wl_data, dict):
                append_to_list_field(intent, "workloads", wl_data)

    def _parse_accounts(self, data: dict[str, Any], intent: Any) -> None:
        if not hasattr(intent, "accounts"):
            return
        from .model_introspection import append_to_list_field

        for acct_data in data.get("accounts", []):
            if isinstance(acct_data, dict):
                append_to_list_field(intent, "accounts", acct_data)

    def _parse_ous(self, data: dict[str, Any], intent: Any) -> None:
        if not hasattr(intent, "ous"):
            return
        from .model_introspection import append_to_list_field

        for ou_data in data.get("ous", data.get("ou", [])):
            if isinstance(ou_data, dict):
                append_to_list_field(intent, "ous", ou_data)

    def extract(self, text: str, llm_response: str | None = None) -> Any:
        if llm_response is not None:
            result = self.parse_response(llm_response)
            intent = result.to_intent(self)
            return intent
        # No LLM response — return default intent (data model drives defaults)

        g = self.graph
        g.apply_defaults_for_remaining()
        intent = self._create_default_intent()
        g.apply_to_intent(intent)
        return intent

    def _create_default_intent(self) -> Any:
        """Create a default intent instance from the pattern's intent_factory."""
        model = self._intent_model
        if model is not None:
            return model()

        # Fallback to dynamic object when no model is known
        class _FallbackIntent:
            pass

        return _FallbackIntent()
