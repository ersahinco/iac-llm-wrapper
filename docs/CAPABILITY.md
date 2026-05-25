# iac-llm-wrapper Real-World Capability

## What This Tool Actually Does

This is a **decision capture and validation engine** for infrastructure design. It sits between architecture documents and IaC implementation.

### With LLM (Full Capability)

When an LLM backend is available (OpenAI, Anthropic, or local Ollama):

1. **Reads unstructured prose** from Markdown design documents
2. **Extracts structured decisions** using the requirement graph as a schema
3. **Detects signals** from text (e.g., "PCI-DSS" → suggests compliance requirements)
4. **Fills gaps** via guided interview with tradeoffs and consequences
5. **Validates** against graph rules (fail-closed)
6. **Generates** decision artifacts engineers map to IaC modules

### Without LLM (Bootstrap Only)

When no LLM is available (`INTENT_ENGINE_DISABLE_LLM=1`):

1. **Applies graph defaults** deterministically
2. **Validates** against graph rules
3. **Generates** decision artifacts from defaults + any explicit `--decisions` JSON
4. **Signal detection** still works on text via keyword matching

**Important**: This is not a production extraction path. A complex design document fed into the tool without an LLM produces default values, not the architect's intent. The deterministic fallback is for unit tests, CI bootstrapping, and quick validation only.

## Decision Artifact → IaC Module Mapping

The tool produces `module-inputs.yaml` which engineers use with their provisioning system:

```yaml
moduleInputs:
  - moduleName: lza-network
    source: terraform-aws-modules/vpc/aws
    version: "~> 5.0"
    variables:
      cidr: 10.0.0.0/16
      hub_cidr: 10.0.0.0/20
      enable_nat_gateway: true
      enable_vpn_gateway: false
  - moduleName: lza-security-baseline
    source: terraform-aws-modules/security-group/aws
    version: "~> 5.0"
    variables:
      audit_retention_days: 2555
      block_public_access: true
      enable_cloudtrail: true
```

Engineers:
1. Copy the `variables` block into their Terraform module call
2. Reference the `source` and `version` for module pinning
3. Use `decision-report.yaml` for compliance audit trails
4. Follow `deployment-graph.yaml` for phased rollout order

## Sample Config Registry

Versioned, pinned sample configurations provide proven starting points:

```bash
# List available sample configs
iac-llm-wrapper catalog list

# Show config with module references
iac-llm-wrapper catalog show --entry lza-baseline

# Diff current decisions against a proven config
iac-llm-wrapper catalog diff --entry lza-financial --input decisions.json

# Apply catalog defaults to current decisions
iac-llm-wrapper catalog apply --entry lza-baseline --input current.json --output merged.json
```

## Signal Detection in Action

When analyzing design documents, the tool detects architectural signals from text:

| Signal Keyword | Triggered Requirement | Context |
|----------------|---------------------|---------|
| "PCI-DSS", "payment card" | `cicd_mode`, `egress_inspection` | Regulated industry needs private CI/CD |
| "on-prem", "Active Directory" | `hybrid_required`, `hybrid_dns_model` | Hybrid connectivity requirements |
| "SAP", "Oracle" | `network_segmentation`, `kms_key_spec` | Enterprise workload patterns |
| "multi-cloud", "GCP" | `network_segmentation`, `data_residency` | Cross-cloud governance |

## Catalog Entries

| Catalog Entry | Pattern | Use Case | Module References |
|---------------|---------|----------|-------------------|
| `lza-minimal` | minimal | 1-2 accounts, no compliance | VPC module |
| `lza-baseline` | baseline | Standard enterprise, 5+ accounts | VPC, security-group |
| `lza-hybrid-enterprise` | hybrid-enterprise | On-prem + strict egress | VPC, security-group, Direct Connect |
| `lza-financial` | financial-services | PCI-DSS, SOX, payment data | VPC, security-group, KMS HSM |
| `lza-healthcare` | healthcare | HIPAA, PHI, BAA | VPC, security-group, PHI logging |

## Known Limitations (Honest Scope)

1. **LLM extraction quality depends on the model**: GPT-4 class models work well; smaller local models (3B) handle standard fields reliably but may miss complex lists (accounts, OUs, workloads).
2. **Deterministic fallback is not real extraction**: Without LLM, only graph defaults apply. It cannot parse free-form prose. This is a bootstrap path, not production.
3. **Does not generate deployable IaC**: Output is decision artifacts + module variable mappings. Engineers still write Terraform/CDK/CloudFormation.
4. **Catalog modules are references, not implementations**: Module refs point to public Terraform registry modules as examples. Organizations maintain their own module libraries.

## Next Capability Improvements

- Better deterministic markdown extractor for accounts/OU/workload parsing (complement to LLM, not replacement)
- More sample configs with real module variable schemas
- Catalog diff visualization (not just JSON)
- Decision report → Terraform variable file generator
- Pattern-specific signal keyword expansion
