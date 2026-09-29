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

## Outcomes

- **Gap:** an applicable question has no explicit answer. Blocks export unless its
  catalog default is deliberately allowed and traced.
- **Conflict:** unusable or contradictory input, or a selected required policy
  violation. Blocks export.
- **Warning:** an explicitly advisory policy outcome, including a scoped exception.
  Stays visible in review, export and the decision trace; does not block export.
- **Not assessed:** insufficient evidence, missing tooling or invalid policy output.
  Does not mean passed. Selected policies with this outcome block export.

OPA must still return one assessment for every selected policy. Re-evaluate after
resolving defaults so the exported values have actually been assessed. A warning is
an explicit policy-author choice; the model cannot downgrade a conflict.

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

## Storage and output

Ingest atomically replaces the whole case. The stored catalog and organisation
snapshot make corrections and policy review reproducible; explicit re-selection
refreshes references. Run ingest/index/review sequentially. This is not a live CMDB,
IP allocator or concurrent editing service.

Both exporters resolve values from the review's facts and reassess selected policy.
They serialize and validate before writing, preflight every destination,
then create it exclusively; an existing file, directory or symlink is a collision.
Use a new output directory per revision. This deliberately avoids overwrite flags,
ownership manifests and migration logic. Failed writes remove files created by
that attempt; earlier outputs and owner files are never deliberately replaced.

`review` renders a deterministic discussion agenda; `ask` provides advisory model
answers. Keep the small extraction adapter until upstream preserves its native
JSON Schema format.

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
