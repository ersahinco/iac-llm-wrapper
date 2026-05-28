# Messy Enterprise Landing Zone Evaluation

This document mimics a workshop note. Some statements are narrative, some are explicit decisions,
and some are intentionally noisy. Finance asked whether a single VPC would be cheaper, but the
architecture board selected hub-and-spoke after reviewing blast radius and shared inspection needs.

Open question from meeting notes: "Could we defer Direct Connect?" Current decision: hybrid is
required because factories and identity services stay on premises during phase one.

## Region

- primary_region: eu-central-1

## Topology

- topology: hub-spoke

## Organizational Units

- Security: Central audit and security operations
- Infrastructure: Shared network and platform services
- CorpApps: Internal enterprise applications
- Manufacturing: Plant and shop-floor systems
- Data: Analytics and lakehouse workloads

## Accounts

- Network: ou=Infrastructure, description=Transit, resolver, inspection
- SharedServices: ou=Infrastructure, description=CI/CD and platform tooling
- Audit: ou=Security, description=Central evidence archive
- SecurityOps: ou=Security, description=Security operations
- CorpProd: ou=CorpApps, description=Corporate production applications
- FactoryProd: ou=Manufacturing, description=Factory integration systems
- DataLake: ou=Data, description=Enterprise data platform

## Network

- network_cidr: 10.80.0.0/16
- hub_cidr: 10.80.0.0/20
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

## Hybrid Connectivity

- hybrid_required: true
- hybrid_dns_model: route53-resolver
- hybrid_ip_model: rfc1918-only
- hybrid_on_prem_cidrs: 10.90.0.0/16, 10.91.0.0/16

## Workloads

- erp-api: target_account=CorpProd, network_mode=private, public_ingress=false, port=8443, cpu=1024, memory=2048
- factory-gateway: target_account=FactoryProd, network_mode=private, public_ingress=false, port=9443, cpu=512, memory=1024
- lake-ingest: target_account=DataLake, network_mode=private, public_ingress=false, port=9092, cpu=2048, memory=4096
