"""Pattern quality checks used by CLI and contributor tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .contracts import ContractValidator
from .patterns import Pattern
from .requirements import expression_dependencies, validate_expression
from .sample_config import GLOBAL_SAMPLE_REGISTRY


@dataclass(frozen=True)
class PatternCheckResult:
    pattern: str
    requirements: int
    contracts: int
    expected_artifacts: int
    samples: int
    context_rules: int
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
            context_rules=0,
            violations=[f"graph factory failed: {exc}"],
        )

    requirements = len(graph._requirements)
    context_rules = 0
    if not pattern.description.strip():
        violations.append("pattern description is missing")
    context_rules += _check_prompt_context(pattern, violations)
    if not graph._requirements:
        violations.append("graph has no requirements")
    cycle = graph.cycle_edges()
    if cycle:
        violations.append(f"requirement graph has a cycle: {cycle}")

    for key, req in graph._requirements.items():
        if not req.label:
            violations.append(f"{key}: missing label")
        if not req.question:
            violations.append(f"{key}: missing question")
        if not req.category:
            violations.append(f"{key}: missing category")
        if not req.target_field:
            violations.append(f"{key}: missing target field")
        if (
            req.required_when_applicable
            and req.default is None
            and not req.options
            and (not req.violation_code or not req.violation_message)
        ):
            violations.append(
                f"{key}: required open requirement must define violation code and message"
            )
        for dep in req.depends_on:
            if dep not in graph._requirements:
                violations.append(f"{key}: unknown dependency {dep}")
        condition_dependencies = (
            set(req.applies_if)
            | set(req.blocked_if)
            | set(expression_dependencies(req.applies_when))
            | set(expression_dependencies(req.blocked_when))
        )
        for error in validate_expression(req.applies_when, path=f"{key}.applies_when"):
            violations.append(f"{key}: {error}")
        for error in validate_expression(req.blocked_when, path=f"{key}.blocked_when"):
            violations.append(f"{key}: {error}")
        for dep in condition_dependencies:
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
        context_rules=context_rules,
        violations=violations,
    )


def _check_prompt_context(pattern: Pattern, violations: list[str]) -> int:
    """Validate bounded LLM context so pattern behavior stays reviewable."""

    rules = 0
    prompt_context = " ".join(pattern.prompt_context.split())
    if not prompt_context:
        violations.append("prompt context is missing")
        return rules

    words = prompt_context.split()
    rules += 1
    if len(words) < 12:
        violations.append("prompt context is too short to define extraction scope")
    if len(words) > 140:
        violations.append("prompt context is too long; move details into graph/contracts")

    lowered = prompt_context.lower()
    extraction_terms = ("extract", "capture", "captures", "gather", "gathers")
    boundary_terms = (
        "approved",
        "contract",
        "do not",
        "existing",
        "handoff",
        "no ",
        "only",
    )
    rules += 1
    if not any(term in lowered for term in extraction_terms):
        violations.append("prompt context must say what the LLM extracts or captures")
    rules += 1
    if not any(term in lowered for term in boundary_terms):
        violations.append("prompt context must state a handoff, contract, or target boundary")

    return rules
