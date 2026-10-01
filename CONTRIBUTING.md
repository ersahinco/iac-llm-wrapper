# Contributing

Questions, documentation fixes, examples, bug reports and code changes are welcome.
Start with the [quickstart](README.md#quickstart) and
[design guide](docs/design.md). You can contribute without running an LLM or using
cloud credentials.

Use whichever editor and development tools you prefer. The same checks and review
requirements apply to every contribution.

## Issues and pull requests

- [Open an issue](https://github.com/ersahinco/iac-llm-wrapper/issues) with the command,
  a minimal sanitised input, and the expected and actual result when reporting a bug.
- Small fixes can go straight to a pull request. Discuss larger features or new
  dependencies in an issue first so we can agree on scope.
- Fork the repository, create a branch, and open a pull request against `main`.
  Keep it focused, explain the problem and verification, and use a draft if you
  want early feedback. Maintainers review behavior, clarity and scope; CI runs the
  automated checks.

`main` requires a pull request, one approval, resolved review conversations and
passing `lint`, `test (3.11)`, `test (3.12)`, `test (3.13)` and `graph` checks.
Branches must be up to date; new commits dismiss stale approvals. These rules also
apply to administrators. Force pushes and deletion of `main` are blocked; merged
pull request branches are deleted automatically.

Be respectful, explain your reasoning, and leave room for questions and learning.
Use sanitised examples in issues and tests; keep client packets, credentials and
generated bundles out of contributions.

By submitting a contribution, you agree to license your original work under the
project's [MIT License](LICENSE). Retain the original licenses and notices for
third-party material, including the [bundled LZA schemas](src/intent_engine/schemas/SOURCE.txt).

## First contribution: one question, one policy, one test

Start with the existing [workload example](samples/vpc/README.md). Its monitoring
question is a small, complete path through this project: a human answer becomes
a typed value, a selected OPA policy checks it, and a test protects the distinction
between an explicit `false` and an unanswered question.

**Worked change: clarify the monitoring question and protect missing/unusable
answers.** This change is already included, so you can inspect and run it before
applying the same approach to another observed ambiguity. It adds no runtime code.

1. In [samples/vpc/organisation.yaml](samples/vpc/organisation.yaml), the
   `detailed_monitoring` question now asks whether the owner requested monitoring,
   explicitly asks for `true` or `false`, and explains the effect of leaving it
   unanswered. Keep `type: bool` and no default: a reference or a hint must never
   stand in for the owner's answer. Questions specific to a selected organisation
   belong here; the four general VPC questions remain in `decisions.yaml`.
2. Follow the `monitoring` policy entry in that same file to
   [samples/vpc/policy.rego](samples/vpc/policy.rego), `monitoring_assessment`.
   Its evidence points to the exact comment on line 5. The existing check already
   has the intended behavior below, so it needs no change. If you change a policy
   later, preserve its selected ID, scope and valid evidence line/quote, and return
   one assessment for it even when an answer is missing. Prose alone creates no check.
3. In [tests/test_workload_policy.py](tests/test_workload_policy.py),
   `test_monitoring_requires_an_explicit_usable_answer` copies the corrected packet
   into pytest's temporary directory and varies only that answer. It reads the
   document, extracts facts, coerces values and calls real OPA. The assertions check
   facts, unusable-value findings, policy status and whether the policy blocks.
   This protects behavior a reviewer cares about, without asserting the hint's wording.

| Packet answer | Expected behavior |
| --- | --- |
| Line absent | No monitoring Fact; `not-assessed` policy blocks export; graph review also asks the missing question |
| `detailed_monitoring: undecided` | Stated but unusable; `UNUSABLE_VALUE` plus `not-assessed`, blocking |
| `detailed_monitoring: false` | Usable answer; visible advisory `warning`, no monitoring-policy blocker |
| `detailed_monitoring: true` | Usable answer; monitoring policy `passed` |

The new test covers the document-to-policy boundary. Existing
`test_workload_warnings_and_exceptions_survive_review_and_export` in
[tests/test_graph.py](tests/test_graph.py) covers CLI review, successful export of
`monitoring: false`, and warnings retained in the trace. Other missing answers or
policy conflicts can still block the case.

Only the question text/hint and the focused test change for this contribution.
The example packets remain explicit answers; the existing
[instance input contract](samples/vpc/instance-inputs.json) already maps
`detailed_monitoring` to `monitoring`. No emitter, schema, dependency or policy
implementation change is needed.

After the host setup below and installing OPA, run the focused check:

```bash
opa version
env -u NEO4J_PASSWORD uv run --locked --extra dev --extra graphrag pytest \
  tests/test_workload_policy.py -k monitoring -v
opa check --strict samples/vpc/policy.rego
opa fmt --fail --list samples/vpc/policy.rego
```

The focus selects six cases, including the four packet variants above. A skip
because OPA is missing is not validation. No database is used by this focused
command. To check CLI/export behavior too, use the isolated full-suite setup below.
After editing selected organisation inputs, CLI users must re-ingest with
`--organisation samples/vpc/organisation.yaml` to refresh their stored snapshot.

For a similar first PR, state the observed ambiguity, the changed question/check,
and which missing, invalid or contradictory input your test distinguishes.
Acceptance means the focused test and relevant local checks pass, explicit false
answers remain warnings, missing answers still block, and the workload walkthrough
still exports the same supported inputs with evidence. Include commands/results
in the PR description; do not describe this as independent user feedback.

## Local checks

Use Python 3.11+ and [uv](https://docs.astral.sh/uv/). From the repository root:

```bash
uv sync --locked --extra dev --extra graphrag
env -u NEO4J_PASSWORD uv run --locked --extra dev --extra graphrag pytest
uv run --locked --extra dev --extra graphrag ruff check .
uv run --locked --extra dev --extra graphrag ruff format --check .
uv run --locked --extra dev --extra graphrag mypy
```

This skips database tests. GraphRAG model calls in automated tests are controlled;
passing tests do not establish live model answer quality.

For packaging or license changes, also run `uv build`. Built distributions must
include both the project's MIT license and the upstream schema license/notices.

## Full suite with Neo4j and OPA

Graph tests erase the database they connect to. Use a dedicated test project,
separate from saved client cases, and choose unused ports. Install OPA on the host
(`brew install opa` on macOS); CI pins its version in
[ci.yml](.github/workflows/ci.yml).

```bash
export COMPOSE_PROJECT_NAME=iac-tests
export NEO4J_BROWSER_PORT=28474 NEO4J_BOLT_PORT=28687
docker compose up -d --wait neo4j
export NEO4J_URI="bolt://127.0.0.1:${NEO4J_BOLT_PORT}"
export NEO4J_USER=neo4j NEO4J_PASSWORD=localdevpassword NEO4J_DATABASE=neo4j
opa check --strict src/intent_engine/policy samples/organisation/policy.rego samples/vpc/policy.rego
opa fmt --fail --list src/intent_engine/policy samples/organisation/policy.rego samples/vpc/policy.rego
uv run --locked --extra dev --extra graphrag pytest
docker compose stop
unset NEO4J_URI NEO4J_USER NEO4J_PASSWORD NEO4J_DATABASE
unset COMPOSE_PROJECT_NAME NEO4J_BROWSER_PORT NEO4J_BOLT_PORT
```

The full suite should finish without skips. Stopping retains the test volume.
No model downloads, cloud credentials or deployment are required.

## Change boundaries

Add a regression check when behavior changes. Reuse Neo4j/Cypher, GraphRAG, OPA
and JSON Schema before introducing custom code or dependencies. New questions,
checks and output mappings need a concrete case and explicit coverage limits.
Preserve source evidence, human confirmation and export gates. Keep deployment
and approvals in the consuming team's pipeline.

The code map and design constraints are in [docs/design.md](docs/design.md). CI runs lint, types,
Python 3.11–3.13 tests, real Neo4j checks and an LZA export journey. Include the
checks you ran and any skipped coverage in your pull request.
