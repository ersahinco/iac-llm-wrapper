# From incomplete answers to an engineering handoff

An architect has recorded a synthetic bank's landing-zone answers. A platform
engineer needs the missing decisions resolved and policy conflicts explained before
accepting configuration inputs. This walkthrough finds both, then shows exactly
what the corrected packet exports and what still belongs to the consuming team.

These are illustrative inputs, not bank approval. Existing on-premises/SD-WAN/Azure
networking and Entra ID remain integration context. No LLM, cloud credentials,
Terraform execution or AWS API calls are involved.

## Run the example

Requires Docker with Compose running; the image includes Python, OPA and the LZA
schemas. The first build downloads images/packages. From the repository root,
choose unused ports and a new project. Keep these variables in the same terminal:

```bash
export COMPOSE_PROJECT_NAME=iac-value-$(date +%Y%m%d-%H%M%S)
export NEO4J_BROWSER_PORT=59374 NEO4J_BOLT_PORT=59387
docker compose build app
```

**Each ingest replaces the whole graph in the selected project.** Never point
these commands or graph tests at a saved client case. The ports above differ from
the [contributor test setup](../../CONTRIBUTING.md#full-suite-with-neo4j-and-opa).
The output directory `build/value-review/lza` must also be unused; choose a fresh
one if repeating the export. Do not delete earlier bundles to make room.

The CLI output below was captured on **2026-09-29** with real Neo4j 5.26.4 and
OPA 1.21.0 in isolated project `iac-value-20260929`. Docker lifecycle messages are
omitted; review excerpts omit the system list and owner integration reminders.
Paths under `/workspace` are inside the container. Hashes/line numbers describe
the checked-in example at capture time and change when the source changes.

### 1. Ingest the incomplete packet and inspect findings

```bash
docker compose run --rm -T app ingest samples/organisation/client.md \
  --organisation samples/organisation/organisation.yaml
```

Exit **0**:

```text
ingested samples/organisation/client.md (sha256 68563b996a92)
organisation references: loaded snapshot — Blue River Bank illustrative organisation
statements: 59  facts: 26
```

```bash
docker compose run --rm -T app review
```

Exit **1**, with one missing answer and one policy conflict:

```text
document: samples/organisation/client.md (sha256 68563b996a92)
applicable decisions: 27  answered: 26  gaps: 1  conflicts: 1

gaps
  - hybrid_connection: How will AWS connect to the existing hybrid enterprise network?
      hint: Connection method only; routes, DNS and attachment implementation remain with the network team.
      evidence: /workspace/samples/organisation/estate.md:5 — AWS needs connectivity to the existing enterprise network; the connection method must be decided.

conflicts
  - ORG_POLICY_CONFLICT: approved-regions: Regions outside the organisation standard: ["us-east-1"]
      evidence: /workspace/samples/organisation/policy.rego:3 — AWS enabled regions must be within the organisation's selected LZA region standard.
      evidence: samples/organisation/client.md:30 — enabled_regions: eu-central-1, eu-west-1, us-east-1
      evidence: /workspace/samples/organisation/lza-reference.yaml (sha256 9b6f6083bda72ed11c1ea14f9fe81c03ed57b48463ec8b00215922efa03e72e1)
```

The missing connection decision points to the estate requirement. The region
conflict points to the policy, the explicit client answer and the selected
reference hash. The reference describes the permitted regions; it does not supply
an answer on the client's behalf.

```bash
docker compose run --rm -T app emit --out build/value-review/lza
```

Exit **2** (stderr):

```text
unresolved conflicts block emission: ORG_POLICY_CONFLICT
```

No output directory is created. These two nonzero exits are expected; run the next
commands after them, rather than joining the whole walkthrough with `&&` or using
`set -e`.

### 2. Record the human correction

Compare [client.md](client.md) with [confirmed.md](confirmed.md). The architect
removes the unapproved region and answers the connectivity question:

```diff
-- enabled_regions: eu-central-1, eu-west-1, us-east-1
+- enabled_regions: eu-central-1, eu-west-1
-The hybrid connection method is still undecided.
+- hybrid_connection: site-to-site-vpn
```

The corrected packet also updates the narrative about deferring the US request.
The example supplies these answers for rehearsal; real answers belong to the owner.

```bash
docker compose run --rm -T app ingest samples/organisation/confirmed.md
```

Exit **0**:

```text
ingested samples/organisation/confirmed.md (sha256 bf690a175d41)
organisation references: reused snapshot — Blue River Bank illustrative organisation
statements: 59  facts: 27
```

No repeated `--organisation` is needed: correcting the document reuses the stored
reference contents and hashes. Both ingests replace the whole graph atomically;
neither is an incremental patch.

```bash
docker compose run --rm -T app review
```

Exit **0**; both selected policies now report `passed`. CLI summary:

```text
document: samples/organisation/confirmed.md (sha256 bf690a175d41)
applicable decisions: 27  answered: 27  gaps: 0  conflicts: 0
```

### 3. Export configuration and inspect its trace

```bash
docker compose run --rm -T app emit --out build/value-review/lza
```

Exit **0**:

```text
wrote build/value-review/lza/organization-config.yaml
wrote build/value-review/lza/accounts-config.yaml
wrote build/value-review/lza/global-config.yaml
wrote build/value-review/lza/iam-config.yaml
wrote build/value-review/lza/network-config.yaml
wrote build/value-review/lza/security-config.yaml
wrote build/value-review/lza/decision-trace.yaml
LZA 1.16.3 schemas passed; integration context is in decision-trace.yaml
```

Open `build/value-review/lza/global-config.yaml`. Its actual region configuration:

```yaml
enabledRegions:
- eu-central-1
- eu-west-1
homeRegion: eu-central-1
```

Open `build/value-review/lza/decision-trace.yaml`. These entries under `decisions`
connect the exported regions and the context-only VPN answer back to the packet:

```yaml
- decision: enabled_regions
  evidence: Architect Clarification Pass:30
  origin: document
  value: eu-central-1, eu-west-1
```

```yaml
- decision: hybrid_connection
  evidence: Existing enterprise integration:94
  origin: document
  output: context-only; configured by the consuming enterprise team
  value: site-to-site-vpn
```

The same trace includes `sourceDocument`, `sourceSha256`, selected reference hashes
and both reassessed policies in `policyAssessments`. `integrationContext.status`
is `requires-owner-validation`: the network team still owns routes, subnets,
attachments, DNS and inspection; the identity team still owns Entra federation.
A VPN answer produces context, not a configured VPN. Six schema-valid LZA files
prove output shape, not connectivity, recovery, compliance or deployment readiness.

Engineers review the bundle and trace before moving the supported inputs into
their LZA 1.16.3 configuration repository and running their existing pipeline.
This tool does not submit the files or authenticate approval.

When finished, stop only this example's containers, retaining its volume:

```bash
docker compose stop
```

Keep the environment variables if continuing to the graph view below. When leaving
this case, clear them so later commands do not accidentally reuse it:

```bash
unset COMPOSE_PROJECT_NAME NEO4J_BROWSER_PORT NEO4J_BOLT_PORT
```

For an independent evaluation, use the [two-engineer trial guide](../../docs/engineer-trial.md).

## What was selected

`organisation.yaml` selects local files and links a small set of systems,
integrations, additional questions and policies to exact source lines/quotes:

- `estate.md`: stated existing and planned systems and required integrations.
- `lza-reference.yaml`: organisation configuration used as policy reference data.
  Its values never become client answers.
- `policy.rego`: the organisation's region restrictions and required security controls.

This selected policy requires logging, Security Hub and GuardDuty. A disabled
control is a conflict unless `lza-reference.yaml` records a scoped exception:

```yaml
securityExceptions:
  guardduty_enabled:
    owner: Security team
    reason: 'EXAMPLE-42: temporary alternative detection agreed for this case'
```

The exception applies only to that control in this selected case. Missing owner,
blank reason or an unusable client answer cannot waive the requirement. Refresh
with `--organisation` after editing references. Review and export show the
exception as a warning and retain it in the trace. The artifact scan still supplies
general security advice; it has no independent region allowlist. Requirements come
from the selected policy, not the document's `compliance_overlay` label.

All selected contents and hashes are stored with the client document in Neo4j.
Supplying `--organisation` again refreshes the snapshot. Without it, correcting
and re-ingesting a document preserves the current snapshot. Use
`ingest DOCUMENT --without-organisation` to deliberately start an unrelated case.
Each ingest still replaces the whole graph atomically. Use a dedicated Compose
project/database for each client.

OPA receives `input.decisions` (usable stated values) and `input.references`
(selected configuration by reference ID). The fixed query is
`data.organisation.assessments`: a list with exactly one `{policy_id, status,
message}` per selected policy; status is `passed`, `warning`, `conflict`, or `not-assessed`.
A warning is advisory and remains in the trace; conflicts and unassessed policies
block export. Record exception scope and rationale in selected references and Rego,
not in model output. See the [workload example](../vpc/README.md).
Missing tools, undefined/malformed results and absent coverage block export.
Review records assessments in Neo4j, including the input and document hashes.
Policy code and configuration hashes remain linked through the selected references.
Emission reassesses resolved values. This is a scoped input check, not a compliance
assessment or a substitute for downstream LZA validation.

## See the graph

Use the same `COMPOSE_PROJECT_NAME`, `NEO4J_BROWSER_PORT` and `NEO4J_BOLT_PORT`
settings as ingestion. If you stopped the example, start it again and check its
published addresses:

```bash
docker compose up -d --wait neo4j
docker compose port neo4j 7474
docker compose port neo4j 7687
```

Open `http://<first address>/browser/` and connect to `bolt://<second address>`.
For the root README quickstart, these are [Neo4j Browser](http://localhost:18474/browser/)
and `bolt://localhost:18687`; without port overrides they are 7474 and 7687.
Use user `neo4j` and local example password `localdevpassword`.
Run `review` first to update decision and policy statuses, then use this focused
query (the full database also holds every source statement):

```cypher
MATCH p=(s:System)-[:SOURCE_OF]->(i:Integration)-[:TARGETS]->(t:System)
RETURN p
UNION ALL
MATCH p=(d:Decision)-[:ABOUT]->(:Integration)
RETURN p
UNION ALL
MATCH p=(:Policy)-[:CONSTRAINS]->(:Decision)
RETURN p
UNION ALL
MATCH p=(:Assessment)-[:ASSESSES]->(:Policy)
RETURN p
```

Click a decision to see `status` (`gap`, `conflict`, `answered`) and its question.
For source evidence, expand a System, Integration or Policy through `EVIDENCE`,
or use:

```cypher
MATCH p=(n)-[:EVIDENCE]->(:ReferenceStatement)-[:FROM]->(:Reference)
RETURN p
UNION ALL
MATCH p=(f:Fact)-[:ANSWERS]->(d:Decision)
WHERE d.key IN ['hybrid_connection', 'enabled_regions', 'workforce_federation']
RETURN p
UNION ALL
MATCH p=(f:Fact)-[:EVIDENCE]->(:Statement)-[:FROM]->(:Document)
WHERE EXISTS {
  MATCH (f)-[:ANSWERS]->(d:Decision)
  WHERE d.key IN ['hybrid_connection', 'enabled_regions', 'workforce_federation']
}
RETURN p
```
