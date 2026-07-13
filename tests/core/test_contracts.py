"""Target contract validation tests."""

from __future__ import annotations

from pathlib import Path

from intent_engine.core.contracts import (
    BLOCKED_ASSESSMENT_CONTRACT,
    CONTEXT_MANIFEST_CONTRACT,
    CORE_CONTRACTS,
    HANDOFF_PLAN_CONTRACT,
    ArtifactContract,
    ArtifactValueAssertion,
    ContractValidator,
    DecisionLineage,
    TargetContract,
)
from intent_engine.core.patterns import GLOBAL_REGISTRY
from intent_engine.core.requirements import Requirement, RequirementGraph
from intent_engine.patterns import load_builtin_patterns

load_builtin_patterns()


def _contract() -> TargetContract:
    return TargetContract(
        name="example",
        kind="terraform-module",
        source_url="https://example.com/module",
        artifacts=[
            ArtifactContract(name="main.tf"),
            ArtifactContract(name="README.md", required=False),
        ],
        required_decisions=["region", "account"],
        lineage=[
            DecisionLineage(decision="region", artifact="main.tf", path="inputs.region"),
        ],
    )


def _yaml_contract() -> TargetContract:
    return TargetContract(
        name="yaml-example",
        kind="yaml-config",
        source_url="https://example.com/config",
        artifacts=[
            ArtifactContract(
                name="config.yaml",
                required_paths=["region", "accounts[]", "accounts[].name"],
                value_assertions=[
                    ArtifactValueAssertion(path="region", equals="eu-central-1"),
                ],
            ),
        ],
        required_decisions=["region"],
        lineage=[
            DecisionLineage(
                decision="region",
                artifact="config.yaml",
                path="region",
            ),
            DecisionLineage(
                decision="account_name",
                artifact="config.yaml",
                path="accounts[].name",
            ),
        ],
    )


