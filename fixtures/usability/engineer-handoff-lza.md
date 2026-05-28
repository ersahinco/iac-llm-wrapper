# Engineer Handoff Trial: Complete Landing Zone

Architect selected a standard AWS LZA hub-and-spoke landing zone. Engineer should be able to open
the generated handoff artifacts and find official LZA config files, lineage, runbook, and sample
recommendations.

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
