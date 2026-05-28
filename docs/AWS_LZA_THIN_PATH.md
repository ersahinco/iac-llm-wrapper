# AWS LZA Thin Path

## Goal

Build `iac-llm-wrapper` as a thin, model-driven intent layer for AWS Landing Zone
Accelerator (LZA). The tool should gather requirements, validate decisions, emit
handoff artifacts, and reuse existing accelerators or modules wherever they already
solve the implementation problem.

This is not an AWS IaC generator by default. It can support IaC generation later when
the selected target needs it, but LZA already provides the deployment engine for the
landing-zone baseline.

## Principles

- Use ubiquitous language from architects, engineers, and the target accelerator.
- Treat existing sample configurations and module schemas as data models.
- Derive questions, validation, and outputs from models rather than hand-written flow.
- Keep provider-specific orchestration explicit instead of pretending clouds are identical.
- Prefer existing accelerators and modules over custom generated IaC.
- Add custom IaC generation only when no existing accelerator or module covers the need.
- Keep the first AWS scope narrow: LZA before custom workloads.

## Data Model View

An accelerator sample configuration is a contract:

- required inputs
- optional inputs
- defaults
- output files or resources
- deployment prerequisites
- ordering constraints
- cross-reference rules

For AWS LZA, the sample configurations provide the first contract. The thin path should
parse or encode the parts of that contract needed for requirement gathering and handoff.
AWS documents six mandatory configuration files:

- `accounts-config.yaml`
- `global-config.yaml`
- `iam-config.yaml`
- `network-config.yaml`
- `organization-config.yaml`
- `security-config.yaml`

`customizations-config.yaml` and `replacements-config.yaml` are optional target-contract
extensions. They should be emitted only when a selected use case needs custom
applications, third-party appliances, CloudFormation stacks, or replacement values.

For other use cases, teams can bring their own module or accelerator contract:

- LZA sample configuration
- Terraform module schema
- organization module catalog
- Kubernetes chart values schema
- custom Pydantic model

The framework should ask only the questions required by the selected contract and emit
only the artifacts that contract needs.

## Where the Graph Fits

The data model defines shape. The requirement graph defines behavior.

Use the source contract to derive:

- fields
- types
- defaults
- target artifacts
- schema-level required values

Use the requirement graph to manage:

- dependency order
- applies-if branching
- blocked decisions
- cascade rules
- fail-closed gaps
- deployment and handoff ordering
- decision provenance

Example: `network_account` is a field in the model, but the graph knows it is required
only when `topology == hub-spoke`. Likewise, optional customizations are not part of the
default LZA handoff, but a custom resource contract can introduce new graph nodes that
emit `customizations-config.yaml` and orchestration notes.

## Architecture Shape

```text
source contract
  -> data model
  -> requirement graph
  -> extraction and interview
  -> normalized intent
  -> validators
  -> target-specific artifacts
  -> handoff bundle
```

Target-specific artifacts vary:

- AWS LZA: LZA YAML configuration, lineage manifest, decision report, deployment runbook
- Terraform module: variables file, module input mapping, dependency notes
- custom workload: generated IaC only when the contract requires it

Provider-specific orchestration lives at the target layer. Core remains generic.

## Inspect Contracts

Contracts are first-class CLI objects. Architects and engineers can inspect the target
before generating artifacts:

```bash
intent-engine contract list
intent-engine contract show --pattern aws-lza
```

This shows required artifacts, optional artifacts, required YAML paths, required
decisions, source URL, value assertions, and decision-to-artifact lineage. The command
reads registered contract metadata rather than hardcoding AWS LZA details.

## Current Fixture Variants

Current AWS LZA review fixtures live under `fixtures/`:

- `aws-lza-standard-v1`: commercial Control Tower baseline, no compliance overlay
- `aws-lza-regulated-v1`: commercial baseline plus regulated overlay and extra Security Hub standard
- `aws-lza-healthcare-v1`: healthcare baseline plus healthcare overlay and PHI-oriented account naming

Each fixture directory includes generated handoff artifacts plus a short `README.md`
describing source contract, upstream variant, and review expectations.
Refresh all sample fixture bundles with `uv run python scripts/sync-sample-fixtures.py`.
Use `--check` in CI or local review to catch stale generated files.

## Borrow From rxt-code-accelerator

Useful ideas:

- Pydantic spec discipline
- graph validation before handoff
- lineage manifest from input decision to emitted artifact path
- preflight checks for tools, prerequisites, and required inputs
- golden tests for generated artifacts
- handoff packaging for engineers

