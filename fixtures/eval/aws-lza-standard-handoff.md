# AWS LZA Standard Handoff Evaluation

The platform team wants a standard Control Tower based AWS Landing Zone
Accelerator handoff. It should use hub-and-spoke networking, centralized
security services, Security Hub, GuardDuty, and one application workload
account. No Terraform root modules should be generated.

## LZA Baseline

- baseline: standard

## Organization

- org_mode: control-tower
- organization_name: ExampleCorp
- organizational_units: Security, Infrastructure, Workloads

## Regions

- home_region: eu-central-1
- enabled_regions: eu-central-1

## Accounts

- workload_accounts: AppProd
- audit_account: Audit
- log_archive_account: LogArchive
- security_tooling_account: SecurityTooling
- network_account: Network

## Identity

- identity_center_delegated_admin_account: SecurityTooling
- identity_center_permission_sets: ReadOnlyAccess, PowerUserAccess
- identity_center_assignments: PlatformAdmins:PowerUserAccess:Management, AppTeam:ReadOnlyAccess:AppProd

## Network

- topology: hub-spoke
- network_cidr: 10.50.0.0/16

## Security

- centralized_logging: true
- security_hub_enabled: true
- guardduty_enabled: true
- compliance_overlay: none
