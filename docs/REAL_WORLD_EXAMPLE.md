# Real-World Example: Payment Platform Landing Zone

This example demonstrates the full intent-driven flow for a PCI-DSS scoped payment platform.

## Design Document

See `fixtures/valid-payments.md` for the input design document.

## Step 1: Discover Signals and Gaps

```bash
iac-llm-wrapper discover -i fixtures/valid-payments.md --pattern baseline --addon pci-compliance
```

The tool will:
- Extract 16+ decisions from the Markdown
- Detect PCI-scope signals and suggest compliance requirements
- Show any gaps that need architect clarification

## Step 2: Diff Against Known-Good Catalog

```bash
# Compare extracted decisions against the financial-services catalog entry
iac-llm-wrapper catalog diff --entry lza-financial --input decisions.json
```

This shows where your design deviates from the proven financial-services pattern.

## Step 3: Compile to Decision Artifacts

```bash
iac-llm-wrapper compile -i fixtures/valid-payments.md -o out/ --pattern baseline --addon pci-compliance
```

Output includes:
- `decision-report.yaml` — all decisions with WA pillar coverage and audit trail
- `global-config.yaml` — organization and OU structure
- `accounts-config.yaml` — account definitions
- `network-config.yaml` — VPC, CIDR, topology
- `security-config.yaml` — audit, logging, encryption settings
- `iam-config.yaml` — permission boundaries and role prefixes
- `customizations-config.yaml` — VPC endpoints for private CI/CD
- `module-inputs.yaml` — mapped Terraform module variables
- `sample-recommendations.yaml` — persisted closest reference bundles for handoff

## Step 4: Engineer Handoff

Engineers use the decision artifacts alongside the sample configuration:

```bash
# Inspect matching sample configs for this pattern
iac-llm-wrapper sample list --pattern financial-services
iac-llm-wrapper sample list --tag regulated

# Show one sample config in detail
iac-llm-wrapper sample show --name lza-baseline-v1
```

The `module-inputs.yaml` provides pinned module references:
- `terraform-aws-modules/vpc/aws ~> 5.0` for networking
- `terraform-aws-modules/security-group/aws ~> 5.0` for security baseline

The generated `sample-recommendations.yaml` preserves closest reference bundles in the
handoff output so engineers can recover proven starting points later without re-running
the interview session.

Engineers apply these inputs to their Terraform/CDK/CloudFormation modules.

## What This Gives Each Stakeholder

| Stakeholder | What They Get |
|-------------|---------------|
| **Architect** | Guided interview surfaces gaps; tradeoffs and consequences are explicit; decision report is living documentation |
| **Compliance** | Audit trail with timestamps; compliance controls mapped to each decision; WA pillar coverage shows due diligence |
| **Engineer** | Clear, validated decision list; module-inputs.yaml maps directly to IaC modules; sample configs provide proven starting points |
| **Platform Team** | Catalog diff shows deviation from approved patterns; pattern registry enforces standard starting points |
