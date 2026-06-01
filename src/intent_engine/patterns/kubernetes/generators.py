"""Artifact generators for Kubernetes handoff."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

import ruamel.yaml

from .models import K8sIntent


def _k8s_intent(payload: Any) -> K8sIntent | None:
    intent = getattr(payload, "intent", payload)
    if isinstance(intent, K8sIntent):
        return intent
    return None


def _write_yaml(output_dir: Path, name: str, data: dict[str, Any]) -> None:
    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    buf = StringIO()
    yaml.dump(data, buf)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / name).write_text(buf.getvalue())


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
    _write_yaml(output_dir, "cluster-config.yaml", data)


def gen_namespace_config(intent: Any, output_dir: Path) -> None:
    model = _k8s_intent(intent)
    if model is None:
        return
    _write_yaml(
        output_dir,
        "namespace-config.yaml",
        {"namespaces": [{"name": model.namespace_name}]},
    )


def gen_k8s_decision_report(intent: Any, output_dir: Path) -> None:
    model = _k8s_intent(intent)
    if model is None:
        return
    data = {
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
    _write_yaml(output_dir, "decision-report.yaml", data)
