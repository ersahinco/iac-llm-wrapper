# Customer Packet - Blue River Bank Landing Zone Intake

This packet combines client meeting notes, architect clarifications, security
review comments, and engineer handoff reminders. Treat it like a realistic
customer packet, not a clean product template. The requested downstream path is
AWS Landing Zone Accelerator handoff only. Do not generate Terraform,
Terragrunt, CloudFormation stacks, or deployment automation from this document.

## Client Kickoff Notes

Blue River Bank is separating a new digital banking platform from older shared
AWS accounts. The bank wants one commercial AWS organization for regulated
customer-facing workloads and supporting shared services. The platform team
already operates AWS Control Tower and wants to keep that operating model.

Security kept saying "financial services controls" in the workshop. Legal
clarified that the first wave is not a formal PCI attestation project, but card
workflow metadata and online banking audit trails mean the environment should be
treated as regulated from day one. The bank wants AWS LZA sample configurations
as the downstream contract because their internal cloud team already reviews LZA
pull requests.

The CTO summary said Europe first. One product owner asked whether a future US
launch should be pre-created now, but the architect rejected that for wave one.
Wave-one regions are Frankfurt and Ireland only, with Frankfurt as the home
region.

## Architect Clarification Pass

These are the clarified decisions after the second architecture review:

- baseline: standard
- org_mode: control-tower
- organization_name: BlueRiverBank
- home_region: eu-central-1
- enabled_regions: eu-central-1, eu-west-1
- organizational_units: Security, Infrastructure, Workloads, Sandbox

Approved accounts:

- audit_account: Audit
- log_archive_account: LogArchive
- security_tooling_account: SecurityTooling
- network_account: NetworkShared
- workload_accounts: DigitalBankingProd, CardsProd, DataShared, SandboxDev

Identity and access decisions:

- identity_center_delegated_admin_account: SecurityTooling
- identity_center_permission_sets: ReadOnlyAccess, SecurityAudit, PowerUserAccess, BreakGlassAdmin, NetworkAdmin
- identity_center_assignments: PlatformAdmins:PowerUserAccess:Management, SecurityAuditors:SecurityAudit:Audit, NetworkEngineers:NetworkAdmin:NetworkShared, DigitalBankingEngineers:PowerUserAccess:DigitalBankingProd, CardsEngineers:PowerUserAccess:CardsProd, DataEngineers:ReadOnlyAccess:DataShared, IncidentCommanders:BreakGlassAdmin:SecurityTooling, SandboxDevelopers:ReadOnlyAccess:SandboxDev

Network decisions:

- topology: hub-spoke
- network_cidr: 10.64.0.0/16

Security decisions:

- centralized_logging: true
- security_hub_enabled: true
- guardduty_enabled: true
- compliance_overlay: financial-services

## Security Review Notes

Centralized logging is mandatory before workload onboarding. GuardDuty and
Security Hub must be enabled organization-wide. The security tooling account is
approved as delegated admin for security services and IAM Identity Center.
Security wants break-glass access documented, but all access values above are
permission-set and assignment names only.

Secrets and credentials must not be copied into prompts, raw evidence, review
HTML, Git, or handoff artifacts. The handoff should reference expected secret
parameters only:

- `/platform/lza/pipeline/github-token` in the bank's approved secret store
- `/platform/lza/network/ipam-api-token` in the bank's approved secret store
- `/platform/lza/security/exception-webhook` in the bank's approved secret store

These are secret-store references, not values.

## Engineer Handoff Review

Platform engineering will review the generated LZA-style YAML with the bank's
existing IaC workflow. Manual gates before any LZA execution:

- confirm Control Tower landing-zone prerequisites
- confirm the LZA pipeline owner and rollback approver
- confirm network TGW, DNS, and inspection design against `NetworkShared`
- confirm card-workflow retention and audit requirements
- confirm IAM Identity Center assignments with identity governance

Allowed next action after this handoff: engineer review of artifacts and manual
gate approval. Deployment is outside this wrapper.
