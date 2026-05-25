# Multi-Cloud Kubernetes Platform Design

## Overview

Designing a Kubernetes platform for a regulated financial services company with multi-region requirements, strict network policies, and PCI-DSS scoped workloads.

## Cluster Configuration

- cluster_name: payments-k8s-platform
- cluster_version: 1.30
- node_pool_name: general-purpose
- node_pool_instance_type: m6i.2xlarge
- node_pool_min_size: 3
- node_pool_max_size: 20
- network_policy_enabled: true

## Network

- pod_cidr: 10.244.0.0/16
- service_cidr: 10.96.0.0/12
- namespace_name: payments

## Compliance Context

This platform handles payment card data and must maintain PCI-DSS compliance boundaries. Network policies must enforce zero-trust between namespaces. All workloads require encrypted service mesh.
