# Healthcare Hybrid Landing Zone Evaluation

The healthcare platform hosts PHI systems, integration engines, imaging ingestion, and patient
services. The hospital network remains on premises for several years, so AWS needs private
connectivity and clear audit evidence for HIPAA review.

## Region

- primary_region: eu-central-1

## Topology

- topology: hub-spoke

## Organizational Units

- Security: HIPAA audit, access logs, and guardrails
- Infrastructure: Network, resolver, and shared build services
- Clinical: PHI workloads and integration engines
- PatientServices: Patient-facing APIs and portals

## Accounts

- Network: ou=Infrastructure, description=Hybrid connectivity and DNS
- SharedServices: ou=Infrastructure, description=Private CI/CD and monitoring
- Audit: ou=Security, description=Audit archive and access evidence
- SecurityOps: ou=Security, description=Security Hub and incident response
- EHRProd: ou=Clinical, description=Production EHR integration
- ImagingProd: ou=Clinical, description=Imaging ingestion and processing
- PatientPortal: ou=PatientServices, description=Patient portal workloads

## Network

- network_cidr: 10.40.0.0/16
- hub_cidr: 10.40.0.0/20
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
- phi_encryption: true
- audit_access_logging: true
- business_associate_agreements: true

## CI/CD

- cicd_mode: private
- cicd_placement: SharedServices/BuildVPC

## Hybrid Connectivity

- hybrid_required: true
- hybrid_dns_model: route53-resolver
- hybrid_ip_model: rfc1918-only
- hybrid_on_prem_cidrs: 10.60.0.0/16, 10.61.0.0/16, 172.20.0.0/16

## Workloads

- ehr-api: target_account=EHRProd, network_mode=private, public_ingress=false, port=8443, cpu=1024, memory=2048
- hl7-ingest: target_account=EHRProd, network_mode=private, public_ingress=false, port=2575, cpu=512, memory=1024
- imaging-worker: target_account=ImagingProd, network_mode=private, public_ingress=false, port=8080, cpu=2048, memory=4096
- patient-portal: target_account=PatientPortal, network_mode=public, public_ingress=true, port=443, cpu=1024, memory=2048
