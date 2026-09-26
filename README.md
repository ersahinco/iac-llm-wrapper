# iac-llm-wrapper

A knowledge-graph tool that captures requirements and architecture decisions from
a customer document, surfaces gaps and conflicts so architects can steer the
client discussion, and emits configuration for an existing AWS accelerator.

It does not deploy anything. It holds no credentials, calls no AWS API, and runs
no Terraform. The output is configuration an owner reviews and feeds to their own
pipeline.

## How it works

```
document ──ingest──▶ Neo4j ──review──▶ gaps + conflicts ──▶ architect discussion
                       │
                       └────emit────▶ AWS LZA config ──scan──▶ OPA / Checkov / Trivy
```

1. **Ingest** reads the whole document. Every run replaces the graph: no
   incremental diff, no baseline, nothing to reconcile.
2. **Neo4j** holds the decision catalog, the document, each prose statement, and
   each accepted fact with the statement it came from.
3. **Review** finds gaps and conflicts deterministically. Gaps come from graph
   applicability in Cypher; conflicts come from named rules. A missing answer, an
   unusable value, and two answers that cannot both hold are three different
   findings.
4. **The LLM is optional and advisory.** It never sees the document and never
   decides anything. It receives the deterministic frontier and turns it into a
   discussion agenda.
5. **Emit** writes AWS LZA sample-style configuration, fail-closed: any gap or
   conflict blocks the bundle. Account root emails are owner input and are never
   generated.
6. **Scan** runs OPA against the landing-zone policy, plus Checkov and Trivy for
   misconfiguration and secret findings.

## Layout

```
src/intent_engine/
  decisions.yaml      the decision catalog: questions only a human can answer
  catalog.py          load and validate the catalog, coerce document values
  ingest.py           whole-document read: statements + facts
  graph.py            Neo4j schema, full replace, gap and contradiction Cypher
  analysis.py         applicability and named conflict rules
  llm.py              optional narration of the deterministic frontier
  emit.py             AWS LZA configuration and the decision trace
  scan.py             OPA, Checkov, Trivy
  policy/lza.rego     the landing-zone policy
samples/              one realistic customer packet
```

## Setup

```bash
uv lock
uv sync --extra dev
docker compose up -d --wait
export NEO4J_URI=bolt://127.0.0.1:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=localdevpassword
```

`--wait` matters: the Docker port proxy accepts connections before Bolt is ready,
and the driver then reports an incomplete handshake rather than a refusal.

`NEO4J_PASSWORD` has no default. Without it the tool refuses to connect rather
than falling back to an anonymous session.

The external tools are optional and separate:

```bash
brew install opa checkov trivy
```

## Use

```bash
uv run iac-llm-wrapper ingest samples/banking-packet.md
uv run iac-llm-wrapper status
uv run iac-llm-wrapper review
uv run iac-llm-wrapper emit --out build/lza
uv run iac-llm-wrapper scan build/lza
```

Narrate the same review with a model. Provider and model are always explicit:

```bash
uv run iac-llm-wrapper review --llm ollama --model llama3.2:3b \
  --base-url http://localhost:11434
uv run iac-llm-wrapper review --llm openai --model gpt-4o-mini \
  --base-url https://api.openai.com/v1 --api-key "$OPENAI_API_KEY"
```

Exit codes: `0` clean, `1` findings (open gaps, conflicts, or scan findings),
`2` the command could not run.

## Checks

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .
uv run --extra dev mypy
NEO4J_PASSWORD=localdevpassword uv run --extra dev pytest tests/test_graph.py
```

The Neo4j tests wipe the database they connect to. Point them at the local
development instance only.

The policy is checked with OPA directly:

```bash
opa check --strict src/intent_engine/policy
opa fmt --fail --list src/intent_engine/policy
```

`opa`, `checkov`, and `trivy` are external tools. When one is absent, `scan`
reports `not-installed` for it. It is never reported as a pass.

## Scope

In: decision capture, gap and conflict detection, AWS LZA configuration output,
policy and secret scanning of that output.

Out: deploying anything, generating Terraform, holding credentials, owning state,
approvals, or drift.
