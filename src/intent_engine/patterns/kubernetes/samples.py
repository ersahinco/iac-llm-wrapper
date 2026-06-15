"""Versioned sample configuration for Kubernetes handoff."""

from __future__ import annotations

from intent_engine.core.sample_config import ModuleRef, SampleConfig


def k8s_samples() -> list[SampleConfig]:
    return [
        SampleConfig(
            name="k8s-cluster-v1",
            pattern="kubernetes-cluster",
            version="1.0.0",
            release_date="2025-06-01",
            source_url="https://github.com/terraform-aws-modules/terraform-aws-eks",
            decisions={
                "cluster_name": "prod-k8s",
                "cluster_version": "1.30",
                "network_policy_enabled": "true",
                "pod_cidr": "10.244.0.0/16",
                "service_cidr": "10.96.0.0/12",
                "node_pool_name": "primary",
                "node_pool_instance_type": "t3.large",
                "node_pool_min_size": "2",
                "node_pool_max_size": "5",
                "namespace_name": "production",
            },
            module_refs=[
                ModuleRef(
                    module_name="terraform-aws-eks",
                    source="terraform-aws-modules/eks/aws",
                    version="~> 20.0",
                    description="EKS cluster with managed node groups, IRSA, security groups",
                ),
                ModuleRef(
                    module_name="terraform-aws-vpc",
                    source="terraform-aws-modules/vpc/aws",
                    version="~> 5.0",
                    description="VPC with public/private subnets for EKS cluster",
                ),
            ],
        )
    ]
