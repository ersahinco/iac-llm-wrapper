"""Graph-native impact traversal across generated handoff bundles."""

from __future__ import annotations

import hashlib
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
PRIORITY_SEVERITIES = ("critical", "high", "medium", "low")

NODE_KIND_DESCRIPTIONS = {
    "artifact": "Generated handoff artifact or evidence file in the bundle.",
    "artifact_path": "Path inside an artifact that is covered by lineage or policy review.",
    "checkov_check": "Checkov built-in or owner custom policy check reference.",
    "checkov_finding": "Finding captured from optional shift-left Checkov evidence.",
    "contract_result": "Result for one target contract inside contract validation evidence.",
    "contract_validation": "Bundle-level target contract validation evidence.",
    "decision": "Accepted or expected graph decision value.",
    "downstream_validation_evidence": "Owner-tool validation evidence captured as review input.",
    "handoff_readiness": "Bundle readiness state and handoffAllowed status.",
    "input_diff": "Incremental input diff report.",
    "manual_gate": "Human or owner-controlled review gate.",
    "module": "Approved IaC module target represented in module-input handoff metadata.",
    "module_variable": "Variable handed to an approved IaC module.",
    "policy_control": "Compliance or client/platform policy control.",
    "policy_pack": "Registered policy pack grouping related policy controls.",
    "readiness_blocker": "Missing, conflicting, or blocking condition for handoff readiness.",
    "requirement": "Requirement graph node that asks for or constrains a decision.",
    "sample": "Registered sample recommendation used for alignment review.",
    "scan_file": "Owner IaC file referenced by shift-left scan evidence.",
    "semantic_constraint": "Typed semantic predicate constraint result.",
    "semantic_entity": "Typed semantic entity derived from the pattern model.",
    "shift_left_evidence": "Optional pre-deployment policy/tool evidence artifact.",
    "source_change": "Changed source document segment or likely impacted requirement.",
    "source_context": "Source packet context and provenance.",
    "target_capability": "Registered target capability or routing coverage node.",
    "target_contract": "Registered target contract that artifacts must satisfy.",
    "validation_violation": "Target contract validation violation.",
}

RELATIONSHIP_DESCRIPTIONS = {
    "accepted-as": "Requirement is satisfied by an accepted decision.",
    "belongs-to": "Artifact path is part of a generated artifact.",
    "blocks-readiness": "Blocker prevents handoff readiness.",
    "changes-decision": "Source change directly changes a decision.",
    "checked-by-constraint": "Decision is evaluated by a semantic constraint.",
    "checks-entity": "Semantic constraint evaluates a semantic entity.",
    "conflict-blocks-readiness": "Decision conflict creates a readiness blocker.",
    "contains-control": "Policy pack contains a policy control.",
    "contains-source-change": "Input diff includes a source change.",
    "contributes-to-readiness": "Decision contributes to handoff readiness state.",
    "describes-artifact": "Semantic entity describes a generated artifact.",
    "emitted-in": "Module handoff is emitted in an artifact.",
    "found-in-file": "Checkov finding was found in an owner scan file.",
    "handled-by-capability": "Decision is handled by a registered target capability.",
    "has-blocker": "Readiness includes a blocker.",
    "has-finding": "Policy control has a mapped Checkov finding.",
    "has-input-diff": "Source context has an incremental input diff.",
    "has-violation": "Contract result includes a validation violation.",
    "impacts-requirement": "Source change likely impacts a requirement decision.",
    "influences-sample-match": "Decision influences sample recommendation match or rank.",
    "input-to": "Module variable is an input to an approved module.",
    "listed-in": "Sample recommendation is listed in an artifact.",
    "mapped-to-control": "Decision, module variable, or finding maps to a policy control.",
    "maps-to-module-variable": "Decision maps to a module variable handoff value.",
    "missing-decision-blocks-readiness": "Missing decision creates a readiness blocker.",
    "precedes-capability": "Target capability must precede another capability.",
    "precedes-gate": "Manual gate must precede another manual gate.",
    "produces": "Target capability produces an artifact.",
    "provides-decision-context": "Source context provides provenance for a decision.",
    "recorded-by-evidence": "Finding is recorded by shift-left evidence.",
    "recorded-in": "Node is recorded in a generated artifact.",
    "recorded-in-validation": "Validation violation is recorded in contract validation.",
    "records-finding": "Shift-left evidence records a Checkov finding.",
    "rendered-in": "Module variable is rendered in an artifact.",
    "reported-in": "Contract result is reported in validation evidence.",
    "required-by-contract": "Decision is required by a target contract.",
    "requires": "Requirement depends on another requirement.",
    "requires-artifact": "Target contract requires an artifact.",
    "requires-manual-gate": "Target capability requires a manual gate.",
    "requires-review-gate": "Artifact must pass a manual review gate.",
    "references-contract": "Policy control references a target contract.",
    "reviewed-with-validation-evidence": "Readiness should be reviewed with validation evidence.",
    "reviews-path": "Policy control reviews a path inside an artifact.",
    "unmapped-in-evidence": "Finding is present in evidence but unmapped to a policy control.",
    "validated-by": "Readiness is validated by contract validation evidence.",
    "validated-by-downstream-evidence": (
        "Artifact was checked by owner downstream validation evidence."
    ),
    "validated-by-result": "Target contract is validated by a contract result.",
    "validates-contract": "Contract result validates a target contract.",
    "verified-by": "Policy control is verified by a Checkov check reference.",
    "violates-check": "Finding violates a Checkov check reference.",
    "writes": "Decision writes a path in an artifact.",
}

SEMANTIC_RELATIONSHIP_DESCRIPTION = "Typed relationship emitted by the pattern semantic model."


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


@dataclass(frozen=True)
class _PathStep:
    edge: _ImpactEdge
    source: str
    target: str
    direction: str


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

    def shortest_steps(self, source: str, target: str, direction: str) -> list[_PathStep]:
        adjacency = self._path_adjacency(direction)
        queue: deque[tuple[str, list[_PathStep]]] = deque([(source, [])])
        seen: set[str] = {source}
        while queue:
            node, path = queue.popleft()
            if node == target:
                return path
            for step in adjacency.get(node, []):
                if step.target in seen:
                    continue
                seen.add(step.target)
                queue.append((step.target, [*path, step]))
        return []

    def neighborhood(
        self, root: str, depth: int, direction: str
    ) -> tuple[dict[str, int], list[_PathStep]]:
        adjacency = self._path_adjacency(direction)
        node_depths: dict[str, int] = {root: 0}
        discovery_steps: list[_PathStep] = []
        queue: deque[str] = deque([root])
        while queue:
            node = queue.popleft()
            current_depth = node_depths[node]
            if current_depth >= depth:
                continue
            for step in adjacency.get(node, []):
                if step.target in node_depths:
                    continue
                node_depths[step.target] = current_depth + 1
                discovery_steps.append(step)
                queue.append(step.target)
        return node_depths, discovery_steps

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

    def _path_adjacency(self, direction: str) -> dict[str, list[_PathStep]]:
        graph: dict[str, list[_PathStep]] = {}
        for edge in self.edges:
            if direction in {"downstream", "either"}:
                graph.setdefault(edge.source, []).append(
                    _PathStep(
                        edge=edge,
                        source=edge.source,
                        target=edge.target,
                        direction="downstream",
                    )
                )
            if direction in {"upstream", "either"}:
                graph.setdefault(edge.target, []).append(
                    _PathStep(
                        edge=edge,
                        source=edge.target,
                        target=edge.source,
                        direction="upstream",
                    )
                )
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
    affected_nodes = [*root_nodes, *downstream_nodes]
    affected_artifacts = _keys_by_kind(affected_nodes, "artifact")
    affected_target_contracts = _keys_by_kind(affected_nodes, "target_contract")
    affected_target_capabilities = _keys_by_kind(affected_nodes, "target_capability")
    affected_samples = _keys_by_kind(affected_nodes, "sample")
    affected_controls = _keys_by_kind(affected_nodes, "policy_control")
    affected_checks = _keys_by_kind(affected_nodes, "checkov_check")
    affected_findings = _keys_by_kind(affected_nodes, "checkov_finding")
    affected_evidence = _keys_by_kind(affected_nodes, "shift_left_evidence")
    affected_variables = _keys_by_kind(affected_nodes, "module_variable")
    affected_semantic_entities = _keys_by_kind(affected_nodes, "semantic_entity")
    affected_semantic_constraints = _keys_by_kind(affected_nodes, "semantic_constraint")
    affected_source_contexts = _keys_by_kind(affected_nodes, "source_context")
    affected_input_diffs = _keys_by_kind(affected_nodes, "input_diff")
    affected_source_changes = _keys_by_kind(affected_nodes, "source_change")
    affected_readiness = _keys_by_kind(affected_nodes, "handoff_readiness")
    affected_readiness_blockers = _keys_by_kind(affected_nodes, "readiness_blocker")
    affected_contract_validation = _keys_by_kind(affected_nodes, "contract_validation")
    affected_contract_results = _keys_by_kind(affected_nodes, "contract_result")
    affected_validation_violations = _keys_by_kind(affected_nodes, "validation_violation")
    affected_downstream_validation = _keys_by_kind(
        affected_nodes,
        "downstream_validation_evidence",
    )
    manual_gates = _keys_by_kind(affected_nodes, "manual_gate")
    impact_paths = _impact_paths(graph, root_ids, downstream_nodes)
    review_priorities = _impact_review_priorities(
        readiness_blockers=affected_readiness_blockers,
        validation_violations=affected_validation_violations,
        downstream_validation=affected_downstream_validation,
        findings=affected_findings,
        shift_left_evidence=affected_evidence,
        source_changes=affected_source_changes,
        manual_gates=manual_gates,
        target_contracts=affected_target_contracts,
        target_capabilities=affected_target_capabilities,
        samples=affected_samples,
        policy_controls=affected_controls,
        artifacts=affected_artifacts,
        module_variables=affected_variables,
    )
    review_checklist = _impact_review_checklist(
        roots=root_nodes,
        priorities=review_priorities,
        impact_paths=impact_paths,
    )
    unmatched = _unmatched_roots(roots, graph, selected_roots)
    if changed_report and not changed_roots:
        unmatched.append({"kind": "changed-report", "key": str(changed_report)})

    status = "matched" if root_ids else "no-match"
    priority_severity_counts = _priority_severity_counts(review_priorities)
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
            "affectedTargetContractCount": len(affected_target_contracts),
            "affectedTargetCapabilityCount": len(affected_target_capabilities),
            "affectedSampleCount": len(affected_samples),
            "affectedPolicyControlCount": len(affected_controls),
            "affectedCheckovFindingCount": len(affected_findings),
            "affectedSemanticConstraintCount": len(affected_semantic_constraints),
            "affectedSourceChangeCount": len(affected_source_changes),
            "affectedReadinessCount": len(affected_readiness),
            "affectedContractValidationCount": len(affected_contract_validation),
            "affectedValidationViolationCount": len(affected_validation_violations),
            "manualGateCount": len(manual_gates),
            "reviewPriorityCount": len(review_priorities),
            "reviewChecklistCount": len(review_checklist),
            "highestReviewPrioritySeverity": _highest_priority_severity(priority_severity_counts),
            "reviewPrioritySeverityCounts": priority_severity_counts,
            "reviewPriorityItemCountsBySeverity": _priority_item_counts_by_severity(
                review_priorities
            ),
        },
        "selectedRoots": [node.to_dict() for node in root_nodes],
        "unmatchedRoots": unmatched,
        "upstreamDependencies": [node.to_dict() for node in upstream_nodes],
        "downstreamImpacts": [node.to_dict() for node in downstream_nodes],
        "affectedArtifacts": affected_artifacts,
        "affectedTargetContracts": affected_target_contracts,
        "affectedTargetCapabilities": affected_target_capabilities,
        "affectedSamples": affected_samples,
        "affectedPolicyControls": affected_controls,
        "affectedChecks": affected_checks,
        "affectedCheckovFindings": affected_findings,
        "affectedShiftLeftEvidence": affected_evidence,
        "affectedModuleVariables": affected_variables,
        "affectedSemanticEntities": affected_semantic_entities,
        "affectedSemanticConstraints": affected_semantic_constraints,
        "affectedSourceContexts": affected_source_contexts,
        "affectedInputDiffs": affected_input_diffs,
        "affectedSourceChanges": affected_source_changes,
        "affectedReadiness": affected_readiness,
        "affectedReadinessBlockers": affected_readiness_blockers,
        "affectedContractValidation": affected_contract_validation,
        "affectedContractResults": affected_contract_results,
        "affectedValidationViolations": affected_validation_violations,
        "affectedDownstreamValidationEvidence": affected_downstream_validation,
        "manualGates": manual_gates,
        "impactPaths": impact_paths,
        "reviewPriorities": review_priorities,
        "reviewChecklist": review_checklist,
        "reviewFocus": _review_focus(
            status=status,
            roots=root_nodes,
            artifacts=affected_artifacts,
            target_contracts=affected_target_contracts,
            target_capabilities=affected_target_capabilities,
            samples=affected_samples,
            controls=affected_controls,
            checks=affected_checks,
            findings=affected_findings,
            semantic_constraints=affected_semantic_constraints,
            source_contexts=affected_source_contexts,
            input_diffs=affected_input_diffs,
            source_changes=affected_source_changes,
            readiness=affected_readiness,
            readiness_blockers=affected_readiness_blockers,
            contract_validation=affected_contract_validation,
            validation_violations=affected_validation_violations,
            downstream_validation=affected_downstream_validation,
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
            "rootKinds": _root_kinds(),
            "rootSelectorSyntax": "<kind>:<key>",
            "findCommand": "iac-llm-wrapper graph find --bundle <bundle> --query <text>",
            "rootsCommand": "iac-llm-wrapper graph roots --bundle <bundle>",
            "impactCommand": (
                "iac-llm-wrapper graph impact --bundle <bundle> --decision <key|other-root>"
            ),
            "pathCommand": (
                "iac-llm-wrapper graph path --bundle <bundle> --from <kind:key> --to <kind:key>"
            ),
            "neighborhoodCommand": (
                "iac-llm-wrapper graph neighbors --bundle <bundle> --root <kind:key>"
            ),
            "matrixCommand": ("iac-llm-wrapper graph matrix --bundle <bundle> --root <kind:key>"),
            "recommendedMatrixCommand": (
                "iac-llm-wrapper graph matrix --bundle <bundle> --recommended"
            ),
            "diffCommand": (
                "iac-llm-wrapper graph diff --before <bundle-before> --after <bundle-after>"
            ),
        },
        "catalog": _bundle_graph_catalog(nodes, edges),
        "indexes": _bundle_graph_indexes(nodes, edges),
        "nodes": nodes,
        "edges": edges,
    }


