# Bank Platform Landing Zone Evaluation

This design intentionally mixes narrative, explicit decisions, compliance context, and workload
details. Architects expect hub-and-spoke because payment systems, fraud analytics, and shared
platform services must remain isolated but centrally governed.

## Region

- primary_region: eu-central-1
- secondary_region: eu-west-1

## Topology

- topology: hub-spoke
- rationale: central egress inspection, transitive routing, and shared services access

## Organizational Units

- Security: Audit, incident response, and security tooling
- Infrastructure: Network and shared platform services
- Payments: Cardholder-data workloads
- Digital: Customer-facing channels
- Sandbox: Restricted experimentation

## Accounts

- Network: ou=Infrastructure, description=Transit gateway, inspection, DNS forwarding
- SharedServices: ou=Infrastructure, description=CI/CD, observability, artifact services
- Audit: ou=Security, description=Immutable logs and evidence
- SecurityOps: ou=Security, description=Security tooling and delegated admin
- CardProd: ou=Payments, description=PCI production card platform
- CardNonProd: ou=Payments, description=PCI development and test
- FraudAnalytics: ou=Payments, description=Fraud models and batch scoring
- MobileBanking: ou=Digital, description=Mobile and web banking channel
- Sandbox01: ou=Sandbox, description=Controlled experiments

## Network

- network_cidr: 10.20.0.0/16
- hub_cidr: 10.20.0.0/20
- central_network_account: Network
- egress: all internet-bound traffic inspected centrally

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
- cicd_runner_platform: self-hosted
- cicd_runner_tool: gitlab-ci

## Hybrid Connectivity

- hybrid_required: true
- hybrid_dns_model: route53-resolver
- hybrid_ip_model: rfc1918-only
- hybrid_on_prem_cidrs: 10.200.0.0/16, 10.210.0.0/16

## Compliance

PCI-DSS, SOX, and GDPR apply. Cardholder-data systems must stay segmented from digital channel
workloads. Audit evidence must survive account compromise and administrator turnover.

- data_residency: true
- encryption_key_management: aws-kms-hsm
- network_segmentation: true

## Workloads

- card-api: target_account=CardProd, network_mode=private, public_ingress=false, port=8443, cpu=1024, memory=2048
- settlement-batch: target_account=CardProd, network_mode=private, public_ingress=false, port=8080, cpu=2048, memory=4096
- fraud-scoring: target_account=FraudAnalytics, network_mode=private, public_ingress=false, port=9090, cpu=1024, memory=2048
- mobile-edge: target_account=MobileBanking, network_mode=public, public_ingress=true, port=443, cpu=512, memory=1024
