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
- **Advisory models.** Extraction and narration require explicit provider/model
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
  hashes. Reassess resolved values before emission.
- **Fail-closed export.** Gaps, conflicts and invalid contracts block output.
  Defaults require `--allow-defaults` and `origin: default` in the trace. Preserve
  owner files and do not overwrite unrelated output files.
- **Honest coverage.** Missing scanners report `not-installed`; no assessed checks
  means `not-assessed`. Neither is a pass. Schema validation proves shape, not
  connectivity, federation, recovery or deployment readiness.
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
  llm.py           optional narration of deterministic review
  emit.py          LZA configuration and decision trace
  contract.py      offline validation against pinned LZA 1.16.3 schemas
  tfvars.py        confirmed values mapped through a JSON Schema contract
  schemas/         unchanged upstream schemas and notices
  scan.py          OPA, Checkov and Trivy over LZA output
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

- Guided local prototype with sourced gap/conflict review, architect-confirmed
  answers, six LZA 1.16.3 files plus a trace, or explicitly mapped module variables
  plus a trace. Hybrid networking and Entra ID remain integration context.
- Input-only scenario changes were exercised with Entra/Okta references and a
  synthetic factory case using a custom catalog, retention policy and input
  contract. No scenario-specific retriever or module catalog was added.
- Live Ollama embeddinggemma and qwen2.5:7b integration works, but answers have
  falsely called a stated CIDR missing and described evidenced systems as unclear.
  Citations do not resolve this. Automated model responses are controlled;
  independent user feedback and live semantic reliability remain unproven.
- Retrieval is bounded to 500 statements, 4,000 characters per statement and 32,000
  prompt characters. Selected references use reviewed links. No automatic policy
  translation, enterprise discovery, shared-service isolation or authenticated
  reviewer sign-off.

### Latest verification

- Published commit `f64f226` passed all five CI jobs (run `36319150998`). The fresh
  clone walkthrough passed as an informed self-test, not independent human testing.
- First-use fixes quiet native query notifications while preserving
  connection/query errors; show each text-review finding once with evidence/hints;
  discover graph-view ports from the active Compose project. JSON and export gates
  are unchanged. All **175 tests passed without skips** on 2026-09-27 using isolated
  Neo4j and OPA; Ruff, mypy and strict OPA checks passed. Host Python 3.14 emits
  upstream Neo4j deprecation warnings.
- Rebuilt Compose verified blocked export, reference reuse after correction,
  seven-file output and visible bad-login failure. Evidence: ignored
  `build/usability-fixes/`; fresh-clone results: `build/colleague-test/self-test/`.
  Input variation and live-model findings: `build/enterprise-review/`,
  `build/graphrag-evaluation/` and `build/graphrag-walkthrough/`.
- Project test containers are stopped, volumes retained. Do not remove saved
  cases or touch unrelated services during housekeeping.
- 2026-09-28 housekeeping consolidates contributor setup, removes repeated README
  instructions and historical session notes, and aligns project descriptions.
  The pre-cleanup working files are retained locally in ignored
  `build/repo-housekeeping/before/`. No runtime logic or dependencies changed.
- GitHub About now describes sourced review, GraphRAG and supported configuration
  inputs; the `graphrag` topic was added. The documented local check passed 153
  tests with 22 database tests deliberately skipped. Ruff, mypy, OPA, local
  links/anchors, shell examples, CLI help and locked
  package metadata passed. The quickstart commands are unchanged; contributor
  Compose isolation was checked without starting services. Existing fixes were
  compared with the saved working files and preserved.
- The user authorised committing and pushing the first-use fixes and housekeeping
  together on 2026-09-28. Generated evidence and saved cases remain ignored;
  check GitHub for the resulting commit's CI status.

### Next

Try one small sanitised client integration with an architect. Record observed
friction and uncovered requirements before adding functionality.