def build_path_report(
    bundle: Path,
    *,
    source: ImpactRoot,
    target: ImpactRoot,
    direction: str = "either",
) -> dict[str, Any]:
    """Build an explainable shortest-path report between two graph roots."""

    graph, pattern = _build_graph(bundle)
    source_ids = _roots_from_selectors(graph, [source])
    target_ids = _roots_from_selectors(graph, [target])
    source_id = source_ids[0] if source_ids else None
    target_id = target_ids[0] if target_ids else None
    status = "matched"
    steps: list[_PathStep] = []
    if source_id is None or target_id is None:
        status = "no-match"
    elif source_id == target_id:
        status = "same-root"
    else:
        steps = graph.shortest_steps(source_id, target_id, direction)
        if not steps:
            status = "no-path"

    unmatched = []
    if source_id is None:
        unmatched.append({"role": "source", "kind": source.kind, "key": source.key})
    if target_id is None:
        unmatched.append({"role": "target", "kind": target.kind, "key": target.key})

    return {
        "schemaVersion": "intent-engine/graph-path/v1",
        "bundle": str(bundle),
        "pattern": pattern,
        "boundary": BOUNDARY,
        "summary": {
            "status": status,
            "direction": direction,
            "hopCount": len(steps),
        },
        "source": _node_or_selector(graph, source_id, source),
        "target": _node_or_selector(graph, target_id, target),
        "unmatchedRoots": unmatched,
        "path": [_path_step_to_dict(graph, step) for step in steps],
        "reviewFocus": _path_review_focus(
            status=status,
            source_id=source_id,
            target_id=target_id,
            direction=direction,
            steps=steps,
        ),
        "graph": {
            "nodeCount": len(graph.nodes),
            "edgeCount": len(graph.edges),
        },
    }


def build_neighborhood_report(
    bundle: Path,
    *,
    root: ImpactRoot,
    depth: int = 1,
    direction: str = "either",
    kinds: list[str] | None = None,
) -> dict[str, Any]:
    """Build a bounded neighborhood report around one typed graph root."""

    graph, pattern = _build_graph(bundle)
    root_ids = _roots_from_selectors(graph, [root])
    root_id = root_ids[0] if root_ids else None
    kind_filter = sorted({item for item in kinds or [] if item})
    node_depths: dict[str, int] = {}
    steps: list[_PathStep] = []
    if root_id is not None:
        node_depths, steps = graph.neighborhood(root_id, depth, direction)
    status = "matched" if root_id is not None else "no-match"
    neighbor_nodes = [
        graph.nodes[node_id]
        for node_id, node_depth in node_depths.items()
        if node_id != root_id
        and node_id in graph.nodes
        and (not kind_filter or graph.nodes[node_id].kind in kind_filter)
        and node_depth <= depth
    ]
    neighbor_ids = {node.id for node in neighbor_nodes}
    visible_ids = neighbor_ids | {root_id or ""}
    filtered_steps = (
        [step for step in steps if step.source in visible_ids or step.target in visible_ids]
        if kind_filter
        else steps
    )

    return {
        "schemaVersion": "intent-engine/graph-neighborhood/v1",
        "bundle": str(bundle),
        "pattern": pattern,
        "boundary": BOUNDARY,
        "summary": {
            "status": status,
            "direction": direction,
            "depth": depth,
            "neighborCount": len(neighbor_nodes),
            "edgeCount": len(filtered_steps),
            "kindFilter": kind_filter,
            "nodeKinds": _count_by([node.to_dict() for node in neighbor_nodes], "kind"),
        },
        "root": _node_or_selector(graph, root_id, root),
        "unmatchedRoots": []
        if root_id is not None
        else [{"role": "root", "kind": root.kind, "key": root.key}],
        "neighbors": [
            {
                "depth": node_depths[node.id],
                **node.to_dict(),
            }
            for node in sorted(neighbor_nodes, key=lambda item: (node_depths[item.id], item.id))
        ],
        "edges": [_path_step_to_dict(graph, step) for step in filtered_steps],
        "reviewFocus": _neighborhood_review_focus(
            status=status,
            root_id=root_id,
            depth=depth,
            direction=direction,
            neighbor_count=len(neighbor_nodes),
            kind_filter=kind_filter,
        ),
        "graph": {
            "nodeCount": len(graph.nodes),
            "edgeCount": len(graph.edges),
        },
    }


