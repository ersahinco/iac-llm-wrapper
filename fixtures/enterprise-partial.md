# Partial Enterprise Design

## Topology

- topology: hub-spoke

## Accounts

- Network: ou=Infrastructure, description=Central networking
- SharedServices: ou=Infrastructure, description=Shared services
- Audit: ou=Security, description=Audit and compliance
- SecurityOps: ou=Security, description=Security operations
- PaymentsProd: ou=Workloads/Prod, description=PCI-DSS payments
- DataPlatform: ou=Workloads/Prod, description=Analytics platform

## Network

- cidr: 10.0.0.0/16
- central_network_account: Network

## Security

- audit_retention_days: 2555
- centralized_logging: true

## Hybrid Connectivity

- required: true
- dns_model: route53-resolver
- on_prem_cidrs: 10.100.0.0/16

## Workloads

- payments-api: target_account=PaymentsProd, network_mode=private
