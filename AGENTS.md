# AGENTS.md

## Project: iac-llm-wrapper / intent-engine core

Core engine for `iac-llm-wrapper`, an architect-exchange-to-registered-target
configuration framework. It captures architecture intent from prose, validates
decisions through requirement graphs and target contracts, and emits traceable
target configuration artifacts that engineers use with existing deployment
mechanisms. Direct deployment and whole-IaC-from-scratch generation stay out of
runtime scope.

AWS Landing Zone Accelerator is the first product path: collected inputs become
validated LZA YAML/config files for the downstream LZA deployment process. The
core must stay generic: patterns own domain models, contracts, validators,
samples, and target configuration emitters.

## Commands

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run --extra dev mypy
uv run --extra dev pyright .
uv run python scripts/sync-sample-fixtures.py --check
uv run python scripts/evaluate-golden-journey.py
uv run python scripts/evaluate-extraction.py
uv run python scripts/evaluate-usability.py
uv run pre-commit run --all-files
```

## Architecture

- **Models** (`src/intent_engine/patterns/*/models.py`): Pydantic v2 intent data models. Pattern-specific models drive extraction, graph sync, validation, semantic model derivation, and artifact emission.
- **Extract** (`extractor.py`): Single graph-driven `Extractor`. Prompts come from requirement nodes, not regex or fixed document layout. Without LLM, deterministic fallback applies graph defaults and structured Markdown entity recovery.
- **Patterns** (`patterns.py`): Lean registry for pluggable product paths. Current built-ins: `aws-lza`, `cloudformation-parameters`, `kubernetes-cluster`, `terraform-vpc`.
- **Requirements** (`requirements.py`): Decision graph with `applies_if`/`blocked_if`, richer `applies_when`/`blocked_when` expressions, `depends_on`, cascade rules, tradeoffs, compliance controls, signals, and audit trail.
- **Semantic model** (`semantic_model.py` + pattern `semantic.py`): Lightweight typed entities, relationships, and predicate constraint results for real-world dependencies without RDF/OWL, Datalog, or a graph database.
- **Interview** (`interview.py`): Graph-ordered requirement capture. Shows context, asks only applicable gaps, supports save/resume, and records rationale.
- **Validate** (`validator.py`): Fail-closed graph and pattern validation. Missing required applicable decisions become compile errors.
- **Generate** (`generator.py`): Registry-driven emitter for decision report, generic handoff plan, target configuration artifacts, lineage, runbook, module inputs when pattern owns module mapping, sample recommendations, and static review artifacts.
- **Contracts** (`contracts.py`): Target artifact contracts define required files, paths, decisions, lineage, and stable value assertions.
- **Samples** (`sample_config.py`): Registered reference bundles with pinned source metadata, module refs, tags, fixture dirs, and match recommendations.
- **LLM** (`llm_caller.py`): Pluggable OpenAI-compatible and Ollama backends with retry/backoff and evidence capture.
- **CLI** (`cli.py`): `compile`, `interview`, `validate`, `explain`, `sample`, `contract`, `graph`, `discover`, `template`, `review`. Default pattern is `aws-lza`.

## Current Pattern Surface

- `aws-lza`: Contract-backed AWS LZA registered target path. Emits official-style LZA YAML target configuration artifacts, decision report, lineage manifest, deployment runbook, and sample recommendations. Does not emit deployable Terraform/Terragrunt landing-zone stacks.
- `cloudformation-parameters`: BYOM CloudFormation parameter handoff for an approved existing template. Emits parameters and decision report, not a stack or deployment.
- `kubernetes-cluster`: Contract-backed K8s handoff for cluster/namespace config with optional Terraform EKS module input references.
- `terraform-vpc`: BYOM Terraform AWS VPC module input capture. Emits module variables/tfvars handoff for an existing module, not root deployment scaffolding.

## Key Decisions

- Core stays domain-agnostic. Use-case logic lives in pattern packages.
- Graph owns decision order, branching, blocked paths, cascades, gaps, provenance, and handoff sequencing.
- Existing accelerators/modules are registered targets with contracts and data models before they are emitted configuration artifacts.
- Current built-ins make no AWS API calls and do not deploy. No arbitrary Terraform from prose.
- "Wrapper" means architect exchange to registered target configuration, not bypassing IaC tools, accelerators, or gates.
- Sample recommendations must persist as artifacts, not terminal-only hints.
- `src/intent_engine/patterns/aws_lza` is the only AWS LZA path. Old research path was removed to avoid two-source confusion.

## Fixtures

- `fixtures/aws-lza-standard-v1/`, `fixtures/aws-lza-regulated-v1/`, `fixtures/aws-lza-healthcare-v1/`: emitted AWS LZA sample handoff bundles.
- `fixtures/k8s-cluster-v1/`: emitted K8s sample handoff bundle.
- `fixtures/usability/`: role trials for architect gap capture, engineer handoff, BYOM Terraform, and BYOM CloudFormation parameter flow.
- `fixtures/eval/`: extraction gold corpus with expected handoff artifact checks.
- Version suffixes (`-v1`) are fixture contract versions. They protect emitted artifact shape from silent drift.

## Model-Driven Flow

1. Architect writes Markdown or runs interview.
2. Extractor asks LLM for graph decisions, or deterministic fallback applies explicit structured inputs plus defaults.
3. Graph applies decisions in dependency order and records provenance.
4. Discovery reports applicable gaps and detected signals.
5. Interview fills only missing applicable decisions.
6. Validate and emit deterministic target configuration artifacts for engineers.

## Extension Contract

Add new target path by registering a pattern with:

- Pydantic intent model.
- Requirement graph.
- Optional deployment target contract.
- Optional sample configs.
- Optional validators/target configuration emitters/module mapping.

Do not add provider-specific branches to core CLI/compiler/extractor/generator.

## Stack

Python 3.11+, Pydantic v2, Typer, ruamel.yaml, networkx, pytest, ruff, mypy, pyright.

## Session State

<!-- UPDATE THIS SECTION AT END OF EVERY SESSION -->

### Current Goal

T62: AWS LZA validation-only evidence adapter

### Status

- **Tests**: 372 passing, 1 skipped; golden journey passed; fixture drift check passed
- **Lint**: clean (`ruff check .`)
- **Format**: clean (`ruff format --check .`)
- **Type check**: clean (`mypy` and `pyright`)
- **Repo**: `github.com/ersahinco/iac-llm-wrapper` (private)
- **Last session**: Added `iac-llm-wrapper lza validate`, a validation-only AWS LZA config-validator adapter that stages generated LZA config files, runs `yarn validate-config` or `corepack yarn validate-config` from a user-supplied local LZA source checkout, and writes `lza-validation-evidence.yaml`. It does not clone, install, synth, deploy, run pipelines, or mutate AWS. Owner validation still requires owner review or downstream acceptance of the evidence.

### Done

- Core: graph-driven extraction/discovery/interview/validation, pattern registry, contracts, handoff generation, static review, contract validation, benchmark/battle artifacts, sample matching, and CLI commands are implemented and covered.
- Built-ins: `aws-lza`, `cloudformation-parameters`, `kubernetes-cluster`, and `terraform-vpc` are contract-backed handoff paths. Current built-ins make no cloud API calls and do not deploy from prose.
- Evaluation: deterministic extraction corpus includes clean, blocked, BYOM, and customer-style prose cases; role usability trials, forbidden-artifact checks, fixture drift guard, contract validation tests, battle-summary tests, static review tests, stakeholder handoff-confidence checks, and full repo gate are green.
- Golden journey: `scripts/evaluate-golden-journey.py` is the quickest product-confidence check for the core promise: messy customer-style AWS LZA notes to service-style reviewed handoff bundle. It supports `--scenario ready`, `--scenario blocked`, `--scenario all`, `--require-conformant`, `--benchmark-output`, and `--output` for readiness, blocked-safety, model baseline checks, and CI/archive result artifacts.
- Bedrock: `--provider bedrock` uses the local AWS CLI session with Bedrock Runtime Converse, defaulting region from `INTENT_ENGINE_AWS_REGION`, `AWS_REGION`, `AWS_DEFAULT_REGION`, then `eu-central-1`; it records Bedrock token usage in the existing trace/benchmark schema without adding a new harness or SDK dependency.
- Observability: `model-benchmark.yaml` now reports raw LLM coverage of accepted decisions, missing accepted keys, and model conformance (`pass`, `review`, `fail`, `not-applicable`); LLM battle summaries surface raw-model misses as expected weaknesses instead of hiding them behind deterministic Markdown success.
- Model comparison: `scripts/compare-model-benchmarks.py` shows `rawCoverage`, `rawMissing`, `missingKeys`, and `conformance`; `--require-conformant` fails non-conformant LLM benchmark runs.
- Static review: `handoff-review.html` starts with a human summary of readiness, contract status, allowed next action, blocker traceability, model conformance, raw LLM coverage, missing raw decision keys, and expected weaknesses.
- Developer visuals: `scripts/render-dev-views.py` writes local `tests/results/dev-views/index.html` plus Mermaid/JSON requirement graphs, Mermaid Pydantic intent model diagrams, a Mermaid module dependency graph, and Markdown summaries of golden journey/model benchmark artifacts. These are local development artifacts, not product UI.
- Customer packet trial: `fixtures/eval/customer-packet-banking-lza.md` captures a realistic banking AWS LZA packet with client notes, architect clarification, security review, secret-store references, and engineer handoff reminders. Its expected artifact contract is part of the existing extraction eval corpus.
- Usability: `scripts/evaluate-usability.py` now includes ready and blocked static-review stakeholder trials plus a service-style handoff-confidence trial that verifies what is ready, what can move next, target contracts, manual gates, and raw evidence omission.
- Cleanup: removed stale LZA research/extension/diff/apply/default-normalizer surfaces, no-contract artifact fallback, pattern `extra_artifacts`, duplicate fixture normalization, and stale duplicate LLM docs.
- Language: user-facing docs now prefer handoff readiness; `deploymentReadiness` remains a legacy compatibility alias in artifacts. Docs now also state that secrets should travel as secret-store references and expected parameter names, never raw values.
- Quality gates: Ruff, Ruff format, mypy, Pyright/Pylance, fixture drift, coverage tests, extraction/usability/golden journey checks, Bandit, pip-audit, uv build, and pre-commit are wired into local/CI workflows as applicable.
- T36 usability: CLI output now points first-time users from discovery and compile results to service-style compile, blocked review generation, `handoff-plan.yaml`, and static review creation. `handoff-review.html` now includes reviewer next actions derived from readiness, contract status, artifacts, and raw evidence state. README and LLM setup now include a concise real customer packet path for Ollama and direct Bedrock runs with `--no-raw-evidence`.
- T37 remediation: review findings are resolved without adding new harnesses, dashboards, private pattern loading, or broad AWS schema depth. The fixes tighten discoverability, evidence handling, generator scope, terminology, and code organization while preserving legacy artifact compatibility where external consumers may still depend on older keys.
- T38 remediation: discovery partial-input handling, public generator scoping, interview artifact parity, active handoff terminology, CloudFormation README accuracy, and discovery regression coverage are fixed. Sample fixtures now include deterministic `llm-trace-summary.yaml` and `model-benchmark.yaml` for interview-generated bundles so review pages no longer show unexplained missing evidence.
- T38 targeted re-review: first-run CLI workflow, interview/compile artifact parity, generator scope, pattern report readiness, handoff terminology, fixture/docs consistency, and `cli_guidance` organization were rechecked. Follow-up fixes preserve interview default provenance, make simulated discovery decisions explicit, remove blocked wording from ready safe handoff paths, and improve raw-evidence omission wording in review HTML.
- T39 operating rhythm: Ran banking AWS LZA, retail board-note AWS LZA, blocked AWS LZA, BYOM Terraform VPC, and blocked BYOM CloudFormation packets through `discover -> compile --no-raw-evidence -> review html`. Ready packets were clear enough for reviewed handoff, blocked compile/review artifacts were safe, and the repeated first-success friction in blocked discovery next steps was fixed without adding harnesses or dashboard surface.
- T39 follow-up rhythm: Ran complex AWS LZA, standard AWS LZA, incomplete architect AWS LZA, BYOM CloudFormation, and BYOM Terraform packets through the same path. The previous discovery guidance fix held. No stuck, mistrust, or manual-translation point repeated or blocked handoff, so no engine change was made.
- T40 incremental compare: `iac-llm-wrapper review compare --before <bundle> --after <bundle> --output handoff-comparison.yaml` compares existing generated bundles without rerunning extraction. The report surfaces readiness changes, requirement completeness changes, accepted decision additions/removals/changes, blocker additions/resolutions, changed artifact file hashes, model quality changes, and sample recommendation additions/removals/rank/score changes. Existing `review diff` remains for decision-report-only comparisons.
- T41 diff-aware compile: `iac-llm-wrapper compile --baseline-bundle <bundle> --baseline-doc <before.md> --changed-doc <after.md> --output <bundle> --no-raw-evidence` supports incremental long-document updates. Baseline decisions are carried forward, changed structured decisions override them, optional LLM extraction sees only scoped delta context plus previous decisions/summary, and the full graph plus contracts still validate the complete resulting state. `input-diff-report.yaml` records changed headings, changed structured decision lines, hunks, and likely impacted requirements. `incremental-compile-report.yaml` records reused, changed, added, removed, carried-forward, and re-confirmation decisions. `review compare --html-output` emits a static delta page.
- T42 target capability graph: the requirement graph remains the decision/readiness layer, and a second target capability graph now explains downstream routing and coverage. AWS LZA is the first reference target: accepted landing-zone decisions are covered by the LZA accelerator path, app/workload infrastructure language is flagged for separate module-composition or generator handling, and arbitrary Terraform/Terragrunt generation remains blocked unless a registered target owns it.
- T43 battle test: Ran realistic ready AWS LZA, blocked AWS LZA, BYOM Terraform, incremental document update, review comparison, static delta HTML, and sample recommendation movement through the current CLI. No new harness or dashboard was added. The only blocking usability issue found was false unsupported target routing from negated generation language and short keyword substring matches; target capability detection now requires affirmative whole-token matches and ignores local negation.
- T44 usability bug sweep: Fixed route-scoping and wording issues found in real generated outputs. Pure AWS LZA handoffs no longer show workload-module gates as active manual gates; blocked target capability rows show unavailable; blocked compile suggests `template --pattern <actual-pattern>`; BYOM patterns without target graphs show `not declared`; blocked reviews explain missing `handoff-plan.yaml`; raw evidence omission displays as `not requested`.
- T45 follow-up usability sweep: After committing T42-T44, re-ran first-run and handoff paths from a clean baseline. Fixed discovery clarifying-question copy so it uses graph questions instead of generic fallback text, fixed comparison HTML so added/removed artifacts are visible alongside changed artifacts, fixed blocked-review traceability so AWS LZA cross-field validator blockers point to concrete requirement questions instead of `unknown`, fixed repeated discovery gap numbering, replaced AWS-shaped safe handoff wording with pattern-neutral target-toolchain language, made ready review next actions owner-neutral for BYOM paths, normalized input diff report values so list decision deltas do not mix list and scalar forms, fixed terminal `review compare` artifact delta output so added/changed/removed artifact groups are visible without opening YAML or HTML, aligned runbook/review/harness wording on `Handoff allowed` instead of `Handoff ready`, and fixed comparison decision-delta rendering so added/changed/removed accepted decisions are all named in terminal and static HTML review output.
- T46 context-as-code guardrails: `pattern check` now validates bounded `Pattern.prompt_context`, rejects missing/vague context, surfaces context rule counts in CLI output, and requires explicit violation code/message for required open decisions without defaults. CloudFormation, Kubernetes, and Terraform VPC prompt contexts now state handoff boundaries and forbid deployable scaffolding generation from prose. Added `docs/CONTEXT_AS_CODE.md` and linked it from README and pattern authoring guidance.
- T47 complete lightweight context-as-code adoption: Successful pattern-backed bundles now emit and validate `context-manifest.yaml`. The manifest records the active pattern, prompt context digest/text, requirement graph inventory, target contracts, samples, target capabilities, runtime LLM/extraction summary, expected artifacts, and guardrails. `Pattern.expected_artifacts()`, `validate_generated`, ready-bundle contract validation, docs, tests, and registered sample fixtures now treat the manifest as a first-class non-deployable artifact.
- T48 semantic facts for target routing: Target capability routing now consumes explicit `UnsupportedAskFact` entities instead of scanning source text inside graph evaluation. Deterministic source-text matching extracts facts with evidence spans first; the graph then selects module-composition/generator/manual/blocked paths from facts and accepted decisions. `target-capability-graph.yaml`, `handoff-plan.yaml`, `llm-trace-summary.yaml`, and `context-manifest.yaml` expose the semantic fact state for review.
- T49 lightweight typed semantic model: Added expression gates to requirement graphs and a no-infrastructure semantic model layer. AWS LZA now derives typed entities, relationships, and predicate constraints for account/OU placement, Identity Center permission-set and assignment references, home-region containment, valid network CIDR, control/artifact relationships, and delegated-admin Security OU placement. Validation and generated decision reports use that model, while existing flat decision fields and artifacts remain backward compatible.
- T50 fail-closed hardening: Compile success now depends on graph/pattern validation, blocked target capability routing, incremental reconfirmation for high-risk changed prose, and post-generation artifact contracts. Contract validation fails closed when readiness metadata is absent. Requirement expression shape is checked by `pattern check`. AWS LZA duplicate account conflicts are semantic blockers, and explicit workload-account OU placement is preserved in generated handoff artifacts.
- T51 residual hardening: Generated target artifacts are staged and promoted only after contract validation passes; failed compiles remove known generated/stale artifact files before writing safe blocked assessment artifacts. Partial readiness metadata in standalone `contract-validation.yaml` is blocked, and runtime expression evaluation fails closed on invalid expression shapes.
- T52 product boundary: Public docs now prefer registered target configuration language over broad IaC generation claims. AWS LZA is documented as the canonical target where validated inputs become LZA YAML/config artifacts for an existing deployment mechanism. Docs guardrail tests prevent accidental claims of direct deployment or whole-IaC-from-scratch generation.
- T53 plan-ready registered target bundle: AWS LZA now declares plan-ready bundle support as metadata only, emits `plan-manifest.yaml` with immutable inputs, prerequisites, expected plan outputs, manual gates, no-apply boundaries, and unresolved plan blockers, and emits `replay-manifest.yaml` with source, contract, and artifact digests. The generic plan-ready contract validates these artifacts only for registered plan-ready patterns; non-AWS patterns are not forced into premature capability machinery.
- T54 AWS LZA plan-ready proof: Realistic AWS LZA packets were compiled and their plan manifests inspected; blocker text is useful for config-ready-but-plan-blocked packets. The almost-plan-ready packet now reaches `planReady: ready` with explicit account emails, core VPC route tables/subnets/NAT gateways, TGW route tables/routes, and TGW attachments, while still emitting metadata only and no invocation. Negated "No Terraform root modules, Terragrunt..." boundary language no longer triggers unsupported Terraform generation routing.
- T55 AWS LZA network schema comparison: Public schema comparison revealed generator fixes. Owner validation still requires a real downstream command, pipeline output, or checklist.
- T56 validation evidence cleanup: Unverified local evidence was removed. Do not claim owner validation without an actual downstream validation signal or deliberate product artifact.
- T57 contributor onboarding and LZA validation packet: README was shortened into a front door and the LZA validation checklist was introduced as the first owner evidence target.
- T58 less-docs refinement: Removed the separate contributor onboarding doc and merged its unique value into `CONTRIBUTING.md`: repo map, tracked-vs-generated rule, change matrix, anti-slop doc rule, and real-owner-evidence rule. README no longer carries repo layout or quality gate detail. The only new doc left is `docs/LZA_DOWNSTREAM_VALIDATION.md`, kept as a checklist-first owner packet.
- T59 implementation reduction: Added a small shared YAML artifact writer in `core/yaml_utils.py` and removed duplicated YAML dump/write helpers from core generator, compiler artifact writes, AWS LZA helpers, and Kubernetes generators without changing CLI/runtime interfaces or artifact intent.
- T60 compiler slimming: Extracted incremental baseline parsing to `core/baseline.py`, readiness shaping to `core/readiness.py`, and artifact staging/promotion/contract validation to `core/compile_artifacts.py`. `compiler.py` remains the orchestrator and still exposes the existing public validation helpers for compatibility.
- T61 LZA ecosystem positioning: Added `docs/LZA_RELATED_WORK_STRATEGY.md` to synthesize AWS LZA Universal Configuration, Luminarlz, Nuvibit NTC, and daily LZA operations into product principles and an ordered backlog. README now frames the tool as pre-flight decision capture and handoff readiness before AWS LZA runs, and CONTRIBUTING rejects related-work-inspired runners, dashboards, plugin loaders, or schema expansion without repeated evidence.
- T62 LZA validation-only evidence: `iac-llm-wrapper lza validate --bundle <bundle> --lza-source <local-lza-repo-or-source>` runs the official local AWS LZA config validator against staged generated config files and writes `lza-validation-evidence.yaml` with command, exit code, stdout/stderr, package version, optional git commit, and explicit no-deploy/no-synth/no-clone/no-install/no-AWS-mutation guardrails. It falls back to Corepack when a direct `yarn` executable is not on PATH.

### Next

1. Run `iac-llm-wrapper lza validate` against a real local AWS LZA source checkout when available, include `lza-validation-evidence.yaml` with the owner packet, and capture owner acceptance before claiming downstream validation.
2. Use diff-aware compile plus `review compare` whenever a long document or sample configuration changes incrementally; review only the delta first, then decide whether a repeated/blocking point deserves implementation.
3. Continue packet-based requirement harvesting before adding product surface: record only stuck/mistrust/manual-translation moments, and implement only repeated or handoff-blocking requirements.
4. Stop harness expansion unless real local/Bedrock model runs expose pain.
5. Run `evaluate-extraction.py --llm`, `evaluate-usability.py --llm`, and `compare-model-benchmarks.py --require-conformant` with approved local/Bedrock models when broader model regression confidence is needed; use result artifacts to decide whether prompts or fixtures need tightening.
6. If reviewers still struggle to resolve blockers, consider adding lightweight anchors from blocker rows to exported requirement graph nodes without adding JavaScript.
7. Continue AWS LZA schema depth only where real customer inputs justify it.
8. Bring Terraform module-composition toward plan-ready only after AWS LZA's plan-ready network/account fields survive one owner-reviewed packet.
9. Next data-modeling increments should add typed entities only where a real
   packet exposes a missed relationship; defer Datalog until constraints become
   deeply inferential or platform-team policy preferences need rule composition.

### Durable Decisions

- Core stays domain-agnostic; pattern packages own models, graphs, contracts, validators, samples, and generators.
- Two-layer graph architecture is the product direction: requirement graphs own decisions, gaps, blockers, provenance, and readiness; target capability graphs own downstream route selection, target coverage, unsupported asks, manual gates, and blocked generation paths.
- Typed property graph plus predicate constraints is the current data-modeling direction. Keep Pydantic as the serialized handoff model and NetworkX/dataclasses for traversal/evaluation; do not introduce RDF/OWL, Datalog, or graph databases until real policy inference needs justify them.
- Graph and contracts own readiness. LLM output is evidence until accepted by graph requirements and artifact contracts.
- Handoff artifacts are not deployments. `handoffReadiness` is the clearer term; legacy `deploymentReadiness` stays for backward compatibility.
- Raw LLM evidence is local development/debug material. Service-style runs can disable raw prompt/response storage with `--no-raw-evidence` while preserving `llm-trace-summary.yaml`, `model-benchmark.yaml`, and `handoff-review.html` for interpretation review.
- Secrets must be represented as secret-store references plus expected parameter names so values do not enter prompts, raw evidence, review HTML, Git, or handoff artifacts.
- Built-ins are enough until a team has proprietary modules, controls, sample bundles, or gates that justify private patterns.
- Customer-style eval fixtures should mix prose, meeting notes, architect clarification passes, review reminders, and structured decisions so the harness protects real handoff behavior, not only template-shaped examples.
- Local customer-fixture hardening should prefer the best model a work MacBook Pro can handle, currently `qwen2.5:7b` in this workspace; Bedrock remains an approved cloud path through an OpenAI-compatible gateway/proxy when cost and policy require it.
- Local T21 comparison showed `qwen2.5:3b` had the best raw AWS LZA coverage on the customer board-notes fixture in this run, while `qwen2.5:7b` remained ready but missed Identity Center keys and `llama3.2:3b` was weak for AWS board notes.
- Direct Bedrock T31 run used SSO role `AWSReservedSSO_AWSAdministratorAccess_0f7a04d12908e8e3` in account `691627364817`. Catalog showed `amazon.nova-2-lite-v1:0` in `eu-central-1`, but runtime required inference profile `eu.amazon.nova-2-lite-v1:0`. Golden journey result: ready `20/20` raw coverage, conformance `pass`, 3657 tokens, 3926.3 ms; blocked `17/17` raw coverage, safely blocked, 4292 tokens, 4314.4 ms. No prompt or fixture tightening needed from this run.
- T33 customer packet trial used `eu.amazon.nova-2-lite-v1:0`. Service-style compile with `--no-raw-evidence` wrote `tests/results/customer-packet-banking-lza-bedrock`, review HTML was ready/contract-pass/model-conformant, raw coverage was `20/20`, raw missing `0`, parse errors `0`, 3771 tokens, 4139.2 ms, and raw evidence was omitted. Existing LLM eval also passed with raw coverage `20/20`, 3493 tokens, 3401.9 ms. Review categories recorded no prompt/model misses and no missing graph/model fields; one expected review note remains that structured Markdown carried accepted decisions.
