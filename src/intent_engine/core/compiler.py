"""Orchestrator: drives the decision engine flow — extract, validate, generate."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

from .baseline import (
    baseline_decisions_from_bundle,
    baseline_summary_from_bundle,
    without_locked_decisions,
)
from .compile_artifacts import (
    generate_validated_artifacts as _generate_validated_artifacts,
)
from .compile_artifacts import (
    remove_generated_artifacts as _remove_generated_artifacts,
)
from .compile_artifacts import (
    validate_generated as _validate_generated_impl,
)
from .compile_artifacts import (
    validate_generated_violations as _validate_generated_violations_impl,
)
from .compile_artifacts import (
    write_intent_yaml_artifact as _write_yaml_artifact,
)
from .document_diff import (
    build_incremental_llm_context,
    build_input_diff_report,
    incremental_decision_report,
)
from .extractor import Extractor, LLMGraphResult
from .interview import InterviewEngine
from .llm_caller import LLMCaller, LLMEvidenceStore
from .markdown_extractor import extract_from_markdown_with_diagnostics
from .observability import build_model_benchmark
from .patterns import GLOBAL_REGISTRY
from .readiness import (
    blocking_contradictions as _blocking_contradictions,
)
from .readiness import (
    blocking_gaps as _blocking_gaps,
)
from .readiness import (
    build_handoff_readiness as _build_handoff_readiness,
)
from .readiness import (
    gap_is_resolved as _gap_is_resolved,
)
from .validator import Violation, validate
from .yaml_utils import read_yaml_mapping


class CompileError(Exception):
    def __init__(self, violations: list[Violation], readiness: dict[str, Any] | None = None):
        self.violations = violations
        self.readiness = readiness or {}
        msgs = "; ".join(f"{v.code}: {v.message}" for v in violations)
        super().__init__(msgs)


def _build_payload(
    intent: Any,
    pattern: str,
    decisions: dict[str, Any] | None = None,
    extraction_summary: dict[str, Any] | None = None,
    handoff_readiness: dict[str, Any] | None = None,
    target_capability_report: dict[str, Any] | None = None,
    source_context: dict[str, Any] | None = None,
    decision_audit: list[dict[str, Any]] | None = None,
) -> Any:
    """Wrap validated intent with artifact generation context."""
    from .module_mapping import IaCIntentPayload

    pattern_obj = GLOBAL_REGISTRY.get(pattern)
    module_inputs = pattern_obj.module_mapper(intent) if pattern_obj.module_mapper else []
    return IaCIntentPayload(
        module_inputs=module_inputs,
        intent=intent,
        pattern=pattern,
        decisions=decisions or {},
        extraction_summary=extraction_summary or {},
        target_capability_report=target_capability_report or {},
        source_context=source_context or {},
        decision_audit=decision_audit or [],
        handoff_readiness=handoff_readiness or {},
    )


def _enrich_handoff_readiness(
    pattern: str,
    intent: Any,
    readiness: dict[str, Any],
) -> dict[str, Any]:
    pattern_obj = GLOBAL_REGISTRY.get(pattern)
    if pattern_obj.readiness_enricher is None:
        return readiness
    return pattern_obj.readiness_enricher(intent, dict(readiness))


def _to_builtin(value: Any) -> Any:
    if hasattr(value, "value"):
        return _to_builtin(value.value)
    if isinstance(value, dict):
        return {str(k): _to_builtin(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_builtin(item) for item in value]
    return value


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _source_context(
    *,
    mode: str,
    text: str = "",
    input_path: Path | None = None,
    paths: list[Path] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "mode": mode,
        "sha256": _sha256_text(text),
    }
    if input_path is not None:
        context["path"] = str(input_path)
    if paths:
        context["paths"] = [str(path) for path in paths]
    if extra:
        context.update(extra)
    return context


def _llm_result_violations(graph, llm_result: LLMGraphResult) -> list[Violation]:
    violations: list[Violation] = []
    for gap in _blocking_gaps(graph, llm_result.gaps):
        key = gap.get("key", "unknown") if isinstance(gap, dict) else "unknown"
        reason = gap.get("reason", "missing decision") if isinstance(gap, dict) else str(gap)
        violations.append(
            Violation(
                code=f"LLM_GAP_{str(key).upper()}",
                message=f"LLM reported missing decision '{key}': {reason}",
            )
        )
    for contradiction in _blocking_contradictions(graph, llm_result.contradictions):
        key = contradiction.get("key", "unknown")
        reason = contradiction.get("reason", "contradiction")
        details = contradiction.get("details", "")
        suffix = f" ({details})" if details else ""
        violations.append(
            Violation(
                code=f"LLM_CONTRADICTION_{str(key).upper()}",
                message=f"LLM reported conflicting decision '{key}': {reason}{suffix}",
            )
        )
    return violations


def _llm_result_for_blocking(
    llm_result: LLMGraphResult,
    locked_decision_keys: set[str],
    accepted_decisions: dict[str, Any],
) -> LLMGraphResult:
    if not locked_decision_keys or not llm_result.contradictions:
        return llm_result
    contradictions = [
        contradiction
        for contradiction in llm_result.contradictions
        if not _locked_llm_contradiction_is_redundant(
            contradiction,
            llm_result,
            locked_decision_keys,
            accepted_decisions,
        )
    ]
    if len(contradictions) == len(llm_result.contradictions):
        return llm_result
    return LLMGraphResult(
        decisions=llm_result.decisions,
        signal_decisions=llm_result.signal_decisions,
        gaps=llm_result.gaps,
        contradictions=contradictions,
        raw_response=llm_result.raw_response,
    )


def _locked_llm_contradiction_is_redundant(
    contradiction: dict[str, Any],
    llm_result: LLMGraphResult,
    locked_decision_keys: set[str],
    accepted_decisions: dict[str, Any],
) -> bool:
    key = str(contradiction.get("key", ""))
    if key not in locked_decision_keys:
        return False
    raw_value = llm_result.decisions.get(key, llm_result.signal_decisions.get(key))
    if raw_value is None or key not in accepted_decisions:
        return False
    return _same_decision_value(raw_value, accepted_decisions[key])


def _same_decision_value(left: Any, right: Any) -> bool:
    return str(left).strip().lower() == str(right).strip().lower()


def _deterministic_applied_decision_keys(applied_decisions: dict[str, list[str]]) -> set[str]:
    keys: set[str] = set()
    for source in ("baseline", "markdown"):
        keys.update(applied_decisions.get(source, []))
    return keys


def _markdown_contradiction_violations(
    contradictions: list[dict[str, Any]],
) -> list[Violation]:
    violations: list[Violation] = []
    for contradiction in contradictions:
        key = contradiction.get("key", "unknown")
        reason = contradiction.get("reason", "conflicting structured Markdown values")
        details = contradiction.get("details", "")
        suffix = f" ({details})" if details else ""
        violations.append(
            Violation(
                code=f"MARKDOWN_CONTRADICTION_{str(key).upper()}",
                message=f"Markdown reported conflicting decision '{key}': {reason}{suffix}",
            )
        )
    return violations


def _code_suffix(value: str) -> str:
    return (
        "".join(char if char.isalnum() else "_" for char in value.upper()).strip("_") or "UNKNOWN"
    )


def _target_capability_violations(
    target_capability_report: dict[str, Any] | None,
) -> list[Violation]:
    if not target_capability_report:
        return []
    violations: list[Violation] = []
    for gap in target_capability_report.get("unsupportedGaps", []) or []:
        if not isinstance(gap, dict):
            continue
        if str(gap.get("recommendedTarget", "")) != "blocked":
            continue
        key = str(gap.get("key") or "unsupported-target-ask")
        reason = str(gap.get("reason") or "Unsupported target request is blocked.")
        evidence = str(gap.get("evidenceSpan") or "")
        suffix = f" Evidence: {evidence}" if evidence else ""
        violations.append(
            Violation(
                code=f"TARGET_CAPABILITY_BLOCKED_{_code_suffix(key)}",
                message=f"{reason}{suffix}",
            )
        )
    return violations


def _plan_ready_capability_violations(
    pattern: str,
    target_capability_report: dict[str, Any] | None,
) -> list[Violation]:
    pattern_obj = GLOBAL_REGISTRY.get(pattern)
    if not pattern_obj.plan_ready:
        return []
    violations: list[Violation] = []
    if not target_capability_report:
        return [
            Violation(
                code="PLAN_READY_TARGET_CAPABILITIES_REQUIRED",
                message="Plan-ready targets must produce a target capability report.",
            )
        ]
    coverage = target_capability_report.get("coverage", {}) if target_capability_report else {}
    unhandled = coverage.get("unhandledAcceptedDecisions", [])
    if isinstance(unhandled, list) and unhandled:
        violations.append(
            Violation(
                code="PLAN_READY_UNHANDLED_DECISIONS",
                message=(
                    "Plan-ready target capability coverage is missing accepted decisions: "
                    + ", ".join(str(item) for item in unhandled)
                ),
            )
        )
    return violations


def _build_target_capability_report(
    pattern_obj: Any,
    decisions: dict[str, Any],
    source_text: str,
) -> dict[str, Any]:
    if pattern_obj.target_report_builder is None:
        return {}
    return cast(dict[str, Any], pattern_obj.target_report_builder(decisions, source_text))


def _incremental_reconfirmation_violations(
    graph,
    incremental_report: dict[str, Any],
    input_diff: dict[str, Any],
    pattern_obj: Any,
) -> list[Violation]:
    source = input_diff.get("source", {}) if isinstance(input_diff.get("source"), dict) else {}
    if not source.get("baselineDocumentAvailable"):
        return []
    decisions = (
        incremental_report.get("decisions", {})
        if isinstance(incremental_report.get("decisions"), dict)
        else {}
    )
    reconfirm = decisions.get("needingReconfirmation", [])
    if not isinstance(reconfirm, list):
        return []
    violations: list[Violation] = []
    requirements = getattr(graph, "_requirements", {})
    for key_value in reconfirm:
        key = str(key_value)
        req = requirements.get(key)
        category = getattr(req, "category", "")
        if key not in pattern_obj.reconfirmation_keys and (
            category not in pattern_obj.reconfirmation_categories
        ):
            continue
        label = getattr(req, "label", key)
        violations.append(
            Violation(
                code=f"INCREMENTAL_RECONFIRMATION_REQUIRED_{_code_suffix(key)}",
                message=(
                    f"Changed input mentions '{label}' but carried forward prior decision "
                    f"'{key}'. Add an explicit structured decision or re-confirm it before handoff."
                ),
            )
        )
    return violations


def _build_extraction_summary(
    *,
    pattern: str,
    evidence_store: LLMEvidenceStore | None,
    raw_evidence_path: Path | None,
    markdown_decisions: dict[str, Any],
    markdown_contradictions: list[dict[str, Any]],
    llm_result: LLMGraphResult,
    readiness: dict[str, Any],
    applied_decisions: dict[str, list[str]],
    accepted_decisions: dict[str, Any],
    graph,
    target_capability_report: dict[str, Any] | None = None,
    blocking_llm_result: LLMGraphResult | None = None,
) -> dict[str, Any]:
    calls = []
    evidence_entries = evidence_store.entries if evidence_store is not None else []
    for entry in evidence_entries:
        calls.append(
            {
                "provider": _readable_provider(entry.get("backend", "unknown")),
                "model": entry.get("model", "unknown"),
                "latencyMs": round(float(entry.get("latency_ms", 0) or 0), 1),
                "tokenUsage": entry.get("token_usage", {}),
                "parseError": entry.get("parse_error"),
            }
        )
    first = calls[0] if calls else {}
    blocking_result = blocking_llm_result or llm_result
    blocking_gaps = _blocking_gaps(graph, blocking_result.gaps)
    resolved_gaps = [
        gap for gap in llm_result.gaps if isinstance(gap, dict) and _gap_is_resolved(graph, gap)
    ]
    blocking_contradictions = _blocking_contradictions(graph, blocking_result.contradictions)
    raw_evidence = _raw_evidence_status(raw_evidence_path, evidence_store)
    summary = {
        "pattern": pattern,
        "provider": first.get("provider", "none"),
        "model": first.get("model", "none") or "none",
        "callCount": len(calls),
        "calls": calls,
        "markdownDecisions": markdown_decisions,
        "markdownContradictions": markdown_contradictions,
        "rawLlmDecisions": llm_result.decisions,
        "rawLlmSignalDecisions": llm_result.signal_decisions,
        "acceptedDecisions": _to_builtin(accepted_decisions),
        "appliedDecisions": applied_decisions,
        "signalDecisions": llm_result.signal_decisions,
        "gaps": {
            "resolved": resolved_gaps,
            "blocking": blocking_gaps,
            "raw": llm_result.gaps,
        },
        "contradictions": {
            "blocking": blocking_contradictions,
            "raw": llm_result.contradictions,
        },
        "handoffReadiness": {
            "handoffAllowed": readiness["handoffAllowed"],
            "status": readiness["status"],
            "blockerCount": len(readiness["blockers"]),
            "blockingGapCount": len(blocking_gaps),
            "blockingContradictionCount": len(blocking_contradictions),
        },
        "rawEvidence": raw_evidence,
    }
    if target_capability_report:
        summary["targetCapabilities"] = target_capability_report
    return summary


def _applied_decisions_from_audit(graph) -> dict[str, list[str]]:
    applied: dict[str, list[str]] = {
        "markdown": [],
        "llm": [],
        "signals": [],
        "defaults": [],
        "interview": [],
    }
    for entry in graph.audit_log():
        key = str(entry.get("key", ""))
        if not key:
            continue
        how = str(entry.get("how", ""))
        if how == "defaulted":
            applied["defaults"].append(key)
        elif how == "decided":
            applied["interview"].append(key)
    return applied


def _readable_provider(provider: Any) -> str:
    value = str(provider or "unknown")
    if value == "OpenAICompatibleBackend":
        return "openai-compatible"
    if value == "BedrockCliBackend":
        return "bedrock"
    if value.endswith("Backend"):
        value = value[: -len("Backend")]
    return value.replace("_", "-").lower() or "unknown"


def _raw_evidence_status(
    raw_evidence_path: Path | None,
    evidence_store: LLMEvidenceStore | None,
) -> dict[str, str]:
    if raw_evidence_path is None:
        return {"path": "not-requested", "status": "not-requested"}
    if evidence_store is None or not evidence_store.entries:
        return {"path": str(raw_evidence_path), "status": "requested-empty"}
    return {"path": str(raw_evidence_path), "status": "requested"}


def _write_failed_compile_artifacts(
    output_dir: Path,
    pattern: str,
    graph,
    readiness: dict[str, Any],
    extraction_summary: dict[str, Any],
    target_capability_report: dict[str, Any] | None = None,
) -> None:
    report = {
        "pattern": pattern,
        "decisions": _to_builtin(graph.typed_decisions()),
        "handoffReadiness": readiness,
    }
    if target_capability_report:
        report["targetCapabilities"] = target_capability_report
    _remove_generated_artifacts(output_dir, pattern)
    _write_yaml_artifact(
        output_dir,
        "decision-report.yaml",
        report,
    )
    _write_yaml_artifact(output_dir, "llm-trace-summary.yaml", extraction_summary)
    if target_capability_report:
        _write_yaml_artifact(
            output_dir,
            "target-capability-graph.yaml",
            target_capability_report,
        )
    _write_yaml_artifact(
        output_dir,
        "model-benchmark.yaml",
        build_model_benchmark(extraction_summary),
    )
    _write_yaml_artifact(
        output_dir,
        "missing-inputs.yaml",
        _missing_inputs_artifact(pattern, graph, readiness),
    )


def _missing_inputs_artifact(pattern: str, graph, readiness: dict[str, Any]) -> dict[str, Any]:
    questions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in readiness.get("missingDecisions", []) or []:
        key = item.get("key") if isinstance(item, dict) else str(item)
        if not key or key in seen:
            continue
        seen.add(key)
        req = getattr(graph, "_requirements", {}).get(key)
        item_dict = item if isinstance(item, dict) else {}
        questions.append(
            {
                "key": key,
                "label": item_dict.get("label", getattr(req, "label", key)),
                "question": item_dict.get("question", getattr(req, "question", "")),
                "reason": item_dict.get(
                    "reason",
                    getattr(req, "violation_message", "") or "Required decision is missing.",
                ),
                "default": getattr(req, "default", None),
                "options": list(getattr(req, "options", []) or []),
                "dependsOn": list(getattr(req, "depends_on", []) or []),
                "category": getattr(req, "category", ""),
            }
        )
    return {
        "schemaVersion": "intent-engine/missing-inputs/v1",
        "pattern": pattern,
        "status": "blocked",
        "questionCount": len(questions),
        "questions": questions,
    }


def _build_failure_artifacts_and_raise(
    *,
    output_dir: Path,
    pattern: str,
    graph,
    intent: Any,
    violations: list[Violation],
    llm_result: LLMGraphResult,
    evidence_store: LLMEvidenceStore | None,
    raw_evidence_path: Path | None,
    markdown_decisions: dict[str, Any],
    markdown_contradictions: list[dict[str, Any]],
    applied_decisions: dict[str, list[str]],
    target_capability_report: dict[str, Any] | None,
    dry_run: bool,
    extra_artifacts: dict[str, Any] | None = None,
    blocking_llm_result: LLMGraphResult | None = None,
) -> None:
    blocking_result = blocking_llm_result or llm_result
    readiness = _build_handoff_readiness(
        graph,
        violations,
        blocking_result,
        target_capability_report,
    )
    readiness = _enrich_handoff_readiness(pattern, intent, readiness)
    extraction_summary = _build_extraction_summary(
        pattern=pattern,
        evidence_store=evidence_store,
        raw_evidence_path=raw_evidence_path,
        markdown_decisions=markdown_decisions,
        markdown_contradictions=markdown_contradictions,
        llm_result=llm_result,
        readiness=readiness,
        applied_decisions=applied_decisions,
        accepted_decisions=graph.typed_decisions(),
        graph=graph,
        target_capability_report=target_capability_report,
        blocking_llm_result=blocking_result,
    )
    if not dry_run:
        _write_failed_compile_artifacts(
            output_dir,
            pattern,
            graph,
            readiness,
            extraction_summary,
            target_capability_report,
        )
        for name, data in (extra_artifacts or {}).items():
            _write_yaml_artifact(output_dir, name, data)
    raise CompileError(violations, readiness=readiness)


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
        pattern: str,
        llm_caller: LLMCaller | None = None,
        evidence_store: LLMEvidenceStore | None = None,
    ) -> None:
        self.prose = prose
        self.graph = graph
        self.llm_caller = llm_caller
        self.evidence_store = evidence_store
        self.extractor = Extractor(graph=graph, pattern=pattern)

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


def _validate_and_generate(
    *,
    pattern: str,
    graph,
    intent: Any,
    output_dir: Path,
    source_text: str,
    source_context: dict[str, Any],
    llm_result: LLMGraphResult,
    evidence_store: LLMEvidenceStore | None,
    raw_evidence_path: Path | None,
    markdown_decisions: dict[str, Any],
    markdown_contradictions: list[dict[str, Any]],
    applied_decisions: dict[str, list[str]],
    dry_run: bool,
    extra_artifacts: dict[str, Any] | None = None,
    extra_violations: list[Violation] | None = None,
) -> None:
    pattern_obj = GLOBAL_REGISTRY.get(pattern)
    target_capability_report = _build_target_capability_report(
        pattern_obj,
        graph.typed_decisions(),
        source_text,
    )
    violations = validate(intent, graph=graph, extra_validators=pattern_obj.validators)
    violations.extend(_markdown_contradiction_violations(markdown_contradictions))
    blocking_llm_result = _llm_result_for_blocking(
        llm_result,
        _deterministic_applied_decision_keys(applied_decisions),
        graph.typed_decisions(),
    )
    violations.extend(_llm_result_violations(graph, blocking_llm_result))
    violations.extend(_target_capability_violations(target_capability_report))
    violations.extend(_plan_ready_capability_violations(pattern, target_capability_report))
    violations.extend(extra_violations or [])

    readiness = _build_handoff_readiness(
        graph,
        violations,
        blocking_llm_result,
        target_capability_report,
    )
    readiness = _enrich_handoff_readiness(pattern, intent, readiness)
    extraction_summary = _build_extraction_summary(
        pattern=pattern,
        evidence_store=evidence_store,
        raw_evidence_path=raw_evidence_path,
        markdown_decisions=markdown_decisions,
        markdown_contradictions=markdown_contradictions,
        llm_result=llm_result,
        readiness=readiness,
        applied_decisions=applied_decisions,
        accepted_decisions=graph.typed_decisions(),
        graph=graph,
        target_capability_report=target_capability_report,
        blocking_llm_result=blocking_llm_result,
    )
    if violations:
        _build_failure_artifacts_and_raise(
            output_dir=output_dir,
            pattern=pattern,
            graph=graph,
            intent=intent,
            violations=violations,
            llm_result=llm_result,
            evidence_store=evidence_store,
            raw_evidence_path=raw_evidence_path,
            markdown_decisions=markdown_decisions,
            markdown_contradictions=markdown_contradictions,
            applied_decisions=applied_decisions,
            target_capability_report=target_capability_report,
            dry_run=dry_run,
            extra_artifacts=extra_artifacts,
            blocking_llm_result=blocking_llm_result,
        )

    if dry_run:
        return

    payload = _build_payload(
        intent,
        pattern,
        graph.typed_decisions(),
        extraction_summary=extraction_summary,
        handoff_readiness=readiness,
        target_capability_report=target_capability_report,
        source_context=source_context,
        decision_audit=graph.audit_log(),
    )
    artifact_violations = _generate_validated_artifacts(
        payload,
        output_dir,
        pattern,
        extra_artifacts=extra_artifacts,
    )
    if artifact_violations:
        _build_failure_artifacts_and_raise(
            output_dir=output_dir,
            pattern=pattern,
            graph=graph,
            intent=intent,
            violations=artifact_violations,
            llm_result=llm_result,
            evidence_store=evidence_store,
            raw_evidence_path=raw_evidence_path,
            markdown_decisions=markdown_decisions,
            markdown_contradictions=markdown_contradictions,
            applied_decisions=applied_decisions,
            target_capability_report=target_capability_report,
            dry_run=False,
            extra_artifacts=extra_artifacts,
            blocking_llm_result=blocking_llm_result,
        )


def compile_design(
    input_path: Path,
    output_dir: Path,
    graph=None,
    llm_caller: LLMCaller | None = None,
    evidence_store: LLMEvidenceStore | None = None,
    raw_evidence_path: Path | None = None,
    dry_run: bool = False,
    pattern: str = "aws-lza",
) -> None:
    """Extract, validate, and generate from a design doc.

    Two-layer architecture:
      1. Non-deterministic: LLMContextProvider reads prose and traverses graph
      2. Deterministic: harness applies gates, cascades, defaults, validates,
         generates artifacts, and records audit trail
    """
    if input_path.is_dir():
        texts = []
        source_paths = []
        for f in sorted(input_path.glob("*.md")):
            source_paths.append(f)
            texts.append(f.read_text())
        text = "\n---\n".join(texts)
        source_context = _source_context(
            mode="directory",
            text=text,
            input_path=input_path,
            paths=source_paths,
        )
    else:
        text = input_path.read_text()
        source_context = _source_context(mode="file", text=text, input_path=input_path)

    pattern_obj = GLOBAL_REGISTRY.get(pattern)
    if graph is None:
        graph = pattern_obj.create_graph()

    # ------------------------------------------------------------------
    # Layer 0: Deterministic Markdown pre-processing
    # ------------------------------------------------------------------
    markdown_result = extract_from_markdown_with_diagnostics(text, graph)
    markdown_decisions = markdown_result.decisions
    markdown_entities = (
        pattern_obj.markdown_entity_extractor(text) if pattern_obj.markdown_entity_extractor else {}
    )
    applied_decisions: dict[str, list[str]] = {
        "markdown": [],
        "llm": [],
        "signals": [],
        "defaults": [],
    }
    if markdown_decisions:
        applied_decisions["markdown"] = graph.apply_decisions(markdown_decisions)

    # ------------------------------------------------------------------
    # Layer 1: Non-deterministic intent understanding (LLM)
    # ------------------------------------------------------------------
    llm_result = LLMContextProvider(
        prose=text,
        graph=graph,
        pattern=pattern,
        llm_caller=llm_caller,
        evidence_store=evidence_store,
    ).run()

    # ------------------------------------------------------------------
    # Layer 2: Deterministic harness processing
    # ------------------------------------------------------------------
    # 2a. Apply LLM-extracted decisions to the graph (gates + cascade)
    locked_decision_keys = set(applied_decisions["markdown"])
    if llm_result.decisions:
        llm_decisions = without_locked_decisions(llm_result.decisions, locked_decision_keys)
        applied_decisions["llm"] = graph.apply_decisions(llm_decisions)
        locked_decision_keys.update(applied_decisions["llm"])

    # 2b. Apply signal-triggered decisions
    if llm_result.signal_decisions:
        signal_decisions = without_locked_decisions(
            llm_result.signal_decisions,
            locked_decision_keys,
        )
        applied_decisions["signals"] = graph.apply_decisions(signal_decisions)

    # 2c. Fill remaining gaps with defaults
    graph.apply_defaults_for_remaining()
    applied_decisions["defaults"] = [
        str(entry["key"]) for entry in graph.audit_log() if entry.get("how") == "defaulted"
    ]

    # 2d. Build intent from LLM decisions (handles complex nested objects)
    # then overlay graph cascade decisions onto the same intent
    if llm_result.decisions or llm_result.signal_decisions:
        extractor = Extractor(graph=graph, pattern=pattern)
        intent = llm_result.to_intent(extractor)
    else:
        intent = pattern_obj.intent_factory()
    # Deterministic entities backfill items that small models often omit.
    if pattern_obj.markdown_entity_applier:
        pattern_obj.markdown_entity_applier(markdown_entities, intent)
    # Apply graph cascades (topology -> network.topology, etc.)
    graph.apply_to_intent(intent)

    _validate_and_generate(
        pattern=pattern,
        graph=graph,
        intent=intent,
        output_dir=output_dir,
        source_text=text,
        source_context=source_context,
        llm_result=llm_result,
        evidence_store=evidence_store,
        raw_evidence_path=raw_evidence_path,
        markdown_decisions=markdown_decisions,
        markdown_contradictions=markdown_result.contradictions,
        applied_decisions=applied_decisions,
        dry_run=dry_run,
    )


def compile_incremental_design(
    *,
    baseline_bundle: Path,
    changed_doc: Path,
    output_dir: Path,
    baseline_doc: Path | None = None,
    graph=None,
    llm_caller: LLMCaller | None = None,
    evidence_store: LLMEvidenceStore | None = None,
    raw_evidence_path: Path | None = None,
    dry_run: bool = False,
    pattern: str = "aws-lza",
) -> None:
    """Compile a changed document by seeding the graph from a previous bundle.

    The LLM sees only scoped delta context. The final graph, validators, and
    target contracts still run over the full resulting decision state.
    """
    if not baseline_bundle.is_dir():
        raise FileNotFoundError(f"baseline bundle does not exist: {baseline_bundle}")
    if not changed_doc.exists():
        raise FileNotFoundError(f"changed document does not exist: {changed_doc}")

    pattern_obj = GLOBAL_REGISTRY.get(pattern)
    if graph is None:
        graph = pattern_obj.create_graph()

    changed_text = changed_doc.read_text()
    baseline_text = baseline_doc.read_text() if baseline_doc is not None else None
    source_context = _source_context(
        mode="incremental",
        text=changed_text,
        input_path=changed_doc,
        extra={
            "baselineBundle": str(baseline_bundle),
            "baselineDocument": str(baseline_doc) if baseline_doc is not None else "",
        },
    )
    baseline_decisions = baseline_decisions_from_bundle(baseline_bundle)
    baseline_summary = baseline_summary_from_bundle(baseline_bundle)
    input_diff = build_input_diff_report(
        before_text=baseline_text,
        after_text=changed_text,
        graph=graph,
        baseline_decisions=baseline_decisions,
    )

    markdown_result = extract_from_markdown_with_diagnostics(changed_text, graph)
    markdown_decisions = markdown_result.decisions
    markdown_entities = (
        pattern_obj.markdown_entity_extractor(changed_text)
        if pattern_obj.markdown_entity_extractor
        else {}
    )
    applied_decisions: dict[str, list[str]] = {
        "baseline": [],
        "markdown": [],
        "llm": [],
        "signals": [],
        "defaults": [],
    }
    if baseline_decisions:
        applied_decisions["baseline"] = graph.apply_decisions(baseline_decisions)
    if markdown_decisions:
        applied_decisions["markdown"] = graph.apply_decisions(markdown_decisions)

    scoped_context = build_incremental_llm_context(
        input_diff_report=input_diff,
        baseline_decisions=baseline_decisions,
        baseline_summary=baseline_summary,
    )
    llm_result = LLMContextProvider(
        prose=scoped_context,
        graph=graph,
        pattern=pattern,
        llm_caller=llm_caller,
        evidence_store=evidence_store,
    ).run()

    locked_decision_keys = set(applied_decisions["markdown"])
    if llm_result.decisions:
        llm_decisions = without_locked_decisions(llm_result.decisions, locked_decision_keys)
        applied_decisions["llm"] = graph.apply_decisions(llm_decisions)
        locked_decision_keys.update(applied_decisions["llm"])
    if llm_result.signal_decisions:
        signal_decisions = without_locked_decisions(
            llm_result.signal_decisions,
            locked_decision_keys,
        )
        applied_decisions["signals"] = graph.apply_decisions(signal_decisions)

    graph.apply_defaults_for_remaining()
    applied_decisions["defaults"] = [
        str(entry["key"]) for entry in graph.audit_log() if entry.get("how") == "defaulted"
    ]

    if llm_result.decisions or llm_result.signal_decisions:
        extractor = Extractor(graph=graph, pattern=pattern)
        intent = llm_result.to_intent(extractor)
    else:
        intent = pattern_obj.intent_factory()
    if pattern_obj.markdown_entity_applier:
        pattern_obj.markdown_entity_applier(markdown_entities, intent)
    graph.apply_to_intent(intent)

    incremental_report = incremental_decision_report(
        baseline_decisions=baseline_decisions,
        final_decisions=graph.typed_decisions(),
        input_diff_report=input_diff,
    )
    incremental_report.update(
        {
            "baselineBundle": str(baseline_bundle),
            "baselineDocument": str(baseline_doc) if baseline_doc is not None else None,
            "changedDocument": str(changed_doc),
            "validationBoundary": (
                "LLM context was scoped to the input delta, but graph validation, "
                "pattern validators, and artifact contracts ran on the full "
                "resulting decision state."
            ),
        }
    )
    extra_artifacts = {
        "input-diff-report.yaml": input_diff,
        "incremental-compile-report.yaml": incremental_report,
    }
    _validate_and_generate(
        pattern=pattern,
        graph=graph,
        intent=intent,
        output_dir=output_dir,
        source_text=changed_text,
        source_context=source_context,
        llm_result=llm_result,
        evidence_store=evidence_store,
        raw_evidence_path=raw_evidence_path,
        markdown_decisions=markdown_decisions,
        markdown_contradictions=markdown_result.contradictions,
        applied_decisions=applied_decisions,
        dry_run=dry_run,
        extra_artifacts=extra_artifacts,
        extra_violations=_incremental_reconfirmation_violations(
            graph,
            incremental_report,
            input_diff,
            pattern_obj,
        ),
    )


def compile_from_interview(
    decisions: dict[str, str],
    output_dir: Path,
    accept_defaults: bool = True,
    pattern: str = "aws-lza",
) -> None:
    pattern_obj = GLOBAL_REGISTRY.get(pattern)
    graph = pattern_obj.create_graph()
    engine = InterviewEngine(graph, pattern=pattern)
    engine.run_from_decisions(decisions)
    if accept_defaults:
        engine.apply_defaults_for_remaining()
    compile_from_graph(engine.graph, output_dir, pattern=pattern)


def compile_from_graph(graph, output_dir: Path, pattern: str = "aws-lza") -> None:
    """Validate and generate from an already-populated interview graph."""
    pattern_obj = GLOBAL_REGISTRY.get(pattern)
    intent = pattern_obj.intent_factory()
    graph.apply_to_intent(intent)
    llm_result = LLMGraphResult()
    applied_decisions = _applied_decisions_from_audit(graph)
    _validate_and_generate(
        pattern=pattern,
        graph=graph,
        intent=intent,
        output_dir=output_dir,
        source_text="",
        source_context=_source_context(mode="interview", text=""),
        llm_result=llm_result,
        evidence_store=None,
        raw_evidence_path=None,
        markdown_decisions={},
        markdown_contradictions=[],
        applied_decisions=applied_decisions,
        dry_run=False,
    )


def validate_generated_violations(input_dir: Path, pattern: str = "aws-lza") -> list[Violation]:
    return _validate_generated_violations_impl(input_dir, pattern)


def validate_generated(input_dir: Path, pattern: str = "aws-lza") -> list[str]:
    return _validate_generated_impl(input_dir, pattern)


def _build_section_map(pattern: str, graph) -> dict[str, tuple[str, str | None]]:
    """Build a section map from pattern metadata plus category fallback.

    New requirements automatically appear in templates under their category
    if no explicit mapping is provided.
    """
    from .patterns import GLOBAL_REGISTRY

    pattern_obj = GLOBAL_REGISTRY.get(pattern)
    section_map: dict[str, tuple[str, str | None]] = dict(pattern_obj.section_map)

    for key, req in graph._requirements.items():
        if key in section_map:
            continue
        category = req.category or "general"
        section_map[key] = (category.replace("-", " ").title(), req.key)

    return section_map


def generate_template(pattern: str = "aws-lza") -> str:
    """Generate a Markdown design doc scaffold from a pattern."""
    from .patterns import GLOBAL_REGISTRY

    pattern_obj = GLOBAL_REGISTRY.get(pattern)
    graph = pattern_obj.create_graph()

    section_map = _build_section_map(pattern, graph)

    sections_content: dict[str, list[tuple[str, Any, str | None]]] = {}
    for key, req in graph._requirements.items():
        info = section_map.get(key)
        if info is None:
            continue
        section_name, field_name = info
        sections_content.setdefault(section_name, []).append((key, req, field_name))

    lines: list[str] = []
    lines.append(f"# Design Document — {pattern} pattern")
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
            if req.applies_when:
                from .requirements import describe_expression

                lines.append(f"# Only when {describe_expression(req.applies_when)}")

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
    report = read_yaml_mapping(report_path)

    lines = ["=== Decision Report ===", ""]

    def _render(data: Any, indent: int = 0) -> None:
        prefix = "  " * indent
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict | list):
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
