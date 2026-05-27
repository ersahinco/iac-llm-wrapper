"""Target contract validation tests."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from intent_engine.core.contracts import (
    ArtifactContract,
    ContractRegistry,
    ContractValidator,
    DecisionLineage,
    TargetContract,
)
from intent_engine.core.requirements import Requirement, RequirementGraph


class ExampleIntent(BaseModel):
    region: str = "eu-central-1"
    account: str = ""


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

    def test_missing_required_decision_fails(self):
        violations = ContractValidator(_contract()).validate_intent(ExampleIntent())
        assert {violation.code for violation in violations} == {"ACCOUNT_REQUIRED"}

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


class TestContractRegistry:
    def test_register_and_get_contract(self):
        registry = ContractRegistry()
        contract = _contract()

        registry.register(contract)

        assert registry.get("example") is contract
        assert registry.list() == ["example"]

    def test_invalid_contract_rejected(self):
        registry = ContractRegistry()
        contract = TargetContract(
            name="bad",
            kind="test",
            source_url="https://example.com",
            artifacts=[],
            required_decisions=[],
        )

        try:
            registry.register(contract)
        except ValueError as exc:
            assert "Invalid contract 'bad'" in str(exc)
        else:
            raise AssertionError("invalid contract was accepted")
