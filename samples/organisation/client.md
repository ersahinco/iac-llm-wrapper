# Customer Packet — Blue River Bank Landing Zone Intake

Illustrative example, not a record of bank approvals. The policy mappings and
workload handoff answers below are example inputs; replace them with owner decisions.

Client meeting notes, architect clarifications, and security review comments in
one document. The whole file is ingested on every run; there is no incremental
mode and no baseline to reconcile.

## Client Kickoff Notes

Blue River Bank is separating a new digital banking platform from older shared
AWS accounts. The bank wants one commercial AWS organization for regulated
customer-facing workloads plus supporting shared services. The platform team
already operates AWS Control Tower and wants to keep that operating model.

Security repeatedly said "financial services controls" in the workshop. Legal
clarified that wave one is not a formal PCI attestation project, but card
workflow metadata and online banking audit trails mean the environment is treated
as regulated from day one.

Europe first. A product owner requested a US region for wave one.
The organisation region standard must be checked before accepting that request.

## Architect Clarification Pass

- org_mode: control-tower
- organization_name: BlueRiverBank
- home_region: eu-central-1
- enabled_regions: eu-central-1, eu-west-1, us-east-1
- organizational_units: Security, Infrastructure, Workloads

Approved accounts:

- audit_account: Audit
- log_archive_account: LogArchive
- security_tooling_account: SecurityTooling
- network_account: NetworkShared
- workload_accounts: DigitalBankingProd, CardsProd, DataShared

Root emails come from the bank's approved mailbox convention. They are owner
input and are never generated:

- account_emails: Management=aws-management@example.com, LogArchive=aws-logarchive@example.com, Audit=aws-audit@example.com, SecurityTooling=aws-sectooling@example.com, NetworkShared=aws-network@example.com, DigitalBankingProd=aws-digitalbanking@example.com, CardsProd=aws-cards@example.com, DataShared=aws-datashared@example.com

## Identity and Access

- identity_center_delegated_admin_account: SecurityTooling
- identity_center_permission_sets: ReadOnlyAccess, SecurityAudit, PowerUserAccess, BreakGlassAdmin, NetworkAdmin
- identity_center_policy_mappings: ReadOnlyAccess=ReadOnlyAccess, SecurityAudit=SecurityAudit, PowerUserAccess=PowerUserAccess, BreakGlassAdmin=AdministratorAccess, NetworkAdmin=AmazonVPCFullAccess
- identity_center_assignments: PlatformAdmins:PowerUserAccess:Management, SecurityAuditors:SecurityAudit:Audit, NetworkEngineers:NetworkAdmin:NetworkShared, DigitalBankingEngineers:PowerUserAccess:DigitalBankingProd, CardsEngineers:PowerUserAccess:CardsProd, DataEngineers:ReadOnlyAccess:DataShared, IncidentCommanders:BreakGlassAdmin:SecurityTooling

## Network

- topology: hub-spoke
- network_cidr: 10.64.0.0/16

Platform engineering will confirm transit gateway route tables, DNS, and
inspection design against `NetworkShared` before any execution.

## Security Review Notes

- centralized_logging: true
- security_hub_enabled: true
- guardduty_enabled: true
- compliance_overlay: financial-services

Centralized logging is mandatory before workload onboarding. Secrets never travel
in this document, in prompts, or in emitted artifacts. Pipeline credentials are
referenced by parameter name only, held in the bank's approved secret store.

## Engineer Handoff

This packet covers the shared foundation for the digital-banking workload and its
supporting accounts. All data and backup locations in this example use the same
approved region set; differing workload constraints need a separate design review.

- data_classification: restricted
- data_regions: eu-central-1, eu-west-1
- recovery_objectives: RPO 15 minutes; RTO 4 hours; workload owner must prove both in a restore exercise
- application_owner: Digital Banking Platform team

Manual gates before any LZA execution:

- confirm Control Tower landing-zone prerequisites
- confirm the LZA pipeline owner and rollback approver
- confirm card-workflow retention and audit requirements
- confirm IAM Identity Center assignments with identity governance

Deployment is outside this tool.

## Existing enterprise integration

The hybrid connection method is still undecided.
- workforce_federation: entra-saml-scim
