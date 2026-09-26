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
  emit.py          AWS LZA configuration plus decision trace
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

Python 3.11+, Pydantic v2, Typer, ruamel.yaml, neo4j driver, Neo4j 5, OPA,
Checkov, Trivy. Tests: pytest. Lint/type: ruff, mypy.

## Session State

<!-- UPDATE THIS SECTION AT END OF EVERY SESSION -->

### Current Goal

Keep the tool to the functional requirement: capture decisions in a graph, find
gaps and conflicts, emit accelerator configuration, check that output with policy
and security tools.

### Status

- **Fresh-start history.** The refactored project is the initial snapshot on
  `main`. The public repository uses Apache 2.0; runtime behavior is unchanged.
- **Open-source contribution path prepared.** README covers cloning, setup,
  explicit decision input, scope, and contributions under Apache 2.0. Corrected
  the license text typo and stale graph-test command in the PR template. Local
  environment files are ignored. Runtime behavior is unchanged.
- **Hard refactor applied.** Every file of the old engine is deleted: 35 core
  modules, 4 pattern packages, 9 eval/validation scripts, 47 old tests, 10 docs,
  all 6 fixture bundles, the packaged Terraform root, and the release/supply-chain
  machinery (bandit, pyright, prek, build constraints, release workflow).
- **Kept deliberately small.** 10 source files, 1 decision catalog, 1 rego policy,
  1 sample packet, 3 test modules, 3 markdown files (README, AGENTS, LICENSE).
- **Connection errors name their cause.** Rejected credentials, an unusable URI,
  and nothing answering Bolt are three messages. The driver is closed before the
  error is raised so its destructor cannot warn later. Default URI is
  `bolt://127.0.0.1:7687`; `localhost` made the driver fail on `::1` first.
- **Neo4j is the graph.** The previous in-memory requirement graph is gone.
  Applicability, blocking chains, and contradictions are Cypher over
  `(:Decision)`, `(:Document)`, `(:Statement)`, `(:Fact)`.
- **Salvaged:** the AWS LZA decision content (now `decisions.yaml`), the LZA
  config shapes (now `emit.py`), and the banking customer packet (now
  `samples/banking-packet.md`).
- **Added:** `policy/lza.rego` for OPA, plus Checkov and Trivy runners with
  distinct not-installed, error, and findings verdicts.

### Verified (2026-09-26, Python 3.14.7, macOS)

- Publication checks: 45 unit/output tests and all 5 local Neo4j integration
  tests pass; Ruff, mypy, and strict OPA validation pass. Gitleaks scanned all
  fetched Git history (233 commits) and reported no leaks.
- 50 tests pass, including the 5 Neo4j tests against `neo4j:5.26.4-community`
  and the OPA negative test. Ruff clean. Mypy clean over 11 source files.
  `opa check --strict src/intent_engine/policy` passes.
- Full journey on `samples/banking-packet.md`: ingest, review reporting no gaps
  and no conflicts, 7 emitted files, and `scan` passing on real binaries —
  opa 1.21.0, checkov 3.3.10, trivy 0.74.0.
- The policy is proven able to fail: flipping `terminationProtection` to false
  produces an OPA denial naming that field.
- Remaining noise is third-party: the neo4j driver calls
  `asyncio.iscoroutinefunction`, deprecated in Python 3.14. Nothing to fix here.

### Next

Nothing is queued. Add a decision to `decisions.yaml` or a conflict rule to
`analysis.py` only when a real packet exposes the gap.
