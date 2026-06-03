"""Document-diff helpers for incremental handoff compilation."""

from __future__ import annotations

import difflib
import re
from typing import Any

from .markdown_extractor import extract_from_markdown_with_diagnostics
from .sample_config import SampleConfig


def build_input_diff_report(
    *,
    before_text: str | None,
    after_text: str,
    graph,
    baseline_decisions: dict[str, Any],
) -> dict[str, Any]:
    """Build a compact source-delta report for incremental packet updates."""
    after_markdown = extract_from_markdown_with_diagnostics(after_text, graph)
    changed_structured = _changed_structured_decisions(
        baseline_decisions,
        after_markdown.decisions,
    )
    changed_lines = _changed_lines(before_text, after_text)
    changed_headings = _changed_headings(after_text, changed_lines)
    impacted = _likely_impacted_requirements(
        graph,
        changed_lines=changed_lines,
        changed_structured=changed_structured,
    )
    return {
        "schemaVersion": "intent-engine/input-diff/v1",
        "source": {
            "mode": "document-diff" if before_text is not None else "baseline-decision-diff",
            "baselineDocumentAvailable": before_text is not None,
        },
        "changedHeadings": changed_headings,
        "changedStructuredDecisionLines": changed_structured,
        "changedLineCount": len(changed_lines),
        "likelyImpactedRequirements": impacted,
        "hunks": _hunks(before_text, after_text),
        "markdownContradictions": after_markdown.contradictions,
    }


def build_incremental_llm_context(
    *,
    input_diff_report: dict[str, Any],
    baseline_decisions: dict[str, Any],
    baseline_summary: dict[str, Any],
) -> str:
    """Build scoped prose for the normal graph-driven LLM extractor."""
    return "\n".join(
        [
            "Incremental architecture update.",
            "",
            "Use only this scoped delta context to propose decision changes.",
            "Previous accepted decisions are trusted unless the changed hunks or",
            "changed structured decision lines explicitly revise them.",
            "Do not restate unchanged decisions as new findings.",
            "",
            "=== PREVIOUS BUNDLE SUMMARY ===",
            _yaml_like(baseline_summary),
            "",
            "=== PREVIOUS ACCEPTED DECISIONS ===",
            _yaml_like(baseline_decisions),
            "",
            "=== INPUT DIFF REPORT ===",
            _yaml_like(input_diff_report),
        ]
    )


def incremental_decision_report(
    *,
    baseline_decisions: dict[str, Any],
    final_decisions: dict[str, Any],
    input_diff_report: dict[str, Any],
) -> dict[str, Any]:
    """Summarize decision carry-forward and delta for an incremental compile."""
    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    reused: list[str] = []
    for key in sorted(set(baseline_decisions) | set(final_decisions)):
        if key not in baseline_decisions:
            added.append({"key": key, "value": SampleConfig.to_builtin(final_decisions[key])})
        elif key not in final_decisions:
            removed.append({"key": key, "value": SampleConfig.to_builtin(baseline_decisions[key])})
        elif not _values_match(baseline_decisions[key], final_decisions[key]):
            changed.append(
                {
                    "key": key,
                    "before": SampleConfig.to_builtin(baseline_decisions[key]),
                    "after": SampleConfig.to_builtin(final_decisions[key]),
                }
            )
        else:
            reused.append(key)
    changed_keys = {str(item["key"]) for item in changed + added + removed}
    impacted_keys = {
        str(item.get("key", ""))
        for item in _coerce_list(input_diff_report.get("likelyImpactedRequirements"))
        if isinstance(item, dict)
    }
    return {
        "schemaVersion": "intent-engine/incremental-compile/v1",
        "decisions": {
            "reused": reused,
            "added": added,
            "removed": removed,
            "changed": changed,
            "needingReconfirmation": sorted(impacted_keys - changed_keys),
            "unchangedCarriedForward": reused,
        },
    }


