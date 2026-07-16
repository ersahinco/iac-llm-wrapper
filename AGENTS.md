# AGENTS.md

## Project: iac-llm-wrapper / intent-engine core

Core engine for `iac-llm-wrapper`, an architect-exchange-to-registered-target
configuration framework. It captures architecture intent from prose, validates
decisions through requirement graphs and target contracts, and emits traceable
target configuration artifacts that engineers use with existing deployment
mechanisms. Direct deployment and whole-IaC-from-scratch generation stay out of
runtime scope.

AWS Landing Zone Accelerator is the first product path: collected inputs become
contract-checked LZA YAML/config files for the downstream LZA deployment process.
The core must stay generic: patterns own domain models, contracts, validators,
samples, and target configuration emitters.

## Commands

```bash
uv run --locked --extra dev pytest
uv run --locked --extra dev ruff check .
uv run --locked --extra dev ruff format --check .
uv run --locked --extra dev mypy
uv run --locked --extra dev pyright .
uv run --locked --extra dev python scripts/sync-sample-fixtures.py --check
uv run --locked --extra dev python scripts/evaluate-golden-journey.py
uv run --locked --extra dev python scripts/evaluate-extraction.py
uv run --locked --extra dev python scripts/evaluate-usability.py
uv run --locked --extra dev prek run --all-files
```

## Architecture

- **Models** (`src/intent_engine/patterns/*/models.py`): Pydantic v2 intent data
  models. Pattern-specific models drive extraction, graph sync, validation,
  semantic model derivation, and artifact emission.
- **Extract** (`extractor.py`): Single graph-driven `Extractor`. Prompts come
  from requirement nodes, not regex or fixed document layout. Without LLM,
  deterministic fallback applies graph defaults and structured Markdown entity
  recovery.
- **Patterns** (`patterns.py`): Lean registry for pluggable product paths.
  Current built-ins: `aws-lza`, `cloudformation-parameters`,
  `kubernetes-cluster`, `terraform-vpc`.
- **Requirements** (`requirements.py`): Decision graph with `applies_if`,
  `blocked_if`, expression gates, dependencies, cascade rules, tradeoffs,
  compliance controls, signals, and audit trail.
- **Semantic model** (`semantic_model.py` + pattern `semantic.py`): Lightweight
  typed entities, relationships, and predicate constraint results for
  real-world dependencies without RDF/OWL, Datalog, or a graph database.
- **Interview** (`interview.py`): Graph-ordered requirement capture. Shows
  context, asks only applicable gaps, supports save/resume, and records
  rationale.
- **Validate** (`validator.py`): Fail-closed graph and pattern validation.
  Missing required applicable decisions become compile errors.
- **Generate** (`generator.py`): Registry-driven emitter for decision report,
  handoff plan, target configuration artifacts, lineage, runbook, module inputs
  when pattern-owned, sample recommendations, and static review artifacts.
- **Contracts** (`contracts.py`): Target artifact contracts define required
  files, paths, decisions, lineage, and stable value assertions.
- **Samples** (`sample_config.py`): Registered reference bundles with pinned
  source metadata, module refs, tags, fixture dirs, and match recommendations.
- **LLM** (`llm_caller.py`): Pluggable OpenAI-compatible, Bedrock-through-local
  AWS CLI, and Ollama backends with retry/backoff and evidence capture.
- **CLI** (`cli.py`): `compile`, `compile-git`, `interview`, `validate`,
  `explain`, `sample`, `contract`, `graph`, `discover`, `template`, `review`,
  `shift-left`, the Terraform VPC speculative plan proof, and AWS LZA validation
  helpers. Default pattern is `aws-lza`.

## Current Pattern Surface

- `aws-lza`: Contract-backed AWS LZA registered target path. Emits official-style
  LZA YAML target configuration artifacts, decision report, lineage manifest,
  deployment runbook, plan/replay metadata, target capability graph, and sample
  recommendations. It does not emit deployable Terraform/Terragrunt
  landing-zone stacks.
- `cloudformation-parameters`: BYOM CloudFormation parameter handoff for an
  approved existing template. Emits parameters and decision report, not a stack
  or deployment.
- `kubernetes-cluster`: Contract-backed Kubernetes handoff for
  cluster/namespace config with optional Terraform EKS module input references.
- `terraform-vpc`: Exact approved Terraform AWS VPC module input capture and
  speculative plan proof. Emits module variables/tfvars, plan/replay manifests,
  and sanitized account-bound plan evidence. Its code-owned root pins Terraform
  1.15.8, module 6.6.1, and AWS provider 6.53.0; it never applies or retains
  state or a plan binary.

