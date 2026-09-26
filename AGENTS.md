# AGENTS.md

## Project: iac-llm-wrapper

A knowledge-graph tool that captures requirements and architecture decisions from
a customer document, surfaces gaps and conflicts so architects can steer client
discussions, and emits configuration for an existing AWS accelerator (Landing Zone
Accelerator). It does not deploy, does not generate Terraform, and holds no
credentials.

## Commands

```bash
uv run --locked --extra dev pytest
uv run --locked --extra dev ruff check .
uv run --locked --extra dev mypy
NEO4J_PASSWORD=localdevpassword uv run --extra dev pytest tests/test_graph.py
opa check --strict src/intent_engine/policy
```

## Architecture

```
src/intent_engine/
  decisions.yaml   decision catalog: questions only a human can answer
  catalog.py       catalog load/validate, document value coercion
  ingest.py        whole-document read into statements and facts
  graph.py         Neo4j schema, full replace, gap and contradiction Cypher
  analysis.py      gate applicability and named conflict rules
  llm.py           optional narration of the deterministic frontier
  emit.py          AWS LZA configuration, decision trace, and layered owner handoff
  contract.py      offline validation against pinned LZA 1.16.3 schemas
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
- **The LLM decides nothing.** It never reads the document. It receives the
  computed frontier and produces discussion questions. Provider and model are
  always explicit; there is no implicit local fallback.
- **Emission is fail-closed.** Any gap or conflict blocks the bundle. Defaults are
  only used with `--allow-defaults` and are recorded as `origin: default` in the
  decision trace.
- **Account root emails are owner input.** They are never generated or inferred.
- **Tool absence is not a pass.** OPA, Checkov, and Trivy each report
  `not-installed` rather than passing silently.
- **One decision catalog.** `decisions.yaml` holds decisions only: no derived
  values, no bookkeeping about itself.
- **Nothing here deploys.** No AWS API calls, no credentials, no state, no apply.
  Owner pipelines keep every execution, approval, and drift decision.
- **Keep the distribution and import names** (`iac-llm-wrapper`, `intent_engine`)
  for compatibility.

## Stack

Python 3.11+, Pydantic v2, Typer, ruamel.yaml, jsonschema, neo4j driver, Neo4j 5, OPA,
Checkov, Trivy. Tests: pytest. Lint/type: ruff, mypy.

## Session State

<!-- UPDATE THIS SECTION AT END OF EVERY SESSION -->

### Current Goal

Make the banking experiment credible through scoped network, identity, data,
and application decisions, while preserving whole-document capture, deterministic
review, optional AI narration, and the configuration-only deployment boundary.

### Status

- **Pinned integration contract implemented locally.** The six LZA configuration
  files validate offline against unchanged v1.16.3 schemas, before emission and
  during scan. The unused baseline selector is removed. JSON Schema validation
  is the one new runtime dependency; no AWS calls or runtime schema downloads.
- **Small layered handoff.** Explicit permission-set policy mappings, data
  classification/regions, recovery objectives, and application ownership feed
  `handoff.yaml`. Unsupported data regions and incomplete policy mappings block
  emission. Example inputs are explicitly illustrative, not bank approvals.
- **Owner boundary is explicit.** Six config files go to the LZA consumer; the
  trace and handoff go to reviewers. Network routes/subnets/attachments, identity
  provider integration, workload data controls, and application delivery remain
  owner work. Handoff status is always `requires-owner-validation`.
- **First banking milestone implemented locally.** Scanner failures, malformed
  reports, unavailable tools, and zero assessed checks cannot produce scan
  success. `not-assessed` distinguishes absent coverage from findings.
- **Policy fails closed for its existing controls.** Missing or mistyped control
  fields and malformed account/assignment inputs are denied. This is not yet
  validation against the full LZA schema.
- **Atomic whole-document replace.** Catalog, document, statements, and facts
  reload in one data transaction. Failed loads preserve the prior graph. Schema
  initialization happens before replacement. Concurrent review snapshot
  consistency remains separate work.
- **Defaults are revalidated.** After opt-in defaults are resolved, semantic
  conflicts block emission before writing the bundle.
- **Layered direction accepted.** REVIEW.md records the banking review and the
  network, identity, data, application, and operations boundaries. The network
  skeleton still needs owner completion; schema success is not deployment readiness.
- **Fresh-start history.** Public repository uses Apache 2.0 with one initial
  commit on main; current milestone changes remain uncommitted. The requested
  local recovery bundle was deleted.
- **Kept focused.** One small contract module and upstream schemas were added.
  Whole-document ingestion, optional advisory AI, and no deployment remain boundaries.

### Verified (2026-09-26, Python 3.14.7, macOS)

- 124 tests pass with no skips, including all 8 local Neo4j tests. Ruff and mypy
  pass over 12 source files. Strict OPA validation passes.
- Full sample journey: 25 decisions captured, 8 files emitted. The six config
  files pass LZA 1.16.3 schemas. Explicit policy mappings are preserved, and data
  region conflicts block emission. No network or application deployment is claimed.
- Real scan: schemas and OPA pass; Checkov 3.3.10 and Trivy 0.74.0 report
  `not-assessed`. CLI correctly exits 1 for incomplete coverage.
- Built source distribution and wheel. Validated all six configs using the wheel
  with socket connections blocked: packaged schemas work offline.
- CI includes checksum-pinned OPA 1.21.0 in Python 3.11. Remote CI not run this
  turn; changes remain local. Existing Neo4j/Python 3.14 warnings are third-party.

### Next

Exercise this handoff with the owner's actual LZA 1.16.3 consumer. Complete the
network design there and verify identity policy/group references. Add richer
workload modeling only when a concrete integration requires it. Bank connectivity,
IdP, actual data-location constraints, and recovery objectives remain owner input.
