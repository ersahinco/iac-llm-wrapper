# Enterprise AWS LZA Intake - Northwind Platform Refresh

This intake came from three architecture workshops, two spreadsheet exports, and a
late security review. It is intentionally messy. Treat it as a real handoff note,
not a clean template. Platform engineering wants AWS Landing Zone Accelerator,
but nobody has approved deployment yet.

## Executive Summary

Northwind wants one commercial AWS organization for customer-facing and internal
platform workloads. Leadership says "standard Control Tower is fine" because
operations already have Control Tower experience. Security says regulated
controls are needed because payment metadata and customer support records may
touch the environment. Application teams are still arguing about region scope,
and network ownership remains unsettled.

The CIO summary says launch must happen in Q3. Platform team says the first
deployment must be read-only handoff until all landing-zone ownership gaps close.

Known messy statements:

- The program charter says US-first launch.
- The compliance addendum says EU workloads need EU residency.
- Security review says PCI-like controls apply, but legal says "not in formal
  PCI scope yet."
- Network architecture says hub-and-spoke, but no team accepted shared network
  account ownership.
- Identity says IAM Identity Center should be delegated to IAMShared, but that
  account is not in the current account plan.

## LZA Baseline

- baseline: standard

Use AWS Landing Zone Accelerator sample configs as downstream contract. Do not
generate Terraform or Terragrunt landing-zone stacks. Platform team will run AWS
LZA after approval.

## Organization

- org_mode: control-tower
- organization_name: NorthwindGlobal
- organizational_units: Security, Workloads

Conflicting notes:

- Security architect says an Infrastructure OU is probably needed for network
  and DNS ownership.
- Finance export omitted Infrastructure because cost center is not approved.
- Legacy spreadsheet lists "Shared Services" but nobody knows if this replaces
  Infrastructure.

## Regions

- home_region: us-east-1
- enabled_regions: eu-central-1, eu-west-1

Contradictory region notes:

- Workshop 1: primary should be `us-east-1` for SaaS latency.
- Workshop 2: enabled regions are `eu-central-1` and `eu-west-1` only because
  customer data residency starts in Europe.
- Security review: GuardDuty/Security Hub aggregation can be global, but all
  retention evidence must show EU regions first.
- Migration team says they might add `us-east-2` later, but not in wave 1.

## Accounts

- workload_accounts: PaymentsProd, ClaimsShared, Sandbox
- audit_account: Audit
- log_archive_account: LogArchive
- security_tooling_account: SecurityTooling

Account notes:

- Network account is missing. Network lead suggested `NetworkShared`, then
  withdrew it because Transit Gateway ownership is unresolved.
- Sandbox may move under a separate Experimental OU, but that OU is not approved.
- PaymentsProd owns customer payment workflow orchestration but should not own
  shared inspection or DNS.
- ClaimsShared handles support attachments and may include PII.
- LogArchive is approved by security.
- Audit is approved by internal audit.
- SecurityTooling is approved for GuardDuty/Security Hub delegated admin.

## Identity

- identity_center_delegated_admin_account: IAMShared

Identity notes:

- IAMShared is named in Okta migration notes.
- IAMShared is not in account vending plan.
- SecurityTooling could own delegated admin temporarily, but identity team has
  not approved that fallback.
- Permission sets and assignments are explicitly missing. Current teams only
  named personas: PlatformAdmin, SecurityReadOnly, AuditReadOnly, AppPowerUser.

## Network

- topology: hub-spoke
- network_cidr: 10.20.0.0/16

Network notes:

- Central inspection is desired.
- Transit Gateway route domains not designed.
- Private endpoint strategy not decided.
- Route 53 Resolver inbound/outbound not designed.
- Firewall vendor choice still pending; one note says native AWS Network
  Firewall, another says keep the existing appliance vendor until 2027.
- CIDR 10.20.0.0/16 overlaps with a corporate lab in one spreadsheet, but the
  IPAM owner has not confirmed if that lab still exists.

## Security

- centralized_logging: true
- security_hub_enabled: true
- guardduty_enabled: true
- compliance_overlay: regulated

Security notes:

- Security wants Security Hub and GuardDuty enabled organization-wide.
- Macie should be considered for regulated workloads, but data classification is
  incomplete.
- Centralized logging is mandatory, but S3 lifecycle and export cadence are not
  approved.
- Legal says this is not official PCI scope yet, but product says payment
  metadata makes PCI evidence likely within six months.
- No one owns security exception workflow after handoff.

## Workloads

- Payments API: target_account=PaymentsProd, network_mode=private, runtime=ecs-fargate, public_ingress=false, port=8443, cpu=1024, memory=2048
- Claims Portal: target_account=ClaimsShared, network_mode=private, runtime=ecs-fargate, public_ingress=false, port=8080, cpu=512, memory=1024
- Sandbox Tools: target_account=Sandbox, network_mode=public, runtime=ec2, public_ingress=true, port=443, cpu=512, memory=1024

Workload notes:

- Payments API requires private connectivity to corporate fraud systems.
- Claims Portal has support attachment data and may require stricter retention.
- Sandbox Tools should not be created in production landing-zone wave unless a
  separate OU and SCP path are approved.

## Deployment Readiness Notes

Do not deploy yet.

Required before deployment:

- Name and owner for shared network account.
- Decide whether Infrastructure OU exists or rename it through an approved
  contract.
- Fix home region versus enabled region mismatch.
- Choose real Identity Center delegated admin account.
- Approve permission sets and assignments.
- Approve TGW, subnet, DNS, and inspection design.
- Record who owns security exceptions, rollback, and LZA pipeline approval.
