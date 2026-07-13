"""Kubernetes cluster intent models."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class K8sIntent(BaseModel):
    """Intent model for kubernetes-cluster pattern."""

    cluster_name: str = "k8s-cluster"
    cluster_version: str = "1.29"
    network_policy_enabled: bool = True
    pod_cidr: str = "10.244.0.0/16"
    service_cidr: str = "10.96.0.0/12"
    node_pool_name: str = "default"
    node_pool_instance_type: str = "t3.medium"
    node_pool_min_size: int = Field(default=1, ge=0)
    node_pool_max_size: int = Field(default=3, ge=0)
    namespace_name: str = "default"

    @model_validator(mode="after")
    def validate_node_pool_bounds(self) -> K8sIntent:
        if self.node_pool_min_size > self.node_pool_max_size:
            raise ValueError("node_pool_min_size must not exceed node_pool_max_size")
        return self