def build_find_report(
    bundle: Path,
    *,
    query: str,
    kinds: list[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Find typed graph nodes by id, key, label, kind, or properties."""

    graph, pattern = _build_graph(bundle)
    kind_filter = sorted({item for item in kinds or [] if item})
    query_tokens = _query_tokens(query)
    candidates = [
        node for node in graph.nodes.values() if not kind_filter or node.kind in kind_filter
    ]
    matches: list[dict[str, Any]] = []
    for node in candidates:
        match = _find_match(node, query_tokens)
        if match is not None:
            matches.append(match)
    matches = sorted(
        [match for match in matches if match is not None],
        key=lambda item: (-int(item["score"]), str(_dict(item.get("node")).get("id", ""))),
    )
    limited_matches = matches[: max(limit, 0)]
    status = "matched" if limited_matches else "no-match"
    return {
        "schemaVersion": "intent-engine/graph-find/v1",
        "bundle": str(bundle),
        "pattern": pattern,
        "boundary": BOUNDARY,
        "summary": {
            "status": status,
            "query": query,
            "kindFilter": kind_filter,
            "matchCount": len(matches),
            "returnedCount": len(limited_matches),
            "limit": max(limit, 0),
            "nodeKinds": _count_by([_dict(match.get("node")) for match in limited_matches], "kind"),
        },
        "matches": limited_matches,
        "reviewFocus": _find_review_focus(
            status=status,
            query=query,
            returned_count=len(limited_matches),
            kind_filter=kind_filter,
        ),
        "graph": {
            "nodeCount": len(graph.nodes),
            "edgeCount": len(graph.edges),
        },
    }


def build_roots_report(
    bundle: Path,
    *,
    kinds: list[str] | None = None,
) -> dict[str, Any]:
    """Build an inventory of concrete graph roots available for traversal."""

    graph, pattern = _build_graph(bundle)
    kind_filter = sorted({item for item in kinds or [] if item})
    root_kinds = set(_root_kinds())
    nodes = [
        node
        for node in sorted(graph.nodes.values(), key=lambda item: item.id)
        if node.kind in root_kinds and (not kind_filter or node.kind in kind_filter)
    ]
    roots = [_root_entry(node) for node in nodes]
    recommendations = _recommended_review_roots(nodes)
    status = "matched" if roots else "no-match"
    return {
        "schemaVersion": "intent-engine/graph-roots/v1",
        "bundle": str(bundle),
        "pattern": pattern,
        "boundary": BOUNDARY,
        "summary": {
            "status": status,
            "rootCount": len(roots),
            "recommendedReviewRootCount": len(recommendations),
            "kindFilter": kind_filter,
            "nodeKinds": _count_by([entry["node"] for entry in roots], "kind"),
        },
        "rootsByKind": _roots_by_kind(roots),
        "recommendedReviewRoots": recommendations,
        "roots": roots,
        "reviewFocus": _roots_review_focus(
            status=status,
            root_count=len(roots),
            recommendation_count=len(recommendations),
            kind_filter=kind_filter,
        ),
        "graph": {
            "nodeCount": len(graph.nodes),
            "edgeCount": len(graph.edges),
        },
    }


def build_impact_matrix_report(
    bundle: Path,
    *,
    roots: list[ImpactRoot],
    root_reasons: dict[str, str] | None = None,
    root_source: str = "explicit",
) -> dict[str, Any]:
    """Build a compact multi-root impact matrix for reviewer triage."""

    reasons = root_reasons or {}
    roots = _dedupe_roots(roots)
    rows = [
        _impact_matrix_row(
            build_impact_report(bundle, roots=[root]),
            recommendation_reason=reasons.get(f"{root.kind}:{root.key}", ""),
        )
        for root in roots
    ]
    severity_counts = _matrix_severity_counts(rows)
    matched_rows = [row for row in rows if _dict(row.get("summary")).get("status") == "matched"]
    affected_artifacts = _matrix_union(rows, "affectedArtifacts")
    affected_contracts = _matrix_union(rows, "affectedTargetContracts")
    affected_capabilities = _matrix_union(rows, "affectedTargetCapabilities")
    affected_samples = _matrix_union(rows, "affectedSamples")
    affected_controls = _matrix_union(rows, "affectedPolicyControls")
    affected_checks = _matrix_union(rows, "affectedChecks")
    affected_gates = _matrix_union(rows, "manualGates")
    upstream_source_changes = _matrix_union(rows, "upstreamSourceChanges")
    upstream_input_diffs = _matrix_union(rows, "upstreamInputDiffs")
    graph_summary = _dict(_dict(rows[0].get("graph")) if rows else {})
    return {
        "schemaVersion": "intent-engine/graph-impact-matrix/v1",
        "bundle": str(bundle),
        "pattern": str(rows[0].get("pattern") or "") if rows else "",
        "boundary": BOUNDARY,
        "summary": {
            "status": "matched" if matched_rows else "no-match",
            "rootSource": root_source,
            "rootCount": len(rows),
            "matchedRootCount": len(matched_rows),
            "highestReviewPrioritySeverity": _highest_priority_severity(severity_counts),
            "reviewPrioritySeverityCounts": severity_counts,
            "affectedArtifactCount": len(affected_artifacts),
            "affectedTargetContractCount": len(affected_contracts),
            "affectedTargetCapabilityCount": len(affected_capabilities),
            "affectedSampleCount": len(affected_samples),
            "affectedPolicyControlCount": len(affected_controls),
            "affectedCheckCount": len(affected_checks),
            "manualGateCount": len(affected_gates),
            "upstreamSourceChangeCount": len(upstream_source_changes),
            "upstreamInputDiffCount": len(upstream_input_diffs),
        },
        "affectedArtifacts": affected_artifacts,
        "affectedTargetContracts": affected_contracts,
        "affectedTargetCapabilities": affected_capabilities,
        "affectedSamples": affected_samples,
        "affectedPolicyControls": affected_controls,
        "affectedChecks": affected_checks,
        "manualGates": affected_gates,
        "upstreamSourceChanges": upstream_source_changes,
        "upstreamInputDiffs": upstream_input_diffs,
        "rows": rows,
        "reviewFocus": _matrix_review_focus(rows),
        "graph": graph_summary,
    }


def build_recommended_impact_matrix_report(
    bundle: Path,
    *,
    kinds: list[str] | None = None,
    extra_roots: list[ImpactRoot] | None = None,
) -> dict[str, Any]:
    """Build an impact matrix from the bundle's recommended review roots."""

    roots_report = build_roots_report(bundle, kinds=kinds)
    recommended = _coerce_list(roots_report.get("recommendedReviewRoots"))
    roots: list[ImpactRoot] = []
    reasons: dict[str, str] = {}
    for item in recommended:
        if not isinstance(item, dict):
            continue
        root = _impact_root_from_value(str(item.get("root") or ""))
        if root is None:
            continue
        roots.append(root)
        reasons[f"{root.kind}:{root.key}"] = str(item.get("reason") or "")
    roots.extend(extra_roots or [])
    deduped_roots = _dedupe_roots(roots)
    report = build_impact_matrix_report(
        bundle,
        roots=deduped_roots,
        root_reasons=reasons,
        root_source="recommended" if not extra_roots else "recommended-plus-explicit",
    )
    report["recommendedReviewRoots"] = recommended
    report["summary"]["recommendedRootCount"] = len(recommended)
    if not recommended and not extra_roots:
        report["reviewFocus"] = [
            "No recommended review roots were found; use graph roots or graph find "
            "to select explicit roots."
        ]
    return report


def changed_report_roots(bundle: Path, changed_report: Path | None) -> list[ImpactRoot]:
    """Return typed decision roots derived from an input-diff report."""

    graph, _pattern = _build_graph(bundle)
    root_ids = _roots_from_changed_report(graph, changed_report)
    roots = [
        ImpactRoot(kind=graph.nodes[node_id].kind, key=graph.nodes[node_id].key)
        for node_id in root_ids
        if node_id in graph.nodes
    ]
    return _dedupe_roots(roots)


def changed_graph_diff_roots(
    graph_diff_report: dict[str, Any],
    *,
    kinds: list[str] | None = None,
) -> list[ImpactRoot]:
    """Return root-selectable nodes that changed or were added in a graph diff."""

    return [root for root, _reason in _changed_graph_diff_root_entries(graph_diff_report, kinds)]


def changed_graph_diff_root_reasons(
    graph_diff_report: dict[str, Any],
    *,
    kinds: list[str] | None = None,
) -> dict[str, str]:
    """Return reason text for root-selectable graph-diff nodes."""

    return {
        f"{root.kind}:{root.key}": reason
        for root, reason in _changed_graph_diff_root_entries(graph_diff_report, kinds)
    }


def _changed_graph_diff_root_entries(
    graph_diff_report: dict[str, Any],
    kinds: list[str] | None,
) -> list[tuple[ImpactRoot, str]]:
    root_kinds = set(_root_kinds())
    kind_filter = {item for item in kinds or [] if item}
    roots: list[tuple[ImpactRoot, str]] = []
    for section in ("changedNodes", "addedNodes"):
        for item in _coerce_list(graph_diff_report.get(section)):
            node = _dict(item.get("after")) if section == "changedNodes" else _dict(item)
            kind = str(node.get("kind") or "")
            key = str(node.get("key") or "")
            if not kind or not key or kind not in root_kinds:
                continue
            if kind_filter and kind not in kind_filter:
                continue
            root = ImpactRoot(kind=kind, key=key)
            roots.append((root, _graph_diff_root_reason(section, item)))
    deduped: list[tuple[ImpactRoot, str]] = []
    seen: set[tuple[str, str]] = set()
    for root, reason in roots:
        root_key = (root.kind, root.key)
        if root_key in seen:
            continue
        seen.add(root_key)
        deduped.append((root, reason))
    return deduped


def _graph_diff_root_reason(section: str, item: Any) -> str:
    if section == "addedNodes":
        return "Graph node was added between compared bundles."
    changed_fields = ", ".join(
        str(field) for field in _coerce_list(_dict(item).get("changedFields"))
    )
    suffix = f": {changed_fields}" if changed_fields else ""
    return f"Graph node changed between compared bundles{suffix}."


def build_graph_diff_report(before: Path, after: Path) -> dict[str, Any]:
    """Compare two generated bundle graphs as typed nodes and edges."""

    before_graph, before_pattern = _build_graph(before)
    after_graph, after_pattern = _build_graph(after)
    before_nodes = before_graph.nodes
    after_nodes = after_graph.nodes
    before_node_ids = set(before_nodes)
    after_node_ids = set(after_nodes)
    added_node_ids = after_node_ids - before_node_ids
    removed_node_ids = before_node_ids - after_node_ids
    shared_node_ids = before_node_ids & after_node_ids
    changed_nodes = [
        _node_change(before_nodes[node_id], after_nodes[node_id])
        for node_id in sorted(shared_node_ids)
        if before_nodes[node_id].to_dict() != after_nodes[node_id].to_dict()
    ]

    before_edges = {_edge_key(edge): edge for edge in before_graph.edges}
    after_edges = {_edge_key(edge): edge for edge in after_graph.edges}
    before_edge_keys = set(before_edges)
    after_edge_keys = set(after_edges)
    added_edges = [after_edges[key].to_dict() for key in sorted(after_edge_keys - before_edge_keys)]
    removed_edges = [
        before_edges[key].to_dict() for key in sorted(before_edge_keys - after_edge_keys)
    ]
    status = (
        "changed"
        if added_node_ids or removed_node_ids or changed_nodes or added_edges or removed_edges
        else "unchanged"
    )
    return {
        "schemaVersion": "intent-engine/graph-diff/v1",
        "before": str(before),
        "after": str(after),
        "patternBefore": before_pattern,
        "patternAfter": after_pattern,
        "boundary": BOUNDARY,
        "summary": {
            "status": status,
            "nodeAddedCount": len(added_node_ids),
            "nodeRemovedCount": len(removed_node_ids),
            "nodeChangedCount": len(changed_nodes),
            "edgeAddedCount": len(added_edges),
            "edgeRemovedCount": len(removed_edges),
            "nodeKindsAdded": _count_by(
                [after_nodes[node_id].to_dict() for node_id in added_node_ids], "kind"
            ),
            "nodeKindsRemoved": _count_by(
                [before_nodes[node_id].to_dict() for node_id in removed_node_ids], "kind"
            ),
        },
        "addedNodes": [after_nodes[node_id].to_dict() for node_id in sorted(added_node_ids)],
        "removedNodes": [before_nodes[node_id].to_dict() for node_id in sorted(removed_node_ids)],
        "changedNodes": changed_nodes,
        "addedEdges": added_edges,
        "removedEdges": removed_edges,
        "reviewFocus": _graph_diff_review_focus(
            status=status,
            changed_nodes=changed_nodes,
            added_edges=added_edges,
            removed_edges=removed_edges,
        ),
        "graph": {
            "beforeNodeCount": len(before_graph.nodes),
            "afterNodeCount": len(after_graph.nodes),
            "beforeEdgeCount": len(before_graph.edges),
            "afterEdgeCount": len(after_graph.edges),
        },
    }


def write_bundle_graph_report(report: dict[str, Any], output: Path) -> None:
    write_yaml_artifact(output, report, "")


def write_graph_diff_report(report: dict[str, Any], output: Path) -> None:
    write_yaml_artifact(output, report, "")


def write_find_report(report: dict[str, Any], output: Path) -> None:
    write_yaml_artifact(output, report, "")


def write_neighborhood_report(report: dict[str, Any], output: Path) -> None:
    write_yaml_artifact(output, report, "")


def write_path_report(report: dict[str, Any], output: Path) -> None:
    write_yaml_artifact(output, report, "")


def write_roots_report(report: dict[str, Any], output: Path) -> None:
    write_yaml_artifact(output, report, "")


def write_impact_matrix_report(report: dict[str, Any], output: Path) -> None:
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


def render_roots_report_text(report: dict[str, Any]) -> str:
    summary = _dict(report.get("summary"))
    lines = [
        "=== Graph Roots ===",
        "",
        f"Status: {summary.get('status', 'unknown')}",
        f"Pattern: {report.get('pattern', '')}",
        f"Bundle: {report.get('bundle', '')}",
        f"Roots: {summary.get('rootCount', 0)}",
        f"Recommended review roots: {summary.get('recommendedReviewRootCount', 0)}",
        "",
        "Root kinds:",
    ]
    for key, count in sorted(_dict(summary.get("nodeKinds")).items()):
        lines.append(f"  - {key}: {count}")
    lines.append("Recommended review roots:")
    recommendations = _coerce_list(report.get("recommendedReviewRoots"))
    if recommendations:
        for item in recommendations[:12]:
            if not isinstance(item, dict):
                continue
            node = _dict(item.get("node"))
            lines.append(f"  - {_node_label(node)}: {item.get('reason', '')}")
        if len(recommendations) > 12:
            lines.append(f"  ... {len(recommendations) - 12} more")
    else:
        lines.append("  - None")
    lines.append("Review focus:")
    lines.extend(_list_or_none(_coerce_list(report.get("reviewFocus"))))
    return "\n".join(lines) + "\n"


def render_find_report_text(report: dict[str, Any]) -> str:
    summary = _dict(report.get("summary"))
    lines = [
        "=== Graph Find ===",
        "",
        f"Status: {summary.get('status', 'unknown')}",
        f"Query: {summary.get('query', '')}",
        f"Pattern: {report.get('pattern', '')}",
        f"Bundle: {report.get('bundle', '')}",
        "",
        f"Matches: {summary.get('returnedCount', 0)} of {summary.get('matchCount', 0)}",
        "Node kinds:",
    ]
    for key, count in sorted(_dict(summary.get("nodeKinds")).items()):
        lines.append(f"  - {key}: {count}")
    lines.append("Results:")
    matches = _coerce_list(report.get("matches"))
    if matches:
        for match in matches:
            if not isinstance(match, dict):
                continue
            node = _dict(match.get("node"))
            fields = ", ".join(str(item) for item in _coerce_list(match.get("matchedFields")))
            root = _dict(match.get("root"))
            suffix = f" root={root.get('root', '')}" if root else ""
            lines.append(f"  - {_node_label(node)} [{fields}]{suffix}")
    else:
        lines.append("  - None")
    lines.append("Review focus:")
    lines.extend(_list_or_none(_coerce_list(report.get("reviewFocus"))))
    return "\n".join(lines) + "\n"


def render_graph_diff_text(report: dict[str, Any]) -> str:
    summary = _dict(report.get("summary"))
    lines = [
        "=== Graph Diff ===",
        "",
        f"Status: {summary.get('status', 'unknown')}",
        f"Before: {report.get('before', '')}",
        f"After:  {report.get('after', '')}",
        f"Pattern: {report.get('patternBefore', '')} -> {report.get('patternAfter', '')}",
        "",
        "Counts:",
        f"  nodes added={summary.get('nodeAddedCount', 0)} "
        f"removed={summary.get('nodeRemovedCount', 0)} "
        f"changed={summary.get('nodeChangedCount', 0)}",
        f"  edges added={summary.get('edgeAddedCount', 0)} "
        f"removed={summary.get('edgeRemovedCount', 0)}",
        "",
        "Changed nodes:",
    ]
    changed_nodes = _coerce_list(report.get("changedNodes"))
    if changed_nodes:
        for item in changed_nodes[:12]:
            if isinstance(item, dict):
                after = _dict(item.get("after"))
                lines.append(f"  - {_node_label(after)}")
        if len(changed_nodes) > 12:
            lines.append(f"  ... {len(changed_nodes) - 12} more")
    else:
        lines.append("  - None")
    lines.append("Added nodes:")
    lines.extend(_node_list_lines(_coerce_list(report.get("addedNodes"))))
    lines.append("Removed nodes:")
    lines.extend(_node_list_lines(_coerce_list(report.get("removedNodes"))))
    lines.append("Review focus:")
    lines.extend(_list_or_none(_coerce_list(report.get("reviewFocus"))))
    return "\n".join(lines) + "\n"


def render_impact_matrix_text(report: dict[str, Any]) -> str:
    summary = _dict(report.get("summary"))
    lines = [
        "=== Graph Impact Matrix ===",
        "",
        f"Status: {summary.get('status', 'unknown')}",
        f"Pattern: {report.get('pattern', '')}",
        f"Bundle: {report.get('bundle', '')}",
        f"Root source: {summary.get('rootSource', 'explicit')}",
        f"Roots: {summary.get('matchedRootCount', 0)} of {summary.get('rootCount', 0)} matched",
        f"Review severity: {_priority_severity_summary(summary)}",
        "",
        "Rows:",
    ]
    rows = _coerce_list(report.get("rows"))
    if rows:
        for row in rows:
            if not isinstance(row, dict):
                continue
            summary_block = _dict(row.get("summary"))
            lines.append(
                f"  - {_node_label(_dict(row.get('root')))}: "
                f"{summary_block.get('status', 'unknown')} "
                f"severity={summary_block.get('highestReviewPrioritySeverity', 'none')} "
                f"artifacts={summary_block.get('affectedArtifactCount', 0)} "
                f"contracts={summary_block.get('affectedTargetContractCount', 0)} "
                f"capabilities={summary_block.get('affectedTargetCapabilityCount', 0)} "
                f"samples={summary_block.get('affectedSampleCount', 0)} "
                f"controls={summary_block.get('affectedPolicyControlCount', 0)} "
                f"checks={summary_block.get('affectedCheckCount', 0)} "
                f"gates={summary_block.get('manualGateCount', 0)} "
                f"sourceChanges={summary_block.get('upstreamSourceChangeCount', 0)}"
            )
            reason = str(row.get("recommendationReason") or "")
            if reason:
                lines.append(f"    reason: {reason}")
    else:
        lines.append("  - None")
    lines.append("Affected artifacts:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedArtifacts"))))
    lines.append("Affected target contracts:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedTargetContracts"))))
    lines.append("Affected target capabilities:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedTargetCapabilities"))))
    lines.append("Affected samples:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedSamples"))))
    lines.append("Affected policy controls:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedPolicyControls"))))
    lines.append("Affected checks:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedChecks"))))
    lines.append("Manual gates:")
    lines.extend(_list_or_none(_coerce_list(report.get("manualGates"))))
    lines.append("Upstream source changes:")
    lines.extend(_list_or_none(_coerce_list(report.get("upstreamSourceChanges"))))
    lines.append("Upstream input diffs:")
    lines.extend(_list_or_none(_coerce_list(report.get("upstreamInputDiffs"))))
    lines.append("Review focus:")
    lines.extend(_list_or_none(_coerce_list(report.get("reviewFocus"))))
    return "\n".join(lines) + "\n"


