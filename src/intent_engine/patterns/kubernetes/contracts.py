"""Target contract for Kubernetes handoff artifacts."""

from __future__ import annotations

from intent_engine.core.contracts import (
    GLOBAL_CONTRACT_REGISTRY,
    ArtifactContract,
    DecisionLineage,
    TargetContract,
)

K8S_CONTRACT = TargetContract(
    name="kubernetes-cluster-config",
    kind="kubernetes-cluster-config",
    source_url="https://github.com/terraform-aws-modules/terraform-aws-eks",
    artifacts=[
        ArtifactContract(
            name="cluster-config.yaml",
            description="Cluster, network, and node pool configuration.",
            required_paths=[
                "cluster.name",
                "cluster.version",
                "cluster.network.podCidr",
                "cluster.network.serviceCidr",
                "cluster.nodePools[]",
                "cluster.nodePools[].name",
                "cluster.nodePools[].instanceType",
            ],
        ),
        ArtifactContract(
            name="namespace-config.yaml",
            description="Primary namespace configuration.",
            required_paths=["namespaces[]", "namespaces[].name"],
        ),
        ArtifactContract(
            name="decision-report.yaml",
            description="Kubernetes decision report.",
            required_paths=["clusterName", "clusterVersion", "network", "nodePool"],
        ),
    ],
    required_decisions=[
        "cluster_name",
        "cluster_version",
        "network_policy_enabled",
        "pod_cidr",
        "service_cidr",
        "node_pool_name",
        "node_pool_instance_type",
        "node_pool_min_size",
        "node_pool_max_size",
    ],
    lineage=[
        DecisionLineage(
            decision="cluster_name",
            artifact="cluster-config.yaml",
            path="cluster.name",
        ),
        DecisionLineage(
            decision="cluster_version",
            artifact="cluster-config.yaml",
            path="cluster.version",
        ),
        DecisionLineage(
            decision="pod_cidr",
            artifact="cluster-config.yaml",
            path="cluster.network.podCidr",
        ),
        DecisionLineage(
            decision="service_cidr",
            artifact="cluster-config.yaml",
            path="cluster.network.serviceCidr",
        ),
        DecisionLineage(
            decision="node_pool_name",
            artifact="cluster-config.yaml",
            path="cluster.nodePools[].name",
        ),
        DecisionLineage(
            decision="namespace_name",
            artifact="namespace-config.yaml",
            path="namespaces[].name",
        ),
    ],
)

GLOBAL_CONTRACT_REGISTRY.register(K8S_CONTRACT)