class TestContractValidator:
    def test_contract_definition_validates(self):
        assert ContractValidator(_contract()).validate_contract() == []

    def test_unknown_lineage_artifact_fails(self):
        contract = _contract()
        contract.lineage.append(
            DecisionLineage(decision="account", artifact="missing.yaml", path="account")
        )

        violations = ContractValidator(contract).validate_contract()
        assert {violation.code for violation in violations} == {"CONTRACT_LINEAGE_ARTIFACT_UNKNOWN"}

    def test_invalid_assertion_definition_fails(self):
        contract = TargetContract(
            name="bad-assertions",
            kind="yaml-config",
            source_url="https://example.com/config",
            artifacts=[
                ArtifactContract(
                    name="config.yaml",
                    value_assertions=[
                        ArtifactValueAssertion(path="region"),
                        ArtifactValueAssertion(path="mode", equals="a", one_of=["a", "b"]),
                    ],
                )
            ],
            required_decisions=["region"],
        )

        violations = ContractValidator(contract).validate_contract()

        assert {violation.code for violation in violations} == {
            "CONTRACT_ASSERTION_RULE_REQUIRED",
            "CONTRACT_ASSERTION_AMBIGUOUS",
        }

    def test_graph_must_contain_required_and_lineage_decisions(self):
        graph = RequirementGraph()
        graph.add(
            Requirement(
                key="region",
                target_field="region",
                target_type="string",
                label="Region",
                question="Region?",
            )
        )

        violations = ContractValidator(_contract()).validate_graph(graph)
        assert {violation.code for violation in violations} == {
            "CONTRACT_REQUIRED_DECISION_NOT_IN_GRAPH"
        }

    def test_required_artifact_missing_fails(self, tmp_path: Path):
        violations = ContractValidator(_contract()).validate_artifacts(tmp_path)
        assert [violation.message for violation in violations] == ["Missing required file: main.tf"]
        assert {violation.code for violation in violations} == {
            "CONTRACT_REQUIRED_ARTIFACT_MISSING"
        }

    def test_optional_artifact_is_not_required(self, tmp_path: Path):
        (tmp_path / "main.tf").write_text("")

        violations = ContractValidator(_contract()).validate_artifacts(tmp_path)
        assert violations == []

    def test_required_path_missing_fails(self, tmp_path: Path):
        (tmp_path / "config.yaml").write_text("region: eu-central-1\n")

        violations = ContractValidator(_yaml_contract()).validate_artifacts(tmp_path)

        assert [violation.message for violation in violations] == [
            "config.yaml missing required path: accounts[]",
            "config.yaml missing required path: accounts[].name",
        ]
        assert {violation.code for violation in violations} == {"CONTRACT_ARTIFACT_SCHEMA_INVALID"}

    def test_plain_required_path_allows_empty_collection(self, tmp_path: Path):
        contract = TargetContract(
            name="empty-ok",
            kind="yaml-config",
            source_url="https://example.com/config",
            artifacts=[
                ArtifactContract(
                    name="config.yaml",
                    required_paths=["accounts", "metadata"],
                ),
            ],
            required_decisions=["region"],
        )
        (tmp_path / "config.yaml").write_text("accounts: []\nmetadata: {}\n")

        violations = ContractValidator(contract).validate_artifacts(tmp_path)

        assert violations == []

    def test_list_item_required_path_missing_fails(self, tmp_path: Path):
        (tmp_path / "config.yaml").write_text("region: eu-central-1\naccounts:\n  - id: 123\n")

        violations = ContractValidator(_yaml_contract()).validate_artifacts(tmp_path)

        assert [violation.message for violation in violations] == [
            "config.yaml missing required path: accounts[].name"
        ]

    def test_asserted_value_mismatch_fails(self, tmp_path: Path):
        (tmp_path / "config.yaml").write_text("region: us-east-1\naccounts:\n  - name: Prod\n")

        violations = ContractValidator(_yaml_contract()).validate_artifacts(tmp_path)

        assert [violation.message for violation in violations] == [
            "config.yaml expected region == 'eu-central-1'"
        ]
        assert {violation.code for violation in violations} == {
            "CONTRACT_ARTIFACT_ASSERTION_FAILED"
        }

    def test_list_item_assertion_uses_all_resolved_values(self, tmp_path: Path):
        contract = TargetContract(
            name="dns-flags",
            kind="yaml-config",
            source_url="https://example.com/config",
            artifacts=[
                ArtifactContract(
                    name="config.yaml",
                    value_assertions=[
                        ArtifactValueAssertion(path="vpcs[].enableDnsSupport", equals=True),
                    ],
                )
            ],
            required_decisions=["region"],
        )
        (tmp_path / "config.yaml").write_text(
            "vpcs:\n  - enableDnsSupport: true\n  - enableDnsSupport: false\n"
        )

        violations = ContractValidator(contract).validate_artifacts(tmp_path)

        assert [violation.message for violation in violations] == [
            "config.yaml expected vpcs[].enableDnsSupport == True"
        ]

    def test_invalid_yaml_artifact_fails(self, tmp_path: Path):
        (tmp_path / "config.yaml").write_text("region: [unterminated\n")

        violations = ContractValidator(_yaml_contract()).validate_artifacts(tmp_path)

        assert len(violations) == 1
        assert violations[0].code == "CONTRACT_ARTIFACT_SCHEMA_INVALID"
        assert "config.yaml is not valid YAML" in violations[0].message

    def test_lineage_path_missing_fails(self, tmp_path: Path):
        (tmp_path / "config.yaml").write_text("region: eu-central-1\naccounts:\n  - name: Prod\n")
        contract = _yaml_contract()
        contract.lineage.append(
            DecisionLineage(
                decision="missing",
                artifact="config.yaml",
                path="metadata.owner",
            )
        )

        violations = ContractValidator(contract).validate_artifacts(tmp_path)

        assert [violation.message for violation in violations] == [
            "Lineage path missing for decision 'missing': config.yaml:metadata.owner"
        ]
        assert {violation.code for violation in violations} == {"CONTRACT_LINEAGE_PATH_MISSING"}

    def test_blocked_assessment_contract_validates_safe_artifacts(self, tmp_path: Path):
        (tmp_path / "decision-report.yaml").write_text(
            """pattern: aws-lza
handoffReadiness:
  handoffAllowed: false
  status: blocked
  summary: Cannot hand off yet.
  blockers:
    - code: EXAMPLE
      message: blocked
  missingDecisions: []
  conflictingDecisions: []
  safeHandoffPath:
    - Fix blockers.
"""
        )
        (tmp_path / "llm-trace-summary.yaml").write_text(
            """pattern: aws-lza
provider: none
model: none
callCount: 0
markdownDecisions: {}
markdownContradictions: []
rawLlmDecisions: {}
acceptedDecisions: {}
appliedDecisions:
  markdown: []
  llm: []
  signals: []
  defaults: []
signalDecisions: {}
gaps:
  resolved: []
  blocking: []
contradictions:
  blocking: []
handoffReadiness:
  handoffAllowed: false
  status: blocked
  blockerCount: 1
  blockingGapCount: 0
  blockingContradictionCount: 0
rawEvidence:
  path: not-requested
  status: not-requested
"""
        )
        (tmp_path / "model-benchmark.yaml").write_text(
            """schemaVersion: intent-engine/model-benchmark/v1
pattern: aws-lza
run:
  mode: deterministic
  provider: none
  model: none
  callCount: 0
readiness:
  status: blocked
  handoffAllowed: false
  blockerCount: 1
latency:
  totalMs: 0.0
  averageMs: 0.0
  maxMs: 0.0
tokens:
  status: not-reported
  promptTokens: 0
  completionTokens: 0
  totalTokens: 0
quality:
  acceptedDecisionCount: 0
  rawLlmDecisionCount: 0
  rawLlmSignalDecisionCount: 0
  appliedDecisionCounts: {}
  resolvedGapCount: 0
  blockingGapCount: 0
  rawGapCount: 0
  blockingContradictionCount: 0
  rawContradictionCount: 0
  parseErrorCount: 0
cost:
  status: not-estimated
rawEvidence:
  path: not-requested
  status: not-requested
boundary: Trace artifact only.
calls: []
"""
        )
        (tmp_path / "missing-inputs.yaml").write_text(
            """schemaVersion: intent-engine/missing-inputs/v1
pattern: aws-lza
status: blocked
questionCount: 0
questions: []
"""
        )

        assert ContractValidator(BLOCKED_ASSESSMENT_CONTRACT).validate_artifacts(tmp_path) == []

    def test_handoff_plan_contract_validates_plan_shape(self, tmp_path: Path):
        (tmp_path / "handoff-plan.yaml").write_text(
            """pattern: cloudformation-parameters
boundary: Handoff only.
allowedNextAction: Pass reviewed artifacts to the existing toolchain.
readiness:
  status: ready
  handoffAllowed: true
targetContracts:
  - name: cloudformation-parameters-handoff
    kind: cloudformation-parameters
    requiredArtifacts:
      - cloudformation-parameters.yaml
steps:
  - id: resolve-decisions
    title: Confirm captured decisions
    owner: architecture-owner
    dependsOn: []
    manualGate: true
    rollback: Re-run compile.
manualGates:
  - No blockers remain.
rollback:
  - Use the previous approved handoff.
"""
        )

        assert ContractValidator(HANDOFF_PLAN_CONTRACT).validate_artifacts(tmp_path) == []

    def test_handoff_plan_contract_catches_missing_owner(self, tmp_path: Path):
        (tmp_path / "handoff-plan.yaml").write_text(
            """pattern: cloudformation-parameters
boundary: Handoff only.
allowedNextAction: Pass reviewed artifacts to the existing toolchain.
readiness:
  status: ready
  handoffAllowed: true
targetContracts:
  - name: cloudformation-parameters-handoff
    kind: cloudformation-parameters
    requiredArtifacts:
      - cloudformation-parameters.yaml
steps:
  - id: resolve-decisions
    title: Confirm captured decisions
    dependsOn: []
    manualGate: true
    rollback: Re-run compile.
manualGates:
  - No blockers remain.
rollback:
  - Use the previous approved handoff.
"""
        )

        violations = ContractValidator(HANDOFF_PLAN_CONTRACT).validate_artifacts(tmp_path)

        assert [violation.message for violation in violations] == [
            "handoff-plan.yaml missing required path: steps[].owner"
        ]

    def test_context_manifest_contract_validates_manifest_shape(self, tmp_path: Path):
        (tmp_path / "context-manifest.yaml").write_text(
            """schemaVersion: intent-engine/context-manifest/v1
pattern: cloudformation-parameters
boundary: Context is code-owned.
contextInventory:
  pattern:
    name: cloudformation-parameters
    description: Parameter handoff
    intentModel: CloudFormationParametersIntent
  promptContext:
    present: true
    sha256: abc123
    wordCount: 20
    text: This pattern captures approved parameter handoff context.
  requirementGraph:
    nodeCount: 1
    edgeCount: 0
    requirements:
      - key: region
        category: cloudformation
        targetField: region
  targetContracts: []
  samples: []
  targetCapabilities: []
runtimeContext:
  acceptedDecisionCount: 1
  moduleInputCount: 0
  unsupportedAskFactCount: 0
  llm:
    provider: none
    model: none
    callCount: 0
outputs:
  expectedArtifacts:
    - context-manifest.yaml
guardrails:
  - LLM output is not authoritative.
"""
        )

        assert ContractValidator(CONTEXT_MANIFEST_CONTRACT).validate_artifacts(tmp_path) == []

    def test_context_manifest_contract_requires_present_prompt_context(self, tmp_path: Path):
        (tmp_path / "context-manifest.yaml").write_text(
            """schemaVersion: intent-engine/context-manifest/v1
pattern: cloudformation-parameters
boundary: Context is code-owned.
contextInventory:
  pattern:
    name: cloudformation-parameters
    description: Parameter handoff
    intentModel: CloudFormationParametersIntent
  promptContext:
    present: false
    sha256: abc123
    wordCount: 0
    text: missing prompt context
  requirementGraph:
    nodeCount: 1
    edgeCount: 0
    requirements:
      - key: region
        category: cloudformation
        targetField: region
  targetContracts: []
  samples: []
  targetCapabilities: []
runtimeContext:
  acceptedDecisionCount: 1
  moduleInputCount: 0
  unsupportedAskFactCount: 0
  llm:
    provider: none
    model: none
    callCount: 0
outputs:
  expectedArtifacts:
    - context-manifest.yaml
guardrails:
  - LLM output is not authoritative.
"""
        )

        violations = ContractValidator(CONTEXT_MANIFEST_CONTRACT).validate_artifacts(tmp_path)

        assert [violation.message for violation in violations] == [
            "context-manifest.yaml expected contextInventory.promptContext.present == True"
        ]


class TestPatternOwnedContracts:
    def test_core_contracts_are_validated_contracts(self):
        assert {contract.name for contract in CORE_CONTRACTS} == {
            "blocked-assessment-artifacts",
            "generic-handoff-plan",
            "generic-context-manifest",
            "generic-plan-ready-bundle",
        }
        for contract in CORE_CONTRACTS:
            assert ContractValidator(contract).validate_contract() == []

    def test_pattern_registry_finds_builtin_contracts(self):
        contract = GLOBAL_REGISTRY.contract("aws-lza-sample-configuration")

        assert contract.kind == "aws-lza-sample-configuration"
