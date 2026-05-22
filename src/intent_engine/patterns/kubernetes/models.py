"""Kubernetes cluster intent models."""

from __future__ import annotations

from pydantic import BaseModel


class K8sIntent(BaseModel):
    """Intent model for kubernetes-cluster pattern."""

    cluster_name: str = "k8s-cluster"
    cluster_version: str = "1.29"
    network_policy_enabled: bool = True
    pod_cidr: str = "10.244.0.0/16"
    service_cidr: str = "10.96.0.0/12"
    node_pool_name: str = "default"
    node_pool_instance_type: str = "t3.medium"
    node_pool_min_size: int = 1
    node_pool_max_size: int = 3
    namespace_name: str = "default"
