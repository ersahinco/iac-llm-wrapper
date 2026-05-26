"""Tests for the fail-closed validation system."""

from __future__ import annotations

from dataclasses import dataclass

from intent_engine.core.requirements import Requirement, RequirementGraph
from intent_engine.core.validator import Violation, validate, validate_graph


@dataclass
class SimpleIntent:
    region: str = ""
    topology: str = ""


class TestValidateGraph:
    def test_empty_graph_no_violations(self):
        g = RequirementGraph()
        assert validate_graph(g) == []

    def test_required_but_missing_triggers_violation(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="region",
                label="Region",
                question="Which region?",
                required_when_applicable=True,
                default="eu-central-1",
            )
        )
        # Not decided, not defaulted — should trigger
        violations = validate_graph(g)
        assert len(violations) == 1
        assert violations[0].code == "REGION_REQUIRED"

    def test_decided_requirement_passes(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="region",
                label="Region",
                question="Which region?",
                required_when_applicable=True,
            )
        )
        g.decide("region", "us-west-2")
        assert validate_graph(g) == []

    def test_defaulted_requirement_passes(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="region",
                label="Region",
                question="Which region?",
                required_when_applicable=True,
                default="eu-central-1",
            )
        )
        g.apply_default("region")
        assert validate_graph(g) == []

    def test_not_required_when_applicable_skips(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="region",
                label="Region",
                question="Which region?",
                required_when_applicable=False,
            )
        )
        assert validate_graph(g) == []

    def test_blocked_requirement_skips(self):
        g = RequirementGraph()
        g.add(Requirement(key="topology", label="Topology", question="?", options=["hub-spoke"]))
        g.add(
            Requirement(
                key="network_account",
                label="Network Account",
                question="?",
                required_when_applicable=True,
                applies_if={"topology": ["hub-spoke"]},
            )
        )
        g.decide("topology", "single-vpc")
        assert validate_graph(g) == []

    def test_not_applicable_skips(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="topology",
                label="Topology",
                question="?",
                options=["hub-spoke", "single-vpc"],
            )
        )
        g.add(
            Requirement(
                key="hub_cidr",
                label="Hub CIDR",
                question="?",
                required_when_applicable=True,
                applies_if={"topology": ["hub-spoke"]},
            )
        )
        g.decide("topology", "single-vpc")
        assert validate_graph(g) == []

    def test_custom_violation_code(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="region",
                label="Region",
                question="?",
                required_when_applicable=True,
                violation_code="CUSTOM_MISSING",
            )
        )
        violations = validate_graph(g)
        assert violations[0].code == "CUSTOM_MISSING"


class TestValidate:
    def test_basic_validate_no_graph(self):
        intent = SimpleIntent(region="eu-west-1")
        assert validate(intent) == []

    def test_validate_with_graph(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="region",
                label="Region",
                question="?",
                required_when_applicable=True,
            )
        )
        intent = SimpleIntent()
        violations = validate(intent, graph=g)
        assert len(violations) == 1

    def test_validate_with_extra_validator(self):
        def extra_check(intent, graph=None):
            if not intent.region:
                return [Violation(code="NO_REGION", message="Missing region")]
            return []

        intent = SimpleIntent()
        violations = validate(intent, extra_validators=[extra_check])
        assert len(violations) == 1
        assert violations[0].code == "NO_REGION"

    def test_extra_validator_passes_when_ok(self):
        def extra_check(intent, graph=None):
            return []

        intent = SimpleIntent(region="eu-west-1")
        assert validate(intent, extra_validators=[extra_check]) == []
