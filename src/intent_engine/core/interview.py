"""Interview engine that navigates requirements in dependency order with full traceability."""

from __future__ import annotations

from dataclasses import dataclass
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

    def answer(self, key: str, value: str) -> None:
        self.graph.decide(key, value)
        self._history.append((key, value))
        self._log_decision(key, value, "decided")

    def accept_default(self, key: str) -> None:
        self.graph.apply_default(key)
        req = self.graph._requirements[key]
        self._history.append((key, f"{req.default} (default)"))
        self._log_decision(key, req.default, "defaulted")

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

    def run_interactive(self, input_fn=None, output_fn=None) -> None:
        input_fn = input_fn or input
        output_fn = output_fn or print

        output_fn("")
        output_fn(f"=== Interview [{self.pattern}] ===")
        output_fn("")

        while True:
            q = self.next_question()
            if q is None:
                break

            output_fn(f"[{q.category}] {q.label}")
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
                opt_str = ", ".join(q.options)
                def_str = f" (default: {q.default})" if q.default else ""
                output_fn(f"  Options: {opt_str}{def_str}")
            else:
                def_str = f" (default: {q.default})" if q.default else ""
                output_fn(f"  {def_str}")

            if q.default is not None:
                answer = input_fn("  Answer (or Enter for default): ").strip()
                if not answer:
                    self.accept_default(q.key)
                else:
                    self.answer(q.key, answer)
            else:
                answer = input_fn("  Answer: ").strip()
                if not answer:
                    self.skip(q.key)
                else:
                    self.answer(q.key, answer)

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
                self.graph.decide(key, value)
                self._log_decision(key, value, "decided")

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
