# Architecture Map

`iac-llm-wrapper` turns architecture intent into validated registered-target
configuration artifacts. It does not deploy infrastructure.

```text
Architect packet / Markdown / Interview
  -> extraction
     - LLM proposes raw decisions
     - structured Markdown can provide deterministic decisions
  -> requirement graph
     - accepts known decisions
     - orders dependencies
     - applies defaults, cascades, applies_if/applies_when gates
     - identifies gaps, asks for missing inputs, and records blockers
  -> semantic model
     - derives typed entities such as accounts, OUs, permission sets, assignments,
       controls, artifacts, and target capabilities where a pattern owns them
     - evaluates predicate constraints over real relationships
  -> target contracts
     - define required artifacts, paths, decisions, assertions, and lineage
     - fail closed when required target configuration shape is missing
  -> target capability facts
     - extract explicit unsupported asks with evidence spans
     - route downstream target coverage from semantic facts and accepted decisions
  -> artifact generators
     - emit decision reports, handoff plans, trace summaries, benchmark files,
       review files, and pattern-specific target configuration files
     - terraform-vpc emits an abstract Atmos catalog and byte-identical approved root
       as an optional Git/contract handoff, without owner runtime configuration
  -> optional target conformance
     - terraform-vpc alone verifies replay, root, module-tree, provider, and tool identities
     - runs a temporary account-bound speculative plan with no apply or retained state
     - gives every applicable requirement/control a plan, input, or deferred-gate outcome
     - fails on contradictions, unknowns, incomplete plans, or untraceable resources
  -> confidence loop
     - evals compare expected decisions and artifacts
     - battle tests produce verdicts and improvement items
     - static review pages help humans inspect readiness and blockers
```

## Ownership

- Core owns extraction orchestration, graph sync, validation, contracts, generic
  semantic graph primitives, artifacts, review pages, and evaluation harnesses.
- Patterns own domain models, requirement graphs, validators, deployment target
  contracts, sample configs, semantic model derivation, predicate constraints,
  and pattern-specific target configuration emitters.
- Existing deployment mechanisms own deployment. Compile/generation paths do not
  call cloud APIs or invoke pipelines. The Terraform VPC plan adapter may use
  owner-approved AWS credentials for caller identity and a temporary speculative
  plan against one exact approved module; it observes the account, not credential
  scope, and cannot apply or retain state. The AWS LZA validation-only
  adapter may run the official local validator, which can require read-only
  account lookup through the provided AWS/LZA context.
- Atmos owns no state here. The `terraform-vpc` pattern emits an abstract catalog
  component and the already-approved root. Owner repositories supply real stack
  names, backend, authentication, workspace, approvals, and execution. The bridge
  adds no core callback, service API, or Python dependency.

## Boundary

The model can suggest. The requirement graph and target contracts decide.
Artifacts can be consumed by another UI or tool, but this repo remains
CLI-first, artifact-first, and handoff-first.

The integration protocol is generated files plus target contracts and replay
digests. Backstage may invoke the CLI, and Atlantis may execute an owner's Atmos
workflow. Terramate and Terragrunt are alternative Terraform orchestrators.
Score and Crossplane require independent target demand. None is a runtime
dependency, and no MCP facade exists in this slice.

Every registered generator declares its output paths. Registration rejects
unsafe paths, ambiguous ownership, core-output replacement, and required target
artifacts with no producer. Target contracts already expose the required native
file inventory; generation rejects undeclared file changes and symlinked
artifacts. This is the shared composition seam: native files are discoverable
and contract-backed, without teaching core how Atmos, LZA, AFT, Crossplane, or
an executor works.

LLM providers remain supported for compatibility, but provider expansion is
frozen. Model output may propose decisions; it may not select target versions,
weaken contracts, construct the Atmos root, or authorize a state transition.

For `terraform-vpc`, the pattern-local conformance specification owns plan JSON
interpretation and resource provenance. `policy-graph.yaml` remains control
mapping metadata, not an evaluator. State, locking, drift, approval, signed
attestation, and any fresh downstream plan remain owner-platform concerns.

## Native OSS owner handoff

The repository owns only the transition from an architecture exchange into a
validated intent packet, and the transition from that packet into native target
artifacts, an evidence sidecar, and a PR-ready handoff. It does not open the PR
or cross into the owner execution boundary.

