# AGENTS.md

## Project

`iac-llm-wrapper` captures sourced architecture decisions in Neo4j, reports gaps
and conflicts, and exports supported LZA configuration or Terraform module variable
JSON. Optional Neo4j GraphRAG helps explore evidence. Nothing deploys, executes
Terraform, calls AWS APIs or needs cloud credentials.

## Working rules

- Preserve existing user changes and saved graph data. Use a separate Compose
  project, ports and volume for exercises. Tests and ingestion erase their target
  graph; use the isolated setup in [CONTRIBUTING.md](CONTRIBUTING.md).
- Prefer deletion and native Neo4j/Cypher, GraphRAG, OPA and JSON Schema features.
  Add custom wiring only for a demonstrated functional need. No parallel ontology,
  speculative framework, module-coverage roadmap or all-cloud promise.
- Accept different scenarios through explicit client documents, estate references,
  preferences, policies, catalogs and input contracts. Reference text alone adds
  neither executable checks nor output mappings. Keep unsupported needs visible.
- Keep the distribution name `iac-llm-wrapper` and import name `intent_engine`.
- Run checks appropriate to the change; see [contributor checks](CONTRIBUTING.md#local-checks).
  Do not present simulated usability tests as independent human feedback.

## Invariants

- **Whole-document ingest.** Each successful ingest replaces the entire graph
  atomically. No incremental diff, baseline or reconciliation. Failed replacement
  preserves the previous case.
- **Stored case snapshot.** The client document holds the selected catalog and
  organisation contents/hashes. Corrections reuse references; `--organisation`
  refreshes them and `--without-organisation` clears them. Review/export use the
  stored catalog; a mismatched explicit catalog requires re-ingestion.
- **Distinct findings.** Gaps are graph-derived; conflicts use named rules. Missing
  answers, unusable values and contradictory answers have separate messages.
- **Human answers.** Only explicit document answers become Facts. Account root
  emails are owner input. References and extracted System/Candidate proposals
  never become answers automatically. The catalog contains decisions only.
- **Advisory models.** Extraction and retrieval require explicit model/endpoint
  choices, with no fallback. Preserve the small async Ollama adapter while upstream
  GraphRAG misroutes model parameters; it retains native JSON Schema format.
- **Advisory retrieval.** `index` embeds the stored snapshot; `ask` uses native
  VectorCypherRetriever and GraphRAG. Re-ingestion requires re-indexing. Source
  identifiers/quotes are validated, not semantic entailment. Model wording cannot
  change facts or unblock export. Show deterministic answers/findings separately.
  Operations are sequential; no concurrent ingest/index/review guarantees.
- **Scoped policy.** OPA's `data.organisation.assessments` must return one assessment
  per selected policy. Missing tools, malformed/undefined output or missing coverage
  are `not-assessed` and block export. Retain evidence and input/document/reference
  hashes. Reassess resolved values before emission. Explicit `warning` assessments
  remain visible in review/export/trace and do not block; the model cannot downgrade findings.
- **Fail-closed export.** Gaps, conflicts and invalid contracts block output.
  Defaults require `--allow-defaults` and `origin: default` in the trace. Preserve
  owner files. Exports require unused destinations, reject symlinks and never
  overwrite earlier output; use a fresh output directory for each revision.
- **Honest coverage.** Missing scanners report `not-installed`; no assessed checks
  means `not-assessed`. Neither is a pass. Schema validation proves shape, not
  connectivity, federation, recovery or deployment readiness. Keep Checkov/Trivy
  adapters: security findings are advisory by default, `scan --strict` gates open
  findings, and reported native exceptions stay visible with their reasons.
- **Owner execution.** Integration context remains `requires-owner-validation`.
  The owner's pipeline keeps deployment, approvals and drift decisions. Terraform
  output is variable JSON only: no resources, state or execution.

## Code map

```text
src/intent_engine/
  decisions.yaml   default human decision catalog
  catalog.py       catalog validation and value coercion
  ingest.py        whole-document statements and explicit facts
  extraction.py    opt-in GraphRAG proposals with evidence
  rag.py           native vector/graph retrieval and advisory answers
  organisation.py  reference snapshots and scoped OPA assessment
  graph.py         Neo4j schema, atomic replacement and queries
  analysis.py      applicability and named conflict rules
  emit.py          LZA configuration and decision trace
  output.py        shared exclusive bundle creation; no replacement of existing files
  contract.py      offline validation against pinned LZA 1.16.3 schemas
  tfvars.py        confirmed values mapped through a JSON Schema contract
  schemas/         unchanged upstream schemas and notices
  scan.py          LZA shape/OPA and advisory Checkov/Trivy over owner IaC
  policy/lza.rego  landing-zone policy
  cli.py           ingest, status, review, index, ask, emit, emit-tfvars, scan
samples/           synthetic organisation, banking and VPC inputs
```

Python 3.11+, Pydantic v2, Typer, ruamel.yaml, jsonschema, Neo4j 5 and OPA.
GraphRAG 1.21.0 is optional on the host and included in the Compose app.
Tests use pytest; lint/types use Ruff and mypy. Add no runtime dependency without
an observed need.

## Session state

<!-- Update in place at session end; keep current facts, not a running diary. -->

### Current outcome

- Guided local prototype: sourced gap/conflict review, explicit architect answers,
  six LZA 1.16.3 files plus a trace, or mapped module variables plus a trace.
  Hybrid networking and Entra ID remain integration context.
- Network consistency now rejects malformed/noncanonical CIDRs, peer subnet
  overlaps, subnets outside their VPC and subnet/zone count mismatch. The scoped
  VPC workload example adds existing allocation checks by routing domain,
  environment instance allowlists, evidenced exceptions and monitoring advice.
  VPC and EC2 module contracts export separate reviewed subsets, not deployed resources.
- Checkov and Trivy are retained for architecture discussions. `review --scan`
  accepts owner IaC; findings are warnings, reported native exceptions remain
  visible, and missing/error/unassessed scans are unsuccessful. `scan --strict`
  additionally fails on open findings. LZA schema failures stay blocking.
- Exports never replace existing destinations. One shared writer validates all
  destinations and creates files exclusively. `review` is deterministic; `ask`
  replaces the separate narration path. Removed the requests runtime dependency
  and duplicate graph fact reads. Design boundaries: `docs/design.md`.
- Live Ollama embeddinggemma and qwen2.5:7b previously produced incorrect answers
  despite valid citations. Live semantic reliability and independent architect
  feedback remain unproven. Retrieval remains bounded to 500 statements, 4,000
  characters per statement and 32,000 prompt characters.
- No live estate discovery, automatic CIDR allocation, capacity recommendation,
  concurrent editing, automatic policy translation or authenticated exception sign-off.

### Latest verification

- 2026-09-28: all 217 tests passed without skips on isolated Compose project
  `iac-lean-20260928` (ports 58474/58687), with real Neo4j and OPA. Ruff, mypy and
  strict OPA checks passed. Python 3.14 emits upstream Neo4j deprecation warnings.
- Real Checkov 3.3.10 and Trivy scans of synthetic owner IaC reported security
  findings and retained scoped exception reasons. Checkov's quiet JSON mode hid
  skipped details, so the adapter no longer uses it. Trivy inline suppressions can
  be absent from reports; the demonstrated `.trivyignore.yaml` preserves reasons.
- Rebuilt Compose passed 13 sequential walkthrough steps: blocked inputs,
  reference reuse, LZA output, refusal to overwrite, corrected scoped policy and
  separate VPC/instance exports with warnings. The real combined `review --scan`
  returned zero blockers while showing both policy and native scanner warnings.
- Locked installation/local checks passed 194 tests with 23 database tests skipped.
  Local Markdown links and CLI help passed. Evidence is ignored under
  `build/security-discussion/`. Earlier saved graphs and unrelated services were
  not changed. The isolated test project is stopped at session end; its volume is retained.
- The user authorised implementation, tests, commit and push for these changes.

### Next

Try one small sanitised client integration with an architect. Record observed
friction and missing requirements before adding further capabilities.
