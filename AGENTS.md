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
- **Keep the model in the working graph.** Neo4j holds sourced case knowledge;
  versioned code, catalogs and input contracts define the supported boundaries.
  Reuse native Neo4j/Cypher, GraphRAG, OPA and JSON Schema capabilities first.
  Add custom wiring only for a demonstrated missing capability; no parallel
  ontology document, speculative roadmap or general-purpose framework.
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
- **Distribution and CI.** Apache 2.0 repository. Organisation milestone `0f71372`
  was pushed to main and passed all five CI jobs (run `36284026882`). OPA is
  installed in the graph CI job for the complete discussion-to-export check.

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

Simplicity review: improve the first-run experience before adding functionality.
Use the organisation example as the main quickstart; keep optional scanner setup
separate from its successful completion. Reduce repeated findings in text review.
Announce whether ingest loaded, reused or cleared organisation references. These
are review recommendations, not implemented changes. No tests were rerun for this
read-only application review; the existing deletion of `.opencode/AGENTS.md` was
left untouched.

Next session should test one isolated Compose journey, make only one small
evidence-backed improvement, then report the result and the next smallest step.
Try adapting one representative, sanitised client packet before broadening module
coverage or ontology. Preserve provenance, human confirmation and blocked export
when findings or unassessed policies remain.

### Focused review session (2026-09-27)

- The organisation example reproduced one `hybrid_connection` gap sourced to
  `estate.md:5` and one `ORG_POLICY_CONFLICT` citing the client answer,
  `policy.rego:3`, and the selected configuration hash. Export exited 2 without
  creating its output directory. Correction preserved the full organisation
  snapshot, passed its scoped policy, and emitted six LZA 1.16.3 schema-valid
  files plus one decision trace.
- Three usability findings: quickstart isolation needs extra setup; text review
  repeats the conflict three times and the missing question twice; ingest does
  not explain snapshot reuse. Only the last was changed: successful ingest now
  reports organisation references as loaded, reused, cleared, or none, naming
  the organisation when present. No reference, evidence, or policy logic changed.
- All 165 tests passed without skips using the new isolated graph; Ruff, mypy
  (15 source files), and strict OPA validation passed. The host test run reports
  upstream Neo4j deprecation warnings on Python 3.14.
- The rebuilt Compose image passed the complete journey again and all four new
  ingest messages were checked. The final seven-file bundle is in
  `build/review-20260927/after-change/lza`; its six schemas and trace reference
  hashes were independently checked. The isolated graph retains the corrected case.
- Isolation: `iac-review-20260927`, Browser 27474, Bolt 27687, data volume
  `iac-review-20260927_graph-data`; override `/tmp/iac-review-20260927-compose.yaml`.
  The existing development and earlier example graphs/volumes were untouched.
  Evidence and bundles are under `build/review-20260927/`. Existing deletions of
  `.devcontainer/devcontainer.json` and `.opencode/AGENTS.md` and earlier edits
  to this file were preserved.
- Next smallest step: document explicit project/port isolation in the organisation
  quickstart. Stop here; no additional functionality or ontology work in this session.

### Simplicity cleanup (2026-09-27)

- Removed the root ontology proposal and historical review; the README now points
  to the implemented graph and example queries. Native capabilities come first;
  custom wiring needs a demonstrated gap. Corrected the stale graph docstring.
- Read-only inspection confirmed the example's systems, integrations, policies,
  assessments and evidence links in Neo4j. The installed GraphRAG async Ollama
  path still misroutes model parameters, so its small compatibility adapter stays.
- README local links, unchanged graph runtime AST, Ruff, mypy and diff whitespace
  checks passed. No runtime behavior changed; tests were not rerun for this cleanup.
  Earlier user changes and graph data remain intact. The next step remains the
  isolated organisation quickstart, without adding a separate design document.

### User testing handoff (2026-09-27)

- User requested committing and pushing the reviewed changes, including cleanup.
- Next: test slowly before adding features. Walk through the organisation packet's
  evidence and blocked export, then correction and trace; try advisory GraphRAG
  separately, then the VPC variable contract. Finally adapt one sanitised client
  packet. Change only friction or missing integration behavior demonstrated there.
- This is a usable guided prototype. Schema checks do not establish working
  connectivity, federation, deployment readiness, or reliable LLM interpretation.