def render_neighborhood_report_text(report: dict[str, Any]) -> str:
    summary = _dict(report.get("summary"))
    lines = [
        "=== Graph Neighborhood ===",
        "",
        f"Status: {summary.get('status', 'unknown')}",
        f"Direction: {summary.get('direction', 'either')}",
        f"Depth: {summary.get('depth', 0)}",
        f"Pattern: {report.get('pattern', '')}",
        f"Bundle: {report.get('bundle', '')}",
        "",
        f"Root: {_node_label(_dict(report.get('root')))}",
    ]
    unmatched = _coerce_list(report.get("unmatchedRoots"))
    if unmatched:
        lines.append("")
        lines.append("Unmatched roots:")
        lines.extend(
            f"  - {item.get('role', 'root')}:{item.get('kind', 'unknown')}:{item.get('key', '')}"
            for item in unmatched
            if isinstance(item, dict)
        )
    lines.extend(["", f"Neighbors: {summary.get('neighborCount', 0)}", "Node kinds:"])
    for key, count in sorted(_dict(summary.get("nodeKinds")).items()):
        lines.append(f"  - {key}: {count}")
    lines.append("Neighborhood:")
    neighbors = _coerce_list(report.get("neighbors"))
    if neighbors:
        for node in neighbors[:12]:
            if isinstance(node, dict):
                lines.append(f"  - depth {node.get('depth', '?')}: {_node_label(node)}")
        if len(neighbors) > 12:
            lines.append(f"  ... {len(neighbors) - 12} more")
    else:
        lines.append("  - None")
    lines.append("Edges:")
    edges = _coerce_list(report.get("edges"))
    if edges:
        for edge in edges[:12]:
            if not isinstance(edge, dict):
                continue
            source = _dict(edge.get("from"))
            target = _dict(edge.get("to"))
            lines.append(
                f"  - {_node_label(source)} --{edge.get('relationship', '')} "
                f"({edge.get('direction', '')})--> {_node_label(target)}"
            )
        if len(edges) > 12:
            lines.append(f"  ... {len(edges) - 12} more")
    else:
        lines.append("  - None")
    lines.append("Review focus:")
    lines.extend(_list_or_none(_coerce_list(report.get("reviewFocus"))))
    return "\n".join(lines) + "\n"


def render_path_report_text(report: dict[str, Any]) -> str:
    summary = _dict(report.get("summary"))
    lines = [
        "=== Graph Path ===",
        "",
        f"Status: {summary.get('status', 'unknown')}",
        f"Direction: {summary.get('direction', 'either')}",
        f"Pattern: {report.get('pattern', '')}",
        f"Bundle: {report.get('bundle', '')}",
        "",
        f"Source: {_node_label(_dict(report.get('source')))}",
        f"Target: {_node_label(_dict(report.get('target')))}",
    ]
    unmatched = _coerce_list(report.get("unmatchedRoots"))
    if unmatched:
        lines.append("")
        lines.append("Unmatched roots:")
        lines.extend(
            f"  - {item.get('role', 'root')}:{item.get('kind', 'unknown')}:{item.get('key', '')}"
            for item in unmatched
            if isinstance(item, dict)
        )
    lines.extend(["", f"Hops: {summary.get('hopCount', 0)}", "Path:"])
    path_lines = []
    for step in _coerce_list(report.get("path")):
        if not isinstance(step, dict):
            continue
        source = _dict(step.get("from"))
        target = _dict(step.get("to"))
        path_lines.append(
            f"  - {_node_label(source)} --{step.get('relationship', '')} "
            f"({step.get('direction', '')})--> {_node_label(target)}"
        )
    lines.extend(path_lines or ["  - None"])
    lines.append("Review focus:")
    lines.extend(_list_or_none(_coerce_list(report.get("reviewFocus"))))
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
            f"Review severity: {_priority_severity_summary(summary)}",
            "",
            "Review priorities:",
        ]
    )
    priorities = _coerce_list(report.get("reviewPriorities"))
    if priorities:
        for item in priorities[:12]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"  - {item.get('severity', 'review')}: "
                f"{item.get('category', 'unknown')} "
                f"({item.get('count', 0)}) - {item.get('reason', '')}"
            )
        if len(priorities) > 12:
            lines.append(f"  ... {len(priorities) - 12} more")
    else:
        lines.append("  - None")
    lines.extend(["", "Review checklist:"])
    checklist = _coerce_list(report.get("reviewChecklist"))
    if checklist:
        for item in checklist[:12]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"  - {item.get('step', '?')}. {item.get('severity', 'review')}: "
                f"{item.get('category', 'unknown')} - {item.get('action', '')}"
            )
        if len(checklist) > 12:
            lines.append(f"  ... {len(checklist) - 12} more")
    else:
        lines.append("  - None")
    lines.extend(
        [
            "",
            "Affected artifacts:",
        ]
    )
    lines.extend(_list_or_none(_coerce_list(report.get("affectedArtifacts"))))
    lines.append("Affected target contracts:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedTargetContracts"))))
    lines.append("Affected target capabilities:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedTargetCapabilities"))))
    lines.append("Affected samples:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedSamples"))))
    lines.append("Affected policy controls:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedPolicyControls"))))
    lines.append("Affected checks:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedChecks"))))
    lines.append("Affected Checkov findings:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedCheckovFindings"))))
    lines.append("Affected shift-left evidence:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedShiftLeftEvidence"))))
    lines.append("Affected module variables:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedModuleVariables"))))
    lines.append("Affected semantic entities:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedSemanticEntities"))))
    lines.append("Affected semantic constraints:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedSemanticConstraints"))))
    lines.append("Affected source contexts:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedSourceContexts"))))
    lines.append("Affected input diffs:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedInputDiffs"))))
    lines.append("Affected source changes:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedSourceChanges"))))
    lines.append("Affected readiness:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedReadiness"))))
    lines.append("Affected readiness blockers:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedReadinessBlockers"))))
    lines.append("Affected contract validation:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedContractValidation"))))
    lines.append("Affected contract results:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedContractResults"))))
    lines.append("Affected validation violations:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedValidationViolations"))))
    lines.append("Affected downstream validation evidence:")
    lines.extend(_list_or_none(_coerce_list(report.get("affectedDownstreamValidationEvidence"))))
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
    replay_manifest = read_yaml_mapping(bundle / "replay-manifest.yaml")
    input_diff = read_yaml_mapping(bundle / "input-diff-report.yaml")
    module_inputs = read_yaml_mapping(bundle / "module-inputs.yaml")
    policy_graph = read_yaml_mapping(bundle / "policy-graph.yaml")
    shift_left_evidence = read_yaml_mapping(bundle / "shift-left-evidence.yaml")
    contract_validation = read_yaml_mapping(bundle / "contract-validation.yaml")
    downstream_validation = read_yaml_mapping(bundle / "lza-validation-evidence.yaml")
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

    _add_semantic_model_nodes(graph, _dict(report.get("semanticModel")))
    _add_module_nodes(graph, module_inputs)
    _add_policy_nodes(graph, policy_graph)
    _add_shift_left_evidence_nodes(graph, shift_left_evidence)
    _add_source_nodes(
        graph, manifest=manifest, replay_manifest=replay_manifest, input_diff=input_diff
    )
    _add_handoff_nodes(graph, handoff)
    _add_target_capability_nodes(graph, target_capability)
    _add_sample_nodes(graph, samples)
    _add_readiness_and_validation_nodes(
        graph,
        report=report,
        handoff=handoff,
        contract_validation=contract_validation,
        downstream_validation=downstream_validation,
    )
    _add_artifact_digest_properties(
        graph,
        bundle=bundle,
        replay_manifest=replay_manifest,
        downstream_validation=downstream_validation,
    )
    return graph, pattern


def _add_semantic_model_nodes(graph: _ImpactGraph, semantic_model: dict[str, Any]) -> None:
    entities = {
        str(entity.get("key")): entity
        for entity in _coerce_list(semantic_model.get("entities"))
        if isinstance(entity, dict) and entity.get("key")
    }
    for key, entity in entities.items():
        entity_id = _add_semantic_entity_node(graph, entity)
        if str(entity.get("kind")) == "Artifact" and key.startswith("artifact:"):
            artifact_name = key.split(":", 1)[1]
            artifact_id = graph.add_node("artifact", artifact_name, artifact_name)
            graph.add_edge(entity_id, artifact_id, "describes-artifact")

    for relationship in _coerce_list(semantic_model.get("relationships")):
        if not isinstance(relationship, dict):
            continue
        source = str(relationship.get("source") or "")
        target = str(relationship.get("target") or "")
        if not source or not target:
            continue
        source_id = _ensure_semantic_entity_node(graph, entities, source)
        target_id = _ensure_semantic_entity_node(graph, entities, target)
        graph.add_edge(
            source_id,
            target_id,
            f"semantic:{relationship.get('relationship') or 'related-to'}",
        )

    for constraint in _coerce_list(semantic_model.get("constraints")):
        if not isinstance(constraint, dict):
            continue
        key = str(constraint.get("key") or "")
        if not key:
            continue
        constraint_id = graph.add_node(
            "semantic_constraint",
            key,
            str(constraint.get("label") or key),
            status=constraint.get("status"),
            violationCode=constraint.get("violationCode"),
            violationMessage=constraint.get("violationMessage"),
            evidence=constraint.get("evidence"),
        )
        expression = _dict(constraint.get("expression"))
        for decision in _semantic_expression_decisions(expression):
            decision_id = graph.add_node("decision", decision, decision)
            graph.add_edge(decision_id, constraint_id, "checked-by-constraint")
        for entity_key in _semantic_expression_entities(expression, entities):
            entity_id = _ensure_semantic_entity_node(graph, entities, entity_key)
            graph.add_edge(constraint_id, entity_id, "checks-entity")


