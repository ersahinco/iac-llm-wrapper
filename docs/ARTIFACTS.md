# Handoff Artifacts

`iac-llm-wrapper` emits portable files for review and registered deployment
targets. These artifacts are target configuration artifacts, not deployments.
Existing deployment mechanisms remain downstream.

| Artifact | Purpose | Owner | Emitted When | Deployable |
| --- | --- | --- | --- | --- |
| `decision-report.yaml` | Accepted decisions, handoff readiness, blockers, safe handoff path, and pattern-owned semantic model details when available. | Core + pattern | Every compile, including blocked compiles. | No |
| `context-manifest.yaml` | Code-owned context inventory: pattern metadata, prompt context digest/text, requirement graph, target contracts, samples, target capabilities, runtime extraction summary, expected artifacts, and guardrails. | Core | Pattern-backed successful handoffs. | No |
| `handoff-plan.yaml` | Ordered review/handoff steps, owners, dependencies, manual gates, rollback, boundary, `handoffAllowed`, and allowed next action. | Core | Contract-backed successful handoffs. | No |
| `plan-manifest.yaml` | Registered target plan metadata: immutable input artifacts, plan readiness, plan-only command text, expected plan outputs, blockers, and no-apply boundary. | Pattern + core contract | Plan-ready registered targets such as AWS LZA. | No |
| `replay-manifest.yaml` | Source, target contract, and artifact digests for deterministic replay and bundle comparison. | Core | Plan-ready registered targets. | No |
| `missing-inputs.yaml` | Durable architect/client question packet for blocked compiles, keyed by requirement graph nodes. | Core | Blocked compiles. | No |
| `llm-trace-summary.yaml` | Provider/model, latency, raw and accepted decisions, applied decisions, gaps, contradictions, and raw evidence status. | Core | Every compile. | No |
| `model-benchmark.yaml` | Mode, provider/model, latency, token availability, raw LLM coverage, conformance, quality counts, readiness, cost status, and external-observability boundary. | Core | Every compile. | No |
| `input-diff-report.yaml` | Changed headings, changed structured decision lines, likely impacted requirements, and scoped hunks for an incremental document update. | Core incremental compile | `compile --baseline-bundle --changed-doc`. | No |
| `incremental-compile-report.yaml` | Reused, changed, added, removed, carried-forward, and re-confirmation decision summary for diff-aware compile. | Core incremental compile | `compile --baseline-bundle --changed-doc`. | No |
| `contract-validation.yaml` | Standalone pass/fail validation of emitted artifacts against target contracts. | Core review tooling | `iac-llm-wrapper review html`. | No |
| `target-capability-graph.yaml` | Downstream target coverage, selected target path, manual gates, and unsupported asks represented as semantic facts with evidence spans. | Pattern-owned target report builder | AWS LZA today; future patterns only when they own comparable target routing. | No |
| `handoff-comparison.yaml` | Compact before/after bundle delta for incremental packet or sample updates: readiness, requirement completeness, decisions, blockers, artifacts, model quality, and sample recommendations. | Core review tooling | `iac-llm-wrapper review compare --output`. | No |
| `handoff-comparison.html` | Static delta review page for what changed, what stayed stable, and what must be reviewed. | Core review tooling | `iac-llm-wrapper review compare --html-output`. | No |
| `lza-validation-evidence.yaml` | Validation-only AWS LZA config-validator command, no-mutation/read-only lookup boundary, temporary-staging/replay boundary, source metadata, config digests, exit code, diagnostic summary, and captured stdout/stderr. | AWS LZA validation adapter | `iac-llm-wrapper lza validate`. | No |
| `battle-summary.yaml` | Battle-test verdict, confidence categories, findings, and improvement items. | Battle harness | `scripts/battle-test.py`. | No |
| `handoff-review.html` | Static human review page summarizing readiness, contract status, allowed next action, reviewer next actions, blocker traceability, raw LLM coverage, expected weaknesses, graph, evidence, benchmark, contract validation, handoff plan, and target artifacts. | Core review tooling | `iac-llm-wrapper review html`. | No |
| `requirement-graph.json` | Machine-readable graph export for external viewers and tools. | Core review tooling | `iac-llm-wrapper review html` or `graph export`. | No |
| `requirement-graph.mmd` | Mermaid graph export for lightweight visual inspection. | Core review tooling | `iac-llm-wrapper review html` or `graph export`. | No |
| Pattern-specific target configuration files | Target-shaped config or parameter handoff, such as AWS LZA YAML or CloudFormation parameters. | Pattern | Successful contract-backed handoffs. | No |

## Consumers

- Architects use `decision-report.yaml`, `context-manifest.yaml`, `handoff-plan.yaml`, and
  `handoff-review.html` to understand readiness and blockers.
- AWS LZA reviewers can inspect `decision-report.yaml.semanticModel` for typed
  entities, relationships, and predicate constraint results.
- Platform engineers use pattern-specific target configuration files, deployment
  target contracts, lineage, and the allowed next action.
- Plan reviewers use `plan-manifest.yaml` and `replay-manifest.yaml` to see
  whether a registered target has enough immutable input for a downstream
  plan/diff without interpretation. These files do not invoke the plan.
- Reviewers use `handoff-comparison.yaml` to inspect only the deltas from an
  incremental document or sample-configuration update.
- Contributors use `context-manifest.yaml`, `llm-trace-summary.yaml`, `model-benchmark.yaml`,
  `battle-summary.yaml`, and eval results to improve extraction and model value.
- LLM reviewers may keep `raw-evidence.yaml` in local development/debug bundles,
  but it is not a required service artifact. Use `--no-raw-evidence` when raw
  prompts and responses should not be stored.
- Secret inputs should appear only as secret-store references with expected
  parameter names, never as secret values in raw evidence or handoff artifacts.
- External UI or observability projects may read these files, but this repo stays
  CLI- and artifact-first.

## Boundary

Artifacts may describe a downstream delivery path, but they do not run Terraform,
CloudFormation, AWS LZA deploy/synth commands, Kubernetes, pipelines, or cloud
mutation. The AWS LZA validation adapter may run the official local config
validator against generated config files and record evidence, but it must not
clone, install, synth, deploy, or mutate AWS. Depending on the AWS LZA version
and local validation path, the official validator may perform read-only AWS
account lookup through the provided AWS/LZA context. AWS LZA YAML is a target
configuration artifact consumed by the downstream LZA deployment process. A
blocked bundle must remain review-only until graph and contract blockers are
resolved.
