# Handoff Artifacts

`iac-llm-wrapper` emits portable files for review and downstream IaC toolchains.
These artifacts are not deployments unless a future pattern explicitly owns that
execution path and passes graph, contract, gate, evidence, and rollback checks.

| Artifact | Purpose | Owner | Emitted When | Deployable |
| --- | --- | --- | --- | --- |
| `decision-report.yaml` | Accepted decisions, handoff readiness, blockers, and safe handoff path. | Core + pattern | Every compile, including blocked compiles. | No |
| `handoff-plan.yaml` | Ordered review/handoff steps, owners, dependencies, manual gates, rollback, boundary, `handoffAllowed`, compatibility `deploymentAllowed`, and allowed next action. | Core | Contract-backed successful handoffs. | No |
| `llm-trace-summary.yaml` | Provider/model, latency, raw and accepted decisions, applied decisions, gaps, contradictions, and raw evidence status. | Core | Every compile. | No |
| `model-benchmark.yaml` | Mode, provider/model, latency, token availability, raw LLM coverage, conformance, quality counts, readiness, cost status, and external-observability boundary. | Core | Every compile. | No |
| `input-diff-report.yaml` | Changed headings, changed structured decision lines, likely impacted requirements, and scoped hunks for an incremental document update. | Core incremental compile | `compile --baseline-bundle --changed-doc`. | No |
| `incremental-compile-report.yaml` | Reused, changed, added, removed, carried-forward, and re-confirmation decision summary for diff-aware compile. | Core incremental compile | `compile --baseline-bundle --changed-doc`. | No |
| `contract-validation.yaml` | Standalone pass/fail validation of emitted artifacts against target contracts. | Core review tooling | `iac-llm-wrapper review html`. | No |
| `handoff-comparison.yaml` | Compact before/after bundle delta for incremental packet or sample updates: readiness, requirement completeness, decisions, blockers, artifacts, model quality, and sample recommendations. | Core review tooling | `iac-llm-wrapper review compare --output`. | No |
| `handoff-comparison.html` | Static delta review page for what changed, what stayed stable, and what must be reviewed. | Core review tooling | `iac-llm-wrapper review compare --html-output`. | No |
| `battle-summary.yaml` | Battle-test verdict, confidence categories, findings, and improvement items. | Battle harness | `scripts/battle-test.py`. | No |
| `handoff-review.html` | Static human review page summarizing readiness, contract status, allowed next action, reviewer next actions, blocker traceability, raw LLM coverage, expected weaknesses, graph, evidence, benchmark, contract validation, handoff plan, and target artifacts. | Core review tooling | `iac-llm-wrapper review html`. | No |
| `requirement-graph.json` | Machine-readable graph export for external viewers and tools. | Core review tooling | `iac-llm-wrapper review html` or `graph export`. | No |
| `requirement-graph.mmd` | Mermaid graph export for lightweight visual inspection. | Core review tooling | `iac-llm-wrapper review html` or `graph export`. | No |
| Pattern-specific handoff files | Target-shaped config or parameter handoff, such as AWS LZA YAML or CloudFormation parameters. | Pattern | Successful contract-backed handoffs. | No by default |

## Consumers

- Architects use `decision-report.yaml`, `handoff-plan.yaml`, and
  `handoff-review.html` to understand readiness and blockers.
- Platform engineers use pattern-specific handoff files, target contracts,
  lineage, and the allowed next action.
- Reviewers use `handoff-comparison.yaml` to inspect only the deltas from an
  incremental document or sample-configuration update.
- Contributors use `llm-trace-summary.yaml`, `model-benchmark.yaml`,
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
CloudFormation, AWS LZA, Kubernetes, or cloud APIs. A blocked bundle must remain
review-only until graph and contract blockers are resolved.