Avoid importing:

- Azure Terragrunt generator shape
- AVM wrapper parity as an AWS default
- portal complexity before the CLI path is proven
- broad cloud-neutral abstractions that hide provider-specific contracts
- custom IaC generation where LZA or established modules already solve the problem

## AWS LZA MVP

MVP should produce a useful handoff without owning deployment:

- `aws-lza` pattern
- `AwsLzaIntent` Pydantic model
- LZA sample references
- requirements for organization, accounts, OUs, regions, network, logging, security,
  IAM, CI/CD, and compliance overlay
- validators for cross-file references and missing required decisions
- LZA YAML emitter for the six mandatory configuration files
- `lineage-manifest.yaml` mapping decisions to emitted files, required artifact paths,
  and YAML lineage paths
- `decision-report.yaml` with audit trail and rationale
- `sample-recommendations.yaml` with persisted closest sample-config matches for handoff
- `deployment-runbook.md` with prerequisites and sequence
- generated-artifact validation that fails closed when required paths, asserted values,
  or lineage paths disappear from emitted YAML

Current emitted YAML targets official LZA-style top-level sections such as:

- `accounts-config.yaml`: `mandatoryAccounts`, `workloadAccounts`
- `global-config.yaml`: `homeRegion`, `enabledRegions`, `controlTower`, `cdkOptions`, `logging`
- `iam-config.yaml`: `homeRegion`, `identityCenter`
- `network-config.yaml`: `defaultVpc`, `centralNetworkServices`, `transitGateways`, `vpcs`
- `organization-config.yaml`: `enable`, `organizationalUnits`, policy lists
- `security-config.yaml`: `accessAnalyzer`, `iamPasswordPolicy`, `awsConfig`, `cloudWatch`, `centralSecurityServices`

Current emitted substructures stay close to upstream LZA shapes instead of hiding them behind
custom wrapper fields:

- `iam-config.yaml`: `identityCenterPermissionSets`, `identityCenterAssignments`
- `network-config.yaml`: VPC `enableDnsHostnames`, `enableDnsSupport`, `routeTables`, `subnets`,
  `natGateways`, `transitGatewayAttachments`, and `tags`; hub-spoke handoff also includes
  Transit Gateway `shareTargets`, central network service placeholders for IPAM, Route 53
  Resolver, Network Firewall, and Gateway Load Balancers
- `global-config.yaml`: `terminationProtection`, CDK bucket/role options, SNS topic/tag arrays,
  centralized logging region, and empty lifecycle-rule lists for central and access log buckets
- `security-config.yaml`: GuardDuty `autoEnableOrgMembers`, `overrideExisting`,
  `exportFrequency`, `s3Protection`, `eksProtection`, and empty `lifecycleRules`;
  Security Hub `autoEnableOrgMembers`, `regionAggregation`, `snsTopicName`,
  `notificationLevel`, and standards with `deploymentTargets` plus `controlsToDisable`;
  `scpRevertChangesConfig`, `snsSubscriptions`, `ssmAutomation.excludeRegions`,
  and Macie publishing frequency

Default handoff stays lean: no fake policy files, no synthetic customizations bundle, no parallel
Terraform/Terragrunt landing-zone stack.

The deployment sequence should reference AWS LZA and Control Tower prerequisites instead
of generating a parallel Terragrunt deployment path.

## Later Workloads

After LZA is complete, workload support can use the same contract model:

- If a workload maps to an existing Terraform module, emit module inputs and dependency
  notes.
- If a workload requires custom resources, enable a provider-specific generator for that
  target only.
- If deployment orchestration is required, derive ordering from the same requirement and
  dependency model used for validation.

This keeps custom generation as a feature, not the default architecture.

## Acceptance Tests

- Adding `aws-lza` does not require changes to core extraction, interview, validation,
  normalization, or generation modules.
- An AWS LZA sample fixture compiles to LZA YAML, decision report, lineage manifest, and
  runbook.
- A regulated fixture selects the correct overlay decisions and fails closed when required
  accounts or controls are missing.
- Generated LZA artifacts are covered by golden tests.
- Validator catches cross-reference errors before handoff.

## Sources

- AWS LZA configuration files:
  https://docs.aws.amazon.com/solutions/latest/landing-zone-accelerator-on-aws/using-configuration-files.html
- AWS LZA configuration reference:
  https://awslabs.github.io/landing-zone-accelerator-on-aws/latest/user-guide/config/
- AWS LZA sample configurations:
  https://awslabs.github.io/landing-zone-accelerator-on-aws/latest/sample-configurations/