def _changed_structured_decisions(
    baseline_decisions: dict[str, Any],
    after_decisions: dict[str, str],
) -> list[dict[str, Any]]:
    changed: list[dict[str, Any]] = []
    for key in sorted(after_decisions):
        after_value = after_decisions[key]
        before_value = baseline_decisions.get(key)
        if key not in baseline_decisions:
            changed.append({"key": key, "before": None, "after": after_value, "change": "added"})
        elif not _values_match(before_value, after_value):
            changed.append(
                {
                    "key": key,
                    "before": SampleConfig.to_builtin(before_value),
                    "after": SampleConfig.to_builtin(after_value),
                    "change": "changed",
                }
            )
    return changed


def _changed_lines(before_text: str | None, after_text: str) -> list[dict[str, Any]]:
    if before_text is None:
        return [
            {"side": "after", "line": idx, "text": line}
            for idx, line in enumerate(after_text.splitlines(), 1)
            if line.strip()
        ]
    before_lines = before_text.splitlines()
    after_lines = after_text.splitlines()
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines)
    changed: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        for idx in range(i1, i2):
            changed.append({"side": "before", "line": idx + 1, "text": before_lines[idx]})
        for idx in range(j1, j2):
            changed.append({"side": "after", "line": idx + 1, "text": after_lines[idx]})
    return changed


def _changed_headings(after_text: str, changed_lines: list[dict[str, Any]]) -> list[str]:
    headings_by_line = _heading_context_by_line(after_text)
    headings: list[str] = []
    for item in changed_lines:
        if item.get("side") != "after":
            continue
        heading = headings_by_line.get(int(item.get("line", 0)), "(document)")
        if heading not in headings:
            headings.append(heading)
    return headings


def _heading_context_by_line(text: str) -> dict[int, str]:
    context: dict[int, str] = {}
    current = "(document)"
    for idx, line in enumerate(text.splitlines(), 1):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            current = match.group(2).strip()
        context[idx] = current
    return context


def _likely_impacted_requirements(
    graph,
    *,
    changed_lines: list[dict[str, Any]],
    changed_structured: list[dict[str, Any]],
) -> list[dict[str, str]]:
    structured_keys = {
        str(item.get("key", ""))
        for item in changed_structured
        if isinstance(item, dict) and item.get("key")
    }
    changed_text = "\n".join(str(item.get("text", "")) for item in changed_lines).lower()
    impacted: list[dict[str, str]] = []
    for key, req in graph._requirements.items():
        reason = ""
        if key in structured_keys:
            reason = "structured decision changed"
        else:
            candidates = [key, req.label, req.target_field or ""]
            if any(candidate and candidate.lower() in changed_text for candidate in candidates):
                reason = "changed text mentions requirement language"
        if reason:
            impacted.append({"key": key, "label": req.label, "reason": reason})
    return impacted


def _hunks(before_text: str | None, after_text: str) -> list[str]:
    if before_text is None:
        return []
    diff = difflib.unified_diff(
        before_text.splitlines(),
        after_text.splitlines(),
        fromfile="before",
        tofile="after",
        lineterm="",
        n=3,
    )
    hunks: list[str] = []
    current: list[str] = []
    for line in diff:
        if line.startswith("@@") and current:
            hunks.append("\n".join(current))
            current = [line]
            continue
        if line.startswith(("---", "+++")):
            continue
        current.append(line)
    if current:
        hunks.append("\n".join(current))
    return hunks


def _yaml_like(data: Any) -> str:
    import io

    import ruamel.yaml

    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    buf = io.StringIO()
    yaml.dump(data, buf)
    return buf.getvalue().strip()


def _coerce_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _values_match(before: Any, after: Any) -> bool:
    return SampleConfig._values_match(
        _normalize_list_like(before, after),
        _normalize_list_like(after, before),
    )


def _normalize_list_like(value: Any, peer: Any) -> Any:
    if isinstance(peer, list) and isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return value