## Key Decisions

- Core stays domain-agnostic. Use-case logic lives in pattern packages.
- Graphs own decision order, branching, blocked paths, cascades, gaps,
  provenance, and handoff sequencing.
- Existing accelerators/modules are registered targets with contracts and data
  models before emitted configuration artifacts are trusted.
- Current compile/generation paths make no AWS API calls and do not deploy. The
  AWS LZA validation-only adapter may run the official local validator, which can
  perform read-only account lookup through the provided AWS/LZA context.
- The Terraform VPC plan adapter is deliberately target-specific. It may run a
  temporary speculative plan for the exact approved module and compare caller
  identity with the packet account; it cannot apply, destroy, own a backend, or
  retain state/raw plan data. Extract a shared execution protocol only after a
  second real target proves the same boundary.
- "Wrapper" means architect exchange to registered target configuration, not
  bypassing IaC tools, accelerators, owner pipelines, or gates.
- Sample recommendations must persist as artifacts, not terminal-only hints.
- `src/intent_engine/patterns/aws_lza` is the only AWS LZA path.
- Handoff artifacts are not deployments. `handoffReadiness` and
  `handoffAllowed` are the canonical readiness fields.
- Secrets travel as secret-store references and expected parameter names, never
  raw values.
- Add data-modeling or graph depth only when real packets expose a missed
  relationship or repeated review failure.

## Fixtures

- `fixtures/aws-lza-standard-v1/`, `fixtures/aws-lza-regulated-v1/`,
  `fixtures/aws-lza-healthcare-v1/`: emitted AWS LZA sample handoff bundles.
- `fixtures/k8s-cluster-v1/`: emitted Kubernetes sample handoff bundle.
- `fixtures/usability/`: role trials for architect gap capture, engineer
  handoff, BYOM Terraform, and BYOM CloudFormation parameter flow.
- `fixtures/eval/`: extraction gold corpus with expected handoff artifact
  checks.
- Version suffixes (`-v1`) are fixture contract versions. They protect emitted
  artifact shape from silent drift.

## Model-Driven Flow

1. Architect writes Markdown or runs interview.
2. Extractor asks LLM for graph decisions, or deterministic fallback applies
   explicit structured inputs plus defaults.
3. Graph applies decisions in dependency order and records provenance.
4. Discovery reports applicable gaps and detected signals.
5. Interview fills only missing applicable decisions.
6. Validate and emit deterministic target configuration artifacts for engineers.

## Extension Contract

Add a new target path by registering a pattern with:

- Pydantic intent model.
- Requirement graph.
- Optional deployment target contract.
- Optional sample configs.
- Optional validators, target configuration emitters, policy packs, target
  capability report, or module mapping.

Do not add provider-specific branches to core CLI/compiler/extractor/generator.

## Stack

Python 3.11+, Pydantic v2, Typer, ruamel.yaml, pytest, ruff, mypy, pyright.

## Session State

<!-- UPDATE THIS SECTION AT END OF EVERY SESSION -->

### Current Goal

Prove one controlled requirements-to-plan path for the exact approved Terraform
VPC module while keeping LLM guidance advisory, target code authoritative, and
all deployment authority downstream.

### Status

- **Repo-wide AI slop audit**: removed roughly 9,000 lines of unused or
  duplicative surface, led by the 4,236-line typed bundle impact graph, its
  1,681-line test suite, unused suggestion paths, hidden compatibility models,
  and provider behavior that had leaked into generic core.
- **Enforced quality checks**: removed 20 external `prek` hooks that silently
  passed when tools were absent. `prek` now runs installed checks that fail on
  evidence gaps; Checkov remains the explicit first-class shift-left evidence
  command for owner-provided IaC.
- **Fail-closed behavior**: patterns must register a Pydantic intent model,
  generator payload/model mismatches raise, mutated models are revalidated,
  malformed booleans no longer become `false`, Terraform AZ counts are bounded,
  Kubernetes node-pool bounds are checked, and malformed CloudFormation
  parameter entries block the handoff.
- **AWS LZA placement trust boundary**: removed the model-only top-level entity
  side channel. Structured Markdown account inventories are now the placement
  authority, `Accounts Inventory` headings are recovered deterministically,
  decision bullets are not misread as entities, and workload accounts must have
  explicit OU mappings when multiple workload-capable OUs exist.
- **Deterministic model boundary**: compile and discovery no longer silently
  select an installed Ollama model. LLM extraction is opt-in and requires an
  explicit provider plus pinned model; deterministic compile remains the local
  product baseline.
