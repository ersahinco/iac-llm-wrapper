# aws-lza-healthcare-v1

AWS LZA fixture for healthcare-oriented handoff with HIPAA-style review focus.

## Metadata

- Pattern: `aws-lza`
- Source contract: `aws-lza-sample-configuration`
- Upstream variant: `healthcare`
- Release: `2026-05-27`

## Decision highlights

- `baseline=healthcare`
- `org_mode=control-tower`
- `topology=hub-spoke`
- `workload_accounts=[ClinicalProd]`
- `compliance_overlay=healthcare`

## What to review

- `decision-report.yaml` should show healthcare baseline plus healthcare overlay.
- Global and network files keep official handoff subsections visible (`cdkOptions`, log-bucket lifecycle arrays, VPC `routeTables`/`subnets`, central network service placeholders).
- `security-config.yaml` keeps AWS foundational controls and adds `NIST Special Publication 800-53 Revision 5`.
- Fixture models PHI-sensitive path but still stops at LZA handoff artifacts, not workload IaC generation.
