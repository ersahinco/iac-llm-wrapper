# Handoff Artifacts

`iac-llm-wrapper` emits portable files for review and registered deployment
targets. These artifacts are target configuration artifacts, not deployments.
Existing deployment mechanisms remain downstream.

| Artifact | Purpose | Owner | Emitted When | Deployable |
| --- | --- | --- | --- | --- |
| `decision-report.yaml` | Accepted decisions, handoff readiness, blockers, safe handoff path, and pattern-owned semantic model details when available. | Core + pattern | Every compile, including blocked compiles. | No |
| `decision-audit.yaml` | Graph audit trail showing each accepted, defaulted, or skipped decision and its reason. | Core generator | Successful pattern-backed compiles. | No |
| `context-manifest.yaml` | Code-owned context inventory: pattern metadata, prompt context digest/text, requirement graph, target contracts, samples, policy packs, target capabilities, runtime extraction summary, expected artifacts, and guardrails. | Core | Pattern-backed successful handoffs. | No |
| `policy-graph.yaml` | Registered policy pack metadata mapping compliance/client controls to requirements, target contracts, artifacts, module variables, Checkov IDs, and owner custom-policy references. | Core + pattern | Successful handoffs for patterns declaring policy packs. | No |
| `handoff-plan.yaml` | Ordered review/handoff steps, owners, dependencies, manual gates, rollback, boundary, `handoffAllowed`, and allowed next action. | Core | Contract-backed successful handoffs. | No |
| `plan-manifest.yaml` | Registered target plan metadata: immutable input artifacts, plan readiness, plan-only command text, expected plan outputs, blockers, and no-apply boundary. | Pattern + core contract | Plan-ready registered targets such as AWS LZA. | No |
| `replay-manifest.yaml` | Source, target contract, and artifact digests for deterministic replay and bundle comparison. | Core | Plan-ready registered targets. | No |
| `missing-inputs.yaml` | Durable architect/client question packet for blocked compiles, keyed by requirement graph nodes. | Core | Blocked compiles. | No |
| `llm-trace-summary.yaml` | Provider/model, latency, raw and accepted decisions, applied decisions, gaps, contradictions, and raw evidence status. | Core | Every compile. | No |
| `model-benchmark.yaml` | Mode, provider/model, latency, token availability, raw LLM coverage, conformance, quality counts, readiness, cost status, and external-observability boundary. | Core | Every compile. | No |
| `input-diff-report.yaml` | Changed headings, changed structured decision lines, likely impacted requirements, and scoped hunks for an incremental document update. | Core incremental compile | `compile --baseline-bundle --changed-doc`. | No |
| `incremental-compile-report.yaml` | Reused, changed, added, removed, carried-forward, and re-confirmation decision summary for diff-aware compile. | Core incremental compile | `compile --baseline-bundle --changed-doc`. | No |
| `git-incremental-plan.yaml` | Git-changed design docs, skipped paths, baseline availability, output bundle paths, and compile status for explicit git-driven incremental runs. | Core incremental compile | `compile-git --base-ref --doc-root --bundle-root --output-root`. | No |
| `contract-validation.yaml` | Standalone pass/fail validation of emitted artifacts against target contracts. | Core validation helper | Explicit validation artifact writes; `review html` computes validation in memory. | No |
| `target-capability-graph.yaml` | Downstream target coverage, selected target path, manual gates, and unsupported asks represented as semantic facts with evidence spans. | Pattern-owned target report builder | AWS LZA today; future patterns only when they own comparable target routing. | No |
| `bundle-graph.yaml` | Full typed graph export for a generated bundle: source context, input diffs, source changes, requirements, decisions, contracts, artifacts with file digest metadata, module variables, policy controls, Checkov refs/findings, shift-left evidence, handoff readiness, readiness blockers, contract validation, downstream validation evidence, target capabilities, samples, manual gates, pattern semantic entities, semantic constraints, edges, topology summary for root-selectable, connected, isolated, source, sink, branch, join, and high-degree hotspot nodes with traversal commands, query indexes for nodes by kind, incoming/outgoing adjacency, relationship-to-edge lookup, and root selectors by kind, node-kind/relationship catalog, and query hints for find/roots/impact/path/neighborhood/matrix/diff traversal. | Core graph tooling | `graph bundle --bundle --output`. | No |
| `graph-roots.yaml` | Concrete typed graph roots available for traversal, grouped by kind, with copy-pasteable impact/neighborhood commands, recommended review roots, topology hotspot roots, and recommendation category rollups for source changes, blockers, findings, and validation evidence. | Core graph tooling | `graph roots --bundle --output`. | No |
| `graph-find.yaml` | Search results for candidate typed graph roots, including matched node ids, matched field rollups, root-selectable/context-only result counts, root selectors and traversal commands when root-selectable, kind filters, result counts, and review focus. | Core graph tooling | `graph find --bundle --query --output`. | No |
| `impact-report.yaml` | Graph traversal impact report showing selected roots, unmatched-root suggestions, upstream/downstream/affected node-kind rollups, upstream dependencies with dependency paths into selected roots, downstream affected nodes, review priorities with highest-severity and per-severity summary counts, ordered review checklist with representative path previews plus follow-up path/neighborhood queries, artifacts, target contracts, target capabilities, sample recommendations, policy controls, checks, module variables, semantic entities, semantic constraints, source context, input diffs, source changes, handoff readiness, readiness blockers, contract validation, downstream validation evidence, manual gates, root-to-target impact paths with relationship descriptions, and review focus. | Core graph tooling | `graph impact --bundle --root --output`; also embedded in `review compare` output. | No |
| `graph-impact-matrix.yaml` | Multi-root impact triage matrix comparing selected, recommended, topology-hotspot, changed-report, or bundle-comparison graph roots by match status, root-selection reason, recommendation category rollups, severity, upstream dependency kind rollups, upstream source-change/input-diff provenance, affected artifacts, target contracts, target capabilities, sample recommendations, policy controls, checks, Checkov findings, module variables, manual gates, per-root review checklists, per-row follow-up traversal commands, and checklist category rollups. | Core graph tooling | `graph matrix --bundle --root --output`, `graph matrix --bundle --recommended --output`, `graph matrix --bundle --hotspots --output`, or `graph matrix --bundle --changed-report --output`; also embedded in `review compare`. | No |
| `graph-path.yaml` | Shortest-path explanation between two typed bundle graph roots, including compact path summary, relationship and node-kind rollups, hop relationships and descriptions, endpoint neighborhood follow-up queries, traversal direction, unmatched-root suggestions, no-path status, and review focus. | Core graph tooling | `graph path --bundle --from --to --output`. | No |
| `graph-neighborhood.yaml` | Bounded dependency neighborhood around one typed bundle graph root, including neighbor node depths, neighbor node-kind and relationship rollups, root-edge incoming/outgoing/bridging summaries, connecting traversal hops with relationship descriptions, optional kind filtering, unmatched-root suggestions, no-match status, and review focus. | Core graph tooling | `graph neighbors --bundle --root --output`. | No |
| `graph-diff.yaml` | Typed graph delta between two generated bundles, including added/removed/changed nodes, follow-up impact/neighborhood commands for root-selectable deltas, changed node-kind and field rollups, property-level changed paths, added/removed edges, edge-relationship rollups, node-kind counts, and review focus. | Core graph tooling | `graph diff --before --after --output`. | No |
| `handoff-comparison.yaml` | Compact before/after bundle delta for incremental packet or sample updates: readiness, requirement completeness, decisions, blockers, artifacts, impact traversal, impact matrix for changed decisions, input-diff roots, and graph-diff changed roots with root-selection categories and follow-up graph traversal commands, typed graph diff, model quality, and sample recommendations. | Core review tooling | `iac-llm-wrapper review compare --output`. | No |
| `shift-left-evidence.yaml` | Optional Checkov evidence for an owner-provided IaC/module/pipeline path, including tool availability, command, registered policy packs, owner custom-policy paths, IaC kind, result, summary counts, findings, mapped controls, unmapped findings, and no-deploy boundary. | Core shift-left tooling | `shift-left checkov --bundle --scan-path`. | No |
| `handoff-comparison.html` | Static delta review page for what changed, what stayed stable, what graph roots entered impact review, why each root was selected, follow-up graph traversal commands, and what must be reviewed. | Core review tooling | `iac-llm-wrapper review compare --html-output`. | No |
| `lza-validation-evidence.yaml` | Validation-only AWS LZA config-validator command, no-mutation/read-only lookup boundary, temporary-staging/replay boundary, source metadata, config digests, exit code, diagnostic summary, and captured stdout/stderr. | AWS LZA validation adapter | `iac-llm-wrapper lza validate`. | No |
| `battle-summary.yaml` | Battle-test verdict, confidence categories, findings, and improvement items. | Battle harness | `scripts/battle-test.py`. | No |
| `handoff-review.html` | Static human review page summarizing readiness, contract status, allowed next action, reviewer next actions, blocker traceability, raw LLM coverage, expected weaknesses, graph links, graph review artifacts when present, evidence, benchmark, contract validation, handoff plan, and target artifacts. | Core review tooling | `iac-llm-wrapper review html`. | No |
| `requirement-graph.json` | Machine-readable graph export for external viewers and tools. | Core graph tooling | `iac-llm-wrapper graph export`. | No |
| `requirement-graph.mmd` | Mermaid graph export for lightweight visual inspection. | Core graph tooling | `iac-llm-wrapper graph export`. | No |
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
  incremental document or sample-configuration update. Its impact matrix includes
  changed decisions, input-diff roots, and changed/added graph roots from
  `graph-diff.yaml`, including generated artifact digest changes.
