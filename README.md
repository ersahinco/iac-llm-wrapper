# IaC Accelerator (`iac-llm-wrapper`)

A knowledge-graph tool that captures requirements and architecture decisions from
a customer document, surfaces gaps and conflicts so architects can steer the
client discussion, and emits configuration for an existing AWS accelerator.

It does not deploy anything. It holds no credentials, calls no AWS API, and runs
no Terraform. The output is configuration an owner reviews and feeds to their own
pipeline.

Open source under [Apache 2.0](LICENSE). Use it, fork it, and contribute focused
improvements through [issues](https://github.com/ersahinco/iac-llm-wrapper/issues)
and pull requests.

## How it works

```
document ──ingest──▶ Neo4j ──review──▶ gaps + conflicts ──▶ architect discussion
                       │
                       └────emit────▶ AWS LZA config ──scan──▶ OPA / Checkov / Trivy
```

1. **Ingest** reads the whole document. Every run replaces the graph: no
   incremental diff, no baseline, nothing to reconcile. Replacement is atomic:
   a failed reload preserves the previous graph. Use a dedicated database because
   ingestion replaces every node in it.
2. **Neo4j** holds the decision catalog, the document, each prose statement, and
   each accepted fact with the statement it came from.
3. **Review** finds gaps and conflicts deterministically. Gaps come from graph
   applicability in Cypher; conflicts come from named rules. A missing answer, an
   unusable value, and two answers that cannot both hold are three different
   findings.
4. **The LLM is optional and advisory.** It never sees the document and never
   decides anything. It receives the deterministic frontier and turns it into a
   discussion agenda.
5. **Emit** writes foundation configuration checked against **LZA 1.16.3** schemas,
   plus a decision trace and owner handoff. Gaps, conflicts, or schema errors block
   the bundle. Account emails and identity policy mappings are explicit inputs.
6. **Scan** rechecks the LZA schemas, runs OPA policy, Checkov secrets, and Trivy
   checks. Each result states its coverage.

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
  contract.py         offline validation against one pinned LZA version
  schemas/            unchanged upstream LZA schemas and license notices
  scan.py             OPA, Checkov, Trivy
  policy/lza.rego     the landing-zone policy
samples/              one realistic customer packet
```

## Setup

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and Docker with Compose
for the local Neo4j database.

```bash
git clone https://github.com/ersahinco/iac-llm-wrapper.git
cd iac-llm-wrapper
uv sync --locked --extra dev
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

Start with the [example packet](samples/banking-packet.md). Answers use
`decision_key: value` lines, with keys from
[`decisions.yaml`](src/intent_engine/decisions.yaml). Other prose is retained as
context; the tool does not infer answers from free-form text. Replace the sample
account emails with owner-provided addresses before using the output.

```bash
uv run iac-llm-wrapper ingest samples/banking-packet.md
uv run iac-llm-wrapper status
uv run iac-llm-wrapper review
uv run iac-llm-wrapper emit --out build/lza
uv run iac-llm-wrapper scan build/lza
```

## Integration contract

| Output | Consumer |
| --- | --- |
| Six `*-config.yaml` files | The owner's LZA **1.16.3** configuration repository, after review and completion |
| `decision-trace.yaml` | Architect: stated answers, source lines, and opt-in defaults |
| `handoff.yaml` | Network, identity, data, and application owners: remaining integration work |

Schemas are bundled and validated offline. There are no AWS lookups, credentials,
or downloads during validation. A different LZA version requires an explicit
contract update; there is no automatic version fallback or baseline selector.

The network output is a foundation skeleton. Owners must complete routes,
subnets, attachments, DNS, and inspection. Identity mappings currently support
AWS-managed policies explicitly named in the packet; owners verify availability
and connect their identity provider. Data classification, approved data/backup
regions, recovery objectives, and the application owner travel in the handoff;
this tool does not provision workload databases, backups, or applications.

Keep each packet to one shared workload handoff scope. Different residency or
recovery requirements need separate design review; this is not yet a per-asset
architecture model. The bundled banking packet is an illustrative example.

The handoff always says `requires-owner-validation`. The consuming pipeline runs
the matching LZA validator, reviews synthesized changes, and owns deployment.
Schema success means the configuration has the expected shape, not that the
architecture is complete. Fixed emitter choices such as log retention and session
duration also require owner review; the decision trace records catalog answers.

Narrate the same review with a model. Provider and model are always explicit:

```bash
uv run iac-llm-wrapper review --llm ollama --model llama3.2:3b \
  --base-url http://localhost:11434
uv run iac-llm-wrapper review --llm openai --model gpt-4o-mini \
  --base-url https://api.openai.com/v1 --api-key "$OPENAI_API_KEY"
```

Exit codes: `0` clean, `1` findings (open gaps, conflicts, or unsuccessful scans),
`2` the command could not run.

## Checks

```bash
uv run --locked --extra dev pytest
uv run --locked --extra dev ruff check .
uv run --locked --extra dev mypy
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
reports `not-installed`. When a scanner provides no evidence of assessed checks,
it reports `not-assessed`. Tool errors, missing tools, unassessed checks, and
findings all make `scan` exit with code `1`.

The current sample's LZA YAML can produce zero assessed checks in Checkov and
Trivy. Such a scan is incomplete even when OPA passes. A secret scan without
findings does not necessarily report which files it assessed. A passing schema or
policy check alone is not a deployment-readiness claim.

## Scope

In: decision capture, gap and conflict detection, AWS LZA configuration output,
policy and secret scanning of that output.

Out: deploying anything, generating Terraform, holding credentials, owning state,
approvals, or drift.

## Contributing

Fork the repository, make a focused change, run the checks above, and open a pull
request explaining the problem and how you verified the fix. Include a regression
test for behavior changes. Graph tests require the local Neo4j instance; policy
changes require OPA.

Add a catalog decision or conflict rule when a concrete use case needs it. Keep
the deterministic review and optional AI agenda separate, and keep deployment in
the consuming pipeline. Use sanitized examples in issues and tests.

## License

Copyright 2026 Cemreoguz Ersahin. Licensed under the [Apache License 2.0](LICENSE).
Contributions are accepted under the same license.
Bundled LZA schemas retain their [upstream notices](src/intent_engine/schemas/NOTICE.txt).
