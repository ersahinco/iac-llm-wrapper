"""Pattern quality checks used by CLI and contributor tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from .contracts import ContractValidator
from .patterns import Pattern
from .sample_config import GLOBAL_SAMPLE_REGISTRY


@dataclass(frozen=True)
class PatternCheckResult:
    pattern: str
    requirements: int
    contracts: int
    expected_artifacts: int
    samples: int
    violations: list[str]

    @property
    def passed(self) -> bool:
        return not self.violations


def check_pattern(
    pattern: Pattern,
    *,
    fixtures_root: Path = Path("fixtures"),
) -> PatternCheckResult:
    """Validate graph, contracts, sample fixtures, and artifact metadata."""

    violations: list[str] = []
    requirements = 0
    try:
        graph = pattern.create_graph()
    except Exception as exc:
        return PatternCheckResult(
            pattern=pattern.name,
            requirements=0,
            contracts=len(pattern.contracts),
            expected_artifacts=len(pattern.expected_artifacts()),
            samples=len(GLOBAL_SAMPLE_REGISTRY.find_by_pattern(pattern.name)),
            violations=[f"graph factory failed: {exc}"],
        )

    requirements = len(graph._requirements)
    if not graph._requirements:
        violations.append("graph has no requirements")
    try:
        cycle = nx.find_cycle(graph._graph)
    except nx.NetworkXNoCycle:
        cycle = []
    if cycle:
        violations.append(f"requirement graph has a cycle: {cycle}")

    for key, req in graph._requirements.items():
        if not req.label:
            violations.append(f"{key}: missing label")
        if not req.question:
            violations.append(f"{key}: missing question")
        if not req.target_field:
            violations.append(f"{key}: missing target field")
        for dep in req.depends_on:
            if dep not in graph._requirements:
                violations.append(f"{key}: unknown dependency {dep}")
        for dep in set(req.applies_if) | set(req.blocked_if):
            if dep not in graph._requirements:
                violations.append(f"{key}: unknown condition dependency {dep}")

    for contract_obj in pattern.contracts:
        validator = ContractValidator(contract_obj)
        violations.extend(
            f"{contract_obj.name}: {violation.message}"
            for violation in validator.validate_contract() + validator.validate_graph(graph)
        )

    expected_artifacts = pattern.expected_artifacts()
    for artifact in expected_artifacts:
        if not artifact:
            violations.append("expected artifact list contains an empty name")

    samples = GLOBAL_SAMPLE_REGISTRY.find_by_pattern(pattern.name)
    for sample in samples:
        if not sample.decisions:
            violations.append(f"{sample.name}: sample has no decisions")
        if sample.fixture_dir or (fixtures_root / sample.fixture_name).exists():
            fixture_dir = fixtures_root / sample.fixture_name
            if not fixture_dir.exists():
                violations.append(f"{sample.name}: missing fixture dir {fixture_dir}")

    return PatternCheckResult(
        pattern=pattern.name,
        requirements=requirements,
        contracts=len(pattern.contracts),
        expected_artifacts=len(expected_artifacts),
        samples=len(samples),
        violations=violations,
    )
