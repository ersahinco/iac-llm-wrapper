# aws-lza-standard-v1

Thin-path AWS LZA fixture for commercial baseline handoff.

## Metadata

- Pattern: `aws-lza`
- Source contract: `aws-lza-sample-configuration`
- Upstream variant: `standard`
- Release: `2026-05-27`

## Decision highlights

- `baseline=standard`
- `org_mode=control-tower`
- `topology=hub-spoke`
- `enabled_regions=[eu-central-1]`
- `compliance_overlay=none`

## What to review

- Official-shape top-level LZA sections exist across six mandatory config files.
- IAM and network files keep empty official subsections (`identityCenterPermissionSets`, VPC `routeTables`/`subnets`) visible for handoff completion.
- Placeholder account emails remain synthetic and must be replaced before deployment.
- `security-config.yaml` enables foundational controls without regulated overlay standards.
