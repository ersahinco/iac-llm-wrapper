# Design boundaries

The product is one reviewable case: explicit client answers, selected reference
snapshots, deterministic findings, and configuration inputs with an evidence trace.
It never deploys infrastructure. Keep decisions close to the data and checks that
justify them; do not introduce another ontology or an orchestration framework.

## Sources of authority

| Concern | Owner | Why |
| --- | --- | --- |
| Confirmed values | Explicit document answers | Reference text and model proposals cannot manufacture agreement. |
| Missing answers and dependencies | Catalog and Neo4j evidence links | A missing answer has a named question and source context. |
| Invalid values and cross-field consistency | Named Python rules using the standard library | These are reproducible without a model or policy service. |
| Organisation restrictions and exceptions | Selected reference data and Rego | Different clients change inputs and policy, not the engine. |
| Output structure and variable mapping | Pinned JSON Schemas and explicit mappings | A contract proves only its stated scope. |
| Common resource security advice | Native Checkov and Trivy reports | Reuse their checks and suppression mechanisms; retain reported exceptions. |
| Explanation and evidence exploration | Optional native GraphRAG `ask` | Model wording has no authority over facts or export gates. |

Only explicit document answers become Facts. References, extracted systems and
candidate proposals never supply answers automatically. Account root emails are
owner input. The catalog describes decisions; it does not hold client answers.

## Outcomes

- **Gap:** an applicable question has no explicit answer. Blocks export unless its
  catalog default is deliberately allowed and traced.
- **Conflict:** unusable or contradictory input, or a selected required policy
  violation. Blocks export. Unusable values and contradictory answers have distinct
  messages; gaps are derived from the graph and conflicts use named rules.
- **Warning:** an explicitly advisory policy outcome, including a scoped exception.
  Stays visible in review, export and the decision trace; does not block export.
- **Not assessed:** insufficient evidence, missing tooling or invalid policy output.
  Does not mean passed. Selected policies with this outcome block export.

OPA must still return one assessment for every selected policy. Re-evaluate after
resolving defaults so the exported values have actually been assessed. A warning is
an explicit policy-author choice; the model cannot downgrade a conflict.
Missing tools, malformed/undefined output and missing policy coverage are
`not-assessed` and block export. Retain evidence and input, document and reference
hashes with each assessment.

Required security controls and region restrictions live in the selected
organisation policy, with scoped exceptions in its reference data. Python checks
value consistency. The bundled LZA scan supplies general security advice without
a second region allowlist. `compliance_overlay` selects emitted template settings;
it does not create a required policy. Existing cases keep their stored rules until
the owner explicitly refreshes `--organisation`.

Artifact scanners are advisory by default; `scan --strict` makes their open
findings fail CI. Invalid LZA shape and incomplete/error scan results remain
unsuccessful in either mode. Native exceptions do not count as assessed passes.
Only exceptions returned in native reports can be retained; scoped ignore files
with reasons are preferable when a scanner omits inline suppressions.
Missing scanners report `not-installed`; no assessed checks reports `not-assessed`.
Neither is a pass. Keep Checkov and Trivy adapters and their native exception reasons.

## Storage and output

Each successful ingest atomically replaces the whole graph; a failed replacement
preserves the previous case. There is no incremental diff, baseline or reconciliation.
Use the [isolated contributor setup](../CONTRIBUTING.md#full-suite-with-neo4j-and-opa)
for tests and exercises, which erase their target graph.

The client document stores the selected catalog and organisation contents/hashes.
Corrections reuse that snapshot; `--organisation` refreshes references and
`--without-organisation` clears them. Review and export use the stored catalog;
a mismatched explicit catalog requires re-ingestion. Run ingest/index/review
sequentially. This is not a live CMDB, IP allocator or concurrent editing service.

Both exporters resolve values from the review's facts and reassess selected policy.
They serialize and validate before writing, preflight every destination,
then create it exclusively; an existing file, directory or symlink is a collision.
Use a new output directory per revision. This deliberately avoids overwrite flags,
ownership manifests and migration logic. Failed writes remove files created by
that attempt; earlier outputs and owner files are never deliberately replaced.
Gaps, conflicts and invalid contracts block export. Defaults require
`--allow-defaults` and `origin: default` in the trace.

Integration context stays `requires-owner-validation`. Schema success proves
shape, not connectivity, federation, recovery or deployment readiness. The owner's
pipeline keeps deployment, approvals and drift decisions. Terraform output is
variable JSON only, with no resources, state or execution. The distribution is
`iac-llm-wrapper`; the Python import name remains `intent_engine`.

`review` renders a deterministic discussion agenda; `ask` provides advisory model
answers. Extraction and retrieval require explicit model and endpoint choices,
with no fallback. The small async Ollama adapter retains native JSON Schema format
while upstream GraphRAG misroutes model parameters.

`index` embeds the stored snapshot; `ask` uses native VectorCypherRetriever and
GraphRAG. Re-ingestion requires re-indexing. Valid source identifiers and quotes
do not prove semantic entailment. Show deterministic answers/findings separately;
model wording cannot change facts or unblock export. These operations have no
concurrent ingest/index/review guarantees.

## Adding a real requirement

1. Capture the owner's explicit answer in a catalog question.
2. Add a named consistency rule for invalid combinations, or selected Rego for
   organisation policy. Prefer native `ipaddress` and OPA built-ins.
3. Add an explicit output mapping only if a consuming interface supports it.
4. Demonstrate valid, invalid, missing and exception outcomes with a small test.
5. Document exactly what still requires owner validation.

For example, peer subnet validity belongs to deterministic consistency checks;
existing-estate overlap needs a supplied routing domain and allocations; instance
allowlists and exceptions belong to a selected organisation. None requires a new
retriever, model-generated Cypher or automatic policy translation.

## Code map

```text
src/intent_engine/
  decisions.yaml   default human decision catalog
  catalog.py       catalog validation and value coercion
  ingest.py        whole-document statements and explicit facts
  extraction.py    opt-in GraphRAG proposals with evidence
  rag.py           native vector/graph retrieval and advisory answers
  organisation.py  reference snapshots and scoped OPA assessment
  graph.py         Neo4j schema, atomic replacement and queries
  analysis.py      applicability and named conflict rules
  emit.py          LZA configuration and decision trace
  output.py        shared exclusive bundle creation; no replacement of existing files
  contract.py      offline validation against pinned LZA 1.16.3 schemas
  tfvars.py        confirmed values mapped through a JSON Schema contract
  schemas/         unchanged upstream schemas and notices
  scan.py          LZA shape/OPA and advisory Checkov/Trivy over owner IaC
  policy/lza.rego  landing-zone policy
  cli.py           ingest, status, review, index, ask, emit, emit-tfvars, scan
samples/           synthetic organisation, banking and VPC inputs
```
