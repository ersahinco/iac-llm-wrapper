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
  rag.py           native vector/graph retrieval and advisory local-model answers
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
  cli.py           ingest, status, review, index, ask, emit, emit-tfvars, scan
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
- **Retrieval stays advisory.** Explicit `index` embeds the stored case; `ask`
  uses native VectorCypherRetriever and GraphRAG with an explicit local model.
  Source citations are checked, not treated as proof of semantic correctness.
  Re-ingestion requires re-indexing. Deterministic policy results and confirmed
  document answers remain authoritative; model wording cannot unblock export.
- **Emission is fail-closed.** Any gap or conflict blocks the bundle. Defaults are
  only used with `--allow-defaults` and are recorded as `origin: default` in the
  decision trace.
- **Account root emails are owner input.** They are never generated or inferred.
- **Tool absence is not a pass.** OPA, Checkov, and Trivy each report
  `not-installed` rather than passing silently.
- **One decision catalog.** `decisions.yaml` holds decisions only: no derived
  values, no bookkeeping about itself.
- **Accept different scenarios through explicit inputs.** Client documents,
  estate details, preferences, selected standards, policies and module input
  contracts are supplied per case. Target this capability, not a built-in module
  catalog or coverage of every cloud. A reference does not automatically create
  an executable check or output mapping; unsupported requirements remain visible.
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

Support different client scenarios through sourced documents, selected estate
references, preferences, policies and explicit input contracts. Test the full
Neo4j GraphRAG retrieval-to-answer flow with a local LLM, then retain human
confirmation and deterministic checks for supported configuration output.
Use native capabilities and minimal wiring; no module-coverage roadmap,
all-cloud promise or general-purpose platform extension framework.

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

The synthetic enterprise trial and simplified README startup are verified below.
Next: have another architect complete the isolated quickstart and adapt one small
real integration, recording where help is needed. Publish a reviewed version before
expecting clones to contain the currently uncommitted GraphRAG work. Keep local
case isolation, existing Git/change approvals and explicit validation coverage.
Model answers still require source inspection; do not broaden ontology, build a
module catalog or add a shared-service framework before a demonstrated need.

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

### Session closed (2026-09-27)

- Commit `5267f70` is on main; CI run `36285014412` passed.
- Live `qwen2.5:7b` extraction and narration responded. Extraction found three
  sourced VPC proposals but omitted estate systems and pruned one relationship;
  human review remains necessary. This check made no graph changes.
- At the user's request, stopped all three project Neo4j containers: development,
  organisation example, and review example. All data volumes and output bundles
  are retained. No project test processes remain; unrelated toolkit/Ollama services
  were left alone. Resume slowly with the organisation example when requested.

### Scenario-driven GraphRAG experiment (2026-09-27)

- Added `index` and `ask` using the existing Neo4j GraphRAG dependency's native
  Ollama embeddings, vector index, VectorCypherRetriever and GraphRAG pipeline.
  Source nodes retain paths, lines and hashes; retrieval expands nearby evidence
  and linked decisions/answers. No parallel store, model-generated Cypher, new
  dependencies, automatic answers or output mappings. Reviewed export gates remain.
- Explicit installed models are required. Indexing uses the stored reference
  snapshot, not mutable host files; ingestion invalidates retrieval. The pilot
  caps cases at 500 statements, each 4,000 characters, and prompts at 32,000
  characters. Operations are sequential; no concurrent ingest/index guarantees.
- Live embeddinggemma and qwen2.5:7b runs changed retrieved context and identity
  answers from Entra ID to Okta by changing inputs only. A caller-defined runtime
  catalog and module contract also worked: the same pipeline correctly returned
  Okta and the confirmed datacentre site, without LZA integration assumptions.
- Three observed issues shaped the small integration: long citation identifiers
  confused the model (short labels retain full metadata); small approximate search
  pools missed evidence (native candidate-pool setting searches the bounded case);
  neighbouring requirements lacked their confirmed answers (expand graph links
  from every returned source line). No scenario-specific retrieval code was added.
- Model quality remains limited: the 7B model sometimes over-abstains about region
  policy rationale despite a deterministic passed result. CLI policy statuses are
  shown separately; citations establish source identity, not entailment. Missing
  estate CIDRs correctly remained insufficient evidence to prove no overlap.
- All 174 tests passed without skips, including real Neo4j retrieval with controlled
  model responses, custom inputs, stale-index/error handling and unchanged facts.
  Ruff, mypy (16 source files), strict OPA and whitespace checks passed. Upstream
  Neo4j warnings on Python 3.14 remain. CI includes the new graph tests.
- The rebuilt Compose image ran the live flow. Original export was blocked with
  one gap and one conflict; explicit input corrections enabled six LZA 1.16.3
  schema-valid files plus a trace. All four reference hashes and the client hash
  independently matched. Evidence is in ignored `build/graphrag-evaluation/`.
- Compose ports now accept environment overrides; README documents isolated
  project `iac-graphrag`, Browser 37474 and Bolt 37687. The original organisation
  sample was restored and indexed for a slow user walkthrough. The test container
  is stopped and `iac-graphrag_graph-data` retained; previous graph volumes
  and unrelated services remain untouched. Changes are local, not committed.

### One-question usability walkthrough (2026-09-27)

- Asked the saved organisation graph: "What connection method is confirmed for
  connecting this estate to AWS, and what remains undecided?" The model correctly
  reported undecided, citing the estate requirement and client line 94.
- Copied the illustrative packet into ignored `build/graphrag-walkthrough/packet/`.
  Changed only client line 94 to `hybrid_connection: site-to-site-vpn`; all four
  reference files remained byte-identical. A separate project/volume
  `iac-graphrag-walkthrough` on Browser 47474/Bolt 47687 preserved the saved case.
