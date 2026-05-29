# AWS LZA Complex Enterprise Landing Zone Requirements

This document represents the architecture handoff for a multi-region enterprise
landing zone. It includes executive goals, compliance context, operating model
notes, account ownership, identity assignments, network boundaries, and manual
gates. The output must remain an AWS LZA handoff bundle only; downstream teams
will run AWS Landing Zone Accelerator through the existing platform pipeline
after manual approval.

## Executive Summary

Contoso is consolidating several business-unit AWS accounts into one governed
commercial organization. The architecture board approved a Control Tower based
landing zone with centralized security, hub-and-spoke networking, and explicit
IAM Identity Center permission-set ownership. The handoff should preserve all
review gates because the network, identity, and compliance owners each sign off
in separate forums.

Goals:

- Establish one governed organization for production, shared services, analytics,
  regulated workloads, and sandbox experimentation.
- Keep AWS LZA as the downstream configuration contract.
- Avoid generating Terraform or CloudFormation deployment stacks from prose.
- Give engineers enough traceable decisions to prepare LZA config review.

## LZA Baseline

- baseline: standard

The platform council reviewed the universal and healthcare examples but selected
the standard commercial baseline, with a regulated overlay for audit evidence.

## Organization

- org_mode: control-tower
- organization_name: ContosoEnterprise
- organizational_units: Security, Infrastructure, Workloads, SharedServices, Analytics, Sandbox

Organizational requirements:

- Security owns audit, logging, delegated security services, and compliance
  evidence review.
- Infrastructure owns shared networking, resolver services, network firewall
  policy review, and transit gateway attachment approval.
- Workloads contains externally facing production applications.
- SharedServices contains platform tooling and shared business services.
- Analytics contains the data platform and reporting workloads.
- Sandbox is isolated from production guardrail exceptions.

## Organizational Units

- Security: Audit, log archive, and delegated security tooling ownership.
- Infrastructure: Shared network, resolver, and central inspection ownership.
- Workloads: Production application accounts.
- SharedServices: Shared application platform services.
- Analytics: Data platform and reporting services.
- Sandbox: Non-production experimentation with separate approval gates.

## Regions

- home_region: us-east-1
- enabled_regions: us-east-1, us-west-2, eu-west-1

Region requirements:

- `us-east-1` is the home region because Control Tower operations, IAM Identity
  Center administration, and primary security aggregation start there.
- `us-west-2` supports disaster recovery and west-coast latency-sensitive
  applications.
- `eu-west-1` supports the first regulated European workload wave.
- Additional regions require a new architecture decision record and are out of
  scope for this handoff.

## Accounts

- workload_accounts: PaymentsProd, ClaimsProd, DataPlatform, SharedServices, SandboxDev
- audit_account: Audit
- log_archive_account: LogArchive
- security_tooling_account: SecurityTooling
- network_account: NetworkShared

Account requirements:

- `Audit` receives audit delegations and read-only security review access.
- `LogArchive` stores centralized logs and is not used for application runtime.
- `SecurityTooling` owns Security Hub, GuardDuty, and IAM Identity Center
  delegated administration.
- `NetworkShared` owns transit gateway, resolver endpoints, and future central
  inspection attachments.
- `PaymentsProd` hosts payment orchestration and requires regulated controls.
- `ClaimsProd` hosts claims processing and customer support integrations.
- `DataPlatform` hosts curated analytics and reporting pipelines.
- `SharedServices` hosts platform services used by multiple business units.
- `SandboxDev` is non-production and must not receive production admin access.

## Accounts Inventory

- Audit: ou=Security, description=Audit review and delegated evidence access
- LogArchive: ou=Security, description=Centralized immutable log archive
- SecurityTooling: ou=Security, description=Delegated security tooling admin
- NetworkShared: ou=Infrastructure, description=Shared network and resolver account
- PaymentsProd: ou=Workloads, description=Regulated payment orchestration
- ClaimsProd: ou=Workloads, description=Claims processing production workload
- DataPlatform: ou=Analytics, description=Enterprise data platform
- SharedServices: ou=SharedServices, description=Shared application platform services
- SandboxDev: ou=Sandbox, description=Developer sandbox account

## Identity

- identity_center_delegated_admin_account: SecurityTooling
- identity_center_permission_sets: ReadOnlyAccess, SecurityAudit, NetworkAdmin, PowerUserAccess, BreakGlassAdmin
- identity_center_assignments: PlatformAdmins:PowerUserAccess:Management, SecurityAuditors:SecurityAudit:Audit, NetworkOperators:NetworkAdmin:NetworkShared, PaymentsEngineers:PowerUserAccess:PaymentsProd, ClaimsEngineers:PowerUserAccess:ClaimsProd, DataEngineers:PowerUserAccess:DataPlatform, SandboxDevelopers:ReadOnlyAccess:SandboxDev, IncidentCommanders:BreakGlassAdmin:SecurityTooling

Identity requirements:

- SecurityTooling is the delegated administrator because security operations own
  entitlement evidence and emergency-access review.
- Break-glass access must be traceable and assigned only to the incident
  commander group.
- Network operators receive network administration only in the shared network
  account.
- Application teams receive power-user access only in their named workload
  accounts.
- Sandbox developers receive read-only access by default; elevated access is a
  separate manual gate outside this handoff.

## Network

- topology: hub-spoke
- network_cidr: 10.64.0.0/16

Network requirements:

- The landing zone uses hub-and-spoke networking with a shared network account.
- Transit gateway route domains are reviewed after the LZA handoff bundle is
  accepted.
- Central inspection and resolver designs are documented as manual gates, not as
  generated appliance or firewall stacks.
- The `10.64.0.0/16` range is approved by IPAM for wave 1 and does not overlap
  corporate datacenter, VPN, or lab ranges.
- Workload subnet carving, route tables, and attachments are downstream LZA
  engineering tasks after this intent handoff is accepted.

## Workloads

- Payments API: target_account=PaymentsProd, public_ingress=false, port=443, cpu=2048, memory=4096
- Claims Portal: target_account=ClaimsProd, public_ingress=false, port=443, cpu=2048, memory=4096
- Reporting Jobs: target_account=DataPlatform, public_ingress=false, port=443, cpu=1024, memory=2048
- Shared Auth: target_account=SharedServices, public_ingress=false, port=443, cpu=1024, memory=2048

## Security

- centralized_logging: true
- security_hub_enabled: true
- guardduty_enabled: true
- compliance_overlay: regulated

Security requirements:

- Security Hub and GuardDuty must be enabled organization-wide.
- Centralized logging is mandatory before any production account is onboarded.
- Regulated overlay evidence is required for payments, claims, and analytics.
- Macie, firewall policy, and data-classification refinements are downstream
  manual gates and must not appear as generated deployable stacks in this output.

## Manual Gates

- Architecture owner confirms captured decisions and signs the decision report.
- Platform owner reviews organization, account, and global LZA files.
- Security owner reviews IAM Identity Center, logging, GuardDuty, and Security
  Hub configuration.
- Network owner reviews shared-network handoff placeholders before LZA pipeline
  execution.
- Release owner confirms placeholder account emails are replaced outside the
  generated artifact bundle.

