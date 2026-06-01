# AWS Landing Zone Customer Board Notes

These notes are a lightly structured architecture-board handoff. They mix
meeting narrative, decision bullets, and review reminders because that is how
early customer design material usually arrives. The intent-engine output must
stay an AWS LZA handoff bundle. It must not generate Terraform, Terragrunt,
CloudFormation, or any deployment runner from these notes.

## Board Context

Northwind Retail is separating production retail workloads from experimentation
while centralizing security ownership. The platform team already uses AWS
Landing Zone Accelerator and wants a reviewed configuration handoff, not a new
provisioning stack.

The final board decision was:

- baseline: standard
- org_mode: control-tower
- organization_name: NorthwindRetail

## Regional Decision

The operations team debated `us-east-1`, but the approved home region for this
wave is Frankfurt because Identity Center and Control Tower operations are run
by the EU platform team.

- home_region: eu-central-1
- enabled_regions: eu-central-1, eu-west-1

## Organization And Account Ownership

The architecture owner confirmed this OU map for wave 1:

- organizational_units: Security, Infrastructure, Workloads, Sandbox

## Organizational Units

- Security: Audit, logging, delegated security tooling, and evidence ownership.
- Infrastructure: Shared networking, resolver, and transit routing ownership.
- Workloads: Retail production application accounts.
- Sandbox: Isolated experimentation with limited guardrail exceptions.

## Accounts

Account owners asked to keep the account names short because they match the
existing account vending registry.

- audit_account: Audit
- log_archive_account: LogArchive
- security_tooling_account: SecurityTooling
- network_account: NetworkShared
- workload_accounts: StorefrontProd, InventoryProd, SandboxDev

- Audit: ou=Security, description=Audit review and compliance evidence.
- LogArchive: ou=Security, description=Central immutable log archive.
- SecurityTooling: ou=Security, description=Delegated security tooling administrator.
- NetworkShared: ou=Infrastructure, description=Shared network and resolver services.
- StorefrontProd: ou=Workloads, description=Retail storefront production workload.
- InventoryProd: ou=Workloads, description=Inventory production workload.
- SandboxDev: ou=Sandbox, description=Developer sandbox account.

## Identity Center Decisions

Security owns delegated administration. Application teams get scoped power-user
access only to their workload accounts, and sandbox developers stay read-only
until a separate exception review.

- identity_center_delegated_admin_account: SecurityTooling
- identity_center_permission_sets: ReadOnlyAccess, SecurityAudit, PowerUserAccess, BreakGlassAdmin
- identity_center_assignments: PlatformAdmins:PowerUserAccess:Management, SecurityAuditors:SecurityAudit:Audit, StorefrontEngineers:PowerUserAccess:StorefrontProd, InventoryEngineers:PowerUserAccess:InventoryProd, SandboxDevelopers:ReadOnlyAccess:SandboxDev, IncidentCommanders:BreakGlassAdmin:SecurityTooling

## Network Decision

Network engineering approved a hub-and-spoke landing-zone layout. Inspection,
route-domain details, and workload subnet carving remain downstream LZA
engineering tasks after this handoff is accepted.

- topology: hub-spoke
- network_cidr: 10.80.0.0/16

## Security Controls

Security requires organization-wide logging and delegated security services in
the first handoff. Data classification refinements are manual follow-up gates,
not generated stacks.

- centralized_logging: true
- security_hub_enabled: true
- guardduty_enabled: true
- compliance_overlay: regulated

## Manual Gates

- Architecture owner reviews `decision-report.yaml`.
- Platform owner reviews organization and account config.
- Security owner reviews Identity Center, logging, Security Hub, and GuardDuty.
- Network owner reviews shared-network placeholders before the LZA pipeline runs.
- Release owner replaces placeholder account emails outside this generated bundle.