- The same models and question retrieved the confirmed VPN answer. Deterministic
  gaps fell from one to zero; the original region-policy conflict remained. Export
  exited 2 and created no output directory. Every returned source hash and quoted
  line matched its input file in both runs.
- **Observed model failure:** the changed-input answer falsely said the network
  CIDR was missing while citing S1, which contains `network_cidr: 10.64.0.0/16`.
  The review and retrieval were correct. Valid citations do not establish semantic
  support. No prompt tuning was performed to conceal or overfit this failure.
- Exact answers, JSON evidence, one-line diff and an annotated walkthrough are in
  `build/graphrag-walkthrough/`. No runtime changes or full test-suite rerun were
  needed for this input-only exercise; whitespace validation passed. Existing
  uncommitted changes remain intact. Both walkthrough services were stopped with
  volumes retained; unrelated services were untouched.

### Advisory answer display (2026-09-27)

- `ask` now shows the review's document answers with source lines and exact
  deterministic missing questions before model prose. Empty lists explicitly say
  none. Values are labelled as potentially conflicting, not approved or policy-valid.
  JSON includes the same sourced facts. This reuses the existing Review facts;
  retrieval, prompt, policy checks and export behavior are unchanged.
- Repeated the exact walkthrough question on the saved graph with qwen2.5:7b.
  The model repeated its false missing-CIDR claim; the display now explicitly shows
  `network_cidr: 10.64.0.0/16` at client line 56 and no missing questions above it.
  This exposes the contradiction without claiming to validate or fix model reasoning.
- All nine existing GraphRAG tests passed against a separate graph on Bolt 57687;
  Ruff, mypy and whitespace checks passed. A replay of the recorded incomplete
  case verified the exact missing question and JSON facts. No new tests were added
  for this display-only change; the full suite was not rerun. Upstream Neo4j
  Python 3.14 warnings remain.
- Evidence: `build/graphrag-display/live-answer.txt`, `missing-question-replay.txt`
  and `tests.log`. The host CLI ran the current source; rebuild the Compose app
  image for this display update. Existing user changes and saved graphs remain.
  The walkthrough and `iac-rag-display-check` test containers were stopped with
  volumes retained. Changes remain local and uncommitted.

### Client trial preparation (2026-09-27)

- Rebuilt `iac-graphrag-app` with the advisory display update. A network-disabled
  container check confirmed the sourced-answer and missing-question display code
  is present. No graph was started or changed; the temporary check container was
  removed. Build log: `build/client-trial/build.log`.
- Awaiting a user-selected sanitised client packet path or short case description,
  including any selected estate, preferences, standards, policies or input contract.
  No client case was invented or trial claimed. Next action is to map that supplied
  packet into existing explicit inputs and run it in an isolated graph. No runtime
  edits or test-suite rerun were needed for this image preparation.

### Enterprise scenario and adoption review (2026-09-27)

- At the user's request, created a clearly synthetic factory telemetry packet with
  four caller-defined questions, OT estate references, selected retention standard,
  scoped Rego policy and an illustrative module input contract. Inputs and evidence
  are in ignored `build/enterprise-review/`; no scenario-specific runtime code.
- Initial Compose review found one missing transport decision and a sourced
  90-day/30-day retention conflict; variable export exited 2 without creating files.
  Explicit corrections selected MQTT over TLS and 30 days. References were unchanged;
  stale retrieval was refused until indexed again. Four variables passed the custom
  schema and a trace was emitted. This fictional contract is not a tested real module.
- Live local GraphRAG tracked the transport change and kept eight-hour recovery
  unproven, but also falsely called integration systems unclear despite its retrieved
  sources. All retrieved line quotes/hashes and trace reference hashes matched.
  A clean catalog/policy review did not prove recovery, routing, capacity or device
  trust: unencoded prose is context, not an automatic export gate.
- Three findings: startup mixed the core journey with optional scanner failures;
  coverage/answer quality depends on explicit requirements and human inspection;
  distribution should remain a maintained local case kit with existing approvals.
  Only the README startup/adoption guidance changed: organisation example first,
  named project/ports, expected blocked steps, seven-file success and optional scans.
- Full current suite passed: 174 tests, no skips, on isolated Bolt 58687. Ruff,
  mypy (16 files), strict OPA and whitespace checks passed. Upstream Neo4j/Python
  3.14 warnings remain. Native model tests are controlled; live answer correctness
  is not established by the automated pass count.
- Rebuilt and executed every revised quickstart command in `iac-quickstart` on
  Browser 18474/Bolt 18687. Six LZA schemas and all source/reference trace hashes
  independently passed; output is `build/quickstart`. Enterprise trial uses
  `iac-enterprise-review`, Browser 58474/Bolt 58687. Both services stopped with
  volumes retained; older graphs and user changes preserved. Nothing deployed.
- Detailed review: `build/enterprise-review/review.md`. Current runtime changes
  remain uncommitted; no push or shared enterprise hosting was performed.

### Reviewed version and colleague trial (2026-09-27)

- User authorised committing and pushing the reviewed native GraphRAG, sourced
  answer display, isolated Compose ports, tests and simplified onboarding together.
  The full current suite previously passed 174 tests; final Ruff, mypy, strict OPA
  and whitespace checks passed again. Generated packets, model outputs and local
  test logs remain ignored under `build/`; they are not part of the published code.
- The next test requires a real colleague using the published README unaided.
  Participant instructions and observer criteria are prepared under
  `build/colleague-test/` against the resulting commit. Recipient/channel are being
  requested; no colleague completion or human usability result may be inferred
  from automated checks. Record actual feedback before changing functionality.
- Check the resulting commit's remote CI before handoff. Keep all saved graph
  volumes and stopped containers unchanged. No new runtime work in this session.
