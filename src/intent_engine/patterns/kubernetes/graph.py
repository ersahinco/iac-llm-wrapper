"""Requirement graph and template metadata for Kubernetes handoff."""

from __future__ import annotations

from intent_engine.core.requirements import Requirement, RequirementGraph

K8S_SECTION_MAP: dict[str, tuple[str, str | None]] = {
    "cluster_name": ("Cluster", "cluster_name"),
    "cluster_version": ("Cluster", "cluster_version"),
    "network_policy_enabled": ("Network", "network_policy_enabled"),
    "pod_cidr": ("Network", "pod_cidr"),
    "service_cidr": ("Network", "service_cidr"),
    "node_pool_name": ("Node Pools", "node_pool_name"),
    "node_pool_instance_type": ("Node Pools", "node_pool_instance_type"),
    "node_pool_min_size": ("Node Pools", "node_pool_min_size"),
    "node_pool_max_size": ("Node Pools", "node_pool_max_size"),
    "namespace_name": ("Namespaces", "namespace_name"),
}

K8S_SECTION_ORDER = [
    "Cluster",
    "Network",
    "Node Pools",
    "Namespaces",
]


def build_k8s_graph() -> RequirementGraph:
    graph = RequirementGraph()
    graph.add(
        Requirement(
            key="cluster_name",
            target_field="cluster_name",
            target_type="string",
            label="Cluster Name",
            question="What is the name of the Kubernetes cluster?",
            default="k8s-cluster",
            category="general",
        )
    )
    graph.add(
        Requirement(
            key="cluster_version",
            target_field="cluster_version",
            target_type="string",
            label="Cluster Version",
            question="Which Kubernetes version should be used?",
            default="1.29",
            category="general",
        )
    )
    graph.add(
        Requirement(
            key="network_policy_enabled",
            target_field="network_policy_enabled",
            target_type="bool",
            label="Network Policy",
            question="Enable network policies for pod-to-pod traffic control?",
            options=["true", "false"],
            default="true",
            category="network",
        )
    )
    graph.add(
        Requirement(
            key="pod_cidr",
            target_field="pod_cidr",
            target_type="string",
            label="Pod CIDR",
            question="What CIDR block should be used for pod IPs?",
            default="10.244.0.0/16",
            category="network",
        )
    )
    graph.add(
        Requirement(
            key="service_cidr",
            target_field="service_cidr",
            target_type="string",
            label="Service CIDR",
            question="What CIDR block should be used for service IPs?",
            default="10.96.0.0/12",
            category="network",
        )
    )
    graph.add(
        Requirement(
            key="node_pool_name",
            target_field="node_pool_name",
            target_type="string",
            label="Node Pool Name",
            question="What is the name of the primary node pool?",
            default="default",
            category="workload",
        )
    )
    graph.add(
        Requirement(
            key="node_pool_instance_type",
            target_field="node_pool_instance_type",
            target_type="string",
            label="Node Pool Instance Type",
            question="What instance type should the nodes use?",
            default="t3.medium",
            category="workload",
        )
    )
    graph.add(
        Requirement(
            key="node_pool_min_size",
            target_field="node_pool_min_size",
            target_type="int",
            label="Node Pool Min Size",
            question="Minimum number of nodes in the pool?",
            default="1",
            category="workload",
        )
    )
    graph.add(
        Requirement(
            key="node_pool_max_size",
            target_field="node_pool_max_size",
            target_type="int",
            label="Node Pool Max Size",
            question="Maximum number of nodes in the pool?",
            default="3",
            category="workload",
        )
    )
    graph.add(
        Requirement(
            key="namespace_name",
            target_field="namespace_name",
            target_type="string",
            label="Namespace Name",
            question="What is the name of the primary namespace?",
            default="default",
            category="general",
            required_when_applicable=False,
        )
    )
    return graph
