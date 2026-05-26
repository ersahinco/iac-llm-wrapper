"""Suggestion engine: generates contextual next steps from requirement graph."""

from __future__ import annotations

from dataclasses import dataclass

from .requirements import RequirementGraph, RequirementStatus


@dataclass
class Suggestion:
    key: str
    label: str
    question: str
    options: list[str] | None
    default: str | None
    hint: str | None
    context: str
    priority: int


class SuggestionEngine:
    """Generates contextual suggestions based on current graph state and decisions."""

    def __init__(self, graph: RequirementGraph) -> None:
        self.graph = graph

    def suggest_next(self) -> list[Suggestion]:
        """Return all ready-to-answer requirements with full context."""
        suggestions = []
        pending = self.graph.pending()

        for key in pending:
            req = self.graph._requirements[key]
            st = self.graph.status(key)

            applies_reason = self.graph.is_applicable_reason(key)
            blocked_reason = self.graph.is_blocked_reason(key)

            if st == RequirementStatus.BLOCKED:
                continue

            context = ""
            if applies_reason:
                context = applies_reason
            if blocked_reason:
                context = blocked_reason
            if req.depends_on:
                dep_values = {d: self.graph.get(d) for d in req.depends_on}
                dep_str = ", ".join(f"{k}={v}" for k, v in dep_values.items() if v)
                if dep_str:
                    context = f"depends on [{dep_str}]"

            priority = self._compute_priority(key, req, st)

            suggestions.append(
                Suggestion(
                    key=key,
                    label=req.label,
                    question=req.question,
                    options=req.options,
                    default=req.default,
                    hint=req.hint,
                    context=context,
                    priority=priority,
                )
            )

        suggestions.sort(key=lambda x: x.priority)
        return suggestions

    def preview_path(self) -> list[dict[str, str]]:
        """Preview the full decision path given current decisions."""
        path = []
        for key in self.graph._requirements:
            req = self.graph._requirements[key]
            st = self.graph.status(key)
            value = self.graph.get(key)
            applies_reason = self.graph.is_applicable_reason(key)
            blocked_reason = self.graph.is_blocked_reason(key)

            path.append(
                {
                    "key": key,
                    "label": req.label,
                    "category": req.category,
                    "status": st.value,
                    "value": value or "(undecided)",
                    "context": blocked_reason or applies_reason or "",
                }
            )
        return path

    def _compute_priority(self, key: str, req, status: RequirementStatus) -> int:
        if status == RequirementStatus.BLOCKED:
            return 99
        if status in (RequirementStatus.DECIDED, RequirementStatus.DEFAULTED):
            return 99

        cat = req.category
        if cat == "organization":
            return 1
        if cat == "network":
            return 3
        if cat == "security":
            return 4
        if cat == "cicd":
            return 5
        if cat == "hybrid":
            return 6
        return 10
