# Engineer Handoff Trial: Complete Landing Zone

Architect selected a standard baseline hub-and-spoke landing zone. Engineer should be able to open
the generated artifacts and find network, security, workload, and module handoff inputs.

## Region

- primary_region: eu-central-1

## Topology

- topology: hub-spoke

## Organizational Units

- Security: Audit and security operations
- Infrastructure: Network and platform services
- Workloads: Business applications

## Accounts

- Network: ou=Infrastructure, description=Transit and inspection
- SharedServices: ou=Infrastructure, description=CI/CD and observability
- Audit: ou=Security, description=Central audit archive
- AppProd: ou=Workloads, description=Production application account

## Network

- network_cidr: 10.50.0.0/16
- hub_cidr: 10.50.0.0/20
- central_network_account: Network

## Security

- audit_retention_days: 2555
- centralized_logging: true
- kms_rotation_required: true
- s3_block_public_access: true
- cloudtrail_org_trail: true
- egress_inspection: required
- inspection_pattern: centralized-nat
- inspection_vendor: aws-network-firewall

## CI/CD

- cicd_mode: private
- cicd_placement: SharedServices/BuildVPC

## Workloads

- orders-api: target_account=AppProd, network_mode=private, public_ingress=false, port=8080, cpu=512, memory=1024