- **Lean cleanup**: deleted unused, test-only model-introspection helpers,
  consolidated duplicate script YAML loaders, removed stale NetworkX claims,
  and made broken built-in pattern imports fail visibly.
- **Code craftsmanship repair**: registry and contributor checks now share one
  pattern-reference validator, graph/extraction/comparison paths share one
  fail-closed requirement coercion path, and JSON recovery uses one ordered
  candidate pipeline. CLI, battle scoring, template, discovery, interview, and
  usability flows now separate validation, orchestration, and rendering without
  changing their public contracts.
- **Complexity contract**: Ruff now enforces cyclomatic complexity at 15,
  branches at 15, and statements at 60. The only localized exception is the
  linear AWS LZA end-to-end artifact contract test; argument and return counts
  remain deliberately ungated. Broad exception catches remain only at parser,
  plugin, evaluation, or external-backend boundaries.
- **Trust-boundary repair**: LLM extraction now accepts valid JSON plus harmless
  presentation wrappers only, validates graph responses with forbidden extras,
  and records parse failures as evidence. Graph-owned typed equality preserves
  account/name case while normalizing valid booleans, integers, lists, enums,
  and optionals.
- **Incremental and artifact safety**: incremental baselines must match the
  requested pattern and pass the generated-bundle contract before seeding.
  Registered artifact and fixture paths must be portable relative paths,
  generated symlinks are unlinked without following them, required YAML fails
  with path-specific errors, and malformed Checkov evidence cannot pass.
- **Package cohesion and supply chain**: Terraform VPC graph, target contract,
  generators, and samples now have separate pattern-owned modules. CLI version
  comes from package metadata; CI and `prek` use the locked uv/Ruff toolchain,
  actions are pinned to verified commit SHAs, Python 3.14 and clean-wheel smoke
  tests are covered, and the SBOM comes directly from the lockfile.
- **Compatible toolchain refresh**: runtime and development dependency floors
  now match the fully tested lock, future breaking releases are capped, and uv
  0.11.29 is declared once in `pyproject.toml`. Builds use a hashed setuptools
  constraint, release tags must match the package version before build or
  publish, and weekly uv/Actions maintenance is grouped for review.
- **Bundle trust boundary**: trust-sensitive bundle reads now share one
  resolver that rejects unsafe portable paths, directories, containment
  escapes, and leaf, parent, or root symlinks. Optional YAML is empty only when
  absent; malformed or non-mapping content fails visibly across validation,
  comparison, review, and AWS LZA staging.
- **Git and provider boundaries**: `compile-git` resolves an accepted ref once
  to an immutable commit, parses NUL-delimited paths, rejects unsafe paths, and
  records the resolved commit. OpenAI-compatible and Bedrock success envelopes
  require usable typed content while malformed usage evidence is ignored;
  retries are limited to transient failures, one to five attempts, and a
  30-second maximum server-directed delay.
- **Pattern ownership**: AWS named-entity recovery, validator-to-requirement
  review mapping, LZA validation evidence, artifact review owners, incremental
  reconfirmation policy, and forbidden artifact checks now live on the AWS LZA
  pattern instead of generic core branches.
- **Terraform VPC plan proof**: `terraform-vpc` now emits exact target/toolchain
  identities, three distinct maturity states, immutable input digests, and a
  replay manifest. `iac-llm-wrapper terraform plan --bundle` verifies those
  contracts, stages the code-owned root in a temporary workspace, runs locked
  init/validate/plan/show, binds success to the requested AWS account, blocks
  delete/replace actions, and emits sanitized evidence without apply, state,
  credentials, raw values, or retained plan files.
- **Plan trust and cohesion**: shared replay verification rejects missing,
  changed, unsafe, or symlinked bundle inputs and changed contracts. Terraform
  VPC compile metadata, execution, and evidence shaping remain separate cohesive
  pattern modules; no generic executor or new Python dependency was added.
- **Terraform build proof**: the packaged root pins Terraform 1.15.8,
  `terraform-aws-modules/vpc/aws` 6.6.1, and `hashicorp/aws` 6.53.0 with a
  four-platform provider lockfile. The real credential-free locked init and JSON
  validate passed; CI and release jobs run the same proof through the pinned
  setup-terraform action.
- **Validation**: 513 tests passed with one optional real-Ollama test skipped;
  coverage is 90.54%. Ruff, Ruff
  format, mypy, Pyright, fixture drift, golden journey, extraction (8/8),
  usability (8/8), all-files `prek`, lock check, Bandit, runtime `pip-audit`,
  full-development `pip-audit`, CycloneDX export, constrained package build,
  both installed CLI entry points, and all three packaged Terraform root assets
  in a clean Python 3.11 environment passed. No fixture drift or known dependency
  vulnerabilities remain.
