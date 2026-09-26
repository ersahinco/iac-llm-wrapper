# Banking landing-zone review

Reviewed 2026-09-26 against `cb36015`. This reviews the published implementation
and example packet, not the bank's deployed environment or confidential trial
evidence. The project is a useful decision-capture prototype; the repository does
not yet establish that its output is a complete, validated banking foundation.

First milestone implemented locally: scanner verdicts now reject errors and
malformed reports, missing tools and zero assessed checks block scan success,
OPA rejects missing/mistyped inputs to its existing controls, graph replacement
uses one data transaction, and resolved defaults are checked for conflicts.
Regression tests cover these changes. The findings below describe the original
review; schema compatibility, scoped layer coverage, and consistent reads across
concurrent ingests remain separate work. Atomic replacement alone does not make
multiple review queries a database snapshot.

Second increment implemented locally: LZA 1.16.3 schemas are bundled unchanged
and checked before emission and during scan. The unused baseline selector is
removed. Permission sets require explicit AWS-managed policy mappings. A small
data/application decision set feeds an owner handoff; it does not introduce a
per-asset model or implement workload resources. The handoff explicitly keeps
network completion and downstream LZA validation with the consuming pipeline.
Schema compatibility is tested; deployment readiness is not claimed.

## Findings, in priority order

1. **P1 — A complete questionnaire is reported as a complete architecture.**
   The sample answers all 21 catalog decisions and has no semantic conflicts,
   while explicitly deferring routing, DNS, inspection, retention, and identity
   review. Those unresolved items remain prose, outside the computed frontier.
   The LLM cannot surface them because it only receives that frontier. Turn the
   packet's actual open questions into scoped decisions. A clean review must name
   its supported scope; anything outside it remains explicitly unassessed.
   Evidence: `samples/banking-packet.md:56`, `src/intent_engine/ingest.py:75`,
   `src/intent_engine/decisions.yaml`, `src/intent_engine/llm.py:65`.

2. **P1 — Scan results can falsely pass.** A Checkov or Trivy process returning
   exit code 2, `{}` on stdout, and an error on stderr is reported as `passed`.
   Missing scanners also allow the CLI to exit successfully. Checkov is invoked
   only for secrets, despite broader claims. Validate tool-specific exit codes
   and response shapes, distinguish coverage from findings, and make incomplete
   required validation non-successful. Do not label generic YAML scanning as LZA
   semantic validation. Evidence: `src/intent_engine/scan.py:149`, `:198`, `:219`,
   and `src/intent_engine/cli.py:262`.

3. **P1 — Required policy fields fail open when absent.** Six mapping-shaped
   config files containing only home/enabled regions pass the current OPA policy.
   Comparisons against missing properties become undefined instead of denials.
   Assert field existence and types before value rules. Add omission tests, not
   just tests that flip a present boolean. Evidence: `src/intent_engine/policy/lza.rego`.

4. **P1 — Network intent is not realized in the output.** Hub-spoke produces
   one VPC, no subnets, no VPC route tables, no attachments, and no TGW route
   tables. The emitter also chooses to delete default VPCs in every account and
   automatically accept shared attachments without capturing those decisions.
   In an existing bank environment these choices require explicit intent. Block
   an incomplete topology or clearly emit a draft for a defined subset.
   Evidence: `src/intent_engine/emit.py:234`.

5. **P1 — Identity authorization is inferred from names.** Every permission-set
   name becomes an AWS-managed policy name, including `BreakGlassAdmin` and
   `NetworkAdmin`, whose policies were never supplied. All principals become
   groups. There is no model for federation, policy definitions, service identities,
   or emergency access requirements. Require explicit permission-set-to-policy
   mappings and principal types. Evidence: `src/intent_engine/emit.py:208`.

6. **P1 — Artifact compatibility and provenance are incomplete.** There is no
   pinned LZA schema contract or upstream compatibility check. The selected
   baseline has no effect on the six LZA files. Retention is fixed at 2,555 days,
   OU placement is hardcoded, and security administration is emitted to the audit
   account despite a separate security-tooling decision. The trace records input
   answers but not all these output choices. Remove unsupported baseline options;
   trace each emitted architectural choice to owner input or an explicitly
   selected, versioned profile. Evidence: `src/intent_engine/emit.py:152`, `:183`,
   `:300` and `src/intent_engine/decisions.yaml:10`.

7. **P1 — Replacing the graph is not atomic.** Delete and reload run in separate
   transactions. Failure after deletion can leave an empty or partial document,
   and concurrent readers can observe mixed stages. Keep whole-document replace,
   but use one transaction for data replacement in a dedicated database. Review
   and emit must read a consistent snapshot of that data and its catalog.
   Evidence: `src/intent_engine/graph.py:106`, `:117`.

These findings do not invalidate the existing passing tests. They identify
properties those tests do not cover. Focused probes reproduced findings 2–5 and
the inert baseline in finding 6 without AWS access or modification of Neo4j.

## The product boundary

The tool should produce a reviewable architecture decision package and validated
configuration for a defined LZA target. It should explain what is answered, what
is missing, what conflicts, and which downstream team must resolve each item.
Deployment, approvals, operational evidence, and application implementation stay
with owner pipelines and teams.

