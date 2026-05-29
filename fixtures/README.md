# Fixtures

Fixtures are split by job so tests and demos do not blur product paths.

## Generated Sample Bundles

Versioned directories are checked-in outputs from registered `SampleConfig`
entries. The suffix (`-v1`) is the fixture contract version, not an upstream
provider version. If generator behavior changes intentionally, refresh these
with `uv run python scripts/sync-sample-fixtures.py`; CI checks drift with
`--check`.

- `aws-lza-standard-v1/`, `aws-lza-regulated-v1/`, `aws-lza-healthcare-v1/`:
  current AWS LZA handoff bundles.
- `k8s-cluster-v1/`: Kubernetes sample bundle for the `kubernetes-cluster`
  pattern.
- `terraform-vpc-basic-v1` is registry-only today; add a fixture bundle only
  when its generated artifacts need drift review like AWS LZA or K8s.

## Authored Trial Inputs

- `usability/`: role-based product trials for architect gaps, engineer handoff,
  and BYOM module flow.
- `eval/`: extraction gold corpus. Each `*.md` has a matching
  `*.expected.yaml`.
New product examples should go under `usability/` or `eval/`, not root.
