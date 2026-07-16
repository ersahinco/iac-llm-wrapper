# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Account-bound speculative plan proof for the exact approved Terraform VPC module, including replay verification, sanitized `terraform-plan-evidence.yaml`, static review evidence, and the no-apply `terraform plan --bundle` command.
- A packaged Terraform VPC root pinned to Terraform 1.15.8, `terraform-aws-modules/vpc/aws` 6.6.1, and `hashicorp/aws` 6.53.0 with a multi-platform provider lockfile and real CI init/validate proof.
- Intent-to-IaC orchestration framework with a model-driven decision core.
- Built-in product paths: aws-lza, cloudformation-parameters, kubernetes-cluster, terraform-vpc.
- Contract-backed sample recommendations for known-good handoff bundles.
- Schema-driven LLM extraction with graph-traversal prompts.
- Guided interview engine with topological question ordering.
- Generic `handoff-plan.yaml` for ordered owners, dependencies, manual gates, rollback, boundary, and allowed next action.
- LLM trace summaries with provider/model, rounded latency, raw and accepted decisions, applied decisions, resolved/blocking gaps, blocking contradictions, and raw evidence status.
- AWS LZA IAM Identity Center permission sets and assignments in model, graph, validation, and `iam-config.yaml`.
- CloudFormation parameter handoff for approved existing templates without stack generation.
- Handoff artifacts: decision reports, lineage manifests, deployment runbooks, audit trails, and sample recommendations.
- CI/CD: lint, format, type check, tests, extraction/usability evals, coverage gate, dependency audit, and static security scan.

### Changed
- Primary project and CLI name is `iac-llm-wrapper`; `intent-engine` remains the core engine and optional CLI alias.
- Structured Markdown decisions take precedence over direct LLM decisions, direct LLM decisions take precedence over signal decisions, and defaults fill only remaining gaps.
- LLM-reported gaps and contradictions only block when they target known applicable requirement graph nodes.
- Root docs and OpenCode/Copilot instructions now point to `AGENTS.md` as the shared project workflow source of truth.
- Runtime and development dependency floors now match the locked compatibility matrix and exclude future breaking releases.
- CI and releases use the uv version declared in `pyproject.toml`, hashed build constraints, deterministic wheel smoke tests, and separate SBOM evidence.

### Fixed
- Bundle reads now reject unsafe paths, directories, broken files, and leaf or parent symlinks before validation, comparison, review, or AWS LZA staging.
- Git incremental compilation resolves the requested base ref once, parses NUL-delimited paths, rejects non-portable paths, and records the resolved commit.
- OpenAI-compatible and Bedrock responses now require usable typed success envelopes; token evidence and retries are bounded and fail closed independently of valid content.
