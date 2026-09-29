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

### Extract proposals

`ingest DOCUMENT --extract-model YOUR_MODEL --base-url http://host.docker.internal:11434`
adds sourced System/Candidate proposals through Neo4j GraphRAG's schema-guided
extractor. It accepts one UTF-8 packet of up to 32,000 statement characters and
needs no vector index. Invalid evidence fails before graph replacement; unsupported
items are pruned with warnings. Architects confirm answers in the document and
re-ingest. Matching quotes and valid JSON do not establish semantic accuracy.

## Output contracts

Exports create new files only. Use a fresh output directory for each revision;
existing files, directories at file destinations and symlinks are refused before
writing. Owner files and earlier bundles stay intact.

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
values block export. Native subnet checks reject malformed or noncanonical CIDRs,
subnets outside their VPC, peer overlaps and mismatched subnet/zone counts.
No schema is fetched remotely.

The [workload policy walkthrough](samples/vpc/README.md) adds routing-domain
allocation checks, environment-specific instance allowlists, recorded exceptions
and advisory monitoring warnings. It also exports two mapped inputs for the pinned
EC2 instance module. These are selected input policies, not live inventory or
capacity recommendations.

The consuming root module declares and passes these variables. It owns other
module settings, providers, backend, routing validation and plan review. This is
a reviewed input subset, not complete module coverage. No resources are generated,
no Terraform command runs, and no state is handled.

## Security discussion and scans

Checkov and Trivy inspect owner-supplied IaC for common security issues. Install
both on the host (`brew install opa checkov trivy` on macOS) and use the
[host environment](CONTRIBUTING.md#local-checks). The Compose app includes OPA
but does not bundle these two scanners.

```bash
# Uses the Neo4j connection variables for the currently selected case.
uv run --locked --extra dev --extra graphrag iac-llm-wrapper review --scan PATH_TO_OWNER_IAC
uv run --locked --extra dev --extra graphrag iac-llm-wrapper scan PATH_TO_OWNER_IAC
uv run --locked --extra dev --extra graphrag iac-llm-wrapper scan PATH_TO_OWNER_IAC --strict
```

Security findings are advisory warnings by default. `--strict` makes open scan
findings return exit 1 for pipeline use. Native exceptions reported by Checkov and
Trivy remain visible, including their reasons when provided. Prefer scoped Checkov
inline exceptions and a `.trivyignore.yaml` in the scanned directory; its statement
should identify the owner's decision and rationale. Scanners can omit inline
suppressions from their reports, so a missing exception entry does not prove there
are none. This tool neither grants nor authenticates an exception.

`scan build/quickstart` additionally checks all six LZA schemas and the bundled OPA
artifact policy. Schema failures remain blocking. Selected organisation policies
are assessed by `review` and reassessed on export: `conflict` and `not-assessed`
block; explicit `warning` outcomes remain visible in review, export and the trace.
A policy author can use that outcome for advice or a scoped, evidenced exception.

Region restrictions and required security controls belong to the selected
organisation policy. The bundled artifact scan supplies general advice and has
no region allowlist. `compliance_overlay` selects LZA template settings; it does
not impose security requirements on its own. The [organisation example](samples/organisation/README.md)
shows required controls with owner/reason exceptions. Existing cases retain their
stored policy; re-ingest with `--organisation` to select updated requirements.

Missing tools report `not-installed`; no assessed checks reports `not-assessed`.
Failures and incomplete coverage return exit 1 even without `--strict`. Neither
LZA YAML nor standalone tfvars establishes resource security coverage; scan the
consuming IaC too. Checkov is scoped to Terraform, CloudFormation, Kubernetes,
Dockerfile and secrets. Trivy runs secret/misconfiguration checks. Neither tool
runs Terraform or contacts AWS. Checkov module downloads and Trivy check updates
are disabled during scans; owners maintain scanner versions and checks separately.

`review --scan` includes a separate `security_scans` array in JSON. Artifact scans
are current directory observations, not stored client facts or automatic export
approvals. CLI exit codes: `0` no blockers (warnings may remain), `1` review blockers,
incomplete scans or strict scan findings, `2` blocked export or command failure.
Use `COMMAND --help` for options and stop Compose with `docker compose stop`.

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) covers setup, isolated tests and pull requests.
Start with an observed problem or small sanitised case. Keep evidence, human
confirmation and explicit output contracts; reuse existing tools before adding
custom code. The [design guide](docs/design.md) explains the boundaries and extension points;
the [code map](AGENTS.md#code-map) shows where changes belong.

## License

Copyright 2026 Cemreoguz Ersahin. [Apache License 2.0](LICENSE).
Bundled LZA schemas retain their [upstream notices](src/intent_engine/schemas/NOTICE.txt).
