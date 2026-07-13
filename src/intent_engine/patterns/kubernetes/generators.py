"""Artifact generators for Kubernetes handoff."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from intent_engine.core.yaml_utils import write_yaml_artifact

from .models import K8sIntent


def _k8s_intent(payload: Any) -> K8sIntent | None:
    intent = getattr(payload, "intent", payload)
    if isinstance(intent, K8sIntent):
        return intent
    return None


def gen_cluster_config(intent: Any, output_dir: Path) -> None:
    model = _k8s_intent(intent)
    if model is None:
        return
    data = {
        "cluster": {
            "name": model.cluster_name,
            "version": model.cluster_version,
            "network": {
                "podCidr": model.pod_cidr,
                "serviceCidr": model.service_cidr,
                "networkPolicyEnabled": model.network_policy_enabled,
            },
            "nodePools": [
                {
                    "name": model.node_pool_name,
                    "instanceType": model.node_pool_instance_type,
                    "minSize": model.node_pool_min_size,
                    "maxSize": model.node_pool_max_size,
                },
            ],
        },
    }
    write_yaml_artifact(output_dir / "cluster-config.yaml", data, header="")


def gen_namespace_config(intent: Any, output_dir: Path) -> None:
    model = _k8s_intent(intent)
    if model is None:
        return
    write_yaml_artifact(
        output_dir / "namespace-config.yaml",
        {"namespaces": [{"name": model.namespace_name}]},
        header="",
    )


def gen_k8s_decision_report(intent: Any, output_dir: Path) -> None:
    readiness = getattr(intent, "handoff_readiness", {})
    model = _k8s_intent(intent)
    if model is None:
        return
    data = {
        "pattern": "kubernetes-cluster",
        "clusterName": model.cluster_name,
        "clusterVersion": model.cluster_version,
        "network": {
            "podCidr": model.pod_cidr,
            "serviceCidr": model.service_cidr,
            "networkPolicyEnabled": model.network_policy_enabled,
        },
        "nodePool": {
            "name": model.node_pool_name,
            "instanceType": model.node_pool_instance_type,
            "minSize": model.node_pool_min_size,
            "maxSize": model.node_pool_max_size,
        },
        "namespace": model.namespace_name,
    }
    if readiness:
        data["handoffReadiness"] = readiness
    write_yaml_artifact(output_dir / "decision-report.yaml", data, header="")
