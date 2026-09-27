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
  organisation.py  selected organisation references and scoped OPA assessment
  graph.py         Neo4j schema, full replace, gap and contradiction Cypher
  analysis.py      gate applicability and named conflict rules
  llm.py           optional narration of the deterministic frontier
  emit.py          AWS LZA configuration and decision trace with integration context
  contract.py      offline validation against pinned LZA 1.16.3 schemas
  tfvars.py        confirmed values mapped to a module JSON Schema input contract
  schemas/         unchanged upstream JSON schemas and notices
  scan.py          OPA, Checkov, Trivy over an emitted bundle
  policy/lza.rego  landing-zone policy
  cli.py           ingest, status, review, emit, scan
samples/           banking intake, organisation discussion, and VPC examples
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

- **Organisation-aware example implemented.** `samples/organisation/README.md`
  documents one client document plus selected estate, LZA region standard and OPA
  policy references. Four sourced systems describe existing hybrid networking and
  Entra ID alongside planned AWS LZA and IAM Identity Center. Two integrations
  link them to explicit decisions. Reference values never become client answers.
- **One gap, one conflict.** The incomplete packet lacks `hybrid_connection` and
  requests `us-east-1` outside the selected organisation standard. Review cites
  the estate requirement, client answer, policy statement and configuration hash.
  The corrected packet selects site-to-site VPN and Frankfurt/Ireland. Connection
  and federation decisions remain context-only, not generated infrastructure.
- **Whole-case reference snapshot.** Organisation contents/hashes and the selected
  decision catalog live on the client Document in the same atomic replacement.
  Corrections preserve references; `--organisation` refreshes them and
  `--without-organisation` deliberately clears them. Review/emission use the
  ingested catalog; mismatched explicit catalogs require re-ingestion.
- **Scoped policy assessment.** OPA receives usable stated decisions plus selected
  configuration data. `data.organisation.assessments` must return one assessment
  per selected policy. Missing OPA, malformed/undefined output or missing coverage
  is `not-assessed` and blocks output. Assessments link to policy and client facts
  in Neo4j, with input/document hashes. Policy/configuration hashes live on linked
  references. Resolved values are reassessed before emission.
- **Handoff consolidated.** LZA emits six configuration files plus
  `decision-trace.yaml`. Review and trace include network, identity, data and
  application integration work. Trace includes reference hashes, scoped policy
  results and context-only questions. A recognised old generated handoff is removed
  during re-emission; arbitrary files are protected. No separate delivery workflow.
- **GraphRAG remains advisory.** Neo4j GraphRAG 1.21.0 extracts System/Candidate
  proposals from one small UTF-8 packet using explicit Ollama model/endpoint.
  Evidence validation and schema pruning remain; candidates never answer gaps.
  The small async Ollama compatibility adapter preserves native JSON Schema format.
- **Existing outputs preserved.** Offline LZA 1.16.3 schemas, owner-network file
  preservation, explicit permission mappings, and VPC 6.7.3 variable input contract
  remain. No deployment, Terraform resource generation or credentials. Compose
  includes OPA/GraphRAG; missing Checkov/Trivy never count as passes.
- **Limits remain explicit.** Only selected local references with reviewed links
  are supported, not arbitrary module discovery or automatic policy translation.
  No ConfigTarget ontology, enterprise discovery, working-connectivity proof or
  general-purpose extension framework. Concurrent review/ingest snapshots remain
  separate work. User-facing graph statuses describe the latest review.
- **Distribution and CI.** Apache 2.0 repository. Prior milestone `9a9a7bf` passed
  all five CI jobs. This milestone adds the organisation example and installs OPA
  in the graph CI job so the complete discussion-to-export check runs there.

### Verified (2026-09-27)

- Initial full suite: 164 tests, no skips, including real Neo4j and OPA organisation
  checks. All 135 affected tests pass after final changes, including explicit
  reference reset and removal of the old generated handoff. Ruff, mypy (15 source
  files), and strict OPA validation pass. No new runtime dependencies were added.
- Tests use a separate `iac-organisation-example` Compose project on Bolt 17687
  and Browser 17474, preserving the existing development graph on 7687.
- The final image passed the full Compose journey: 27 applicable questions,
  26 answers, one gap and one policy conflict; emission blocked without creating
  files. Corrected intake has 27 answers, no gaps/conflicts, and identical selected
  references. Six LZA schemas passed; seven files were emitted under
  `build/organisation-example`. Before/after review JSON is retained under `build/`.
  OPA uses the snapshot rather than mutable host files during review.
- Neo4j Browser is connected to the isolated corrected example at
  `http://localhost:17474/browser/` / `bolt://localhost:17687`. The focused graph
  view shows 13 nodes and 10 relationships; the selected region policy is `passed`.
  The example container/volume remain available for the user. Compose override:
  `/tmp/iac-organisation-compose.yaml`. Existing development data was preserved.
- Earlier live Ollama `qwen2.5:7b` extracted three stated VPC proposals, leaving
  private subnets undecided; invalid relationships were visibly pruned. Model
  quality still requires architect confirmation. No model downloads.
- Prior VPC/LZA output checks validate input contracts/schema shape only. No
  Terraform plan, AWS API, enterprise integration or deployment was run.

### Next

Try the documented workflow with one representative, sanitised client packet and
its actual selected references. Improve only questions or source mappings that
that exercise shows are missing. Keep the example lean; broaden module coverage
or ontology only when a concrete functional requirement needs it.
