"""Kubernetes cluster handoff pattern registration."""

from __future__ import annotations

from typing import Any

from intent_engine.core.generator import register_generator
from intent_engine.core.module_mapping import ModuleInputs
from intent_engine.core.patterns import GLOBAL_REGISTRY, Pattern

from .contracts import K8S_CONTRACT
from .generators import gen_cluster_config, gen_k8s_decision_report, gen_namespace_config
from .graph import (
    K8S_FREE_FORM_EXAMPLES,
    K8S_SECTION_MAP,
    K8S_SECTION_ORDER,
    build_k8s_graph,
)
from .models import K8sIntent
from .samples import register_k8s_samples

_K8S_GENERATOR_SCOPE = {"kubernetes-cluster"}


def map_k8s_intent_to_modules(intent: Any) -> list[ModuleInputs]:
    """Map Kubernetes intent to optional IaC module variable references."""
    if not isinstance(intent, K8sIntent):
        return []
    return [
        ModuleInputs(
            module_name="terraform-aws-eks",
            variables={
                "cluster_name": intent.cluster_name,
                "cluster_version": intent.cluster_version,
                "vpc_id": "${module.vpc.vpc_id}",
                "subnet_ids": "${module.vpc.private_subnets}",
            },
        )
    ]


def _register_generators() -> None:
    register_generator(
        "k8s-cluster-config",
        gen_cluster_config,
        priority=10,
        applies_to=_K8S_GENERATOR_SCOPE,
    )
    register_generator(
        "k8s-namespace-config",
        gen_namespace_config,
        priority=11,
        applies_to=_K8S_GENERATOR_SCOPE,
    )
    register_generator(
        "k8s-decision-report",
        gen_k8s_decision_report,
        priority=5,
        applies_to=_K8S_GENERATOR_SCOPE,
    )


def _register_pattern() -> None:
    GLOBAL_REGISTRY.register(
        Pattern(
            name="kubernetes-cluster",
            description=(
                "Kubernetes cluster handoff with optional Terraform EKS module input references"
            ),
            graph_factory=build_k8s_graph,
            intent_factory=K8sIntent,
            section_map=dict(K8S_SECTION_MAP),
            section_order=list(K8S_SECTION_ORDER),
            free_form_examples=dict(K8S_FREE_FORM_EXAMPLES),
            prompt_context=(
                "This pattern captures Kubernetes cluster handoff configuration for an "
                "existing approved cluster or module workflow. Extract values as follows:\n"
                "- Cluster Configuration section -> cluster_name, cluster_version\n"
                "- Network section -> pod_cidr, service_cidr, network_policy_enabled\n"
                "- Node Pool section -> node_pool_name, node_pool_instance_type, "
                "node_pool_min_size, node_pool_max_size\n"
                "- Namespace section -> namespace_name\n"
                "Do not generate deployable cluster scaffolding from prose."
            ),
            module_mapper=map_k8s_intent_to_modules,
            contracts=[K8S_CONTRACT],
        )
    )


_register_generators()
_register_pattern()
register_k8s_samples()