- **Model comparison**: the historical implicit local Ollama fallback used
  `llama3.2:3b`, took about 79 seconds, and produced a graph delta from the
  deterministic bundle. It inferred `SandboxDev` belongs to the `Sandbox` OU,
  while deterministic recovery assigned it to `Workloads`; the packet does not
  explicitly map workload accounts to OUs. That ready verdict is now invalidated:
  current compilation blocks with `AWS_LZA_WORKLOAD_ACCOUNT_OU_AMBIGUOUS` until
  the packet supplies explicit mappings.
- **AWS cost boundary**: validation-only remains the recommended LZA cloud
  ceiling. Current AWS guidance estimates the sample LZA environment at roughly
  $430.22/month even with no activity or workloads, so full personal-account LZA
  deployment is not a minimum-cost test.
- **Remaining blockers**: the requested Terraform owner acceptance plan needs an
  owner-approved non-production packet/account and matching read-only AWS
  credentials; the local environment does not establish that authorization, so
  no cloud plan was attempted. Downstream-clean AWS LZA evidence still requires
  owner-approved account emails and an AWS/LZA validation context with read-only
  account lookup permission; no deploy/apply path was added.

### Durable Decisions

- Keep the product boundary narrow: registered target configuration handoff,
  contract checks, review evidence, and owner-controlled downstream execution.
- Prefer packet-driven fixes over imagined platform features.
- Prefer deletion and shared local helpers over new abstractions.
- Share domain knowledge only when its meaning and change boundary are the same;
  leave coincidental repetition local when a shared abstraction would add flags
  or coupling.
- Treat complexity metrics as enforceable investigation thresholds, not a reason
  to fragment linear contract assertions or introduce indirection.
- Require a real packet, contract, review failure, or measured gap before adding
  a feature; do not preserve test-only feature families without product callers.
- Do not register quality checks that pass when their required tool is absent.
- Parse model output without syntax repair; invalid JSON is evidence, not a
  decision source.
- Validate incremental bundles and portable artifact paths before reading them
  as trusted handoff state.
- Keep CI dependency audits scoped to the locked dependencies shipped by the
  product, and verify the full development environment during compatibility
  upgrades.
- Keep the uv version single-sourced in `pyproject.toml` and require hashed
  build constraints plus hash-locked runtime installation for release evidence.
- Treat generated bundles as untrusted filesystem input: validate containment,
  type, and every path component before reading, and never follow bundle
  symlinks.
- Resolve Git refs to immutable commits before diff or historical reads; keep
  the original ref only as user-facing provenance.
- Validate provider content independently from optional token evidence, and
  retry only explicitly transient failures within bounded attempts and delays.
- Keep pattern-specific review, extraction, and validation behavior on the
  owning pattern rather than branching in generic core.
- Keep LLMs out of HCL and version selection. Approved roots, modules, providers,
  contracts, and replay identities are code-owned and human-reviewed.
- Treat configuration readiness, plan invocation allowance, and a proven plan as
  separate states. A speculative plan never grants apply authority.
- Keep Terraform plan evidence value-free and portable: record identities,
  actions, counts, blockers, and account match only; discard temporary state,
  raw plan JSON, and the binary plan.
- Do not create an executor registry for one target. Generalize only after a
  second real plan-capable target demonstrates the same protocol.
- Keep generated/ignored evidence out of committed source unless it is an
  intentional fixture or contract artifact.
- Treat deterministic compile as the local product baseline and explicit,
  pinned-model compile as a separate extraction-quality experiment.
- Never accept model-inferred account-to-OU placement as handoff evidence;
  require explicit structured packet data when more than one OU is eligible.
- Compare deterministic and model bundles before handoff; an exit-zero result
  alone does not prove interpretation equivalence.
- Do not use a full personal LZA deployment as a cost-minimal validation path.

### Next

1. Run the explicit Terraform owner acceptance trial only after receiving an
   owner-approved non-production packet/account and matching read-only AWS
   credentials; require passing account-bound evidence and verify no state or
   plan binary remains.
2. Clarify the intended OU for each workload account in the banking customer
   packet and record the mappings under an account inventory; compilation now
   fails closed until that evidence exists.
3. Re-run official `iac-llm-wrapper lza validate` with owner-approved account
   emails and an AWS/LZA lookup-capable validation context.
4. If validation still fails, fix only packet-backed repo issues or record
   owner-side failures as downstream evidence.
