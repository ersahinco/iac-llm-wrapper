# AWS LZA Deployment Runbook

## Inputs

- Baseline: `standard`
- Organization mode: `control-tower`
- Home region: `eu-central-1`
- Enabled regions: `eu-central-1, eu-west-1`

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

## Recommended Sample Configs

Ranked recommendations are also persisted in `sample-recommendations.yaml`.

- `aws-lza-regulated-v1`: 14/14 decisions match, 0 differ, fixture `aws-lza-regulated-v1/`
- `aws-lza-standard-v1`: 12/13 decisions match, 1 differ, fixture `aws-lza-standard-v1/`
- `aws-lza-healthcare-v1`: 10/14 decisions match, 4 differ, fixture `aws-lza-healthcare-v1/`

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
