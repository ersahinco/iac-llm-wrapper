# AGENTS.md

## Project: iac-llm-wrapper

A knowledge-graph tool that captures requirements and architecture decisions from
a customer document, surfaces gaps and conflicts so architects can steer client
discussions, and emits configuration for an existing AWS accelerator (Landing Zone
Accelerator). It does not deploy, does not generate Terraform, and holds no
credentials.

## Commands

```bash
uv run --locked --extra dev --extra graphrag pytest
uv run --locked --extra dev --extra graphrag ruff check .
uv run --locked --extra dev --extra graphrag mypy
NEO4J_PASSWORD=localdevpassword uv run --extra dev pytest tests/test_graph.py
opa check --strict src/intent_engine/policy
```

## Architecture

```
src/intent_engine/
  decisions.yaml   decision catalog: questions only a human can answer
  catalog.py       catalog load/validate, document value coercion
  ingest.py        whole-document read into statements and facts
  extraction.py    opt-in Neo4j GraphRAG proposals with source evidence
  graph.py         Neo4j schema, full replace, gap and contradiction Cypher
  analysis.py      gate applicability and named conflict rules
  llm.py           optional narration of the deterministic frontier
  emit.py          AWS LZA configuration, decision trace, and layered owner handoff
  contract.py      offline validation against pinned LZA 1.16.3 schemas
  tfvars.py        confirmed values mapped to a module JSON Schema input contract
  schemas/         unchanged upstream JSON schemas and notices
  scan.py          OPA, Checkov, Trivy over an emitted bundle
  policy/lza.rego  landing-zone policy
  cli.py           ingest, status, review, emit, scan
samples/           one realistic customer packet
```

Flow: ingest a whole document → Neo4j holds catalog, document, statements, facts →
deterministic review reports gaps and conflicts → optional LLM turns that frontier
into a client agenda → emit LZA configuration fail-closed → scan the bundle.

## Key Decisions

- **Whole-document ingest only.** Every run replaces the graph. No incremental
  diff, no baseline, no reconciliation. If the document changes, ingest it again.
- **Gaps are graph-derived, conflicts are named rules.** A missing answer, a value
  that cannot be coerced, and two answers that cannot both hold are three separate
  findings with three separate messages.
- **The LLM decides nothing.** Opt-in GraphRAG ingestion sends source statements
  to an explicit Ollama model and stores unconfirmed System/Candidate proposals.
  Only explicit document answers become Facts. Review narration receives the
  computed frontier, values, evidence, and proposals. No implicit model fallback.
- **Emission is fail-closed.** Any gap or conflict blocks the bundle. Defaults are
  only used with `--allow-defaults` and are recorded as `origin: default` in the
  decision trace.
- **Account root emails are owner input.** They are never generated or inferred.
- **Tool absence is not a pass.** OPA, Checkov, and Trivy each report
  `not-installed` rather than passing silently.
- **One decision catalog.** `decisions.yaml` holds decisions only: no derived
  values, no bookkeeping about itself.
- **Nothing here deploys.** No AWS API calls, no credentials, no state, no apply.
  Terraform output means variable JSON only, never resource definitions/execution.
  Owner pipelines keep every execution, approval, and drift decision.
- **Keep the distribution and import names** (`iac-llm-wrapper`, `intent_engine`)
  for compatibility.

## Stack

Python 3.11+, Pydantic v2, Typer, ruamel.yaml, jsonschema, neo4j driver, Neo4j 5, OPA,
Checkov, Trivy. Tests: pytest. Lint/type: ruff, mypy.

## Session State

<!-- UPDATE THIS SECTION AT END OF EVERY SESSION -->

### Current Goal

Support sourced functional requirements and architectural discussions from a
client document and selected organisation references, then emit supported LZA
configuration. Prioritise easy Compose startup and one complete example. Keep
only essential integration context, deterministic checks, and advisory AI; no
general-purpose platform extension framework.

### Status

- **GraphRAG ingestion implemented.** The optional `graphrag` extra pins
  Neo4j GraphRAG 1.21.0; Compose includes it. `ingest --extract-model MODEL`
  uses the upstream extraction and schema-pruning components against an explicit
  Ollama endpoint. One UTF-8 text/Markdown packet, up to 32,000 characters of
  statements; no embeddings or vector index are needed for this slice.
