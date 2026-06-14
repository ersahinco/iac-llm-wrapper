# AWS LZA Downstream Validation

Owner-facing packet for the generated AWS LZA configuration bundle. Do not claim
owner validation until this checklist, exact validation command output, pipeline
output, schema/error output, or `lza-validation-evidence.yaml` reviewed by the
downstream owner exists.

## Packet To Send

- generated AWS LZA config files:
  `accounts-config.yaml`, `global-config.yaml`, `iam-config.yaml`,
  `network-config.yaml`, `organization-config.yaml`, and `security-config.yaml`
- `decision-report.yaml`
- `lineage-manifest.yaml`
- `handoff-plan.yaml`
- `plan-manifest.yaml` when present
- `lza-validation-evidence.yaml` when local validation has been run
- this checklist

Ask only whether the generated AWS LZA config bundle can enter the current AWS
LZA validation or pipeline path after normal manual gates.

## Checklist Template

```markdown
# AWS LZA Generated Config Bundle Owner Checklist

Reviewer:
Team:
Date:
LZA repo, pipeline, or validation path:
LZA version, schema version, or commit if known:
Generated bundle path or commit:

## Decision

- [ ] Accepted for the current LZA validation or pipeline path.
- [ ] Accepted with non-blocking notes.
- [ ] Rejected until blocking notes are resolved.
- [ ] Unable to assess with the provided packet.

## Reviewed Sections

- [ ] `homeRegion`
- [ ] `accounts-config.yaml`
- [ ] `global-config.yaml`
- [ ] `iam-config.yaml`
- [ ] `defaultVpc`
- [ ] `transitGateways`
- [ ] `transitGateways[].routeTables`
- [ ] `transitGateways[].shareTargets`
- [ ] `vpcs`
- [ ] `vpcs[].cidrs`
- [ ] `vpcs[].routeTables`
- [ ] `vpcs[].subnets`
- [ ] `vpcs[].natGateways`
- [ ] `vpcs[].transitGatewayAttachments`
- [ ] `centralNetworkServices`
- [ ] `organization-config.yaml`
- [ ] `security-config.yaml`
- [ ] Other:

## Required Owner Answers

Can this generated AWS LZA config bundle enter your current LZA validation or
pipeline path after normal manual gates?

Answer:

If no, what is blocking?

Answer:

What fields, sections, or relationships are missing for your current process?

Answer:

What fields or sections are present but shaped incorrectly?

Answer:

What LZA schema, package version, sample configuration, validator, command, or
pipeline did you compare against?

Answer:

Did the file produce schema, validation, or pipeline errors? Paste the exact
output if available.

Answer:

Are any notes non-blocking follow-up items rather than blockers?

Answer:

## Blocking Notes

1.
2.
3.

## Non-Blocking Notes

1.
2.
3.
```

## What Not To Do

- Do not infer owner validation from local YAML shape inspection.
- Do not mark plan readiness as owner-validated without the completed checklist,
  real command/schema/pipeline output, or owner-reviewed
  `lza-validation-evidence.yaml`.
- Do not run LZA synth, deploy, pipeline stages, cloud APIs, clone, or install
  steps from this project. `iac-llm-wrapper lza validate` is validation-only and
  requires an already-prepared local AWS LZA source checkout.
- Do not broaden AWS LZA schema depth unless the checklist exposes a real
  handoff blocker.
