"""Kubernetes cluster pattern — acceptance test for generic framework.

This module demonstrates that a new use case can be added without
modifying any core framework file (extractor, compiler, validator,
normalizer, interview, cli, generator core).

Steps taken:
1. Define Pydantic models in kubernetes_models.py
2. Define RequirementGraph factory below
3. Register generators below
4. Register Pattern in GLOBAL_REGISTRY below
5. Add defaults to defaults.yaml
"""

from __future__ import annotations

from pathlib import Path

from intent_engine.core.generator import register_generator
from intent_engine.core.module_mapping import ModuleInputs, register_module_mapper
from intent_engine.core.patterns import GLOBAL_REGISTRY, Pattern
from intent_engine.core.requirements import Requirement, RequirementGraph

from .models import K8sIntent

# ---------------------------------------------------------------------------
# Requirement graph
# ---------------------------------------------------------------------------


def _k8s_graph_factory() -> RequirementGraph:
    g = RequirementGraph()

    g.add(
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

    g.add(
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

    g.add(
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

    g.add(
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

    g.add(
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

    g.add(
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

    g.add(
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

    g.add(
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

    g.add(
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

    g.add(
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

    return g


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------


def gen_cluster_config(intent: K8sIntent, output_dir: Path) -> None:
    if not hasattr(intent, "cluster_name"):
        return
    import ruamel.yaml

    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    yaml.sort_keys = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    from io import StringIO

    data = {
        "cluster": {
            "name": intent.cluster_name,
            "version": intent.cluster_version,
            "network": {
                "podCidr": intent.pod_cidr,
                "serviceCidr": intent.service_cidr,
                "networkPolicyEnabled": intent.network_policy_enabled,
            },
            "nodePools": [
                {
                    "name": intent.node_pool_name,
                    "instanceType": intent.node_pool_instance_type,
                    "minSize": intent.node_pool_min_size,
                    "maxSize": intent.node_pool_max_size,
                },
            ],
        },
    }
    buf = StringIO()
    yaml.dump(data, buf)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cluster-config.yaml").write_text(buf.getvalue())


def gen_namespace_config(intent: K8sIntent, output_dir: Path) -> None:
    if not hasattr(intent, "namespace_name"):
        return
    import ruamel.yaml

    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    yaml.sort_keys = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    from io import StringIO

    data = {
        "namespaces": [
            {"name": intent.namespace_name},
        ],
    }
    buf = StringIO()
    yaml.dump(data, buf)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "namespace-config.yaml").write_text(buf.getvalue())


def gen_k8s_decision_report(intent: K8sIntent, output_dir: Path) -> None:
    if not hasattr(intent, "cluster_name"):
        return
    import ruamel.yaml

    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    yaml.sort_keys = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    from io import StringIO

    data = {
        "clusterName": intent.cluster_name,
        "clusterVersion": intent.cluster_version,
        "network": {
            "podCidr": intent.pod_cidr,
            "serviceCidr": intent.service_cidr,
            "networkPolicyEnabled": intent.network_policy_enabled,
        },
        "nodePool": {
            "name": intent.node_pool_name,
            "instanceType": intent.node_pool_instance_type,
            "minSize": intent.node_pool_min_size,
            "maxSize": intent.node_pool_max_size,
        },
        "namespace": intent.namespace_name,
    }
    buf = StringIO()
    yaml.dump(data, buf)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "decision-report.yaml").write_text(buf.getvalue())


# Register generators (they coexist with other pattern generators thanks to hasattr guards)
register_generator("k8s-cluster-config", gen_cluster_config, priority=10, category="core")
register_generator("k8s-namespace-config", gen_namespace_config, priority=11, category="core")
register_generator("k8s-decision-report", gen_k8s_decision_report, priority=5, category="meta")


# ---------------------------------------------------------------------------
# Pattern registration
# ---------------------------------------------------------------------------

K8S_SECTION_MAP: dict[str, tuple[str, str | None]] = {
    "cluster_name": ("Cluster", "name"),
    "cluster_version": ("Cluster", "version"),
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

K8S_FREE_FORM_EXAMPLES: dict[str, list[str]] = {
    "Node Pools": [
        "primary: instance_type=t3.large, min_size=2, max_size=5",
    ],
    "Namespaces": [
        "production: labels=env=prod,team=platform",
    ],
}


def _k8s_artifact_validator(input_dir: Path) -> list[str]:
    errors: list[str] = []
    required = ["cluster-config.yaml", "namespace-config.yaml", "decision-report.yaml"]
    for fname in required:
        if not (input_dir / fname).exists():
            errors.append(f"Missing required file: {fname}")
    return errors


def map_k8s_intent_to_modules(intent: K8sIntent) -> list[ModuleInputs]:
    """Map Kubernetes intent to IaC module variable inputs."""
    modules: list[ModuleInputs] = []
    modules.append(
        ModuleInputs(
            module_name="terraform-aws-eks",
            variables={
                "cluster_name": intent.cluster_name,
                "cluster_version": intent.cluster_version,
                "vpc_id": "${module.vpc.vpc_id}",
                "subnet_ids": "${module.vpc.private_subnets}",
            },
        )
    )
    return modules


register_module_mapper("kubernetes-cluster", map_k8s_intent_to_modules)


GLOBAL_REGISTRY.register(
    Pattern(
        name="kubernetes-cluster",
        description="Kubernetes cluster provisioning with node pools and network policies",
        graph_factory=_k8s_graph_factory,
        intent_factory=K8sIntent,
        section_map=dict(K8S_SECTION_MAP),
        section_order=list(K8S_SECTION_ORDER),
        free_form_examples=dict(K8S_FREE_FORM_EXAMPLES),
        prompt_context="This pattern designs Kubernetes cluster configurations.",
        required_artifacts=["cluster-config.yaml", "namespace-config.yaml", "decision-report.yaml"],
        artifact_validators=[_k8s_artifact_validator],
    )
)

# ---------------------------------------------------------------------------
# Versioned sample configuration
# ---------------------------------------------------------------------------

from intent_engine.core.sample_config import (  # noqa: E402
    GLOBAL_SAMPLE_REGISTRY,
    ModuleRef,
    SampleConfig,
)

GLOBAL_SAMPLE_REGISTRY.register(
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
)