Keep the current whole-document workflow, deterministic rules, optional AI
agenda, and one catalog. Add depth to one bank workload before breadth across
industries, cloud providers, or application platforms.

## Layers and their contracts

These are review boundaries, not new services or packages.

| Layer | Decisions the bank must supply | Relationship to other layers | Output boundary |
| --- | --- | --- | --- |
| Organization and ownership | Existing Control Tower footprint; account/OU placement; production isolation; approved regions; platform and workload owners | Establishes where every resource and responsibility belongs | LZA accounts, organization, and global config |
| Network | Per-workload CIDRs and AZs; bank connectivity; allowed source/destination flows; inspection and egress; DNS; private service endpoints | Data/app flows require routes, DNS, and permitted network paths | LZA network config for the agreed topology |
| Identity | Workforce IdP; groups and explicit permission policies; delegated admins; emergency access; workload identities and trust boundaries | A reachable service still requires authorized access to data and keys | LZA-supported identity config; workload-role requirements handed to app owners |
| Data protection | Data classification; primary/replica/backup locations; key ownership and access; retention; deletion; immutability; recovery objectives | Constrains regions, identities, logging, backup, and application storage choices | Supported LZA foundation controls plus explicit workload requirements |
| Application/workload | Workload and environment; runtime choice; ingress and dependencies; data stores; availability and recovery needs; delivery owner | Binds network paths, service identities, data classification, and recovery requirements | An owner handoff; optional LZA customizations only for a concrete supported use case |
| Operations and evidence, across all layers | Log classes and destinations; retention/access; alert ownership; recovery/restore evidence; incident responsibilities | A configured control is distinct from evidence that it operates effectively | Configuration checks and requirements for owner-run verification |

Use separate residency decisions for customer data, replicas, backups, and logs.
Do not infer that enabling a region permits every data class there. Do not assign
retention or recovery targets from the label `financial-services`.

## What the graph must explain

An answer needs a scope: a workload/environment, account, data asset, or network
segment as appropriate. Today two workloads giving different answers to one
global decision key appear contradictory. Begin with scoped decision instances
and evidence links, adding entity types only when an actual rule needs them.

For example, follow the digital-banking API's connection to its customer store:

`workload → network path → service identity → data/key access → backup/recovery`

Every step must have an owner-provided answer, an unresolved question, or an
explicitly documented boundary. Useful rules include:

- A backup or replica location outside the data asset's approved locations conflicts.
- An overlapping bank/workload CIDR blocks a routed private connection unless an
  explicit supported translation design resolves it.
- A required service connection without DNS or a route is an architecture gap.
- A workload's declared data access without a matching identity/policy mapping is a gap.
- Production/nonproduction sharing that violates the bank's stated isolation rule conflicts.
- Missing RPO/RTO or recovery location is a gap; specified targets alone do not
  prove that a restore or failover meets them.

Rules must cite the relevant scoped answers and source lines. AI may explain
these findings and draft questions; it must not invent answers or certify coverage.

## Smallest credible next implementation

1. **Restore trustworthy verdicts.** Fix scanner error/coverage semantics, OPA
   missing-field behavior, and atomic graph replacement. Recheck resolved values
   after opt-in defaults. Add negative tests for each demonstrated failure.
2. **Establish the output contract.** Pick the bank's actual LZA version. Validate
   the emitted files against that version's schemas. Remove the unused baseline
   selector until it selects a real supported profile. Any upstream validation
   requiring AWS credentials belongs in the owner pipeline; report it as pending.
3. **Complete one vertical slice.** Use `DigitalBankingProd` as the provisional
   workload from the packet. Capture its bank connection, identity and policy
   bindings, customer-data locations, and recovery requirements. Leave the
   runtime, IdP, connectivity implementation, and recovery targets unanswered
   until the owner supplies them. Do not add an invented reference deployment.
4. **Prove useful failures and a bounded success.** The existing incomplete packet
   should produce specific layer gaps. A completed, sanitized packet should
   produce schema-valid configuration for the supported foundation and an
   explicit workload handoff. Mutations must catch disallowed backup regions,
   undefined policies, missing routes, omitted controls, and unavailable checks.

The milestone is one explainable workload handoff with honest validation coverage,
not a larger catalog or a green scanner summary.

## AWS references used

- [LZA configuration files and JSON Schema](https://docs.aws.amazon.com/solutions/latest/landing-zone-accelerator-on-aws/using-configuration-files.html): configuration boundaries and schema support.
- [AWS Control Tower landing-zone design](https://docs.aws.amazon.com/prescriptive-guidance/latest/designing-control-tower-landing-zone/transit-vif.html): decisions across accounts, networking, identity, logging, and controls.
- [AWS privacy reference architecture](https://docs.aws.amazon.com/prescriptive-guidance/latest/privacy-reference-architecture/global-expansion.html): questions about residency, backups, access, and regional boundaries; the bank must supply its requirements.
- [AWS sample LZA validator](https://github.com/aws-samples/lza-validator): release-specific validation; its documented AWS credential requirements mean it cannot be assumed to be an offline check inside this tool.