def _add_semantic_entity_node(graph: _ImpactGraph, entity: dict[str, Any]) -> str:
    key = str(entity.get("key") or "")
    return graph.add_node(
        "semantic_entity",
        key,
        str(entity.get("label") or key),
        semanticKind=entity.get("kind"),
        entityProperties=_dict(entity.get("properties")),
    )


def _ensure_semantic_entity_node(
    graph: _ImpactGraph,
    entities: dict[str, dict[str, Any]],
    key: str,
) -> str:
    entity = entities.get(key)
    if entity is not None:
        return _add_semantic_entity_node(graph, entity)
    return graph.add_node("semantic_entity", key, key)


def _semantic_expression_decisions(expression: Any) -> list[str]:
    decisions: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            decision = value.get("decision")
            if decision:
                decisions.add(str(decision))
            source = value.get("source")
            if source:
                decisions.add(str(source))
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(expression)
    return sorted(decisions)


def _semantic_expression_entities(
    expression: Any,
    entities: dict[str, dict[str, Any]],
) -> list[str]:
    matches: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            required = value.get("requires_entity")
            if isinstance(required, dict):
                entity_key = _find_semantic_entity_key(
                    entities,
                    kind=str(required.get("kind") or ""),
                    name=str(required.get("name") or ""),
                )
                if entity_key:
                    matches.add(entity_key)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(expression)
    return sorted(matches)


def _find_semantic_entity_key(
    entities: dict[str, dict[str, Any]],
    *,
    kind: str,
    name: str,
) -> str | None:
    if not kind or not name:
        return None
    normalized_name = name.casefold()
    for key, entity in entities.items():
        if str(entity.get("kind", "")).casefold() != kind.casefold():
            continue
        label = str(entity.get("label", ""))
        if label.casefold() == normalized_name:
            return key
        if key.rsplit(":", 1)[-1].casefold() == normalized_name:
            return key
    return None


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


def _add_shift_left_evidence_nodes(
    graph: _ImpactGraph,
    shift_left_evidence: dict[str, Any],
) -> None:
    if not shift_left_evidence:
        return
    result = _dict(shift_left_evidence.get("result"))
    summary = _dict(shift_left_evidence.get("summary"))
    input_block = _dict(shift_left_evidence.get("input"))
    evidence_id = graph.add_node(
        "shift_left_evidence",
        "shift-left-evidence.yaml",
        "shift-left-evidence.yaml",
        tool=_dict(shift_left_evidence.get("tool")).get("name"),
        status=result.get("status"),
        exitCode=result.get("exitCode"),
        scanPath=input_block.get("scanPath"),
        iacKind=input_block.get("iacKind"),
        failed=summary.get("failed"),
        passed=summary.get("passed"),
    )
    artifact_id = graph.add_node(
        "artifact",
        "shift-left-evidence.yaml",
        "shift-left-evidence.yaml",
    )
    graph.add_edge(evidence_id, artifact_id, "recorded-in")

    findings_by_key: dict[str, str] = {}
    for finding in _coerce_list(shift_left_evidence.get("findings")):
        if not isinstance(finding, dict):
            continue
        finding_key = _finding_key(finding)
        findings_by_key[finding_key] = _add_checkov_finding_node(graph, finding, finding_key)
        graph.add_edge(evidence_id, findings_by_key[finding_key], "records-finding")
        graph.add_edge(findings_by_key[finding_key], evidence_id, "recorded-by-evidence")
        check_id = str(finding.get("checkId") or "")
        if check_id:
            check_node = graph.add_node("checkov_check", check_id, check_id)
            graph.add_edge(findings_by_key[finding_key], check_node, "violates-check")
        file_path = str(finding.get("filePath") or "")
        if file_path:
            file_node = graph.add_node("scan_file", file_path, file_path)
            graph.add_edge(findings_by_key[finding_key], file_node, "found-in-file")

    for mapped in _coerce_list(shift_left_evidence.get("mappedControls")):
        if not isinstance(mapped, dict):
            continue
        finding_key = _finding_key(mapped)
        finding_id = findings_by_key.get(finding_key)
        if finding_id is None:
            finding_id = _add_checkov_finding_node(graph, mapped, finding_key)
            graph.add_edge(evidence_id, finding_id, "records-finding")
            graph.add_edge(finding_id, evidence_id, "recorded-by-evidence")
        control_id = str(mapped.get("controlId") or "")
        if control_id:
            control_node = graph.add_node(
                "policy_control",
                control_id,
                str(mapped.get("controlTitle") or control_id),
                frameworks=mapped.get("frameworks"),
            )
            graph.add_edge(finding_id, control_node, "maps-to-control")
            graph.add_edge(control_node, finding_id, "has-finding")
        check_id = str(mapped.get("checkId") or "")
        if check_id:
            check_node = graph.add_node("checkov_check", check_id, check_id)
            graph.add_edge(finding_id, check_node, "violates-check")

    for finding in _coerce_list(shift_left_evidence.get("unmappedFindings")):
        if not isinstance(finding, dict):
            continue
        finding_key = _finding_key(finding)
        finding_id = findings_by_key.get(finding_key)
        if finding_id is None:
            finding_id = _add_checkov_finding_node(graph, finding, finding_key)
            graph.add_edge(evidence_id, finding_id, "records-finding")
            graph.add_edge(finding_id, evidence_id, "recorded-by-evidence")
        graph.add_edge(finding_id, evidence_id, "unmapped-in-evidence")


def _add_source_nodes(
    graph: _ImpactGraph,
    *,
    manifest: dict[str, Any],
    replay_manifest: dict[str, Any],
    input_diff: dict[str, Any],
) -> None:
    source = _first_mapping(
        _dict(manifest.get("runtimeContext")).get("source"),
        replay_manifest.get("source"),
        _dict(input_diff.get("source")),
    )
    source_id = ""
    if source:
        source_key = str(source.get("sha256") or source.get("mode") or "source")
        source_id = graph.add_node(
            "source_context",
            source_key,
            "Source context",
            mode=source.get("mode"),
            sha256=source.get("sha256"),
            baselineDocumentAvailable=source.get("baselineDocumentAvailable"),
        )
        for artifact_name in ("context-manifest.yaml", "replay-manifest.yaml"):
            if artifact_name == "replay-manifest.yaml" and not replay_manifest:
                continue
            artifact_id = graph.add_node("artifact", artifact_name, artifact_name)
            graph.add_edge(source_id, artifact_id, "recorded-in")
        for node in list(graph.nodes.values()):
            if node.kind == "decision":
                graph.add_edge(source_id, node.id, "provides-decision-context")

    if not input_diff:
        return
    diff_source = _dict(input_diff.get("source"))
    diff_id = graph.add_node(
        "input_diff",
        "input-diff-report.yaml",
        "Input diff report",
        mode=diff_source.get("mode"),
        baselineDocumentAvailable=diff_source.get("baselineDocumentAvailable"),
        changedLineCount=input_diff.get("changedLineCount"),
    )
    artifact_id = graph.add_node("artifact", "input-diff-report.yaml", "input-diff-report.yaml")
    graph.add_edge(diff_id, artifact_id, "recorded-in")
    if source_id:
        graph.add_edge(source_id, diff_id, "has-input-diff")
    for item in _coerce_list(input_diff.get("changedStructuredDecisionLines")):
        if not isinstance(item, dict) or not item.get("key"):
            continue
        key = str(item["key"])
        change_id = graph.add_node(
            "source_change",
            f"structured:{key}",
            key,
            changeType="structured-decision-line",
            before=item.get("before"),
            after=item.get("after"),
        )
        decision_id = graph.add_node("decision", key, key)
        graph.add_edge(diff_id, change_id, "contains-source-change")
        graph.add_edge(change_id, decision_id, "changes-decision")
    for item in _coerce_list(input_diff.get("likelyImpactedRequirements")):
        if not isinstance(item, dict) or not item.get("key"):
            continue
        key = str(item["key"])
        change_id = graph.add_node(
            "source_change",
            f"likely-impacted:{key}",
            str(item.get("label") or key),
            changeType="likely-impacted-requirement",
            reason=item.get("reason"),
        )
        decision_id = graph.add_node("decision", key, key)
        graph.add_edge(diff_id, change_id, "contains-source-change")
        graph.add_edge(change_id, decision_id, "impacts-requirement")
    for index, heading in enumerate(_coerce_list(input_diff.get("changedHeadings"))):
        if not heading:
            continue
        change_id = graph.add_node(
            "source_change",
            f"heading:{index}",
            str(heading),
            changeType="changed-heading",
        )
        graph.add_edge(diff_id, change_id, "contains-source-change")


def _add_checkov_finding_node(
    graph: _ImpactGraph,
    finding: dict[str, Any],
    key: str,
) -> str:
    return graph.add_node(
        "checkov_finding",
        key,
        str(finding.get("checkName") or finding.get("checkId") or key),
        checkId=finding.get("checkId"),
        resource=finding.get("resource"),
        filePath=finding.get("filePath"),
        guideline=finding.get("guideline"),
        status=finding.get("status") or "fail",
    )


def _finding_key(finding: dict[str, Any]) -> str:
    check_id = str(finding.get("checkId") or "unknown-check")
    resource = str(finding.get("resource") or "unknown-resource")
    file_path = str(finding.get("filePath") or "")
    return "|".join([check_id, resource, file_path])


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
        for dependency in _coerce_list(capability.get("dependsOn")):
            dep_key = str(dependency)
            if not dep_key:
                continue
            dep_id = graph.add_node("target_capability", dep_key, dep_key)
            graph.add_edge(dep_id, cap_id, "precedes-capability")


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
        for decision_key in _sample_decision_keys(sample):
            decision_id = graph.add_node("decision", decision_key, decision_key)
            graph.add_edge(decision_id, sample_id, "influences-sample-match")


def _sample_decision_keys(sample: dict[str, Any]) -> list[str]:
    keys: set[str] = set()
    keys.update(str(item) for item in _coerce_list(sample.get("sameDecisions")) if item)
    for sample_field in ("differentDecisions", "missingDecisions", "extraCurrentDecisions"):
        keys.update(str(key) for key in _dict(sample.get(sample_field)) if key)
    return sorted(keys)


def _add_readiness_and_validation_nodes(
    graph: _ImpactGraph,
    *,
    report: dict[str, Any],
    handoff: dict[str, Any],
    contract_validation: dict[str, Any],
    downstream_validation: dict[str, Any],
) -> None:
    readiness = _first_mapping(
        report.get("handoffReadiness"),
        handoff.get("readiness"),
        contract_validation.get("readiness"),
    )
    readiness_id = ""
    if readiness:
        readiness_id = graph.add_node(
            "handoff_readiness",
            "handoffReadiness",
            "Handoff readiness",
            status=readiness.get("status"),
            handoffAllowed=_readiness_allowed(readiness),
            summary=readiness.get("summary"),
            blockerCount=_readiness_blocker_count(readiness),
        )
        for artifact_name in ("decision-report.yaml", "handoff-plan.yaml"):
            artifact_id = graph.add_node("artifact", artifact_name, artifact_name)
            graph.add_edge(readiness_id, artifact_id, "recorded-in")
        for node in list(graph.nodes.values()):
            if node.kind == "decision":
                graph.add_edge(node.id, readiness_id, "contributes-to-readiness")
        _add_readiness_blocker_nodes(graph, readiness_id, readiness)

    if contract_validation:
        validation_summary = _dict(contract_validation.get("summary"))
        validation_id = graph.add_node(
            "contract_validation",
            "contract-validation.yaml",
            "Contract validation",
            status=validation_summary.get("status"),
            contractCount=validation_summary.get("contractCount"),
            violationCount=validation_summary.get("violationCount"),
        )
        artifact_id = graph.add_node(
            "artifact",
            "contract-validation.yaml",
            "contract-validation.yaml",
        )
        graph.add_edge(validation_id, artifact_id, "recorded-in")
        if readiness_id:
            graph.add_edge(readiness_id, validation_id, "validated-by")
        for contract in _coerce_list(contract_validation.get("contracts")):
            if isinstance(contract, dict):
                _add_contract_result_node(graph, validation_id, contract)

    if downstream_validation:
        evidence_id = _add_downstream_validation_node(graph, downstream_validation)
        if readiness_id:
            graph.add_edge(readiness_id, evidence_id, "reviewed-with-validation-evidence")