```text
Architect / ticket / optional AI conversation
  -> intent-engine
     requirements, applicability, gaps, provenance, target contract
  -> native target artifact + evidence sidecar + PR-ready handoff
  -> Atmos / AWS LZA / AFT / Crossplane / Terramate       [owner repository]
  -> Atlantis or another owner-controlled executor        [owner platform]
  -> state, policy, approval, apply, drift, and audit      [owner platform]
```

Target outputs stay native rather than converging on an intent-engine-specific
deployment format:

| Target | Native handoff | Status |
| --- | --- | --- |
| AWS Landing Zone Accelerator | Official-style LZA configuration | Implemented |
| Atmos | Abstract catalog plus approved Terraform component root | Implemented for `terraform-vpc` |
| CloudFormation | Parameters for an owner-approved existing template | Implemented |
| AWS Control Tower AFT | Fixed-template `account-request.tf` module call | Candidate only |
| Score | Workload specification | Demand-gated |
| Crossplane | XR matching an owner XRD/Composition | Demand-gated |

The durable value hypothesis is not "AI writes configuration." It is that an
architecture exchange reaches an existing OSS delivery path with unresolved
decisions, contradictions, applicability, provenance, and target shape made
explicit before runtime authority is involved. Native schemas and validators
remain authoritative for their own formats; this repository earns its place
only when the requirements and evidence sidecar changes a real review outcome.

Composition is admitted target by target: require an owner contract, emit the
native artifact, reuse the official validator, keep lifecycle authority
downstream, and prove repeated PR use. If a form is equivalent, evidence is
ignored, or use does not repeat, remove the bridge instead of expanding the
framework.

### Next candidate: AFT, not another executor

[AWS documents](https://docs.aws.amazon.com/controltower/latest/userguide/aft-provision-account.html)
an account request Terraform file committed to the AFT account-request
repository, with `git push` invoking the downstream AFT CodePipeline. That is a
natural configuration-only handoff, so AFT is the next native target candidate.
It is not the next implementation.

Before registering an AFT pattern, require an owner-provided AFT repository
contract, one real account request, approved handling of account and SSO email
data, and repeat use. Account name, email, managed OU, SSO user fields, change
reason, requester, tags, custom fields, and customization selection must be
explicit owner input; an LLM must never infer identity or email data. A future
emitter may render only the official owner-approved fixed module call. It must
not push Git, invoke CodePipeline, obtain credentials, provision AFT, or add a
plan-conformance evaluator.

### Smallest adjacent OSS integrations

Only self-hosted, OSI-licensed paths are eligible for required integrations;
hosted or proprietary features may be optional downstream owner choices but
cannot become compile or validation dependencies.

- For `cloudformation-parameters`, add
  [cfn-lint](https://github.com/aws-cloudformation/cfn-lint) template validation
  and [cfn-guard](https://github.com/aws-cloudformation/cloudformation-guard)
  owner-rule validation only when an owner supplies the local approved template
  and rules. These tools validate template shape and policy; the intent-engine
  contract remains authoritative for the parameter artifact. Their result is
  validation evidence, not deployment authority. cfn-lint describes complex
  dynamic values as best-effort validation, so its success is not semantic proof.
- The [AWS IaC MCP server](https://github.com/awslabs/mcp/tree/main/src/aws-iac-mcp-server)
  can expose cfn-lint and cfn-guard conversationally, but remains optional and
  non-authoritative. It must not become the contract, credential, or execution
  boundary.
- Keep Atlantis downstream. Its
  [custom workflows](https://www.runatlantis.io/docs/custom-workflows.html) can
  call Atmos from the owner repository; this project needs no Atlantis API.
- Defer Terramate because a second Terraform orchestration bridge would
  duplicate the still-unproven Atmos workflow.
- Defer Crossplane until an owner supplies the exact XRD and Composition. An XR
  is an organization-defined custom API whose schema comes from its XRD, so
  `apiVersion`, `kind`, and accepted fields cannot be guessed generically. See
  the [Crossplane composite-resource model](https://docs.crossplane.io/latest/composition/composite-resources/).

AWS Landing Zone Accelerator is the reference target: accepted decisions produce
contract-checked LZA YAML/config files, and the downstream LZA process remains
responsible for validating and applying them.
