# Architect Workshop Notes: Incomplete Landing Zone

The company wants a hub-and-spoke AWS landing zone for regulated workloads. Security wants
centralized logging, private delivery pipelines, and no public S3 exposure. Platform team has not
yet named the central network account in the notes.

## Region

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

- workload_accounts: Prod
- audit_account: Audit
- log_archive_account: LogArchive
- security_tooling_account: SecurityTooling

## Network

- topology: hub-spoke
- network_cidr: 10.50.0.0/16

## Security

- audit_retention_days: 2555
- centralized_logging: true
- security_hub_enabled: true
- guardduty_enabled: true
