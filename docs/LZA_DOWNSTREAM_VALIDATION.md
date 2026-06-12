# AWS LZA Downstream Validation

Owner-facing packet for generated AWS LZA `network-config.yaml`. Do not claim
owner validation until this checklist, exact validation command output, pipeline
output, or schema/error output exists.

## Packet To Send

- generated `network-config.yaml`
- `decision-report.yaml`
- `lineage-manifest.yaml`
- `handoff-plan.yaml`
- `plan-manifest.yaml` when present
- this checklist

Ask only whether `network-config.yaml` can enter the current AWS LZA validation
or pipeline path after normal manual gates.

## Checklist Template

```markdown
# AWS LZA network-config.yaml Owner Checklist

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
- [ ] Other:

## Required Owner Answers

Can this `network-config.yaml` enter your current LZA validation or pipeline
path after normal manual gates?

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
- Do not mark plan readiness as owner-validated without the completed checklist
  or real command/schema/pipeline output.
- Do not add an LZA command runner until the owner provides the exact command and
  running it here becomes a deliberate product decision.
- Do not broaden AWS LZA schema depth unless the checklist exposes a real
  handoff blocker.
