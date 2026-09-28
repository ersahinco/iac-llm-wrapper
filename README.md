# iac-llm-wrapper

Turn client requirements and selected organisation references into sourced
architecture reviews and configuration inputs. Architects resolve missing answers
and policy conflicts before handing work to an engineering team.

Neo4j stores the evidence; optional Neo4j GraphRAG and local LLMs help explore it.
Supported exports are AWS Landing Zone Accelerator (LZA) configuration and Terraform
module variable JSON, each with a decision trace. Nothing deploys or runs Terraform.

**Status: guided local prototype.** The example workflow is tested. Real client
adoption and model answer quality still need evaluation; output requires owner review.

## Quickstart

Requires Docker with Compose. No Python or LLM setup is needed. Run the commands
in order; the first review and export deliberately fail to demonstrate the gates.

```bash
git clone https://github.com/ersahinco/iac-llm-wrapper.git
cd iac-llm-wrapper
export COMPOSE_PROJECT_NAME=iac-quickstart
export NEO4J_BROWSER_PORT=18474 NEO4J_BOLT_PORT=18687
docker compose build app
docker compose run --rm app ingest samples/organisation/client.md \
  --organisation samples/organisation/organisation.yaml
docker compose run --rm app review  # expected exit 1: one gap and one conflict
docker compose run --rm app emit --out build/quickstart  # expected exit 2: blocked
docker compose run --rm app ingest samples/organisation/confirmed.md
docker compose run --rm app review
docker compose run --rm app emit --out build/quickstart
docker compose stop
```

The initial packet lacks a hybrid connection decision and requests a region outside
its selected organisation policy. The corrected packet records VPN and permitted
regions, reuses the references, and produces **six schema-valid LZA files plus
`decision-trace.yaml`** in `build/quickstart`. These are synthetic inputs.

Keep the environment variables for the whole walkthrough. Use a different project
name and unused ports for each case: **ingestion replaces every node in that
project's database**. Replacement is atomic; a failed ingest preserves the prior
case. Stopping retains the data volume. The image includes OPA and LZA schemas.

