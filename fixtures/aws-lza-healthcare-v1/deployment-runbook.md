# AWS LZA Deployment Runbook

## Inputs

- Baseline: `healthcare`
- Organization mode: `control-tower`
- Home region: `eu-central-1`
- Enabled regions: `eu-central-1`

## LZA Config Contract

Mandatory configuration files:

- `accounts-config.yaml`
- `global-config.yaml`
- `iam-config.yaml`
- `network-config.yaml`
- `organization-config.yaml`
- `security-config.yaml`

Optional configuration files are emitted only when custom target contracts require them:

- `customizations-config.yaml`
- `replacements-config.yaml`

## Sequence

1. Confirm AWS Organizations or Control Tower baseline matches `org_mode`.
2. Review generated LZA configuration files and compare with AWS sample baseline.
3. Replace placeholder account emails before deployment.
4. Populate customer-specific Identity Center assignments, VPC route tables/subnets, and optional security exports.
5. Run AWS LZA deployment using its documented installer and pipeline.
6. Preserve `decision-report.yaml`, `decision-audit.yaml`, and `lineage-manifest.yaml` as handoff evidence.

## Boundary

This handoff does not generate a parallel Terraform or Terragrunt landing-zone stack.
Use AWS LZA for landing-zone deployment unless a documented gap requires custom IaC.
