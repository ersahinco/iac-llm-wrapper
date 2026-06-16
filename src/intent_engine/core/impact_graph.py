"""Graph-native impact traversal across generated handoff bundles."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .patterns import GLOBAL_REGISTRY
from .yaml_utils import read_yaml_mapping, write_yaml_artifact

BOUNDARY = (
    "Impact analysis traverses registered requirement, contract, module, policy, "
    "artifact, and review metadata. It does not deploy, mutate cloud resources, "
    "run policy tools, or provide compliance attestation."
)


@dataclass(frozen=True)
class ImpactRoot:
    kind: str
    key: str


@dataclass
class _ImpactNode:
    id: str
    kind: str
    key: str
    label: str
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "key": self.key,
            "label": self.label,
            "properties": self.properties,
        }


@dataclass(frozen=True)
class _ImpactEdge:
    source: str
    target: str
    relationship: str

    def to_dict(self) -> dict[str, str]:
        return {
            "from": self.source,
            "to": self.target,
            "relationship": self.relationship,
        }


class _ImpactGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, _ImpactNode] = {}
        self.edges: list[_ImpactEdge] = []
        self._edge_keys: set[tuple[str, str, str]] = set()

    def add_node(
        self,
        kind: str,
        key: str,
        label: str | None = None,
        **properties: Any,
    ) -> str:
        node_id = f"{kind}:{key}"
        existing = self.nodes.get(node_id)
        if existing is not None:
            existing.properties.update({k: v for k, v in properties.items() if v not in (None, "")})
            return node_id
        self.nodes[node_id] = _ImpactNode(
            id=node_id,
            kind=kind,
            key=key,
            label=label or key,
            properties={k: v for k, v in properties.items() if v not in (None, "")},
        )
        return node_id

    def add_edge(self, source: str, target: str, relationship: str) -> None:
        if source not in self.nodes or target not in self.nodes:
            return
        key = (source, target, relationship)
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self.edges.append(_ImpactEdge(source=source, target=target, relationship=relationship))

    def downstream(self, roots: list[str]) -> set[str]:
        return _walk(roots, self._outgoing())

    def upstream(self, roots: list[str]) -> set[str]:
        return _walk(roots, self._incoming())

    def shortest_path(self, roots: list[str], target: str) -> list[_ImpactEdge]:
        outgoing = self._outgoing_edges()
        queue: deque[tuple[str, list[_ImpactEdge]]] = deque((root, []) for root in roots)
        seen: set[str] = set(roots)
        while queue:
            node, path = queue.popleft()
            if node == target:
                return path
            for edge in outgoing.get(node, []):
                if edge.target in seen:
                    continue
                seen.add(edge.target)
                queue.append((edge.target, [*path, edge]))
        return []

    def _outgoing(self) -> dict[str, list[str]]:
        graph: dict[str, list[str]] = {}
        for edge in self.edges:
            graph.setdefault(edge.source, []).append(edge.target)
        return graph

    def _incoming(self) -> dict[str, list[str]]:
        graph: dict[str, list[str]] = {}
        for edge in self.edges:
            graph.setdefault(edge.target, []).append(edge.source)
        return graph

    def _outgoing_edges(self) -> dict[str, list[_ImpactEdge]]:
        graph: dict[str, list[_ImpactEdge]] = {}
        for edge in self.edges:
            graph.setdefault(edge.source, []).append(edge)
        return graph


def build_impact_report(
    bundle: Path,
    *,
    roots: list[ImpactRoot],
    changed_report: Path | None = None,
) -> dict[str, Any]:
    """Build an impact report for selected bundle graph roots."""

    graph, pattern = _build_graph(bundle)
    selected_roots = _roots_from_selectors(graph, roots)
    changed_roots = _roots_from_changed_report(graph, changed_report) if changed_report else []
    root_ids = list(dict.fromkeys([*selected_roots, *changed_roots]))
    downstream = graph.downstream(root_ids) - set(root_ids) if root_ids else set()
    upstream = graph.upstream(root_ids) - set(root_ids) if root_ids else set()
    downstream_nodes = _sorted_nodes(graph, downstream)
    upstream_nodes = _sorted_nodes(graph, upstream)
    root_nodes = _sorted_nodes(graph, set(root_ids))
    affected_artifacts = _keys_by_kind(downstream_nodes, "artifact")
    affected_controls = _keys_by_kind(downstream_nodes, "policy_control")
    affected_checks = _keys_by_kind(downstream_nodes, "checkov_check")
    affected_variables = _keys_by_kind(downstream_nodes, "module_variable")
    manual_gates = _keys_by_kind(downstream_nodes, "manual_gate")
    impact_paths = _impact_paths(graph, root_ids, downstream_nodes)
    unmatched = _unmatched_roots(roots, graph, selected_roots)
    if changed_report and not changed_roots:
        unmatched.append({"kind": "changed-report", "key": str(changed_report)})

    status = "matched" if root_ids else "no-match"
    return {
        "schemaVersion": "intent-engine/impact-report/v1",
        "bundle": str(bundle),
        "pattern": pattern,
        "boundary": BOUNDARY,
        "summary": {
            "status": status,
            "rootCount": len(root_ids),
            "downstreamImpactCount": len(downstream),
            "upstreamDependencyCount": len(upstream),
            "affectedArtifactCount": len(affected_artifacts),
            "affectedPolicyControlCount": len(affected_controls),
            "manualGateCount": len(manual_gates),
        },
        "selectedRoots": [node.to_dict() for node in root_nodes],
        "unmatchedRoots": unmatched,
        "upstreamDependencies": [node.to_dict() for node in upstream_nodes],
        "downstreamImpacts": [node.to_dict() for node in downstream_nodes],
        "affectedArtifacts": affected_artifacts,
        "affectedPolicyControls": affected_controls,
        "affectedChecks": affected_checks,
        "affectedModuleVariables": affected_variables,
        "manualGates": manual_gates,
        "impactPaths": impact_paths,
        "reviewFocus": _review_focus(
            status=status,
            roots=root_nodes,
            artifacts=affected_artifacts,
            controls=affected_controls,
            checks=affected_checks,
            gates=manual_gates,
        ),
        "graph": {
            "nodeCount": len(graph.nodes),
            "edgeCount": len(graph.edges),
            "edges": [edge.to_dict() for edge in graph.edges],
        },
    }


def build_bundle_graph_report(bundle: Path) -> dict[str, Any]:
    """Build the full typed graph for a generated handoff bundle."""

    graph, pattern = _build_graph(bundle)
    nodes = [node.to_dict() for node in sorted(graph.nodes.values(), key=lambda item: item.id)]
    edges = [
        edge.to_dict()
        for edge in sorted(
            graph.edges,
            key=lambda item: (item.source, item.relationship, item.target),
        )
    ]
    return {
        "schemaVersion": "intent-engine/bundle-graph/v1",
        "bundle": str(bundle),
        "pattern": pattern,
        "boundary": BOUNDARY,
        "summary": {
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
            "nodeKinds": _count_by(nodes, "kind"),
            "relationships": _count_by(edges, "relationship"),
        },
        "queryHints": {
            "rootKinds": [
                "decision",
                "artifact",
                "policy_control",
                "module_variable",
                "target_contract",
                "target_capability",
                "manual_gate",
            ],
            "impactCommand": (
                "iac-llm-wrapper graph impact --bundle <bundle> --decision <key|other-root>"
            ),
        },
        "nodes": nodes,
        "edges": edges,
    }


def write_bundle_graph_report(report: dict[str, Any], output: Path) -> None:
    write_yaml_artifact(output, report, "")


def render_bundle_graph_text(report: dict[str, Any]) -> str:
    summary = _dict(report.get("summary"))
    lines = [
        "=== Bundle Graph ===",
        "",
        f"Pattern: {report.get('pattern', '')}",
        f"Bundle: {report.get('bundle', '')}",
        f"Nodes: {summary.get('nodeCount', 0)}",
        f"Edges: {summary.get('edgeCount', 0)}",
        "",
        "Node kinds:",
    ]
    for key, count in sorted(_dict(summary.get("nodeKinds")).items()):
        lines.append(f"  - {key}: {count}")
    lines.append("Relationships:")
    for key, count in sorted(_dict(summary.get("relationships")).items()):
        lines.append(f"  - {key}: {count}")
    lines.append("Query roots:")
    for kind in _coerce_list(_dict(report.get("queryHints")).get("rootKinds")):
        lines.append(f"  - {kind}")
    return "\n".join(lines) + "\n"


def write_impact_report(report: dict[str, Any], output: Path) -> None:
    write_yaml_artifact(output, report, "")


def render_impact_report_text(report: dict[str, Any]) -> str:
    summary = _dict(report.get("summary"))
    lines = [
        "=== Impact Analysis ===",
        "",
        f"Status: {summary.get('status', 'unknown')}",
        f"Pattern: {report.get('pattern', '')}",
        f"Bundle: {report.get('bundle', '')}",
        "",
        "Roots:",
    ]
    roots = _coerce_list(report.get("selectedRoots"))
    if roots:
        lines.extend(f"  - {_node_label(item)}" for item in roots if isinstance(item, dict))
    else:
        lines.append("  - No matching roots found.")
    unmatched = _coerce_list(report.get("unmatchedRoots"))
    if unmatched:
        lines.append("")
        lines.append("Unmatched roots:")
        lines.extend(
            f"  - {item.get('kind', 'unknown')}:{item.get('key', '')}"
            for item in unmatched
            if isinstance(item, dict)
        )
    lines.extend(
        [
            "",
            f"Downstream impacts: {summary.get('downstreamImpactCount', 0)}",
            f"Upstream dependencies: {summary.get('upstreamDependencyCount', 0)}",
            "",
            "Affected artifacts:",
        ]
    )
    lines.extend(_list_or_none(_coerce_list(report.get("affectedArtifacts"))))
    lines.append("Affected policy controls:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedPolicyControls"))))
    lines.append("Affected checks:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedChecks"))))
    lines.append("Affected module variables:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedModuleVariables"))))
    lines.append("Manual gates:")
    lines.extend(_list_or_none(_coerce_list(report.get("manualGates"))))
    lines.append("Impact paths:")
    lines.extend(_path_lines(_coerce_list(report.get("impactPaths"))))
    lines.append("Review focus:")
    lines.extend(_list_or_none(_coerce_list(report.get("reviewFocus"))))
    return "\n".join(lines) + "\n"


def changed_decision_roots(compare_report: dict[str, Any]) -> list[ImpactRoot]:
    decision_delta = _dict(compare_report.get("decisionDelta"))
    roots: list[ImpactRoot] = []
    for section in ("added", "changed", "removed"):
        for item in _coerce_list(decision_delta.get(section)):
            if isinstance(item, dict) and item.get("key"):
                roots.append(ImpactRoot(kind="decision", key=str(item["key"])))
    return roots


def _build_graph(bundle: Path) -> tuple[_ImpactGraph, str]:
    report = read_yaml_mapping(bundle / "decision-report.yaml")
    trace = read_yaml_mapping(bundle / "llm-trace-summary.yaml")
    manifest = read_yaml_mapping(bundle / "context-manifest.yaml")
    module_inputs = read_yaml_mapping(bundle / "module-inputs.yaml")
    policy_graph = read_yaml_mapping(bundle / "policy-graph.yaml")
    handoff = read_yaml_mapping(bundle / "handoff-plan.yaml")
    target_capability = read_yaml_mapping(bundle / "target-capability-graph.yaml")
    samples = read_yaml_mapping(bundle / "sample-recommendations.yaml")
    pattern = str(report.get("pattern") or manifest.get("pattern") or trace.get("pattern") or "")
    pattern_obj = GLOBAL_REGISTRY.get(pattern) if pattern in GLOBAL_REGISTRY.list() else None
    graph = _ImpactGraph()
    accepted = _dict(trace.get("acceptedDecisions"))

    if pattern_obj is not None:
        requirement_graph = pattern_obj.create_graph()
        for key, req in requirement_graph._requirements.items():
            req_id = graph.add_node("requirement", key, req.label, category=req.category)
            if key in accepted:
                decision_id = graph.add_node("decision", key, key, value=accepted.get(key))
                graph.add_edge(req_id, decision_id, "accepted-as")
            for dep in req.depends_on:
                dep_id = graph.add_node("requirement", dep, dep)
                graph.add_edge(dep_id, req_id, "requires")
        for contract in pattern_obj.contracts:
            contract_id = graph.add_node("target_contract", contract.name, contract.name)
            for decision in contract.required_decisions:
                decision_id = graph.add_node(
                    "decision",
                    decision,
                    decision,
                    value=accepted.get(decision),
                )
                graph.add_edge(decision_id, contract_id, "required-by-contract")
            for artifact in contract.artifacts:
                artifact_id = graph.add_node("artifact", artifact.name, artifact.name)
                graph.add_edge(contract_id, artifact_id, "requires-artifact")
            for item in contract.lineage:
                decision_id = graph.add_node("decision", item.decision, item.decision)
                artifact_path_id = graph.add_node(
                    "artifact_path",
                    f"{item.artifact}:{item.path}",
                    f"{item.artifact}:{item.path}",
                    artifact=item.artifact,
                    path=item.path,
                )
                artifact_id = graph.add_node("artifact", item.artifact, item.artifact)
                graph.add_edge(decision_id, artifact_path_id, "writes")
                graph.add_edge(artifact_path_id, artifact_id, "belongs-to")

    _add_module_nodes(graph, module_inputs)
    _add_policy_nodes(graph, policy_graph)
    _add_handoff_nodes(graph, handoff)
    _add_target_capability_nodes(graph, target_capability)
    _add_sample_nodes(graph, samples)
    return graph, pattern


def _add_module_nodes(graph: _ImpactGraph, module_inputs: dict[str, Any]) -> None:
    for module in _coerce_list(module_inputs.get("moduleInputs")):
        if not isinstance(module, dict):
            continue
        module_name = str(module.get("moduleName", "module"))
        module_id = graph.add_node("module", module_name, module_name)
        artifact_id = graph.add_node("artifact", "module-inputs.yaml", "module-inputs.yaml")
        graph.add_edge(module_id, artifact_id, "emitted-in")
        variables = _dict(module.get("variables"))
        for name, value in variables.items():
            var_id = graph.add_node(
                "module_variable",
                str(name),
                f"{module_name}.{name}",
                module=module_name,
                value=value,
            )
            graph.add_edge(var_id, module_id, "input-to")
            graph.add_edge(var_id, artifact_id, "rendered-in")


def _add_policy_nodes(graph: _ImpactGraph, policy_graph: dict[str, Any]) -> None:
    for pack in _coerce_list(policy_graph.get("policyPacks")):
        if not isinstance(pack, dict):
            continue
        pack_name = str(pack.get("name", ""))
        pack_id = graph.add_node("policy_pack", pack_name, pack_name)
        for control in _coerce_list(pack.get("controls")):
            if not isinstance(control, dict):
                continue
            control_id_value = str(control.get("id", ""))
            control_id = graph.add_node(
                "policy_control",
                control_id_value,
                str(control.get("title") or control_id_value),
                frameworks=control.get("frameworks") or pack.get("frameworks"),
            )
            graph.add_edge(pack_id, control_id, "contains-control")
            mapping = _dict(control.get("mapping"))
            requirement_keys = [str(item) for item in _coerce_list(mapping.get("requirementKeys"))]
            module_variables = [str(item) for item in _coerce_list(mapping.get("moduleVariables"))]
            for req_key in requirement_keys:
                decision_id = graph.add_node("decision", str(req_key), str(req_key))
                graph.add_edge(decision_id, control_id, "mapped-to-control")
                for variable in module_variables:
                    variable_id = graph.add_node("module_variable", variable, variable)
                    graph.add_edge(decision_id, variable_id, "maps-to-module-variable")
            for contract_name in _coerce_list(mapping.get("targetContracts")):
                contract_id = graph.add_node(
                    "target_contract",
                    str(contract_name),
                    str(contract_name),
                )
                graph.add_edge(control_id, contract_id, "references-contract")
            for path in _coerce_list(mapping.get("artifactPaths")):
                path_text = str(path)
                artifact_name = path_text.split(":", 1)[0]
                artifact_path_id = graph.add_node("artifact_path", path_text, path_text)
                artifact_id = graph.add_node("artifact", artifact_name, artifact_name)
                graph.add_edge(control_id, artifact_path_id, "reviews-path")
                graph.add_edge(artifact_path_id, artifact_id, "belongs-to")
            for variable in module_variables:
                variable_id = graph.add_node("module_variable", variable, variable)
                graph.add_edge(variable_id, control_id, "mapped-to-control")
            for check_id in _coerce_list(mapping.get("checkovCheckIds")):
                check_node = graph.add_node("checkov_check", str(check_id), str(check_id))
                graph.add_edge(control_id, check_node, "verified-by")
            for check in _coerce_list(control.get("checks")):
                if not isinstance(check, dict):
                    continue
                check_id = str(check.get("checkId") or check.get("check_id") or "")
                if check_id:
                    check_node = graph.add_node(
                        "checkov_check",
                        check_id,
                        str(check.get("name") or check_id),
                    )
                    graph.add_edge(control_id, check_node, "verified-by")


def _add_handoff_nodes(graph: _ImpactGraph, handoff: dict[str, Any]) -> None:
    for step in _coerce_list(handoff.get("steps")):
        if not isinstance(step, dict):
            continue
        if not step.get("manualGate"):
            continue
        title = str(step.get("title") or step.get("key") or "")
        if not title:
            continue
        gate_id = graph.add_node("manual_gate", title, title, owner=step.get("owner"))
        for artifact in _coerce_list(step.get("artifacts")):
            artifact_id = graph.add_node("artifact", str(artifact), str(artifact))
            graph.add_edge(artifact_id, gate_id, "requires-review-gate")
        for dependency in _coerce_list(step.get("dependsOn")):
            if dependency:
                dep_id = graph.add_node("manual_gate", str(dependency), str(dependency))
                graph.add_edge(dep_id, gate_id, "precedes-gate")


def _add_target_capability_nodes(graph: _ImpactGraph, target_capability: dict[str, Any]) -> None:
    for capability in _coerce_list(target_capability.get("capabilities")):
        if not isinstance(capability, dict):
            continue
        cap_id = graph.add_node(
            "target_capability",
            str(capability.get("key", "")),
            str(capability.get("label") or capability.get("key", "")),
            type=capability.get("type"),
        )
        for decision in _coerce_list(capability.get("handledDecisions")):
            decision_id = graph.add_node("decision", str(decision), str(decision))
            graph.add_edge(decision_id, cap_id, "handled-by-capability")
        for artifact in _coerce_list(capability.get("producedArtifacts")):
            artifact_id = graph.add_node("artifact", str(artifact), str(artifact))
            graph.add_edge(cap_id, artifact_id, "produces")
        for gate in _coerce_list(capability.get("manualGates")):
            gate_id = graph.add_node("manual_gate", str(gate), str(gate))
            graph.add_edge(cap_id, gate_id, "requires-manual-gate")


def _add_sample_nodes(graph: _ImpactGraph, samples: dict[str, Any]) -> None:
    artifact_id = graph.add_node(
        "artifact",
        "sample-recommendations.yaml",
        "sample-recommendations.yaml",
    )
    for sample in _coerce_list(samples.get("recommendations")):
        if not isinstance(sample, dict):
            continue
        sample_name = str(sample.get("name", ""))
        if not sample_name:
            continue
        sample_id = graph.add_node("sample", sample_name, sample_name)
        graph.add_edge(sample_id, artifact_id, "listed-in")


def _roots_from_selectors(graph: _ImpactGraph, roots: list[ImpactRoot]) -> list[str]:
    selected: list[str] = []
    for root in roots:
        exact = f"{root.kind}:{root.key}"
        if exact in graph.nodes:
            selected.append(exact)
            continue
        for node in graph.nodes.values():
            if node.kind == root.kind and node.key == root.key:
                selected.append(node.id)
    return list(dict.fromkeys(selected))


def _roots_from_changed_report(graph: _ImpactGraph, changed_report: Path | None) -> list[str]:
    if changed_report is None or not changed_report.exists():
        return []
    report = read_yaml_mapping(changed_report)
    roots: list[ImpactRoot] = []
    for item in _coerce_list(report.get("likelyImpactedRequirements")):
        if isinstance(item, dict) and item.get("key"):
            roots.append(ImpactRoot(kind="decision", key=str(item["key"])))
    for item in _coerce_list(report.get("changedStructuredDecisionLines")):
        if isinstance(item, dict) and item.get("key"):
            roots.append(ImpactRoot(kind="decision", key=str(item["key"])))
    return _roots_from_selectors(graph, roots)


def _unmatched_roots(
    roots: list[ImpactRoot],
    graph: _ImpactGraph,
    matched_ids: list[str],
) -> list[dict[str, str]]:
    matched = set(matched_ids)
    unmatched: list[dict[str, str]] = []
    for root in roots:
        exact = f"{root.kind}:{root.key}"
        if exact in matched:
            continue
        if not any(
            node.kind == root.kind and node.key == root.key for node in graph.nodes.values()
        ):
            unmatched.append({"kind": root.kind, "key": root.key})
    return unmatched


def _walk(roots: list[str], adjacency: dict[str, list[str]]) -> set[str]:
    seen: set[str] = set()
    queue: deque[str] = deque(roots)
    while queue:
        node = queue.popleft()
        for target in adjacency.get(node, []):
            if target in seen:
                continue
            seen.add(target)
            queue.append(target)
    return seen


def _sorted_nodes(graph: _ImpactGraph, ids: set[str]) -> list[_ImpactNode]:
    return [graph.nodes[node_id] for node_id in sorted(ids) if node_id in graph.nodes]


def _keys_by_kind(nodes: list[_ImpactNode], kind: str) -> list[str]:
    return sorted({node.key for node in nodes if node.kind == kind and node.key})


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return counts


def _impact_paths(
    graph: _ImpactGraph,
    roots: list[str],
    downstream_nodes: list[_ImpactNode],
) -> list[dict[str, Any]]:
    interesting_kinds = {
        "artifact",
        "artifact_path",
        "checkov_check",
        "manual_gate",
        "module_variable",
        "policy_control",
        "target_contract",
        "target_capability",
    }
    paths: list[dict[str, Any]] = []
    for node in downstream_nodes:
        if node.kind not in interesting_kinds:
            continue
        edges = graph.shortest_path(roots, node.id)
        if not edges:
            continue
        root_id = edges[0].source
        root_node = graph.nodes.get(root_id)
        paths.append(
            {
                "root": root_node.to_dict() if root_node is not None else {"id": root_id},
                "target": node.to_dict(),
                "hops": [
                    {
                        "from": graph.nodes[edge.source].to_dict(),
                        "relationship": edge.relationship,
                        "to": graph.nodes[edge.target].to_dict(),
                    }
                    for edge in edges
                    if edge.source in graph.nodes and edge.target in graph.nodes
                ],
            }
        )
    return sorted(paths, key=lambda item: str(_dict(item.get("target")).get("id", "")))


def _review_focus(
    *,
    status: str,
    roots: list[_ImpactNode],
    artifacts: list[str],
    controls: list[str],
    checks: list[str],
    gates: list[str],
) -> list[str]:
    if status == "no-match":
        return [
            "No matching graph roots were found; verify the selected decision, "
            "artifact, policy control, or module variable."
        ]
    focus = [f"Review impact from {', '.join(node.id for node in roots)}."]
    if artifacts:
        focus.append("Review affected artifacts: " + ", ".join(artifacts) + ".")
    if controls:
        focus.append("Review affected policy controls: " + ", ".join(controls) + ".")
    if checks:
        focus.append(
            "Use affected Checkov refs as shift-left evidence inputs: " + ", ".join(checks) + "."
        )
    if gates:
        focus.append("Re-run or re-approve manual gates: " + ", ".join(gates) + ".")
    return focus


def _node_label(node: dict[str, Any]) -> str:
    return f"{node.get('kind', 'unknown')}:{node.get('key', '')}"


def _list_or_none(items: list[Any]) -> list[str]:
    if not items:
        return ["  - None"]
    return [f"  - {item}" for item in items]


def _path_lines(paths: list[Any]) -> list[str]:
    if not paths:
        return ["  - None"]
    lines: list[str] = []
    for path in paths[:8]:
        if not isinstance(path, dict):
            continue
        target = _dict(path.get("target"))
        hops = _coerce_list(path.get("hops"))
        rendered_hops = []
        for hop in hops:
            if not isinstance(hop, dict):
                continue
            source = _dict(hop.get("from"))
            destination = _dict(hop.get("to"))
            rendered_hops.append(
                f"{source.get('id', '')} --{hop.get('relationship', '')}--> "
                f"{destination.get('id', '')}"
            )
        lines.append(f"  - {target.get('id', 'unknown')}: " + " | ".join(rendered_hops))
    if len(paths) > 8:
        lines.append(f"  ... {len(paths) - 8} more")
    return lines or ["  - None"]


def _coerce_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
