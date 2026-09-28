# One organisation-aware architecture discussion

Synthetic example, not a record of bank approval. Existing on-premises/SD-WAN/Azure
networking and Entra ID are referenced; this tool does not create or configure them.

From the repository root:

```bash
docker compose build app
docker compose run --rm app ingest samples/organisation/client.md \
  --organisation samples/organisation/organisation.yaml
docker compose run --rm app review
```

Review exits **1** with exactly:

- `hybrid_connection` missing, supported by `estate.md:5`.
- `ORG_POLICY_CONFLICT`: `us-east-1` lies outside the selected organisation region
  standard. Evidence includes the client's enabled-regions answer, `policy.rego:3`,
  and the selected `lza-reference.yaml` hash.

`emit --out build/organisation` is blocked and creates no output directory.

The architect records site-to-site VPN and removes the US region in the corrected
packet. Re-ingestion keeps the selected organisation snapshot:

```bash
docker compose run --rm app ingest samples/organisation/confirmed.md
docker compose run --rm app review
docker compose run --rm app emit --out build/organisation
```

Now review exits **0** and emission writes six LZA 1.16.3 schema-valid configuration
files plus `decision-trace.yaml`. The trace includes source hashes, the scoped OPA
assessment, integration context and remaining work for consuming teams. Connection
method and Entra federation are explicitly context-only decisions, not generated
VPN or identity-provider configuration. No separate handoff file is produced.

## What was selected

`organisation.yaml` selects local files and links a small set of systems,
integrations, additional questions and policies to exact source lines/quotes:

- `estate.md`: stated existing and planned systems and required integrations.
- `lza-reference.yaml`: organisation configuration used as policy reference data.
  Its values never become client answers.
- `policy.rego`: the organisation's executable region constraint.

All selected contents and hashes are stored with the client document in Neo4j.
Supplying `--organisation` again refreshes the snapshot. Without it, correcting
and re-ingesting a document preserves the current snapshot. Use
`ingest DOCUMENT --without-organisation` to deliberately start an unrelated case.
Each ingest still replaces the whole graph atomically. Use a dedicated Compose
project/database for each client.

OPA receives `input.decisions` (usable stated values) and `input.references`
(selected configuration by reference ID). The fixed query is
`data.organisation.assessments`: a list with exactly one `{policy_id, status,
message}` per selected policy; status is `passed`, `conflict`, or `not-assessed`.
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
