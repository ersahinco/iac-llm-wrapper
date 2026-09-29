# Scoped network and compute discussion

This synthetic case adds policy to the four-question VPC example. It checks the
requested VPC against a supplied routing-domain allocation list, restricts instance
types by environment, and keeps security advice and recorded exceptions visible.

For a small contribution, follow the [monitoring question through its policy and
test](../../CONTRIBUTING.md#first-contribution-one-question-one-policy-one-test).

Use a separate case and unused ports. Ingestion replaces that case's whole graph.
OPA is included in the Compose app; no model or cloud credentials are needed.

```bash
export COMPOSE_PROJECT_NAME=iac-workload
export NEO4J_BROWSER_PORT=59474 NEO4J_BOLT_PORT=59687
docker compose build app
docker compose run --rm app ingest samples/vpc/client-policy.md \
  --catalog samples/vpc/decisions.yaml --organisation samples/vpc/organisation.yaml
docker compose run --rm app review
# Expected exit 1: overlapping peer subnets, an existing allocation conflict,
# an out-of-scope instance type, plus an advisory monitoring warning.
docker compose run --rm app emit-tfvars \
  --contract samples/vpc/instance-inputs.json --out build/workload-blocked
# Expected exit 2, no output.
docker compose run --rm app ingest samples/vpc/confirmed-policy.md \
  --catalog samples/vpc/decisions.yaml
docker compose run --rm app review
# Exit 0: corrected networking; the instance exception and monitoring advice remain warnings.
docker compose run --rm app emit-tfvars \
  --contract samples/vpc/module-inputs.json --out build/workload-vpc
docker compose run --rm app emit-tfvars \
  --contract samples/vpc/instance-inputs.json --out build/workload-instance
docker compose stop
```

Choose fresh output directories when repeating exports. Corrections reuse the
stored references. To change policy or allocations, edit the selected inputs and
explicitly supply `--organisation` again on ingestion.

## What each file owns

| File | Responsibility |
| --- | --- |
| `decisions.yaml` | Four explicit VPC answers, including peer private subnets |
| `organisation.yaml` | Additional questions and the selected policy scopes/evidence |
| `estate.yaml` | Synthetic allocations by routing domain, instance allowlists, scoped exception owner and reason |
| `policy.rego` | Three named OPA assessments; no policy is inferred from prose |
| `client-policy.md`, `confirmed-policy.md` | The architect's requested and corrected values |
| `module-inputs.json`, `instance-inputs.json` | Explicit mappings to two independent module input subsets |

The same `10.42.0.0/16` in a disconnected lab does not conflict with the corporate
case. Selecting that lab's routing domain does report the overlap. Only compare
peer allocations in the supplied domain; subnet containment within its own VPC is
expected. The owner must establish snapshot completeness and freshness. Missing or
malformed allocation data yields `not-assessed`, never an assertion of free space.

Development normally permits `t3.micro` and `t3.small`. The synthetic selected
reference permits `m5.large` through one development-only exception with an owner
and reason. `r5.xlarge` has no exception and blocks export with the allowed
alternatives. A missing reason cannot waive the rule. Disabled detailed monitoring
is advice, so it produces a warning without preventing export. These rules express
this case's policy; they are not universal security or sizing recommendations.

## Engineering handoff

The VPC output uses the existing 6.7.3 input subset. The instance output contains
only `instance_type` and `monitoring` for
[`terraform-aws-modules/ec2-instance/aws` 6.4.0](https://github.com/terraform-aws-modules/terraform-aws-ec2-instance/tree/v6.4.0).
Its [upstream version floor](https://github.com/terraform-aws-modules/terraform-aws-ec2-instance/blob/v6.4.0/versions.tf)
is Terraform 1.5.7 and AWS provider 6.37. The owner's consuming root module supplies
AMI, subnet, storage, identity, other inputs, backend and deployment approvals.
These two subsets do not automatically wire the modules together.

Each output directory includes `decision-trace.json`: the input contract hash,
source evidence, reference hashes and reassessed policies, including warnings and
the exception rationale. Owner names in reference text are not authenticated sign-off.
No Terraform command runs, and no state or AWS resource is changed. Capacity,
actual connectivity and deployment readiness remain owner validation work.

For common resource security warnings, use `review --scan PATH_TO_OWNER_IAC` on the
host with Checkov and Trivy installed. Bare module variable JSON does not provide
enough resource detail for a complete security assessment.
