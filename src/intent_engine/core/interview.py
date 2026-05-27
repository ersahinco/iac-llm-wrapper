"""Interview engine that navigates requirements in dependency order with full traceability."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .patterns import GLOBAL_REGISTRY
from .requirements import (
    RequirementGraph,
    RequirementStatus,
)


@dataclass
class Question:
    key: str
    label: str
    question: str
    options: list[str] | None
    default: str | None
    category: str
    hint: str | None
    depends_on: list[str]
    applies_reason: str | None
    blocked_reason: str | None
    # Knowledge fields
    compliance_controls: list[str]
    tradeoffs: list[str]
    consequences: list[str]
    signals: list[str]
    confidence: float
    overridable: bool


class InterviewEngine:
    """Guided interview that walks the requirement graph in dependency order."""

    def __init__(
        self,
        graph: RequirementGraph | None = None,
        pattern: str = "baseline",
    ) -> None:
        if graph is None:
            graph = GLOBAL_REGISTRY.get(pattern).create_graph()
        self.graph = graph
        self.pattern = pattern
        self._history: list[tuple[str, str]] = []
        self._path_log: list[str] = []

    def next_question(self) -> Question | None:
        pending = self.graph.pending()
        if not pending:
            return None
        key = pending[0]
        req = self.graph._requirements[key]
        return Question(
            key=key,
            label=req.label,
            question=req.question,
            options=req.options,
            default=req.default,
            category=req.category,
            hint=req.hint,
            depends_on=req.depends_on,
            applies_reason=self.graph.is_applicable_reason(key),
            blocked_reason=self.graph.is_blocked_reason(key),
            compliance_controls=req.compliance_controls,
            tradeoffs=req.tradeoffs,
            consequences=req.consequences,
            signals=req.signals,
            confidence=req.confidence,
            overridable=req.overridable,
        )

    def answer(self, key: str, value: Any) -> None:
        req = self.graph._requirements[key]
        serialized = self.graph.stringify_decision_value(value, req.target_type)
        self.graph.decide(key, serialized)
        self._history.append((key, serialized))
        self._log_decision(key, serialized, "decided")

    def accept_default(self, key: str) -> None:
        self.graph.apply_default(key)
        req = self.graph._requirements[key]
        self._history.append((key, f"{req.default} (default)"))
        self._log_decision(key, req.default or "", "defaulted")

    def skip(self, key: str, reason: str | None = None) -> None:
        self.graph.skip(key)
        reason_text = reason or self.graph.is_applicable_reason(key) or "no value provided"
        self._history.append((key, "(skipped)"))
        self._path_log.append(f"  SKIP   {key}: {reason_text}")

    def _log_decision(self, key: str, value: str, how: str) -> None:
        req = self.graph._requirements[key]
        dep_values = {d: self.graph.get(d) for d in req.depends_on}
        dep_str = ", ".join(f"{k}={v}" for k, v in dep_values.items() if v)
        if dep_str:
            self._path_log.append(f"  {how.upper():8} {key}={value}  (deps: {dep_str})")
        else:
            self._path_log.append(f"  {how.upper():8} {key}={value}")

    def _validate_answer(self, q: Question, answer: str) -> str | None:
        """Validate and coerce an answer. Returns None if valid, or an error message."""
        if q.options and answer not in q.options:
            similar = [o for o in q.options if answer.lower() in o.lower()]
            hint = f" Did you mean one of: {', '.join(similar)}?" if similar else ""
            return f"Invalid choice '{answer}'. Options: {', '.join(q.options)}.{hint}"
        req = self.graph._requirements.get(q.key)
        if req and req.target_type == "int":
            try:
                int(answer)
            except ValueError:
                return f"'{answer}' is not a valid number. Enter an integer value."
        if req and req.target_type == "bool":
            if answer.lower() not in ("true", "false", "yes", "no", "1", "0"):
                return f"'{answer}' is not a valid boolean. Enter true/false, yes/no, or 1/0."
        return None

    def _undo_last_decision(self, key: str) -> None:
        """Reset a requirement and all downstream cascaded decisions to PENDING."""
        self.graph._status[key] = RequirementStatus.PENDING
        self.graph._decisions.pop(key, None)
        # Remove downstream cascade targets
        req = self.graph._requirements.get(key)
        if req:
            for target_key in req.cascade:
                if target_key in self.graph._requirements:
                    self.graph._status[target_key] = RequirementStatus.PENDING
                    self.graph._decisions.pop(target_key, None)
        self.graph._update_blocked()

    def run_interactive(self, input_fn=None, output_fn=None) -> None:
        input_fn = input_fn or input
        output_fn = output_fn or print

        output_fn("")
        output_fn(f"=== Interview [{self.pattern}] ===")
        output_fn("")
        output_fn("  Commands: \\back (revisit previous), \\save <path> (checkpoint)")
        output_fn("")

        asked_sequence: list[str] = []
        asked = 0
        while True:
            q = self.next_question()
            if q is None:
                break
            asked += 1
            total = asked + len(self.graph.pending())
            asked_sequence.append(q.key)

            output_fn(f"─── [{q.category}] {q.label} ({asked}/{total}) ───")
            if q.blocked_reason:
                output_fn(f"  BLOCKED: {q.blocked_reason}")
                self.skip(q.key, q.blocked_reason)
                continue
            if q.applies_reason:
                output_fn(f"  Context: {q.applies_reason}")
            if q.hint:
                output_fn(f"  Hint: {q.hint}")
            if q.compliance_controls:
                output_fn(f"  Compliance: {', '.join(q.compliance_controls)}")
            if q.signals:
                output_fn(f"  Signals: {', '.join(q.signals)}")
            if q.tradeoffs:
                output_fn("  Tradeoffs:")
                for t in q.tradeoffs:
                    output_fn(f"    - {t}")
            if q.consequences:
                output_fn("  Consequences:")
                for c in q.consequences:
                    output_fn(f"    - {c}")
            output_fn(f"  {q.question}")

            if q.options:
                for opt in q.options:
                    marker = "  (default)" if opt == q.default else ""
                    output_fn(f"    - {opt}{marker}")
            else:
                type_hint = ""
                req = self.graph._requirements.get(q.key)
                if req:
                    type_hints = {"int": " (integer)", "bool": " (yes/no)"}
                    type_hint = type_hints.get(req.target_type, "")
                def_str = f" (default: {q.default})" if q.default else ""
                output_fn(f"  Enter value{type_hint}{def_str}")

            max_attempts = 3
            for attempt in range(max_attempts):
                prompt = (
                    "  Answer (or Enter for default): " if q.default is not None else "  Answer: "
                )
                raw = input_fn(prompt).strip()

                # Commands must be checked before stripping whitespace
                if raw.startswith("\\save"):
                    save_path = raw[5:].strip()
                    if save_path:
                        self.save_state(save_path)
                        output_fn(f"  ✓ Interview state saved to: {save_path}")
                        output_fn("  Exiting interview. Resume with --resume.")
                        return
                    else:
                        output_fn("  ! Usage: \\save <path>")
                        continue

                if raw == "\\back":
                    if len(asked_sequence) > 1:
                        prev_key = asked_sequence[-2]
                        asked_sequence = asked_sequence[:-2]
                        asked -= 2
                        self._undo_last_decision(prev_key)
                        output_fn("  ↺ Back to previous question.")
                        output_fn("")
                        break
                    else:
                        output_fn("  ! Cannot go back — this is the first question.")
                        continue

                if not raw and q.default is not None:
                    self.accept_default(q.key)
                    break
                if not raw:
                    self.skip(q.key)
                    break

                err = self._validate_answer(q, raw)
                if err is None:
                    self.answer(q.key, raw)
                    break
                if attempt < max_attempts - 1:
                    output_fn(f"  ! {err}  Try again.")
                else:
                    output_fn(f"  ! {err}  Skipping.")
                    self.skip(q.key)

            output_fn("")

        self._log_skipped_and_blocked()

    def _log_skipped_and_blocked(self) -> None:
        for key, st in self.graph._status.items():
            if st == RequirementStatus.SKIPPED:
                reason = self.graph.is_applicable_reason(key) or "not applicable"
                self._path_log.append(f"  SKIP   {key}: {reason}")
            elif st == RequirementStatus.BLOCKED:
                reason = self.graph.is_blocked_reason(key) or "blocked by prior decision"
                self._path_log.append(f"  BLOCK  {key}: {reason}")

    def run_from_decisions(self, decisions: dict[str, str]) -> None:
        for key, value in decisions.items():
            if key in self.graph._requirements:
                self.answer(key, value)

    def apply_defaults_for_remaining(self) -> None:
        while True:
            pending = self.graph.pending()
            if not pending:
                break
            key = pending[0]
            req = self.graph._requirements[key]
            if req.default:
                self.accept_default(key)
            else:
                self.skip(key)

    def to_intent(self) -> Any:
        from .patterns import GLOBAL_REGISTRY

        pattern_obj = GLOBAL_REGISTRY.get(self.pattern)
        intent = pattern_obj.intent_factory()
        self.graph.apply_to_intent(intent)
        return intent

    def path_log(self) -> list[str]:
        return list(self._path_log)

    def summary(self) -> str:
        lines = ["=== Interview Summary ===", ""]
        for key, value in self._history:
            req = self.graph._requirements.get(key)
            label = req.label if req else key
            status = self.graph.status(key).value
            lines.append(f"  [{status}] {label}: {value}")

        if self._path_log:
            lines.append("")
            lines.append("=== Path taken ===")
            lines.extend(self._path_log)

        pending = self.graph.pending()
        if pending:
            lines.append("")
            lines.append(f"  Still pending: {', '.join(pending)}")

        return "\n".join(lines)

    def save_state(self, path: str | Path) -> None:
        """Save interview state to a JSON file for later resume."""
        state = {
            "pattern": self.pattern,
            "decisions": {
                key: val for key, val in self.graph._decisions.items() if val is not None
            },
            "skipped": [
                key for key, st in self.graph._status.items() if st == RequirementStatus.SKIPPED
            ],
            "history": self._history,
            "path_log": self._path_log,
            "audit": self.graph._audit_log,
        }
        Path(path).write_text(json.dumps(state, indent=2))

    @classmethod
    def load_state(cls, path: str | Path, graph: RequirementGraph | None = None) -> InterviewEngine:
        """Load a saved interview state and resume from where it left off.

        If *graph* is provided, it is used instead of creating one from
        the saved pattern. This is useful in tests or when the caller
        already has a configured graph.
        """
        state = json.loads(Path(path).read_text())
        if graph is None:
            engine = cls(pattern=state.get("pattern", "baseline"))
        else:
            engine = cls(graph=graph, pattern=state.get("pattern", "baseline"))
        # Replay decisions first (triggers _update_blocked), then skip
        # so that skip status sticks after blocked re-evaluation
        for key, value in state.get("decisions", {}).items():
            if key in engine.graph._requirements:
                engine.graph.decide(key, value)
        for key in state.get("skipped", []):
            if key in engine.graph._requirements:
                engine.graph._status[key] = RequirementStatus.SKIPPED
        engine._history = list(state.get("history", []))
        engine._path_log = list(state.get("path_log", []))
        engine.graph._audit_log = list(state.get("audit", []))
        return engine

    def to_markdown(self) -> str:
        """Generate a fillable Markdown design document from interview responses."""
        lines = ["# Design Document — Interview Transcript", ""]
        sections: dict[str, list[str]] = {}
        for key, value in self._history:
            req = self.graph._requirements.get(key)
            if not req:
                continue
            cat = req.category or "general"
            if cat not in sections:
                sections[cat] = []
            val_str = str(value).replace(" (default)", "").replace(" (decided)", "")
            sections[cat].append(f"- {key}: {val_str}")

        for cat, items in sections.items():
            lines.append(f"## {cat.title()}")
            lines.append("")
            lines.extend(items)
            lines.append("")

        pending = self.graph.pending()
        if pending:
            lines.append("## Unanswered")
            lines.append("")
            for key in pending:
                req = self.graph._requirements.get(key)
                if req:
                    lines.append(f"# {req.question}")
                    lines.append(f"# - {key}: <fill in>")
            lines.append("")

        return "\n".join(lines)
