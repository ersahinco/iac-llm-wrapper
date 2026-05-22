# Enterprise Cloud Adoption Landing Zone

## Region

- primary: eu-central-1
- secondary: eu-west-1

## Topology

- topology: hub-spoke
- multi-region: true

## Organizational Units

- Security: Security baseline, audit, and compliance OU
- Infrastructure: Shared services, network, and connectivity OU
- Workloads/Prod: Production business workloads OU
- Workloads/NonProd: Development and testing OU
- Sandbox: Experimental and PoC workloads OU

## Accounts

- Network: ou=Infrastructure, description=Central networking and transit
- SharedServices: ou=Infrastructure, description=Shared services (CI/CD, monitoring)
- Audit: ou=Security, description=Audit, log aggregation, and compliance
- SecurityOps: ou=Security, description=Security operations and SOC
- PaymentsProd: ou=Workloads/Prod, description=PCI-DSS scoped payments production
- PaymentsNonProd: ou=Workloads/NonProd, description=Payments dev and test
- WebPortalProd: ou=Workloads/Prod, description=Customer-facing web portal
- DataPlatform: ou=Workloads/Prod, description=Analytics and data lake platform

## Network

- cidr: 10.0.0.0/16
- hub_cidr: 10.0.0.0/20
- central_network_account: Network
- secondary_region_cidr: 10.1.0.0/16

## Security

- audit_retention_days: 2555
- centralized_logging: true
- kms_rotation: true
- s3_block_public_access: true
- cloudtrail_org_trail: true
- egress_inspection: required
- inspection_pattern: centralized-nat
- inspection_vendor: aws-network-firewall

## IAM and AuthN/AuthZ

- identity_source: on-prem-ad
- sso_enabled: true
- permission_boundary: true
- cross_account_role_pattern: deny-root
- break_glass_procedure: documented

## CI/CD

- mode: private
- placement: SharedServices/BuildVPC
- artifact_encryption: true
- pipeline_separation: true

## Hybrid Connectivity

- required: true
- dns_model: route53-resolver
- ip_model: rfc1918-only
- on_prem_cidrs: 10.100.0.0/16, 192.168.0.0/24, 172.16.0.0/20
- direct_connect: true
- vpn_backup: true

## Compliance

- frameworks: PCI-DSS, GDPR, ISO27001
- data_classification: restricted
- encryption_at_rest: required
- encryption_in_transit: required
- key_management: aws-kms-with-hsm
- dlp_enabled: true

## Workloads

- payments-api: target_account=PaymentsProd, network_mode=private, public_ingress=false, port=8080, cpu=512, memory=1024
- payments-web: target_account=PaymentsProd, network_mode=private, public_ingress=false, port=443, cpu=256, memory=512
- web-portal: target_account=WebPortalProd, network_mode=public, public_ingress=true, port=443, cpu=1024, memory=2048
- data-ingestion: target_account=DataPlatform, network_mode=private, public_ingress=false, port=9092, cpu=2048, memory=4096