def _add_readiness_blocker_nodes(
    graph: _ImpactGraph,
    readiness_id: str,
    readiness: dict[str, Any],
) -> None:
    for index, blocker in enumerate(_coerce_list(readiness.get("blockers"))):
        if not isinstance(blocker, dict):
            continue
        blocker_id = _add_readiness_blocker_node(graph, blocker, index)
        graph.add_edge(readiness_id, blocker_id, "has-blocker")
        graph.add_edge(blocker_id, readiness_id, "blocks-readiness")
    for item in _coerce_list(readiness.get("missingDecisions")):
        if not isinstance(item, dict) or not item.get("key"):
            continue
        key = str(item["key"])
        blocker_id = graph.add_node(
            "readiness_blocker",
            f"missing:{key}",
            str(item.get("label") or key),
            code="MISSING_DECISION",
            message=item.get("reason") or item.get("suggestion"),
            question=item.get("question"),
        )
        decision_id = graph.add_node("decision", key, key)
        graph.add_edge(decision_id, blocker_id, "missing-decision-blocks-readiness")
        graph.add_edge(readiness_id, blocker_id, "has-blocker")
        graph.add_edge(blocker_id, readiness_id, "blocks-readiness")
    for index, item in enumerate(_coerce_list(readiness.get("conflictingDecisions"))):
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or item.get("code") or f"conflict-{index}")
        blocker_id = graph.add_node(
            "readiness_blocker",
            f"conflict:{key}",
            str(item.get("code") or item.get("key") or key),
            code=item.get("code"),
            message=item.get("reason") or item.get("details"),
        )
        if item.get("key"):
            decision_id = graph.add_node("decision", str(item["key"]), str(item["key"]))
            graph.add_edge(decision_id, blocker_id, "conflict-blocks-readiness")
        graph.add_edge(readiness_id, blocker_id, "has-blocker")
        graph.add_edge(blocker_id, readiness_id, "blocks-readiness")


def _add_readiness_blocker_node(
    graph: _ImpactGraph,
    blocker: dict[str, Any],
    index: int,
) -> str:
    code = str(blocker.get("code") or f"blocker-{index}")
    key = f"{code}:{index}"
    return graph.add_node(
        "readiness_blocker",
        key,
        code,
        code=blocker.get("code"),
        message=blocker.get("message"),
    )


def _add_contract_result_node(
    graph: _ImpactGraph,
    validation_id: str,
    contract: dict[str, Any],
) -> None:
    name = str(contract.get("name") or "")
    if not name:
        return
    result_id = graph.add_node(
        "contract_result",
        name,
        name,
        contractKind=contract.get("kind"),
        status=contract.get("status"),
        violationCount=contract.get("violationCount"),
    )
    graph.add_edge(result_id, validation_id, "reported-in")
    target_contract_id = graph.add_node("target_contract", name, name)
    graph.add_edge(target_contract_id, result_id, "validated-by-result")
    graph.add_edge(result_id, target_contract_id, "validates-contract")
    for index, violation in enumerate(_coerce_list(contract.get("violations"))):
        if not isinstance(violation, dict):
            continue
        code = str(violation.get("code") or f"violation-{index}")
        violation_id = graph.add_node(
            "validation_violation",
            f"{name}:{code}:{index}",
            code,
            code=violation.get("code"),
            message=violation.get("message"),
        )
        graph.add_edge(result_id, violation_id, "has-violation")
        graph.add_edge(violation_id, validation_id, "recorded-in-validation")


def _add_downstream_validation_node(
    graph: _ImpactGraph,
    downstream_validation: dict[str, Any],
) -> str:
    command = _dict(downstream_validation.get("command"))
    diagnostic = _dict(downstream_validation.get("diagnostic"))
    evidence_id = graph.add_node(
        "downstream_validation_evidence",
        "lza-validation-evidence.yaml",
        "LZA validation evidence",
        status=downstream_validation.get("status"),
        exitCode=command.get("exitCode"),
        diagnosticCategory=diagnostic.get("category"),
        diagnosticSummary=diagnostic.get("summary"),
    )
    artifact_id = graph.add_node(
        "artifact",
        "lza-validation-evidence.yaml",
        "lza-validation-evidence.yaml",
    )
    graph.add_edge(evidence_id, artifact_id, "recorded-in")
    input_block = _dict(downstream_validation.get("input"))
    for item in _coerce_list(input_block.get("configFileDigests")):
        if not isinstance(item, dict) or not item.get("name"):
            continue
        artifact_id = graph.add_node("artifact", str(item["name"]), str(item["name"]))
        graph.add_edge(artifact_id, evidence_id, "validated-by-downstream-evidence")
    for artifact_name in _coerce_list(input_block.get("configFiles")):
        artifact_id = graph.add_node("artifact", str(artifact_name), str(artifact_name))
        graph.add_edge(artifact_id, evidence_id, "validated-by-downstream-evidence")
    return evidence_id


def _add_artifact_digest_properties(
    graph: _ImpactGraph,
    *,
    bundle: Path,
    replay_manifest: dict[str, Any],
    downstream_validation: dict[str, Any],
) -> None:
    replay_digests = _digests_by_name(_dict(replay_manifest.get("artifacts")).get("files"))
    validation_digests = _digests_by_name(
        _dict(downstream_validation.get("input")).get("configFileDigests")
    )
    for node in graph.nodes.values():
        if node.kind != "artifact" or not node.key:
            continue
        artifact_path = _artifact_file_path(bundle, node.key)
        actual_sha = ""
        if artifact_path is not None and artifact_path.is_file():
            actual_sha = _sha256_file(artifact_path)
            node.properties.update(
                {
                    "existsInBundle": True,
                    "sha256": actual_sha,
                    "sizeBytes": artifact_path.stat().st_size,
                    "digestSource": "bundle-file",
                }
            )
        replay_sha = replay_digests.get(node.key)
        if replay_sha:
            node.properties["replaySha256"] = replay_sha
            if actual_sha:
                node.properties["replayDigestMatches"] = actual_sha == replay_sha
        validation_sha = validation_digests.get(node.key)
        if validation_sha:
            node.properties["downstreamValidationSha256"] = validation_sha
            if actual_sha:
                node.properties["downstreamValidationDigestMatches"] = actual_sha == validation_sha


def _digests_by_name(value: Any) -> dict[str, str]:
    digests: dict[str, str] = {}
    for item in _coerce_list(value):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        sha256 = str(item.get("sha256") or "")
        if name and sha256:
            digests[name] = sha256
    return digests


def _artifact_file_path(bundle: Path, artifact_name: str) -> Path | None:
    path = Path(artifact_name)
    if path.is_absolute():
        return None
    try:
        candidate = (bundle / path).resolve()
        candidate.relative_to(bundle.resolve())
    except ValueError:
        return None
    return candidate


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _first_mapping(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict) and value:
            return value
    return {}


def _readiness_allowed(readiness: dict[str, Any]) -> bool | None:
    if "handoffAllowed" in readiness:
        return bool(readiness["handoffAllowed"])
    if "deploymentAllowed" in readiness:
        return bool(readiness["deploymentAllowed"])
    if "allowed" in readiness:
        return bool(readiness["allowed"])
    return None


def _readiness_blocker_count(readiness: dict[str, Any]) -> int:
    if isinstance(readiness.get("blockerCount"), int):
        return int(readiness["blockerCount"])
    blocker_count = len(_coerce_list(readiness.get("blockers")))
    blocker_count += len(_coerce_list(readiness.get("missingDecisions")))
    blocker_count += len(_coerce_list(readiness.get("conflictingDecisions")))
    return blocker_count


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


def _node_or_selector(
    graph: _ImpactGraph,
    node_id: str | None,
    selector: ImpactRoot,
) -> dict[str, Any]:
    if node_id is not None and node_id in graph.nodes:
        return graph.nodes[node_id].to_dict()
    return {
        "id": f"{selector.kind}:{selector.key}",
        "kind": selector.kind,
        "key": selector.key,
        "label": selector.key,
        "properties": {},
    }


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


def _root_kinds() -> list[str]:
    return [
        "decision",
        "artifact",
        "policy_control",
        "module_variable",
        "target_contract",
        "target_capability",
        "manual_gate",
        "source_context",
        "input_diff",
        "source_change",
        "handoff_readiness",
        "readiness_blocker",
        "contract_validation",
        "contract_result",
        "validation_violation",
        "downstream_validation_evidence",
        "semantic_entity",
        "semantic_constraint",
        "shift_left_evidence",
        "checkov_finding",
        "scan_file",
    ]


def _root_entry(node: _ImpactNode) -> dict[str, Any]:
    root = f"{node.kind}:{node.key}"
    return {
        "root": root,
        "node": node.to_dict(),
        "commands": {
            "impact": f"iac-llm-wrapper graph impact --bundle <bundle> --root {root}",
            "neighbors": f"iac-llm-wrapper graph neighbors --bundle <bundle> --root {root}",
        },
    }


