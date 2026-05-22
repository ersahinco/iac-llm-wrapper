# Payments Landing Zone Design

## Region

- primary: eu-central-1

## Topology

- topology: hub-spoke

## Organizational Units

- Security: Security baseline OU
- Infrastructure: Infrastructure and shared services OU
- Workloads/Prod: Production workloads OU

## Accounts

- Network: ou=Infrastructure, description=Central networking account
- Audit: ou=Security, description=Audit and compliance account
- LogArchive: ou=Security, description=Log archival account
- SharedServices: ou=Infrastructure, description=Shared services account
- PaymentsProd: ou=Workloads/Prod, description=Payments production account

## Network

- cidr: 10.0.0.0/16
- hub_cidr: 10.0.0.0/20
- central_network_account: Network

## Security

- audit_retention_days: 2555
- centralized_logging: true

## CI/CD

- mode: private
- placement: shared-vpc

## Workloads

- payments-api: target_account=PaymentsProd, network_mode=private, public_ingress=false, port=8080, cpu=512, memory=1024
