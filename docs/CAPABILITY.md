# iac-llm-wrapper Capability

## What This Tool Actually Does

`iac-llm-wrapper` is an intent-to-IaC orchestration framework. The shipped core
is `intent-engine`: today it wraps LLM extraction with deterministic decision
validation and emits handoff artifacts. Future target adapters can wrap module
generation or controlled IaC execution, but only after graph, contract, and gate
checks pass.

### With LLM (Full Capability)

When an LLM backend is available (OpenAI, Anthropic, or local Ollama):

1. **Reads design prose** from Markdown documents
2. **Extracts structured decisions** using the requirement graph as schema
3. **Detects signals** from text, such as regulated data or hybrid connectivity
4. **Fills gaps** through guided interview
5. **Validates** against graph rules, model rules, and target contracts
6. **Emits handoff artifacts** for existing accelerators, modules, or pipelines
7. **Can later drive target adapters** for module generation or controlled execution

### Without LLM (Bootstrap Only)

When no LLM is available (`INTENT_ENGINE_DISABLE_LLM=1`):

1. **Applies graph defaults** deterministically
2. **Validates** against graph rules
3. **Emits** handoff artifacts from defaults plus any explicit decisions
4. **Signal detection** still works on text via keyword matching
5. **Structured Markdown entity sections** can recover named accounts, OUs, and workloads

**Important**: This is not a production extraction path. A complex narrative design document fed into the tool without an LLM produces defaults plus explicitly structured entities, not the full architect intent. The deterministic fallback is for unit tests, CI bootstrapping, and quick validation only.

## Decision Record → Engineer Handoff

For `aws-lza`, the tool produces official-style AWS LZA handoff files plus lineage and
runbook artifacts. No Terraform/Terragrunt landing-zone stack is emitted by default.

For BYOM module patterns such as `terraform-vpc`, the tool produces
`module-inputs.yaml` for the owning provisioning system:

```yaml
moduleInputs:
  - moduleName: terraform-aws-vpc
    source: terraform-aws-modules/vpc/aws
    version: "~> 5.0"
    variables:
      name: orders-vpc
      cidr: 10.30.0.0/16
      enable_nat_gateway: true
```

For `cloudformation-parameters`, the tool emits parameter handoff for an
approved existing template, not a generated stack.

Engineer workflow:
1. Review `decision-report.yaml` for readiness, blockers, and decisions
2. Use AWS LZA config files directly when pattern is `aws-lza`
3. Copy `module-inputs.yaml` variables into module calls when a pattern emits module inputs
4. Reference `source` and `version` for module pinning when provided
5. Use `lineage-manifest.yaml` for traceability
6. Use `sample-recommendations.yaml` for persisted reference-bundle guidance
7. Use `handoff-plan.yaml` for owners, ordering, manual gates, rollback, and boundary
8. Use `llm-trace-summary.yaml` to audit provider/model calls, raw and accepted
   decisions, gaps, contradictions, and raw evidence status
9. Validate blocked compile output against `blocked-assessment-artifacts`

## Sample Config Registry

Versioned, pinned sample configurations provide proven starting points:

```bash
# List available sample configs
iac-llm-wrapper sample list

# Filter by tag or contract
iac-llm-wrapper sample list --tag regulated
iac-llm-wrapper sample list --contract aws-lza-sample-configuration

# Show AWS LZA sample contract metadata and decisions
iac-llm-wrapper sample show --name aws-lza-standard-v1

# Inspect required artifacts and lineage for a contract-backed pattern
iac-llm-wrapper contract show --pattern aws-lza
```

`compile` and `interview` also print closest sample matches for the chosen pattern.
Architects can start from proven variants. Engineers can inspect source contract
metadata without re-running discovery.

## Signal Detection

Signal detection is pattern-owned. Signals can make graph decisions more explicit
or add review context, but only requirement keys that exist in the selected graph
can block handoff. Model-invented findings remain trace evidence in
`llm-trace-summary.yaml`.

## Reference Entries

| Reference Entry | Pattern | Use Case | Contract / Module References |
|---------------|---------|----------|-------------------|
| `aws-lza-standard-v1` | aws-lza | Standard Control Tower landing zone | AWS LZA sample configuration |
| `aws-lza-regulated-v1` | aws-lza | Regulated Control Tower landing zone | AWS LZA sample configuration |
| `aws-lza-healthcare-v1` | aws-lza | Healthcare landing zone | AWS LZA sample configuration |
| `k8s-cluster-v1` | kubernetes-cluster | EKS-style cluster handoff | Terraform EKS/VPC module refs |
| `terraform-vpc-basic-v1` | terraform-vpc | BYOM VPC module handoff | Terraform VPC module refs |

## Known Limitations (Honest Scope)

1. **LLM extraction quality depends on the model**: GPT-4 class models work well; smaller local models handle standard fields reliably but can miss complex workload details in long documents.
2. **Deterministic fallback is limited extraction**: Without LLM, graph defaults apply and structured Markdown sections can recover named accounts, OUs, and workloads. It still cannot interpret arbitrary free-form prose. This is a bootstrap path, not production.
3. **Current paths do not emit deployable IaC**: `aws-lza` emits accelerator handoff files; module patterns emit variables for existing IaC modules. Future target adapters may generate or execute IaC only behind graph, contract, and gate checks.
4. **Module refs are references, not implementations**: Module refs point to public Terraform registry modules as examples. Organizations maintain their own module libraries.

## Next Capability Improvements

- More sample configs with real module variable schemas
- Signal expansion only when it maps to current pattern graph requirements
