"""Target contracts and validation helpers.

Contracts describe downstream handoff targets such as AWS LZA configs, module
inputs, or parameter files. They define shape; the requirement graph still owns
branching and decision order.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .validator import Violation


class ArtifactContract(BaseModel):
    """Artifact expected by a target contract."""

    name: str
    required: bool = True
    description: str = ""
    required_paths: list[str] = Field(default_factory=list, serialization_alias="requiredPaths")
    value_assertions: list[ArtifactValueAssertion] = Field(
        default_factory=list,
        serialization_alias="valueAssertions",
    )


class ArtifactValueAssertion(BaseModel):
    """Literal value assertions for generated artifact paths."""

    path: str
    equals: Any | None = None
    one_of: list[Any] = Field(default_factory=list, serialization_alias="oneOf")


class DecisionLineage(BaseModel):
    """Mapping from captured decision to target artifact path."""

    decision: str
    artifact: str
    path: str


class TargetContract(BaseModel):
    """External target contract that drives questions, validation, and artifacts."""

    name: str
    kind: str
    source_url: str
    artifacts: list[ArtifactContract] = Field(default_factory=list)
    required_decisions: list[str] = Field(default_factory=list)
    lineage: list[DecisionLineage] = Field(default_factory=list)

    @property
    def required_artifacts(self) -> list[str]:
        return [artifact.name for artifact in self.artifacts if artifact.required]

    @property
    def optional_artifacts(self) -> list[str]:
        return [artifact.name for artifact in self.artifacts if not artifact.required]


class ContractValidator:
    """Validate contract definitions, decisions, and generated artifacts."""

    def __init__(self, contract: TargetContract) -> None:
        self.contract = contract

    def validate_contract(self) -> list[Violation]:
        violations: list[Violation] = []
        known_artifacts = {artifact.name for artifact in self.contract.artifacts}
        known_decisions = set(self.contract.required_decisions)
        for artifact in self.contract.artifacts:
            for assertion in artifact.value_assertions:
                if assertion.equals is None and not assertion.one_of:
                    violations.append(
                        Violation(
                            code="CONTRACT_ASSERTION_RULE_REQUIRED",
                            message=(
                                f"Artifact assertion for '{artifact.name}:{assertion.path}' "
                                "must define equals or oneOf."
                            ),
                        )
                    )
                if assertion.equals is not None and assertion.one_of:
                    violations.append(
                        Violation(
                            code="CONTRACT_ASSERTION_AMBIGUOUS",
                            message=(
                                f"Artifact assertion for '{artifact.name}:{assertion.path}' "
                                "cannot define both equals and oneOf."
                            ),
                        )
                    )
        for item in self.contract.lineage:
            if item.artifact not in known_artifacts:
                violations.append(
                    Violation(
                        code="CONTRACT_LINEAGE_ARTIFACT_UNKNOWN",
                        message=(
                            f"Lineage for decision '{item.decision}' references unknown "
                            f"artifact '{item.artifact}'."
                        ),
                    )
                )
            known_decisions.add(item.decision)
        if not known_artifacts:
            violations.append(
                Violation(
                    code="CONTRACT_ARTIFACTS_REQUIRED",
                    message=f"Contract '{self.contract.name}' must define at least one artifact.",
                )
            )
        if not known_decisions:
            violations.append(
                Violation(
                    code="CONTRACT_DECISIONS_REQUIRED",
                    message=f"Contract '{self.contract.name}' must define at least one decision.",
                )
            )
        return violations

    def validate_intent(self, intent: Any) -> list[Violation]:
        violations: list[Violation] = []
        for decision in self.contract.required_decisions:
            value = self._get_dotted(intent, decision)
            if value in (None, "", [], {}):
                violations.append(
                    Violation(
                        code=f"{decision.upper()}_REQUIRED",
                        message=(
                            f"Contract '{self.contract.name}' requires decision '{decision}'."
                        ),
                    )
                )
        return violations

    def validate_graph(self, graph: Any) -> list[Violation]:
        violations: list[Violation] = []
        requirements = getattr(graph, "_requirements", {})
        for decision in self.contract.required_decisions:
            if decision not in requirements:
                violations.append(
                    Violation(
                        code="CONTRACT_REQUIRED_DECISION_NOT_IN_GRAPH",
                        message=(
                            f"Contract '{self.contract.name}' requires decision "
                            f"'{decision}', but graph has no matching requirement."
                        ),
                    )
                )
        for item in self.contract.lineage:
            if item.decision not in requirements:
                violations.append(
                    Violation(
                        code="CONTRACT_LINEAGE_DECISION_NOT_IN_GRAPH",
                        message=(
                            f"Lineage decision '{item.decision}' for contract "
                            f"'{self.contract.name}' has no matching graph requirement."
                        ),
                    )
                )
        return violations

    def validate_artifacts(self, input_dir: Path) -> list[Violation]:
        violations: list[Violation] = []
        schema_invalid_artifacts: set[str] = set()
        data_by_artifact: dict[str, dict[str, Any]] = {}
        for artifact in self.contract.artifacts:
            if not artifact.required:
                continue
            artifact_path = input_dir / artifact.name
            if not artifact_path.exists():
                violations.append(
                    Violation(
                        code="CONTRACT_REQUIRED_ARTIFACT_MISSING",
                        message=f"Missing required file: {artifact.name}",
                    )
                )
                continue
            if not artifact.required_paths and not artifact.value_assertions:
                data_by_artifact[artifact.name] = {}
                continue
            data, load_violations = self._load_yaml_mapping(artifact.name, artifact_path)
            if load_violations:
                schema_invalid_artifacts.add(artifact.name)
                violations.extend(load_violations)
                continue
            data_by_artifact[artifact.name] = data
            shape_violations = self._validate_artifact_shape(artifact, data)
            if shape_violations:
                schema_invalid_artifacts.add(artifact.name)
            violations.extend(shape_violations)
            assertion_violations = self._validate_artifact_assertions(artifact, data)
            if assertion_violations:
                schema_invalid_artifacts.add(artifact.name)
            violations.extend(assertion_violations)
        violations.extend(self._validate_lineage_paths(data_by_artifact, schema_invalid_artifacts))
        return violations

    def _validate_artifact_shape(
        self,
        artifact: ArtifactContract,
        data: dict[str, Any],
    ) -> list[Violation]:
        if not artifact.required_paths:
            return []

        shape_violations: list[Violation] = []
        for path in artifact.required_paths:
            if not self._path_exists(data, path):
                shape_violations.append(
                    Violation(
                        code="CONTRACT_ARTIFACT_SCHEMA_INVALID",
                        message=f"{artifact.name} missing required path: {path}",
                    )
                )
        return shape_violations

    def _validate_artifact_assertions(
        self,
        artifact: ArtifactContract,
        data: dict[str, Any],
    ) -> list[Violation]:
        if not artifact.value_assertions:
            return []

        violations: list[Violation] = []
        for assertion in artifact.value_assertions:
            values = self._path_values(data, assertion.path)
            if not values:
                violations.append(
                    Violation(
                        code="CONTRACT_ARTIFACT_ASSERTION_FAILED",
                        message=f"{artifact.name} missing asserted path: {assertion.path}",
                    )
                )
                continue
            if assertion.equals is not None:
                expected = self._normalize_value(assertion.equals)
                if not all(self._normalize_value(value) == expected for value in values):
                    violations.append(
                        Violation(
                            code="CONTRACT_ARTIFACT_ASSERTION_FAILED",
                            message=(
                                f"{artifact.name} expected {assertion.path} == {assertion.equals!r}"
                            ),
                        )
                    )
                continue
            allowed = {self._normalize_value(value) for value in assertion.one_of}
            if not all(self._normalize_value(value) in allowed for value in values):
                violations.append(
                    Violation(
                        code="CONTRACT_ARTIFACT_ASSERTION_FAILED",
                        message=(
                            f"{artifact.name} expected {assertion.path} in {assertion.one_of!r}"
                        ),
                    )
                )
        return violations

    def _validate_lineage_paths(
        self,
        data_by_artifact: dict[str, dict[str, Any]],
        schema_invalid_artifacts: set[str],
    ) -> list[Violation]:
        artifacts = {artifact.name: artifact for artifact in self.contract.artifacts}
        violations: list[Violation] = []

        for item in self.contract.lineage:
            artifact = artifacts.get(item.artifact)
            if (
                artifact is None
                or not artifact.required
                or not artifact.required_paths
                or item.artifact in schema_invalid_artifacts
            ):
                continue
            if item.artifact not in data_by_artifact:
                continue
            if not self._path_exists(data_by_artifact[item.artifact], item.path):
                violations.append(
                    Violation(
                        code="CONTRACT_LINEAGE_PATH_MISSING",
                        message=(
                            f"Lineage path missing for decision '{item.decision}': "
                            f"{item.artifact}:{item.path}"
                        ),
                    )
                )
        return violations

    def _load_yaml_mapping(
        self,
        artifact_name: str,
        artifact_path: Path,
    ) -> tuple[dict[str, Any], list[Violation]]:
        import ruamel.yaml

        yaml = ruamel.yaml.YAML(typ="safe")
        try:
            data = yaml.load(artifact_path.read_text()) or {}
        except Exception as exc:  # noqa: BLE001 - include parser-specific YAML errors.
            return {}, [
                Violation(
                    code="CONTRACT_ARTIFACT_SCHEMA_INVALID",
                    message=f"{artifact_name} is not valid YAML: {exc}",
                )
            ]

        if not isinstance(data, dict):
            return {}, [
                Violation(
                    code="CONTRACT_ARTIFACT_SCHEMA_INVALID",
                    message=f"{artifact_name} must contain a YAML mapping.",
                )
            ]

        return data, []

    def _path_exists(self, data: Any, path: str) -> bool:
        return self._path_parts_exist(data, path.split("."))

    def _path_values(self, data: Any, path: str) -> list[Any]:
        return self._path_part_values(data, path.split("."))

    def _path_parts_exist(self, current: Any, parts: list[str]) -> bool:
        if not parts:
            # Plain dotted paths model schema presence. Use the [] suffix when a
            # contract needs to require a non-empty list value.
            return current not in (None, "")

        part = parts[0]
        rest = parts[1:]
        if part.endswith("[]"):
            key = part[:-2]
            if not isinstance(current, dict) or key not in current:
                return False
            items = current[key]
            if not isinstance(items, list) or not items:
                return False
            if not rest:
                return True
            return all(self._path_parts_exist(item, rest) for item in items)

        if not isinstance(current, dict) or part not in current:
            return False
        return self._path_parts_exist(current[part], rest)

    def _path_part_values(self, current: Any, parts: list[str]) -> list[Any]:
        if not parts:
            return [current]

        part = parts[0]
        rest = parts[1:]
        if part.endswith("[]"):
            key = part[:-2]
            if not isinstance(current, dict) or key not in current:
                return []
            items = current[key]
            if not isinstance(items, list) or not items:
                return []
            if not rest:
                return list(items)
            values: list[Any] = []
            for item in items:
                values.extend(self._path_part_values(item, rest))
            return values

        if not isinstance(current, dict) or part not in current:
            return []
        return self._path_part_values(current[part], rest)

    def _normalize_value(self, value: Any) -> Any:
        if isinstance(value, bool):
            return value
        if isinstance(value, list):
            return tuple(self._normalize_value(item) for item in value)
        if isinstance(value, dict):
            return tuple(sorted((key, self._normalize_value(item)) for key, item in value.items()))
        if isinstance(value, str):
            normalized = value.strip()
            lowered = normalized.lower()
            if lowered == "true":
                return True
            if lowered == "false":
                return False
            return normalized
        return value

    def _get_dotted(self, obj: Any, dotted_path: str) -> Any:
        current = obj
        for part in dotted_path.split("."):
            if not hasattr(current, part):
                return None
            current = getattr(current, part)
        return current


class ContractRegistry:
    """Registry for reusable target contracts."""

    def __init__(self) -> None:
        self._contracts: dict[str, TargetContract] = {}

    def register(self, contract: TargetContract) -> None:
        violations = ContractValidator(contract).validate_contract()
        if violations:
            msg = "; ".join(f"{violation.code}: {violation.message}" for violation in violations)
            raise ValueError(f"Invalid contract '{contract.name}': {msg}")
        self._contracts[contract.name] = contract

    def get(self, name: str) -> TargetContract:
        if name not in self._contracts:
            available = ", ".join(sorted(self._contracts))
            raise KeyError(f"Unknown contract '{name}'. Available: {available}")
        return self._contracts[name]

    def list(self) -> list[str]:
        return sorted(self._contracts)


GLOBAL_CONTRACT_REGISTRY = ContractRegistry()


BLOCKED_ASSESSMENT_CONTRACT = TargetContract(
    name="blocked-assessment-artifacts",
    kind="intent-engine-diagnostic",
    source_url="intent-engine://contracts/blocked-assessment-artifacts/v1",
    required_decisions=["deploymentReadiness"],
    artifacts=[
        ArtifactContract(
            name="decision-report.yaml",
            description="Safe blocked-compile assessment with no deployable target config.",
            required_paths=[
                "pattern",
                "deploymentReadiness.deploymentAllowed",
                "deploymentReadiness.status",
                "deploymentReadiness.summary",
                "deploymentReadiness.blockers[]",
                "deploymentReadiness.blockers[].code",
                "deploymentReadiness.blockers[].message",
                "deploymentReadiness.missingDecisions",
                "deploymentReadiness.conflictingDecisions",
                "deploymentReadiness.safeHandoffPath[]",
            ],
            value_assertions=[
                ArtifactValueAssertion(
                    path="deploymentReadiness.deploymentAllowed",
                    equals=False,
                ),
                ArtifactValueAssertion(path="deploymentReadiness.status", equals="blocked"),
            ],
        ),
        ArtifactContract(
            name="llm-trace-summary.yaml",
            description="Lean extraction evidence summary for blocked compile diagnostics.",
            required_paths=[
                "pattern",
                "provider",
                "model",
                "callCount",
                "markdownDecisions",
                "markdownContradictions",
                "rawLlmDecisions",
                "acceptedDecisions",
                "appliedDecisions",
                "signalDecisions",
                "gaps.resolved",
                "gaps.blocking",
                "contradictions.blocking",
                "deploymentReadiness.deploymentAllowed",
                "deploymentReadiness.status",
                "deploymentReadiness.blockerCount",
                "deploymentReadiness.blockingGapCount",
                "deploymentReadiness.blockingContradictionCount",
                "rawEvidence.path",
                "rawEvidence.status",
            ],
            value_assertions=[
                ArtifactValueAssertion(
                    path="deploymentReadiness.deploymentAllowed",
                    equals=False,
                ),
                ArtifactValueAssertion(path="deploymentReadiness.status", equals="blocked"),
            ],
        ),
        ArtifactContract(
            name="model-benchmark.yaml",
            description="Lean model behavior rollup for blocked compile diagnostics.",
            required_paths=[
                "schemaVersion",
                "pattern",
                "run.mode",
                "run.provider",
                "run.model",
                "run.callCount",
                "readiness.status",
                "readiness.deploymentAllowed",
                "readiness.blockerCount",
                "latency.totalMs",
                "latency.averageMs",
                "latency.maxMs",
                "tokens.status",
                "tokens.promptTokens",
                "tokens.completionTokens",
                "tokens.totalTokens",
                "quality.acceptedDecisionCount",
                "quality.rawLlmDecisionCount",
                "quality.rawLlmSignalDecisionCount",
                "quality.appliedDecisionCounts",
                "quality.resolvedGapCount",
                "quality.blockingGapCount",
                "quality.rawGapCount",
                "quality.blockingContradictionCount",
                "quality.rawContradictionCount",
                "quality.parseErrorCount",
                "cost.status",
                "rawEvidence.path",
                "rawEvidence.status",
                "boundary",
                "calls",
            ],
            value_assertions=[
                ArtifactValueAssertion(path="readiness.deploymentAllowed", equals=False),
                ArtifactValueAssertion(path="readiness.status", equals="blocked"),
            ],
        ),
    ],
)

HANDOFF_PLAN_CONTRACT = TargetContract(
    name="generic-handoff-plan",
    kind="intent-engine-handoff-plan",
    source_url="intent-engine://contracts/generic-handoff-plan/v1",
    required_decisions=["handoffPlan"],
    artifacts=[
        ArtifactContract(
            name="handoff-plan.yaml",
            description="Generic handoff plan with owners, ordering, gates, and rollback.",
            required_paths=[
                "pattern",
                "boundary",
                "allowedNextAction",
                "readiness.status",
                "readiness.deploymentAllowed",
                "targetContracts[]",
                "targetContracts[].name",
                "targetContracts[].kind",
                "targetContracts[].requiredArtifacts",
                "steps[]",
                "steps[].id",
                "steps[].title",
                "steps[].owner",
                "steps[].dependsOn",
                "steps[].manualGate",
                "steps[].rollback",
                "manualGates[]",
                "rollback[]",
            ],
        )
    ],
)

GLOBAL_CONTRACT_REGISTRY.register(BLOCKED_ASSESSMENT_CONTRACT)
GLOBAL_CONTRACT_REGISTRY.register(HANDOFF_PLAN_CONTRACT)