- Reviewers and agents use `bundle-graph.yaml` as the queryable bundle graph.
  Its catalog describes node kinds, selectable roots, relationship meanings, and
  observed source/target node-kind pairs so an agent can traverse the graph
  without reverse-engineering edge labels. Use `graph-roots.yaml` or
  `graph-find.yaml` to discover candidate roots, then use
  `graph-impact-matrix.yaml` to compare several roots at once. Use
  `graph matrix --recommended` to triage recommended review roots from
  `graph-roots.yaml`, `graph matrix --hotspots` to triage high-degree topology
  pivots, or use `impact-report.yaml`
  and the `review compare` impact traversal section to see which artifacts,
  policy controls, Checkov refs/findings, shift-left evidence, module
  variables, and manual gates are downstream of a changed graph root. When a
  pattern emits a semantic model, these graph artifacts also expose typed
  semantic entities, relationships, and predicate constraints, including the
  traversal path that explains why each impact is connected. Use
  `graph-path.yaml` when the review question is narrower: explain how one
  specific graph root is connected to another. Use `graph-neighborhood.yaml` to
  inspect the bounded upstream, downstream, or bidirectional context around one
  graph root before choosing a more precise impact or path query.
- Use `graph-diff.yaml` when the review question is graph-native: which typed
  nodes, artifact file digests, or edges changed between two generated bundles. Use
  `handoff-comparison.yaml` when the review question spans readiness, decisions,
  artifacts, typed graph deltas, samples, and model quality.
- Regulated-environment reviewers use `policy-graph.yaml` and
  `shift-left-evidence.yaml` as pre-deployment policy evidence for
  owner-controlled CI/CD gates. These artifacts are not compliance attestation
  and do not authorize deployment.
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
