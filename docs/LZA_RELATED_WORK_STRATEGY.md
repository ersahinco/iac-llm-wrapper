# LZA Related Work Strategy

This project is the architecture-decision companion before AWS Landing Zone
Accelerator runs. It does not replace AWS LZA, Luminarlz, Terraform, Nuvibit
NTC, or deployment pipelines.

## What We Learn

- **AWS LZA and Universal Configuration** are the authority for downstream
  landing-zone deployment, sample baselines, and compliance evidence posture.
- **Luminarlz CLI** improves authoring ergonomics with templates, local LZA Core
  CLI access, synthesis, and an exit path back to raw LZA configuration.
- **Nuvibit NTC** frames landing zones as a productized platform with modular
  building blocks, strong developer experience, and implementation support.
- **Daily LZA operations** show the recurring friction: update diffs, pipeline
  failures, version drift, config complexity, account lifecycle, and knowing what
  changed before a long downstream run.

## What We Adopt

- Stay upstream of execution: turn architect prose into editable data models,
  accepted decisions, sample alignment, and reviewable handoff evidence.
- Treat AWS LZA as the downstream authority. This project prepares validated LZA
  configuration packets; owners still run their LZA validation and pipeline.
- Use external tools as product signals, not surfaces to duplicate. Adopt the
  useful perspectives: better authoring flow, clearer version/sample context,
  operator-focused review language, and explicit evidence boundaries.
- Prefer narrow improvements tied to owner evidence, decision validation, sample
  alignment, review clarity, or registered-target contract depth.

## What We Do Not Copy

- No LZA synth/deploy runner, Core CLI deployment wrapper, repository clone
  manager, or deployment path. A validation-only adapter may run the official
  local config validator and record evidence.
- No dashboard, broad plugin loader, or generic platform portal until repeated
  usage evidence shows review artifacts are insufficient.
- No broad AWS LZA schema expansion from curiosity. Add schema depth only when a
  downstream owner checklist, command output, or pipeline error exposes a real
  handoff blocker.
- No claim that AWS Universal Configuration or the Compliance Workbook is owner
  validation for generated artifacts.

## Ordered Backlog

1. **Owner validation signal**: send `docs/LZA_DOWNSTREAM_VALIDATION.md` with a
   generated `network-config.yaml` and capture a completed checklist, exact LZA
   command output, pipeline output, or schema/error output before claiming owner
   validation.
2. **Validation-only evidence**: run the official local LZA config validator
   against generated config files when the user supplies an existing LZA source
   checkout and development toolchain. Record command output as evidence only.
3. **Version and sample awareness, not execution**: surface the LZA
   baseline/sample source used by generated bundles when known. Do not clone LZA
   repositories, install dependencies, synthesize, deploy, or run pipelines.
4. **Daily-ops review language**: improve static review guidance around update
   drift, pipeline failure ownership, account lifecycle, and config sections
   requiring owner review.

## Source Threads

- [AWS Universal Configuration and Compliance Workbook](https://aws.amazon.com/blogs/security/introducing-the-landing-zone-accelerator-on-aws-universal-configuration-and-lza-compliance-workbook/)
- [AWS Landing Zone Accelerator vs Nuvibit NTC](https://manuel-vogel.de/posts/2025-09-03-aws-landing-zone-accelerator-deep-vs-nuvibit-ntc/)
- [Using AWS Luminarlz CLI for LZA](https://manuel-vogel.de/posts/2025-11-09-using-aws-luminarlz-cli-for-the-landing-zone-accelerator/)
- [AWS Luminarlz CLI README](https://github.com/superluminar-io/aws-luminarlz-cli/tree/v0.0.44)
- [AWS Landing Zone Accelerator setup](https://manuel-vogel.de/posts/2023-07-01-setup-landing-zone-accelerator/)
- [Daily working with AWS LZA](https://manuel-vogel.de/posts/2024-07-30-daily-working-with-the-landing-zone-accelerator/)
- [Daily working with AWS LZA, part 2](https://manuel-vogel.de/posts/2024-11-17-daily-working-with-the-landing-zone-accelerator-part2/)