- **Proposals stay separate.** System/Candidate nodes carry source quotes and
  EVIDENCE links. Candidates PROPOSE answers; only Fact nodes ANSWER decisions.
  ABOUT/CONNECTS_TO relationships support discussion. Unsupported graph items
  are pruned with visible warnings; invalid evidence aborts before replacement.
  The architect records confirmed answers in the document and ingests again.
- **Upstream compatibility kept small.** GraphRAG 1.21.0's async Ollama adapter
  drops format settings. A short adapter invokes its synchronous method in a
  thread to preserve native JSON Schema output. Remove when upstream fixes it.
- **Discussion context is richer.** Review narration receives stated values,
  source locations, findings, and the unconfirmed architecture projection.
  Conflicted facts are excluded from accepted LLM context. Source text remains
  untrusted evidence, never model instructions.
- **Terraform variable export implemented.** `emit-tfvars` validates
  confirmed decisions against an explicit JSON Schema contract, then emits
  `terraform.tfvars.json` and `decision-trace.json`. The example covers name,
  CIDR, availability zones, and private subnets for community VPC module 6.7.3.
  It records module version, contract hash, and source evidence. No HCL resources,
  module discovery, Terraform execution, or state handling. The consuming root
  must declare/pass these variables; this is input validation, not a plan.
- **Compose application available.** Locked Python dependencies, OPA 1.21.0,
  and packaged LZA schemas run without host Python. An explicit local model is
  optional; none is downloaded automatically. Checkov/Trivy are absent from the
  image and correctly reported as unavailable rather than passing.
- **Existing boundaries preserved.** Atomic whole-document replacement,
  deterministic gap/conflict review, opt-in defaults with conflict revalidation,
  offline LZA 1.16.3 schema checks, owner network-file preservation, and honest
  scanner coverage remain. Existing enterprise systems are never provisioned.
- **Still pending.** Organisation-reference ingestion and policy-result graph
  links are not implemented. Integration/Policy/ConfigTarget nodes remain design
  ideas in ONTOLOGY.md. The separate LZA handoff file still needs consolidation.
  The graph does not prove real connectivity, identity integration, or compliance.
- **Distribution and CI.** Apache 2.0 public repository. This milestone includes
  the Compose application, GraphRAG ingestion, and VPC input export. GitHub CI
  includes the GraphRAG extra; the verification below records local results.

### Verified (2026-09-27)

- 152 tests pass with no skips, including 11 isolated Neo4j tests. Ruff, mypy
  (14 source files), and strict OPA validation pass. Updated Docker image builds.
  The real model output was persisted and reviewed in Neo4j: three proposals,
  four still-unconfirmed decisions, and the pruning warning survived storage.
  The final container ingested the confirmed VPC packet and exported both JSON
  files successfully. These checks used a disposable Compose graph project.
- Live local Ollama `qwen2.5:7b` extracted the three stated VPC decisions with
  matching source quotes; the undecided private-subnet value remained absent.
  One unsupported relationship was pruned and reported. Earlier runs produced
  poor or malformed graphs: valid structure is not semantic accuracy, and
  architect confirmation remains necessary. No new model was downloaded.
- Offline tests exercise actual GraphRAG components with controlled responses,
  source validation, pruning, typed export, missing mappings, remote-reference
  rejection, provenance, and the Ollama compatibility adapter.
- Neo4j tests prove candidate evidence survives storage, candidates do not close
  gaps, re-ingestion replaces proposals, and missing answers block variable output.
- The community VPC 6.7.3 input declarations were read from upstream. Its stated
  floors are Terraform >= 1.0 and AWS provider >= 6.28. No runtime, provider,
  backend, or plan was invoked or validated here.
- Earlier LZA sample/scanner checks remain: schemas and OPA pass; absent or
  unassessed Checkov/Trivy coverage makes scan exit 1. This is not deployment
  readiness. Local Python 3.14/Neo4j deprecation warnings are upstream.

### Next

Use one client case with selected organisation references to connect policy
findings to sourced functional decisions. Consolidate the redundant LZA handoff
output. Keep extraction proposals advisory and exports restricted to explicit
input contracts. Improve local-model quality using representative packets rather
than adding a larger ontology or a general-purpose module framework.
