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
- Prioritise simple, readable implementations of functional requirements. Treat
  additional nonfunctional tuning as separate work justified by an observed need.
- Accept different scenarios through explicit client documents, estate references,
  preferences, policies, catalogs and input contracts. Reference text alone adds
  neither executable checks nor output mappings. Keep unsupported needs visible.
- Keep the distribution name `iac-llm-wrapper` and import name `intent_engine`.
- Original code and documentation use MIT. Preserve bundled LZA schemas and their
  Apache-2.0 license/notices; distribution metadata accounts for both licenses.
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
  Required security controls and region restrictions belong to selected policies;
  `compliance_overlay` selects LZA template settings, not export requirements.
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
- README explains the pre-handoff value and relationship to CNOE/owner pipelines.
  The organisation walkthrough includes captured CLI output and configuration/trace
  excerpts. CONTRIBUTING follows the monitoring question through its existing policy
  and a document-to-policy regression test. A blank two-engineer trial guide measures
  setup friction, useful findings and comparable effort; no human trial has run.
- Native Typer options handle connection defaults. Pydantic reads GraphRAG objects
  directly; Cypher loads catalog relationships and orders gap dependencies.
  Review converts answers once and keeps each value with its first source.
  CLI warnings appear once with their reasons and evidence.
- Selected organisation policy owns region/security restrictions and scoped
  owner/reason exceptions. Existing cases require `--organisation` refresh to
  adopt changed example policies. Checkov/Trivy adapters and exceptions remain.
- The VPC example checks canonical CIDRs, containment, subnet overlap and zone
  counts; selected OPA adds routing-domain allocations, instance allowlists,
  evidenced exceptions and monitoring advice. Contracts export reviewed subsets.
- Live embeddinggemma and qwen2.5:7b previously produced incorrect answers despite
  valid citations. Semantic reliability and independent architect feedback remain
  unproven. Retrieval limits: 500 statements, 4,000 characters per statement,
  32,000 prompt characters.
- No live estate discovery, CIDR allocation, capacity recommendations, concurrent
  editing, automatic policy translation or authenticated exception sign-off.

### Latest verification

- 2026-09-29: all 244 tests passed without skips with real Neo4j and OPA on isolated
  project `iac-value-tests-20260929` (ports 59574/59587). Ruff, formatting,
  mypy, strict OPA and Rego formatting passed. Upstream Neo4j/GraphRAG warnings
  remain on host Python 3.14; model responses in automated tests are controlled.
- The organisation CLI journey ran without LLM/cloud credentials on isolated
  `iac-value-20260929` (ports 59374/59387): one gap/one conflict, blocked emission,
  corrected answers and seven output files. Documented CLI/YAML excerpts match
  the captured output; source hash and 42 local links/anchors verified. The focused
  contribution command passes six real-OPA cases. Evidence is in `build/value-review/`.
  Changes are docs, monitoring question wording/hint and four regression cases;
  runtime code, dependencies, MIT licensing and upstream notices are unchanged.
- Model and extraction schemas are unchanged. New graph checks retain facts and
  assessments when evidence links or policy answers are absent. Native Rego
  membership preserves findings across 72 valid/missing/malformed combinations;
  the named helper retains warnings on undefined inputs. Existing coverage retains
  atomic replacement, stored snapshots, policy/default gates, no-clobber exports
  and native scanner exception handling.
- The 109-function complexity review is complete: no further worthwhile cuts
  identified for current requirements. Decisions, source hashes and test results
  are in `build/complete-review/`. Further changes need a concrete readability or
  functional benefit. No dependencies were added; review evidence is ignored.
- MIT licensing and contributor guidance are in place. Source and wheel builds,
  lockfile, Ruff, formatting and mypy checks passed; package contents retain all
  nine upstream schema/provenance files unchanged and include both licenses and
  upstream notices. Evidence is in `build/open-source-review/`. CI also builds
  distributions. Runtime code and dependencies are unchanged.
- Both new isolated projects are stopped at session end; their volumes are retained.
  Saved cases and unrelated services were not changed. Earlier real Checkov/Trivy
  evidence remains in `build/security-discussion/`.
- The user authorised implementation, tests, commit and push for these changes.

### Next

Run `docs/engineer-trial.md` with two independent engineers, then try one small
sanitised client integration with an architect if the observations justify it.
Record actual friction, useful findings and missing requirements before adding
further capabilities. Practical value, time savings and adoption remain unproven.
