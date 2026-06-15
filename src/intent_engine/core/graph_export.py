"""Requirement graph export helpers."""

from __future__ import annotations

import json
import re
from typing import Any

from .requirements import (
    RequirementGraph,
    describe_expression,
    expression_dependencies,
)


def graph_to_dict(graph: RequirementGraph, pattern: str) -> dict[str, Any]:
    """Return a stable JSON-serializable view of a requirement graph."""
    try:
        ordered_keys = graph.topological_order()
    except ValueError:
        ordered_keys = list(graph._requirements)

    nodes = []
    for key in ordered_keys:
        if key not in graph._requirements:
            continue
        req = graph._requirements[key]
        nodes.append(
            {
                "key": key,
                "label": req.label,
                "category": req.category,
                "question": req.question,
                "targetField": req.target_field,
                "targetType": req.target_type,
                "requiredWhenApplicable": req.required_when_applicable,
                "default": req.default,
                "options": req.options or [],
                "dependsOn": list(req.depends_on),
                "appliesIf": req.applies_if,
                "appliesWhen": req.applies_when,
                "blockedIf": req.blocked_if,
                "blockedWhen": req.blocked_when,
                "cascade": req.cascade,
                "hint": req.hint,
                "signals": list(req.signals),
                "complianceControls": list(req.compliance_controls),
                "status": graph.status(key).value,
                "decision": graph.get(key),
            }
        )

    return {
        "pattern": pattern,
        "nodeCount": len(nodes),
        "edgeCount": graph.edge_count(),
        "nodes": nodes,
        "edges": [
            {
                "source": source,
                "target": target,
                "kind": _edge_kind(graph, source, target),
                "condition": _edge_condition(graph, source, target),
            }
            for source, target in graph.edges()
            if target in graph._requirements
        ],
    }


def graph_to_json(graph: RequirementGraph, pattern: str) -> str:
    """Return pretty JSON for a requirement graph."""
    return json.dumps(graph_to_dict(graph, pattern), indent=2, sort_keys=False) + "\n"


def graph_to_mermaid(graph: RequirementGraph, pattern: str) -> str:
    """Return a Mermaid flowchart for a requirement graph."""
    data = graph_to_dict(graph, pattern)
    lines = [
        "---",
        f"title: {pattern} requirement graph",
        "---",
        "flowchart TD",
    ]
    for node in data["nodes"]:
        node_id = _node_id(str(node["key"]))
        label = f"{node['label']}\\n{node['key']}\\n{node['category']}"
        lines.append(f'  {node_id}["{_escape_mermaid_label(label)}"]')
    for edge in data["edges"]:
        source = _node_id(str(edge["source"]))
        target = _node_id(str(edge["target"]))
        label = edge["kind"]
        if edge["condition"]:
            label = f"{label}: {edge['condition']}"
        lines.append(f"  {source} -->|{_escape_mermaid_edge(label)}| {target}")
    lines.append("")
    return "\n".join(lines)


def _edge_kind(graph: RequirementGraph, source: str, target: str) -> str:
    req = graph._requirements[target]
    kinds = []
    if source in req.depends_on:
        kinds.append("depends_on")
    if source in req.applies_if:
        kinds.append("applies_if")
    if source in expression_dependencies(req.applies_when):
        kinds.append("applies_when")
    if source in req.blocked_if:
        kinds.append("blocked_if")
    if source in expression_dependencies(req.blocked_when):
        kinds.append("blocked_when")
    return "+".join(kinds) if kinds else "orders"


def _edge_condition(graph: RequirementGraph, source: str, target: str) -> str:
    req = graph._requirements[target]
    if source in req.applies_if:
        return ",".join(req.applies_if[source])
    if source in expression_dependencies(req.applies_when):
        return describe_expression(req.applies_when)
    if source in req.blocked_if:
        return ",".join(req.blocked_if[source])
    if source in expression_dependencies(req.blocked_when):
        return describe_expression(req.blocked_when)
    return ""


def _node_id(key: str) -> str:
    return "n_" + re.sub(r"[^a-zA-Z0-9_]", "_", key)


def _escape_mermaid_label(value: str) -> str:
    return value.replace('"', '\\"')


def _escape_mermaid_edge(value: str) -> str:
    return value.replace("|", "/").replace("\n", " ")
