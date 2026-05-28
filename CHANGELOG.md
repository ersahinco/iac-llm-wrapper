# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial alpha release with intent-driven infrastructure decision framework.
- Seven built-in patterns: baseline, minimal, workload, hybrid-enterprise, financial-services, healthcare, kubernetes-cluster.
- Composable addon system (pci-compliance, hipaa, self-hosted-cicd, hashicorp-vault, paloalto-fw, hybrid-challenges).
- ConfigCatalog with diff/apply for known-good decision sets.
- Schema-driven LLM extraction with graph-traversal prompts.
- Guided interview engine with topological question ordering.
- Decision reports with Well-Architected pillar coverage and audit trails.
- CI/CD: lint, format, type check, tests, coverage gate, dependency audit, and static security scan.