def _roots_by_kind(roots: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for root in roots:
        node = _dict(root.get("node"))
        kind = str(node.get("kind") or "unknown")
        root_value = str(root.get("root") or "")
        if root_value:
            grouped.setdefault(kind, []).append(root_value)
    return {kind: sorted(items) for kind, items in sorted(grouped.items())}


def _recommended_review_roots(nodes: list[_ImpactNode]) -> list[dict[str, Any]]:
    recommendations = []
    for node in nodes:
        reason = _review_root_reason(node)
        if reason:
            entry = _root_entry(node)
            entry["reason"] = reason
            recommendations.append(entry)
    return sorted(
        recommendations,
        key=lambda item: (_recommendation_rank(_dict(item.get("node"))), str(item.get("root", ""))),
    )


def _review_root_reason(node: _ImpactNode) -> str:
    status = str(node.properties.get("status") or "").lower()
    if node.kind == "source_change":
        return "Source change can affect downstream decisions and emitted handoff artifacts."
    if node.kind == "readiness_blocker":
        return "Readiness blocker must be resolved or accepted before handoff."
    if node.kind == "validation_violation":
        return "Contract validation violation requires review before handoff."
    if node.kind == "checkov_finding":
        return "Checkov finding is shift-left evidence for owner policy review."
    if node.kind == "downstream_validation_evidence" and status not in {"", "pass"}:
        return "Downstream validation evidence is not passing."
    if node.kind == "contract_validation" and status not in {"", "pass"}:
        return "Contract validation status is not passing."
    if node.kind == "handoff_readiness" and (
        status not in {"", "ready"} or node.properties.get("handoffAllowed") is False
    ):
        return "Handoff readiness is not ready or not allowed."
    if node.kind == "shift_left_evidence" and status not in {"", "pass", "skipped"}:
        return "Shift-left evidence is not passing."
    return ""


def _recommendation_rank(node: dict[str, Any]) -> int:
    kind = str(node.get("kind") or "")
    return {
        "readiness_blocker": 0,
        "validation_violation": 1,
        "downstream_validation_evidence": 2,
        "contract_validation": 3,
        "checkov_finding": 4,
        "shift_left_evidence": 5,
        "source_change": 6,
        "handoff_readiness": 7,
    }.get(kind, 20)


def _bundle_graph_indexes(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "nodesByKind": _node_ids_by_kind(nodes),
        "outgoing": _adjacency_index(edges, source_key="from", target_key="to"),
        "incoming": _adjacency_index(edges, source_key="to", target_key="from"),
        "edgesByRelationship": _edges_by_relationship(edges),
        "rootSelectorsByKind": _root_selectors_by_kind(nodes),
    }


def _edges_by_relationship(edges: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for edge in edges:
        relationship = str(edge.get("relationship") or "")
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if relationship and source and target:
            grouped.setdefault(relationship, []).append(
                {"from": source, "to": target, "relationship": relationship}
            )
    return {
        relationship: sorted(items, key=lambda item: (item["from"], item["to"]))
        for relationship, items in sorted(grouped.items())
    }


def _root_selectors_by_kind(nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
    root_kinds = set(_root_kinds())
    grouped: dict[str, list[str]] = {}
    for node in nodes:
        kind = str(node.get("kind") or "")
        key = str(node.get("key") or "")
        if kind in root_kinds and key:
            grouped.setdefault(kind, []).append(f"{kind}:{key}")
    return {kind: sorted(selectors) for kind, selectors in sorted(grouped.items())}


def _bundle_graph_catalog(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "rootSelectorSyntax": "<kind>:<key>",
        "nodeKinds": _node_kind_catalog(nodes),
        "relationships": _relationship_catalog(nodes, edges),
    }


def _node_kind_catalog(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = _count_by(nodes, "kind")
    root_kinds = set(_root_kinds())
    return [
        {
            "kind": kind,
            "description": NODE_KIND_DESCRIPTIONS.get(
                kind,
                "Pattern or evidence-specific graph node.",
            ),
            "rootSelectable": kind in root_kinds,
            "nodeCount": count,
        }
        for kind, count in sorted(counts.items())
    ]


def _relationship_catalog(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, str]],
) -> list[dict[str, Any]]:
    nodes_by_id = {str(node.get("id") or ""): node for node in nodes}
    grouped: dict[str, dict[str, Any]] = {}
    for edge in edges:
        relationship = str(edge.get("relationship") or "unknown")
        source = nodes_by_id.get(str(edge.get("from") or ""), {})
        target = nodes_by_id.get(str(edge.get("to") or ""), {})
        item = grouped.setdefault(
            relationship,
            {
                "relationship": relationship,
                "description": _relationship_description(relationship),
                "edgeCount": 0,
                "sourceKinds": set(),
                "targetKinds": set(),
            },
        )
        item["edgeCount"] += 1
        if source.get("kind"):
            item["sourceKinds"].add(str(source["kind"]))
        if target.get("kind"):
            item["targetKinds"].add(str(target["kind"]))
    return [
        {
            "relationship": relationship,
            "description": item["description"],
            "edgeCount": item["edgeCount"],
            "sourceKinds": sorted(item["sourceKinds"]),
            "targetKinds": sorted(item["targetKinds"]),
        }
        for relationship, item in sorted(grouped.items())
    ]


def _relationship_description(relationship: str) -> str:
    if relationship.startswith("semantic:"):
        return SEMANTIC_RELATIONSHIP_DESCRIPTION
    return RELATIONSHIP_DESCRIPTIONS.get(
        relationship,
        "Pattern or evidence-specific graph relationship.",
    )


def _node_ids_by_kind(nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for node in nodes:
        kind = str(node.get("kind") or "unknown")
        node_id = str(node.get("id") or "")
        if not node_id:
            continue
        grouped.setdefault(kind, []).append(node_id)
    return {kind: sorted(ids) for kind, ids in sorted(grouped.items())}


def _adjacency_index(
    edges: list[dict[str, str]],
    *,
    source_key: str,
    target_key: str,
) -> dict[str, list[dict[str, str]]]:
    adjacency: dict[str, list[dict[str, str]]] = {}
    for edge in edges:
        source = str(edge.get(source_key) or "")
        target = str(edge.get(target_key) or "")
        relationship = str(edge.get("relationship") or "")
        if not source or not target:
            continue
        adjacency.setdefault(source, []).append(
            {
                target_key: target,
                "relationship": relationship,
            }
        )
    return {
        node_id: sorted(items, key=lambda item: (item.get(target_key, ""), item["relationship"]))
        for node_id, items in sorted(adjacency.items())
    }


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return counts


def _edge_key(edge: _ImpactEdge) -> tuple[str, str, str]:
    return (edge.source, edge.target, edge.relationship)


def _node_change(before: _ImpactNode, after: _ImpactNode) -> dict[str, Any]:
    before_dict = before.to_dict()
    after_dict = after.to_dict()
    changed_fields = [
        field
        for field in ("kind", "key", "label", "properties")
        if before_dict.get(field) != after_dict.get(field)
    ]
    return {
        "id": after.id,
        "changedFields": changed_fields,
        "before": before_dict,
        "after": after_dict,
    }


def _query_tokens(query: str) -> list[str]:
    return [token.casefold() for token in query.replace(":", " ").split() if token.strip()]


def _find_match(node: _ImpactNode, query_tokens: list[str]) -> dict[str, Any] | None:
    haystack = _node_search_fields(node)
    if query_tokens and not all(
        any(token in value for value in haystack.values()) for token in query_tokens
    ):
        return None
    matched_fields = sorted(
        {
            field
            for token in query_tokens or [""]
            for field, value in haystack.items()
            if token in value
        }
    )
    score = sum(1 for field in matched_fields if field in {"id", "key", "label"})
    score += len(matched_fields)
    if node.key.casefold() in query_tokens:
        score += 3
    if node.label.casefold() in query_tokens:
        score += 2
    match = {
        "score": score,
        "matchedFields": matched_fields,
        "node": node.to_dict(),
    }
    if node.kind in set(_root_kinds()):
        match["root"] = _root_entry(node)
    else:
        match["rootSelectable"] = False
    return match


def _node_search_fields(node: _ImpactNode) -> dict[str, str]:
    return {
        "id": node.id.casefold(),
        "kind": node.kind.casefold(),
        "key": node.key.casefold(),
        "label": node.label.casefold(),
        "properties": _stringify(node.properties).casefold(),
    }


def _stringify(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{key} {_stringify(item)}" for key, item in sorted(value.items()))
    if isinstance(value, list):
        return " ".join(_stringify(item) for item in value)
    return str(value)


def _impact_paths(
    graph: _ImpactGraph,
    roots: list[str],
    downstream_nodes: list[_ImpactNode],
) -> list[dict[str, Any]]:
    interesting_kinds = {
        "artifact",
        "artifact_path",
        "checkov_finding",
        "checkov_check",
        "contract_validation",
        "contract_result",
        "downstream_validation_evidence",
        "handoff_readiness",
        "manual_gate",
        "module_variable",
        "policy_control",
        "readiness_blocker",
        "scan_file",
        "sample",
        "semantic_constraint",
        "semantic_entity",
        "source_context",
        "input_diff",
        "source_change",
        "shift_left_evidence",
        "target_contract",
        "target_capability",
        "validation_violation",
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


def _path_step_to_dict(graph: _ImpactGraph, step: _PathStep) -> dict[str, Any]:
    edge = step.edge
    return {
        "from": graph.nodes[step.source].to_dict(),
        "to": graph.nodes[step.target].to_dict(),
        "relationship": edge.relationship,
        "direction": step.direction,
        "edge": {
            "from": edge.source,
            "to": edge.target,
            "relationship": edge.relationship,
        },
    }


def _impact_matrix_row(
    report: dict[str, Any],
    *,
    recommendation_reason: str = "",
) -> dict[str, Any]:
    summary = _dict(report.get("summary"))
    root = _matrix_root(report)
    upstream_source_changes = _matrix_upstream_keys(report, root, "source_change")
    upstream_input_diffs = _matrix_upstream_keys(report, root, "input_diff")
    row = {
        "root": root,
        "unmatchedRoots": _coerce_list(report.get("unmatchedRoots")),
        "summary": {
            "status": summary.get("status", "unknown"),
            "downstreamImpactCount": summary.get("downstreamImpactCount", 0),
            "upstreamDependencyCount": summary.get("upstreamDependencyCount", 0),
            "highestReviewPrioritySeverity": summary.get("highestReviewPrioritySeverity", "none"),
            "reviewPrioritySeverityCounts": _dict(summary.get("reviewPrioritySeverityCounts")),
            "affectedArtifactCount": len(_coerce_list(report.get("affectedArtifacts"))),
            "affectedTargetContractCount": len(_coerce_list(report.get("affectedTargetContracts"))),
            "affectedTargetCapabilityCount": len(
                _coerce_list(report.get("affectedTargetCapabilities"))
            ),
            "affectedSampleCount": len(_coerce_list(report.get("affectedSamples"))),
            "affectedPolicyControlCount": len(_coerce_list(report.get("affectedPolicyControls"))),
            "affectedCheckCount": len(_coerce_list(report.get("affectedChecks"))),
            "affectedCheckovFindingCount": len(_coerce_list(report.get("affectedCheckovFindings"))),
            "affectedModuleVariableCount": len(_coerce_list(report.get("affectedModuleVariables"))),
            "manualGateCount": len(_coerce_list(report.get("manualGates"))),
            "upstreamSourceChangeCount": len(upstream_source_changes),
            "upstreamInputDiffCount": len(upstream_input_diffs),
        },
        "affectedArtifacts": _coerce_list(report.get("affectedArtifacts")),
        "affectedTargetContracts": _coerce_list(report.get("affectedTargetContracts")),
        "affectedTargetCapabilities": _coerce_list(report.get("affectedTargetCapabilities")),
        "affectedSamples": _coerce_list(report.get("affectedSamples")),
        "affectedPolicyControls": _coerce_list(report.get("affectedPolicyControls")),
        "affectedChecks": _coerce_list(report.get("affectedChecks")),
        "affectedCheckovFindings": _coerce_list(report.get("affectedCheckovFindings")),
        "affectedModuleVariables": _coerce_list(report.get("affectedModuleVariables")),
        "manualGates": _coerce_list(report.get("manualGates")),
        "upstreamSourceChanges": upstream_source_changes,
        "upstreamInputDiffs": upstream_input_diffs,
        "reviewFocus": _coerce_list(report.get("reviewFocus")),
        "reviewChecklist": _coerce_list(report.get("reviewChecklist")),
        "impactPathCount": len(_coerce_list(report.get("impactPaths"))),
        "pattern": report.get("pattern", ""),
        "graph": _dict(report.get("graph")),
    }
    if recommendation_reason:
        row["recommendationReason"] = recommendation_reason
    return row


def _matrix_upstream_keys(report: dict[str, Any], root: dict[str, Any], kind: str) -> list[str]:
    keys = {
        str(node.get("key"))
        for node in _coerce_list(report.get("upstreamDependencies"))
        if isinstance(node, dict) and node.get("kind") == kind and node.get("key")
    }
    if root.get("kind") == kind and root.get("key"):
        keys.add(str(root["key"]))
    return sorted(keys)


def _impact_root_from_value(value: str) -> ImpactRoot | None:
    if ":" not in value:
        return None
    kind, key = value.split(":", 1)
    if not kind or not key:
        return None
    return ImpactRoot(kind=kind, key=key)


def _dedupe_roots(roots: list[ImpactRoot]) -> list[ImpactRoot]:
    seen: set[tuple[str, str]] = set()
    deduped: list[ImpactRoot] = []
    for root in roots:
        key = (root.kind, root.key)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return deduped


def _matrix_root(report: dict[str, Any]) -> dict[str, Any]:
    selected = _coerce_list(report.get("selectedRoots"))
    if selected and isinstance(selected[0], dict):
        return selected[0]
    unmatched = _coerce_list(report.get("unmatchedRoots"))
    if unmatched and isinstance(unmatched[0], dict):
        kind = str(unmatched[0].get("kind", "unknown"))
        key = str(unmatched[0].get("key", ""))
        return {
            "id": f"{kind}:{key}",
            "kind": kind,
            "key": key,
            "label": key,
            "properties": {},
        }
    return {
        "id": "unknown:",
        "kind": "unknown",
        "key": "",
        "label": "",
        "properties": {},
    }


def _matrix_union(rows: list[dict[str, Any]], key: str) -> list[str]:
    values: set[str] = set()
    for row in rows:
        values.update(str(item) for item in _coerce_list(row.get(key)) if item)
    return sorted(values)


def _matrix_severity_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {severity: 0 for severity in PRIORITY_SEVERITIES}
    for row in rows:
        row_counts = _dict(_dict(row.get("summary")).get("reviewPrioritySeverityCounts"))
        for severity in PRIORITY_SEVERITIES:
            counts[severity] += int(row_counts.get(severity, 0) or 0)
    return counts


def _matrix_review_focus(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["No graph roots were provided for matrix review."]
    unmatched = [
        _node_label(_dict(row.get("root")))
        for row in rows
        if _dict(row.get("summary")).get("status") != "matched"
    ]
    focus = [
        f"Compare impact across {len(rows)} selected graph root(s) before choosing deeper "
        "path or neighborhood queries."
    ]
    if unmatched:
        focus.append("Verify unmatched roots: " + ", ".join(unmatched) + ".")
    high_rows = [
        _node_label(_dict(row.get("root")))
        for row in rows
        if _dict(row.get("summary")).get("highestReviewPrioritySeverity") in {"critical", "high"}
    ]
    if high_rows:
        focus.append("Prioritize high-severity roots: " + ", ".join(high_rows) + ".")
    return focus


def _impact_review_priorities(
    *,
    readiness_blockers: list[str],
    validation_violations: list[str],
    downstream_validation: list[str],
    findings: list[str],
    shift_left_evidence: list[str],
    source_changes: list[str],
    manual_gates: list[str],
    target_contracts: list[str],
    target_capabilities: list[str],
    samples: list[str],
    policy_controls: list[str],
    artifacts: list[str],
    module_variables: list[str],
) -> list[dict[str, Any]]:
    priorities = [
        _priority(
            "critical",
            "readiness-blockers",
            readiness_blockers,
            "Resolve or explicitly accept readiness blockers before handoff.",
        ),
        _priority(
            "critical",
            "validation-violations",
            validation_violations,
            "Review target contract validation violations before handoff.",
        ),
        _priority(
            "high",
            "downstream-validation",
            downstream_validation,
            "Review downstream validation evidence before claiming validation.",
        ),
        _priority(
            "high",
            "checkov-findings",
            findings,
            "Review Checkov findings as shift-left policy evidence.",
        ),
        _priority(
            "high",
            "shift-left-evidence",
            shift_left_evidence,
            "Review shift-left evidence status and owner policy gate expectations.",
        ),
        _priority(
            "medium",
            "source-changes",
            source_changes,
            "Confirm source changes are intentional and scoped to affected requirements.",
        ),
        _priority(
            "medium",
            "manual-gates",
            manual_gates,
            "Re-run or re-approve affected manual review gates.",
        ),
        _priority(
            "medium",
            "target-contracts",
            target_contracts,
            "Review affected target contracts before treating the handoff as covered.",
        ),
        _priority(
            "medium",
            "target-capabilities",
            target_capabilities,
            "Review affected target capability routing and coverage.",
        ),
        _priority(
            "medium",
            "policy-controls",
            policy_controls,
            "Review affected policy controls and mapped checks.",
        ),
        _priority(
            "low",
            "samples",
            samples,
            "Review sample alignment and recommendation changes.",
        ),
        _priority(
            "low",
            "module-variables",
            module_variables,
            "Review affected module variable handoff values.",
        ),
        _priority(
            "low",
            "artifacts",
            artifacts,
            "Review affected generated handoff artifacts.",
        ),
    ]
    return [item for item in priorities if item]


def _impact_review_checklist(
    *,
    roots: list[_ImpactNode],
    priorities: list[dict[str, Any]],
    impact_paths: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not roots:
        return []
    root_ids = [node.id for node in roots]
    root_id = root_ids[0]
    checklist: list[dict[str, Any]] = []
    for priority in priorities:
        category = str(priority.get("category") or "")
        items = [str(item) for item in _coerce_list(priority.get("items")) if item]
        if not category or not items:
            continue
        node_kind = _review_category_node_kind(category)
        entry: dict[str, Any] = {
            "step": len(checklist) + 1,
            "severity": str(priority.get("severity") or "review"),
            "category": category,
            "action": str(priority.get("reason") or ""),
            "items": items,
            "source": "reviewPriorities",
        }
        if node_kind:
            entry["targetRootKind"] = node_kind
            entry["pathQueries"] = [
                f"iac-llm-wrapper graph path --bundle <bundle> --from {root_id} "
                f"--to {node_kind}:{item}"
                for item in items[:5]
            ]
        checklist.append(entry)
    if impact_paths:
        targets = [
            str(_dict(item.get("target")).get("id") or "")
            for item in impact_paths[:5]
            if isinstance(item, dict)
        ]
        checklist.append(
            {
                "step": len(checklist) + 1,
                "severity": "info",
                "category": "impact-paths",
                "action": (
                    "Inspect representative root-to-target graph paths before closing review."
                ),
                "items": [item for item in targets if item],
                "source": "impactPaths",
            }
        )
    return checklist


def _review_category_node_kind(category: str) -> str:
    return {
        "readiness-blockers": "readiness_blocker",
        "validation-violations": "validation_violation",
        "downstream-validation": "downstream_validation_evidence",
        "checkov-findings": "checkov_finding",
        "shift-left-evidence": "shift_left_evidence",
        "source-changes": "source_change",
        "manual-gates": "manual_gate",
        "target-contracts": "target_contract",
        "target-capabilities": "target_capability",
        "policy-controls": "policy_control",
        "samples": "sample",
        "module-variables": "module_variable",
        "artifacts": "artifact",
    }.get(category, "")


def _priority_severity_counts(priorities: list[dict[str, Any]]) -> dict[str, int]:
    counts = {severity: 0 for severity in PRIORITY_SEVERITIES}
    for item in priorities:
        severity = str(item.get("severity") or "unknown")
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _priority_item_counts_by_severity(priorities: list[dict[str, Any]]) -> dict[str, int]:
    counts = {severity: 0 for severity in PRIORITY_SEVERITIES}
    for item in priorities:
        severity = str(item.get("severity") or "unknown")
        counts[severity] = counts.get(severity, 0) + int(item.get("count", 0) or 0)
    return counts


def _highest_priority_severity(counts: dict[str, int]) -> str:
    for severity in PRIORITY_SEVERITIES:
        if counts.get(severity, 0) > 0:
            return severity
    return "none"


def _priority_severity_summary(summary: dict[str, Any]) -> str:
    counts = _dict(summary.get("reviewPrioritySeverityCounts"))
    highest = str(summary.get("highestReviewPrioritySeverity") or "none")
    detail = " ".join(
        f"{severity}={int(counts.get(severity, 0) or 0)}" for severity in PRIORITY_SEVERITIES
    )
    return f"highest={highest} {detail}"


def _priority(
    severity: str,
    category: str,
    items: list[str],
    reason: str,
) -> dict[str, Any]:
    if not items:
        return {}
    return {
        "severity": severity,
        "category": category,
        "count": len(items),
        "items": items,
        "reason": reason,
    }


def _review_focus(
    *,
    status: str,
    roots: list[_ImpactNode],
    artifacts: list[str],
    target_contracts: list[str],
    target_capabilities: list[str],
    samples: list[str],
    controls: list[str],
    checks: list[str],
    findings: list[str],
    semantic_constraints: list[str],
    source_contexts: list[str],
    input_diffs: list[str],
    source_changes: list[str],
    readiness: list[str],
    readiness_blockers: list[str],
    contract_validation: list[str],
    validation_violations: list[str],
    downstream_validation: list[str],
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
    if target_contracts:
        focus.append("Review affected target contracts: " + ", ".join(target_contracts) + ".")
    if target_capabilities:
        focus.append("Review affected target capabilities: " + ", ".join(target_capabilities) + ".")
    if samples:
        focus.append("Review affected sample recommendations: " + ", ".join(samples) + ".")
    if controls:
        focus.append("Review affected policy controls: " + ", ".join(controls) + ".")
    if semantic_constraints:
        focus.append(
            "Review affected semantic constraints: " + ", ".join(semantic_constraints) + "."
        )
    if source_contexts:
        focus.append("Review affected source context: " + ", ".join(source_contexts) + ".")
    if input_diffs:
        focus.append("Review affected input diff reports: " + ", ".join(input_diffs) + ".")
    if source_changes:
        focus.append("Review affected source changes: " + ", ".join(source_changes) + ".")
    if readiness:
        focus.append("Review affected handoff readiness state: " + ", ".join(readiness) + ".")
    if readiness_blockers:
        focus.append("Review affected readiness blockers: " + ", ".join(readiness_blockers) + ".")
    if contract_validation:
        focus.append(
            "Review affected contract validation evidence: " + ", ".join(contract_validation) + "."
        )
    if validation_violations:
        focus.append(
            "Review affected validation violations: " + ", ".join(validation_violations) + "."
        )
    if downstream_validation:
        focus.append(
            "Review downstream validation evidence: " + ", ".join(downstream_validation) + "."
        )
    if findings:
        focus.append("Review affected Checkov findings: " + ", ".join(findings) + ".")
    if checks:
        focus.append(
            "Use affected Checkov refs as shift-left evidence inputs: " + ", ".join(checks) + "."
        )
    if gates:
        focus.append("Re-run or re-approve manual gates: " + ", ".join(gates) + ".")
    return focus


def _path_review_focus(
    *,
    status: str,
    source_id: str | None,
    target_id: str | None,
    direction: str,
    steps: list[_PathStep],
) -> list[str]:
    if status == "no-match":
        return ["One or both selected graph roots were not found in the generated bundle graph."]
    if status == "same-root":
        return ["Source and target resolve to the same graph node; no traversal is required."]
    if status == "no-path":
        return [
            "No path was found between the selected graph roots for direction "
            f"'{direction}'. Try --direction either or inspect graph impact upstream/downstream."
        ]
    upstream_hops = len([step for step in steps if step.direction == "upstream"])
    downstream_hops = len(steps) - upstream_hops
    return [
        f"Review graph path from {source_id} to {target_id}.",
        "Shortest path uses "
        f"{downstream_hops} downstream hop(s) and {upstream_hops} upstream hop(s).",
    ]


def _find_review_focus(
    *,
    status: str,
    query: str,
    returned_count: int,
    kind_filter: list[str],
) -> list[str]:
    if status == "no-match":
        suffix = f" within {', '.join(kind_filter)}" if kind_filter else ""
        return [f"No graph nodes matched query '{query}'{suffix}."]
    focus = [
        f"Use the returned {returned_count} graph node id(s) as roots "
        "for impact, path, or neighbors queries."
    ]
    if kind_filter:
        focus.append("Applied node-kind filter: " + ", ".join(kind_filter) + ".")
    return focus


def _roots_review_focus(
    *,
    status: str,
    root_count: int,
    recommendation_count: int,
    kind_filter: list[str],
) -> list[str]:
    if status == "no-match":
        suffix = f" for {', '.join(kind_filter)}" if kind_filter else ""
        return [f"No graph traversal roots were found{suffix}."]
    focus = [f"Use the {root_count} concrete graph root(s) as impact/path/neighborhood inputs."]
    if recommendation_count:
        focus.append(
            f"Start with the {recommendation_count} recommended review root(s) "
            "for likely blockers, source changes, findings, or validation evidence."
        )
    if kind_filter:
        focus.append("Applied node-kind filter: " + ", ".join(kind_filter) + ".")
    return focus


def _graph_diff_review_focus(
    *,
    status: str,
    changed_nodes: list[dict[str, Any]],
    added_edges: list[dict[str, Any]],
    removed_edges: list[dict[str, Any]],
) -> list[str]:
    if status == "unchanged":
        return ["No typed graph node or edge changes were detected."]
    focus = ["Review typed graph node and edge deltas before downstream handoff."]
    if changed_nodes:
        focus.append(
            "Changed graph nodes: "
            + ", ".join(str(item.get("id", "")) for item in changed_nodes[:8])
            + "."
        )
    if added_edges:
        focus.append(f"Review {len(added_edges)} added graph edge(s).")
    if removed_edges:
        focus.append(f"Review {len(removed_edges)} removed graph edge(s).")
    return focus


def _neighborhood_review_focus(
    *,
    status: str,
    root_id: str | None,
    depth: int,
    direction: str,
    neighbor_count: int,
    kind_filter: list[str],
) -> list[str]:
    if status == "no-match":
        return ["The selected graph root was not found in the generated bundle graph."]
    if neighbor_count == 0:
        suffix = f" matching {', '.join(kind_filter)}" if kind_filter else ""
        return [
            f"No{suffix} neighbors were found within depth {depth} for direction '{direction}'."
        ]
    focus = [
        f"Review {neighbor_count} graph neighbor(s) around {root_id} "
        f"within depth {depth} using direction '{direction}'."
    ]
    if kind_filter:
        focus.append("Applied node-kind filter: " + ", ".join(kind_filter) + ".")
    return focus


def _node_label(node: dict[str, Any]) -> str:
    return f"{node.get('kind', 'unknown')}:{node.get('key', '')}"


def _list_or_none(items: list[Any]) -> list[str]:
    if not items:
        return ["  - None"]
    return [f"  - {item}" for item in items]


def _node_list_lines(nodes: list[Any]) -> list[str]:
    if not nodes:
        return ["  - None"]
    lines = []
    for node in nodes[:12]:
        if isinstance(node, dict):
            lines.append(f"  - {_node_label(node)}")
    if len(nodes) > 12:
        lines.append(f"  ... {len(nodes) - 12} more")
    return lines or ["  - None"]


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
