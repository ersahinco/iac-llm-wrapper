"""Orchestrator: drives the decision engine flow — extract, normalize, validate, generate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import ruamel.yaml

from .extractor import Extractor, LLMGraphResult
from .generator import generate_all
from .interview import InterviewEngine
from .llm_caller import LLMCaller, LLMEvidenceStore
from .markdown_extractor import extract_entities_from_markdown, extract_from_markdown
from .model_introspection import append_to_list_field
from .normalizer import normalize
from .patterns import GLOBAL_REGISTRY
from .validator import Violation, validate


class CompileError(Exception):
    def __init__(self, violations: list[Violation]):
        self.violations = violations
        msgs = "; ".join(f"{v.code}: {v.message}" for v in violations)
        super().__init__(msgs)


def _build_payload(
    intent: Any,
    pattern: str,
    design_doc_data: dict[str, Any] | None = None,
) -> Any:
    """Wrap intent in IaCIntentPayload with design doc and module inputs."""
    from .module_mapping import DesignDocument, IaCIntentPayload, map_intent_to_modules

    design_doc = DesignDocument()
    if design_doc_data:
        design_doc.project_name = design_doc_data.get("project_name", "")
        design_doc.business_justification = design_doc_data.get("business_justification", "")
        design_doc.estimated_tier = design_doc_data.get("estimated_tier", "")
        design_doc.compliance_tags = design_doc_data.get("compliance_tags", [])

    module_inputs = map_intent_to_modules(intent, pattern)
    return IaCIntentPayload(
        design_doc=design_doc,
        module_inputs=module_inputs,
        intent=intent,
    )


class LLMContextProvider:
    """Non-deterministic layer: the LLM reads prose and traverses the requirement graph.

    This is the *intent understanding* layer. The LLM may hallucinate, miss,
    or misread — that is expected and handled downstream by the deterministic
    harness.
    """

    def __init__(
        self,
        prose: str,
        graph,
        llm_caller: LLMCaller | None = None,
        evidence_store: LLMEvidenceStore | None = None,
    ) -> None:
        self.prose = prose
        self.graph = graph
        self.llm_caller = llm_caller
        self.evidence_store = evidence_store
        self.extractor = Extractor(graph=graph)

    def run(self) -> LLMGraphResult:
        """Run LLM graph traversal and return structured result.

        When no LLM is available, returns an empty result — the harness
        will apply defaults and fill gaps deterministically.
        """
        if self.llm_caller is None:
            return LLMGraphResult()

        prompt = self.extractor.build_prompt(self.prose)
        response, evidence = self.llm_caller.call(prompt)
        if self.evidence_store is not None:
            self.evidence_store.record(evidence)

        result = self.extractor.parse_response(response)
        return result


def compile_design(
    input_path: Path,
    output_dir: Path,
    graph=None,
    llm_caller: LLMCaller | None = None,
    evidence_store: LLMEvidenceStore | None = None,
    dry_run: bool = False,
    pattern: str = "baseline",
) -> None:
    """Extract, normalize, validate, and generate from a design doc.

    Two-layer architecture:
      1. Non-deterministic: LLMContextProvider reads prose and traverses graph
      2. Deterministic: harness applies gates, cascades, defaults, validates,
         generates artifacts, and records audit trail
    """
    if input_path.is_dir():
        texts = []
        for f in sorted(input_path.glob("*.md")):
            texts.append(f.read_text())
        text = "\n---\n".join(texts)
    else:
        text = input_path.read_text()

    pattern_obj = GLOBAL_REGISTRY.get(pattern)
    if graph is None:
        graph = pattern_obj.create_graph()

    # ------------------------------------------------------------------
    # Layer 0: Deterministic Markdown pre-processing
    # ------------------------------------------------------------------
    markdown_decisions = extract_from_markdown(text, graph)
    if markdown_decisions:
        graph.apply_decisions(markdown_decisions)

    # ------------------------------------------------------------------
    # Layer 1: Non-deterministic intent understanding (LLM)
    # ------------------------------------------------------------------
    llm_result = LLMContextProvider(
        prose=text,
        graph=graph,
        llm_caller=llm_caller,
        evidence_store=evidence_store,
    ).run()

    # ------------------------------------------------------------------
    # Layer 2: Deterministic harness processing
    # ------------------------------------------------------------------
    # 2a. Apply LLM-extracted decisions to the graph (gates + cascade)
    if llm_result.decisions:
        graph.apply_decisions(llm_result.decisions)

    # 2b. Apply signal-triggered decisions
    if llm_result.signal_decisions:
        graph.apply_decisions(llm_result.signal_decisions)

    # 2c. Apply addon suggestions (future: auto-compose addons)
    # Currently recorded in evidence but not auto-applied — architect decides

    # 2d. Fill remaining gaps with defaults
    graph.apply_defaults_for_remaining()

    # 2e. Build intent from LLM decisions (handles complex nested objects)
    # then overlay graph cascade decisions onto the same intent
    if llm_result.decisions or llm_result.signal_decisions:
        extractor = Extractor(graph=graph, pattern=pattern)
        intent = llm_result.to_intent(extractor)
    else:
        intent = pattern_obj.intent_factory()
        # Deterministic entity extraction fills accounts/OUs/workloads from
        # Markdown sections when no LLM is available.
        entities = extract_entities_from_markdown(text)
        for entity_type in ("ous", "accounts", "workloads"):
            for item in entities.get(entity_type, []):
                append_to_list_field(intent, entity_type, item)
    # Apply graph cascades (topology -> network.topology, etc.)
    graph.apply_to_intent(intent)

    # 2f. Apply normalizer guardrails
    if pattern_obj.normalizer is not None:
        intent = pattern_obj.normalizer(intent)
    else:
        intent = normalize(intent)

    # 2g. Validate fail-closed (graph-driven when available)
    violations = validate(intent, graph=graph, extra_validators=pattern_obj.validators)
    if violations:
        raise CompileError(violations)

    if dry_run:
        return

    # 2h. Generate artifacts
    payload = _build_payload(intent, pattern, llm_result.design_doc)
    generate_all(payload, output_dir)


def compile_from_interview(
    decisions: dict[str, str],
    output_dir: Path,
    accept_defaults: bool = True,
    pattern: str = "baseline",
) -> None:
    pattern_obj = GLOBAL_REGISTRY.get(pattern)
    graph = pattern_obj.create_graph()
    engine = InterviewEngine(graph, pattern=pattern)
    engine.run_from_decisions(decisions)
    if accept_defaults:
        engine.apply_defaults_for_remaining()
    intent = engine.to_intent()
    if pattern_obj.normalizer is not None:
        intent = pattern_obj.normalizer(intent)
    else:
        intent = normalize(intent)
    violations = validate(intent, graph=graph, extra_validators=pattern_obj.validators)
    if violations:
        raise CompileError(violations)
    generate_all(_build_payload(intent, pattern), output_dir)

    # Write decision audit trail for traceability
    audit = graph.audit_log()
    if audit:
        import ruamel.yaml

        yaml = ruamel.yaml.YAML()
        yaml.default_flow_style = False
        audit_path = output_dir / "decision-audit.yaml"
        with open(audit_path, "w") as f:
            yaml.dump({"auditTrail": audit}, f)


def validate_generated(input_dir: Path, pattern: str = "baseline") -> list[str]:
    errors = []
    from .patterns import GLOBAL_REGISTRY

    pattern_obj = GLOBAL_REGISTRY.get(pattern)
    required_files = pattern_obj.required_artifacts or []
    for fname in required_files:
        if not (input_dir / fname).exists():
            errors.append(f"Missing required file: {fname}")

    # Run pattern-specific artifact validators
    for validator in pattern_obj.artifact_validators:
        errors.extend(validator(input_dir))

    return errors


def review_reports(before_path: Path, after_path: Path) -> dict:
    """Diff two decision reports and return structured review."""
    yaml_loader = ruamel.yaml.YAML(typ="safe")

    with open(before_path) as f:
        before = yaml_loader.load(f) or {}
    with open(after_path) as f:
        after = yaml_loader.load(f) or {}

    result: dict = {"changes": [], "added": [], "removed": [], "audit": {}}

    def _flatten(d: dict, prefix: str = "") -> dict[str, Any]:
        items: dict[str, Any] = {}
        for k, v in d.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict) and k not in (
                "wellArchitectedCoverage",
                "decisionAuditTrail",
            ):
                items.update(_flatten(v, key))
            elif isinstance(v, list):
                items[key] = sorted(v) if v and not isinstance(v[0], dict) else v
            elif k == "wellArchitectedCoverage":
                pass
            elif k == "decisionAuditTrail":
                pass
            else:
                items[key] = v
        return items

    flat_before = _flatten(before)
    flat_after = _flatten(after)

    all_keys = set(flat_before) | set(flat_after)

    for key in sorted(all_keys):
        b_val = flat_before.get(key)
        a_val = flat_after.get(key)
        if key not in flat_before:
            result["added"].append({"key": key, "value": a_val})
        elif key not in flat_after:
            result["removed"].append({"key": key, "value": b_val})
        elif b_val != a_val:
            result["changes"].append({"key": key, "before": b_val, "after": a_val})

    # WA coverage diff
    b_wa = before.get("wellArchitectedCoverage", {}) or {}
    a_wa = after.get("wellArchitectedCoverage", {}) or {}
    result["wellArchitectedCoverage"] = {"before": b_wa, "after": a_wa}

    # Audit trail diff
    b_audit = before.get("decisionAuditTrail", []) or []
    a_audit = after.get("decisionAuditTrail", []) or []
    result["audit"] = {
        "before_count": len(b_audit),
        "after_count": len(a_audit),
        "new_entries": a_audit[len(b_audit) :] if len(a_audit) > len(b_audit) else [],
    }

    return result


def _build_section_map(
    pattern: str,
    addon_names: list[str] | None,
    graph,
) -> dict[str, tuple[str, str | None]]:
    """Build a section map from pattern metadata + addons + category fallback.

    New requirements automatically appear in templates under their category
    if no explicit mapping is provided.
    """
    from .patterns import ADDON_REGISTRY, GLOBAL_REGISTRY

    pattern_obj = GLOBAL_REGISTRY.get(pattern)
    section_map: dict[str, tuple[str, str | None]] = dict(pattern_obj.section_map)
    if addon_names:
        section_map.update(ADDON_REGISTRY.get_section_map(addon_names))

    # Fallback: derive section from requirement category
    _CATEGORY_TO_SECTION: dict[str, str] = {
        "organization": "Region",
        "network": "Network",
        "security": "Security",
        "compliance": "Security",
        "hybrid": "Hybrid Connectivity",
        "cicd": "CI/CD",
        "cost": "Network",
        "workload": "Workloads",
        "general": "General",
    }
    for key, req in graph._requirements.items():
        if key in section_map:
            continue
        category = req.category or "general"
        section_name = _CATEGORY_TO_SECTION.get(category)
        if section_name:
            section_map[key] = (section_name, req.key)

    return section_map


def generate_template(
    pattern: str = "baseline",
    addon_names: list[str] | None = None,
) -> str:
    """Generate a Markdown design doc scaffold from a pattern + optional addons."""
    from .patterns import ADDON_REGISTRY, GLOBAL_REGISTRY

    pattern_obj = GLOBAL_REGISTRY.get(pattern)
    graph = pattern_obj.create_graph()
    if addon_names:
        graph = ADDON_REGISTRY.compose(graph, addon_names)

    section_map = _build_section_map(pattern, addon_names, graph)

    sections_content: dict[str, list[tuple[str, Any, str | None]]] = {}
    for key, req in graph._requirements.items():
        info = section_map.get(key)
        if info is None:
            continue
        section_name, field_name = info
        sections_content.setdefault(section_name, []).append((key, req, field_name))

    lines: list[str] = []
    addon_label = f" + {', '.join(addon_names)}" if addon_names else ""
    lines.append(f"# Design Document — {pattern} pattern{addon_label}")
    lines.append("#")
    lines.append("# Generated by intent-engine template. Fill in your decisions below.")
    lines.append("# Lines starting with # are comments. Uncomment and edit to set values.")
    lines.append("")

    section_order = pattern_obj.section_order or []
    free_form_examples = pattern_obj.free_form_examples or {}

    for section_name in section_order:
        has_fields = section_name in sections_content
        has_examples = section_name in free_form_examples
        if not has_fields and not has_examples:
            continue

        lines.append(f"## {section_name}")
        lines.append("")

        if section_name in free_form_examples:
            for example in free_form_examples[section_name]:
                lines.append(f"# - {example}")
            lines.append("")
            # Only skip field-based content if there are no requirements for this section
            if section_name not in sections_content:
                continue

        for key, req, field_name in sections_content.get(section_name, []):
            if req.applies_if:
                for cond_key, cond_vals in req.applies_if.items():
                    lines.append(f"# Only when {cond_key} is one of: {', '.join(cond_vals)}")

            lines.append(f"# {req.question}")
            if req.options:
                lines.append(f"# Options: {', '.join(req.options)}")
            if req.default:
                lines.append(f"# Default: {req.default}")

            if field_name is None:
                # Topology field: show default uncommented, alternatives commented
                if req.options:
                    for opt in req.options:
                        if opt == req.default:
                            lines.append(f"- {opt}")
                        else:
                            lines.append(f"# - {opt}")
                elif req.default:
                    lines.append(f"- {req.default}")
            else:
                line = f"- {field_name}: "
                if req.default:
                    line += req.default
                lines.append(line)

            lines.append("")

    return "\n".join(lines)


def explain_report(report_path: Path) -> str:
    yaml_loader = ruamel.yaml.YAML(typ="safe")
    with open(report_path) as f:
        report = yaml_loader.load(f) or {}

    lines = ["=== Decision Report ===", ""]

    def _render(data: Any, indent: int = 0) -> None:
        prefix = "  " * indent
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    lines.append(f"{prefix}{k}:")
                    _render(v, indent + 1)
                else:
                    lines.append(f"{prefix}{k}: {v}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    lines.append(f"{prefix}-")
                    _render(item, indent + 1)
                else:
                    lines.append(f"{prefix}- {item}")
        else:
            lines.append(f"{prefix}{data}")

    _render(report)
    return "\n".join(lines)