The [organisation guide](samples/organisation/README.md) explains the evidence,
policy contract and [graph view](samples/organisation/README.md#see-the-graph).

## Use your own case

```text
client document + selected references
                  ↓ ingest
             Neo4j evidence
                  ↓ review
             gaps + conflicts
                  ↓ architect records answers and ingests again
             checked configuration + decision trace
```

Answers use `decision_key: value` lines, with questions from the
[default catalog](src/intent_engine/decisions.yaml) or an explicit `--catalog`.
Other prose is retained as context. Account emails and identity policy mappings
must come from the owner; the tool does not invent them.

Selected references can describe existing hybrid estates, preferences, standards,
policies and module contracts. Re-ingestion preserves their stored contents and
hashes. Supply `--organisation` again to refresh them, or `--without-organisation`
to clear them for an unrelated case. Reference values never become client answers.

A maintainer prepares the questions, reviewed Rego checks and output mappings;
architects edit answers and inspect findings. Keep these inputs together in approved
version control. Engineers validate the handoff through their existing approvals
and pipeline. The trace records evidence, not reviewer identity or sign-off.

A requirement only blocks export when covered by an applicable question, executable
policy or output contract. Requirements such as recovery time, capacity and device
trust need explicit coverage and owner validation. Adding reference text does not
create checks or mappings. The local Compose setup supports one operator; it has
no per-client authentication or concurrent editing guarantees.

## Optional GraphRAG

### Ask about the ingested case with GraphRAG

After the quickstart, keep its Compose environment settings and use two already
installed Ollama models: one for embeddings and one for answers. These names are
examples; select models available on your server. No model is downloaded automatically.

```bash
docker compose run --rm app index --embedding-model embeddinggemma:latest \
  --base-url http://host.docker.internal:11434
docker compose run --rm app ask \
  "What connection method is recorded for this estate, and what evidence supports it?" \
  --model qwen2.5:7b --base-url http://host.docker.internal:11434
docker compose stop
```

`index` embeds the stored client and reference snapshot. Native Neo4j GraphRAG
`VectorCypherRetriever` expands source hits through evidence links; `GraphRAG`
passes the context to the answer model. `ask` shows sourced document answers,
deterministic gaps and policy statuses before the model's advisory response.
Use `--json` for structured facts, findings and retrieved sources.

Re-ingestion invalidates retrieval: run `index` again. Use the same embedding
model/server for indexing and questions. To test another scenario, change the
inputs, refresh selected references and re-index; no scenario-specific retriever
is needed. Run ingest, index and ask sequentially.

The current limits are 500 source statements, 4,000 characters per statement and
32,000 characters per prompt. Reduce `--top-k` or narrow the case if needed.
Unknown citation identifiers are rejected, but valid citations do not prove a
claim is supported. Live tests have produced incorrect statements despite matching
citations. Inspect the sources; model answers never supply confirmed facts or
unblock export. No model-generated Cypher is executed.

### Extract proposals or narrate a review

`ingest DOCUMENT --extract-model YOUR_MODEL --base-url http://host.docker.internal:11434`
adds sourced System/Candidate proposals through Neo4j GraphRAG's schema-guided
extractor. It accepts one UTF-8 packet of up to 32,000 statement characters and
needs no vector index. Invalid evidence fails before graph replacement; unsupported
items are pruned with warnings. Architects confirm answers in the document and
re-ingest. Matching quotes and valid JSON do not establish semantic accuracy.

To turn the deterministic review into a discussion agenda:

```bash
docker compose run --rm app review --llm ollama --model YOUR_MODEL \
  --base-url http://host.docker.internal:11434
docker compose stop
```

Provider and model are always explicit. `review --help` also documents the
OpenAI-compatible provider options; only use an external endpoint approved for
the case's data.

## Output contracts

### AWS Landing Zone Accelerator

| Output | Consumer |
| --- | --- |
| Six `*-config.yaml` files | The owner's LZA **1.16.3** configuration repository |
| `decision-trace.yaml` | Answers, evidence, reference hashes, policy assessments and integration context |

Bundled schemas are validated offline. Gaps, conflicts, unassessed selected
policies and schema errors block export. Defaults require `--allow-defaults`
and are recorded as `origin: default`. Changing LZA versions requires an explicit
contract update. No AWS API calls or cloud credentials are needed.

Network output is a foundation skeleton. Owners complete routes, subnets,
attachments, DNS and inspection. To preserve an owner-maintained network file:

```bash
docker compose run --rm app emit --out build/lza \
  --network-config /workspace/build/owner-lza/network-config.yaml
```

Place the owner file in the ignored `build/owner-lza/` directory locally.
Keep it outside the generated output directory. Its data is preserved
and schema-checked; the trace records its path and SHA-256. The packet's region,
host/CIDR and topology must match. Cross-file and routing validation remain in the
owner's LZA pipeline.

Identity output supports explicitly named AWS-managed policies; owners verify them
and connect their identity provider. Hybrid networking, federation, data/backup
regions, recovery objectives and application ownership also travel as integration
context; the tool does not provision those external systems or workloads.
Keep a packet to one shared workload scope.

Integration context is labelled `requires-owner-validation`. Schema success
establishes shape, not working connectivity or a complete architecture. Fixed
emitter choices such as retention and session duration also need owner review.

### Terraform module variables

The [VPC example](samples/vpc/requirements.md) uses a caller-supplied catalog and
JSON Schema input contract. Run it in a separate case:

```bash
export COMPOSE_PROJECT_NAME=iac-vpc
export NEO4J_BROWSER_PORT=48474 NEO4J_BOLT_PORT=48687
docker compose build app
docker compose run --rm app ingest samples/vpc/requirements.md \
  --without-organisation --catalog samples/vpc/decisions.yaml
docker compose run --rm app review  # expected exit 1: four questions need explicit answers
docker compose run --rm app ingest samples/vpc/confirmed.md \
  --catalog samples/vpc/decisions.yaml
docker compose run --rm app emit-tfvars \
  --contract samples/vpc/module-inputs.json --out build/vpc
docker compose stop
```

This writes `terraform.tfvars.json` and `decision-trace.json` for four inputs of
[`terraform-aws-modules/vpc/aws` 6.7.3](https://github.com/terraform-aws-modules/terraform-aws-vpc/tree/v6.7.3):
name, CIDR, availability zones and private subnet CIDRs. The
[contract](samples/vpc/module-inputs.json) uses `x-decision` mappings and `x-module`
provenance. Missing mappings, unanswered or conflicting decisions and invalid
values block export. No schema is fetched remotely.

The consuming root module declares and passes these variables. It owns other
module settings, providers, backend, network validation and plan review. This is
a reviewed input subset, not complete module coverage. No resources are generated,
no Terraform command runs, and no state is handled.

## Optional scans

`docker compose run --rm app scan build/quickstart` rechecks LZA schemas and runs
OPA, Checkov secrets and Trivy checks. It does not scan Terraform variable output.
Checkov and Trivy are not bundled; install them separately for host use
(`brew install opa checkov trivy` on macOS). See [host setup](CONTRIBUTING.md#local-checks).

Missing tools report `not-installed`; no evidence of assessed checks reports
`not-assessed`. Either makes a scan incomplete, even if OPA passes. The sample LZA
YAML can produce zero assessed checks in Checkov and Trivy. Each result states its
coverage; a secret scan without findings is not proof of a complete assessment.

CLI exit codes: `0` clean, `1` review findings or unsuccessful scans, `2` blocked
export or a command failure. Use `docker compose run --rm app COMMAND --help`
for options. Stop the database after optional commands with `docker compose stop`.

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) covers setup, isolated tests and pull requests.
Start with an observed problem or small sanitised case. Keep evidence, human
confirmation and explicit output contracts; reuse existing tools before adding
custom code. The [code map](AGENTS.md#code-map) shows where changes belong.

## License

Copyright 2026 Cemreoguz Ersahin. [Apache License 2.0](LICENSE).
Bundled LZA schemas retain their [upstream notices](src/intent_engine/schemas/NOTICE.txt).
