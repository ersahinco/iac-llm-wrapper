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

## Recommended Sample Configs

Ranked recommendations are also persisted in `sample-recommendations.yaml`.

- `aws-lza-healthcare-v1`: 16/16 decisions match, 0 differ, fixture `aws-lza-healthcare-v1/`
- `aws-lza-standard-v1`: 11/15 decisions match, 4 differ, fixture `aws-lza-standard-v1/`
- `aws-lza-regulated-v1`: 10/16 decisions match, 6 differ, fixture `aws-lza-regulated-v1/`

## Sequence

1. Platform owner confirms AWS Organizations or Control Tower baseline matches `org_mode`.
2. Network owner reviews generated LZA network config against approved CIDR plan.
3. Security owner reviews logging, Security Hub, GuardDuty, and delegated admin decisions.
4. Populate customer-specific Identity Center assignments and permission sets; identity owner approves delegated admin.
5. Release owner replaces placeholder account emails before deployment.
6. Platform owner populates customer-specific VPC route tables/subnets, TGW attachments, and optional security exports.
7. Manual gate: approve `decision-report.yaml`, `lineage-manifest.yaml`, and LZA diff.
8. Run AWS LZA deployment using its documented installer and pipeline.
9. Preserve `decision-report.yaml`, `decision-audit.yaml`, and `lineage-manifest.yaml` as handoff evidence.
10. Rollback note: revert through AWS LZA pipeline history; do not hand-edit generated artifacts.

## Manual Gates

- Architecture owner approves unresolved decisions are zero.
- Security owner approves logging/security services and IAM Identity Center scope.
- Network owner approves CIDRs, TGW attachments, and routing boundaries.
- Release owner confirms AWS LZA pipeline prereqs and rollback owner.

## Dependencies

- AWS Organizations or Control Tower baseline exists before LZA deploy.
- Account vending/email ownership complete before accounts config deploy.
- Identity Center delegated admin exists before IAM config deploy.
- Network CIDR/IPAM plan approved before network config deploy.

## Rollback

- Stop AWS LZA pipeline before re-running with corrected config.
- Revert to previous known-good LZA config commit.
- Keep generated reports as evidence; regenerate after decision changes.

## Boundary

This handoff does not generate a parallel Terraform or Terragrunt landing-zone stack.
Use AWS LZA for landing-zone deployment unless a documented gap requires custom IaC.
