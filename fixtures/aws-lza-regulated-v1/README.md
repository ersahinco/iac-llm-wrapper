# aws-lza-regulated-v1

Thin-path AWS LZA fixture for regulated commercial path.

## Metadata

- Pattern: `aws-lza`
- Source contract: `aws-lza-sample-configuration`
- Upstream variant: `standard`
- Release: `2026-05-27`

## Decision highlights

- `baseline=standard`
- `org_mode=control-tower`
- `topology=hub-spoke`
- `enabled_regions=[eu-central-1, eu-west-1]`
- `compliance_overlay=regulated`

## What to review

- `security-config.yaml` adds `NIST Special Publication 800-53 Revision 5` beside AWS foundational standard in Security Hub.
- Macie sensitive-data publishing flips on for regulated path.
- Placeholder account emails still require engineer replacement before deployment.
