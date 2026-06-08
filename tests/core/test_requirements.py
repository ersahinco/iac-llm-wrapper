"""Tests for requirement graph and interview engine (generic core)."""

from __future__ import annotations

from intent_engine.core.requirements import (
    Requirement,
    RequirementGraph,
    RequirementStatus,
    evaluate_expression,
    validate_expression,
)


class TestRequirementGraph:
    def test_add_and_decide(self):
        g = RequirementGraph()
        g.add(Requirement(key="region", label="Region", question="Which region?"))
        g.decide("region", "eu-central-1")
        assert g.get("region") == "eu-central-1"
        assert g.status("region") == RequirementStatus.DECIDED

    def test_default_application(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="region",
                label="Region",
                question="Which region?",
                default="eu-central-1",
            )
        )
        g.apply_default("region")
        assert g.get("region") == "eu-central-1"
        assert g.status("region") == RequirementStatus.DEFAULTED

    def test_dependency_blocking(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="topology",
                label="Topology",
                question="Topology?",
                options=["hub-spoke", "single-vpc"],
            )
        )
        g.add(
            Requirement(
                key="network_acct",
                label="Network Account",
                question="Network account name?",
                depends_on=["topology"],
                applies_if={"topology": ["hub-spoke"]},
            )
        )
        g.decide("topology", "single-vpc")
        assert not g.is_applicable("network_acct")
        assert "network_acct" not in g.pending()

    def test_expression_applies_when_supports_equals_and_contains(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="topology",
                label="Topology",
                question="Topology?",
                default="hub-spoke",
            )
        )
        g.add(
            Requirement(
                key="organizational_units",
                label="OUs",
                question="OUs?",
                target_type="string_list",
                default="Security, Infrastructure",
            )
        )
        g.add(
            Requirement(
                key="network_account",
                label="Network Account",
                question="Network account?",
                applies_when={
                    "all": [
                        {"equals": {"decision": "topology", "value": "hub-spoke"}},
                        {
                            "contains": {
                                "decision": "organizational_units",
                                "value": "Infrastructure",
                            }
                        },
                    ]
                },
            )
        )

        g.apply_defaults_for_remaining()

        assert g.is_applicable("network_account")

    def test_expression_blocked_when_sets_status(self):
        g = RequirementGraph()
        g.add(Requirement(key="mode", label="Mode", question="Mode?"))
        g.add(
            Requirement(
                key="unsafe_action",
                label="Unsafe Action",
                question="Unsafe?",
                blocked_when={"equals": {"decision": "mode", "value": "blocked"}},
            )
        )

        g.decide("mode", "blocked")

        assert g.status("unsafe_action") == RequirementStatus.BLOCKED
        assert "mode == blocked" in (g.is_blocked_reason("unsafe_action") or "")

    def test_expression_malformed_compounds_fail_closed(self):
        assert evaluate_expression({"all": []}, {}) is False
        assert evaluate_expression({"all": ["bad"]}, {}) is False
        assert (
            evaluate_expression(
                {
                    "equals": {"decision": "mode", "value": "ready"},
                    "bogus": {"decision": "mode"},
                },
                {"mode": "ready"},
            )
            is False
        )
        assert validate_expression({"all": []}) == ["expression.all: must be a non-empty list"]
        assert validate_expression({"bogus": {"decision": "x"}}) == [
            "expression: unsupported operator bogus",
            "expression: expression must define exactly one operator",
        ]

    def test_dependency_readiness(self):
        g = RequirementGraph()
        g.add(Requirement(key="a", label="A", question="A?"))
        g.add(Requirement(key="b", label="B", question="B?", depends_on=["a"]))
        assert not g.is_ready("b")
        g.decide("a", "value")
        assert g.is_ready("b")

    def test_cascade_values(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="topology",
                label="Topology",
                question="Topology?",
                cascade={"network_topo": "{value}"},
            )
        )
        g.add(
            Requirement(
                key="network_topo",
                label="Network Topo",
                question="Network topo?",
            )
        )
        g.decide("topology", "hub-spoke")
        assert g.get("network_topo") == "hub-spoke"

    def test_pending_order_respects_dependencies(self):
        g = RequirementGraph()
        g.add(Requirement(key="a", label="A", question="A?"))
        g.add(Requirement(key="b", label="B", question="B?", depends_on=["a"]))
        g.add(Requirement(key="c", label="C", question="C?", depends_on=["b"]))
        pending = g.pending()
        assert pending == ["a"]
        g.decide("a", "val")
        pending = g.pending()
        assert pending == ["b"]

    def test_all_decided(self):
        g = RequirementGraph()
        g.add(Requirement(key="a", label="A", question="A?"))
        g.add(Requirement(key="b", label="B", question="B?", default="x"))
        g.decide("a", "val")
        assert not g.all_decided()
        g.apply_default("b")
        assert g.all_decided()

    def test_skip_makes_non_applicable(self):
        g = RequirementGraph()
        g.add(Requirement(key="a", label="A", question="A?"))
        g.add(Requirement(key="b", label="B", question="B?", depends_on=["a"]))
        g.decide("a", "val")
        g.skip("b")
        assert g.status("b") == RequirementStatus.SKIPPED

    def test_apply_defaults_for_remaining(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="region",
                label="Region",
                question="Which region?",
                default="eu-central-1",
            )
        )
        g.add(
            Requirement(
                key="topology",
                label="Topology",
                question="Topology?",
                options=["hub-spoke", "single-vpc"],
                default="single-vpc",
            )
        )
        g.apply_defaults_for_remaining()
        assert g.get("region") == "eu-central-1"
        assert g.get("topology") == "single-vpc"
        assert g.all_decided()

    def test_decisions_returns_all_decided(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="region",
                label="Region",
                question="Which region?",
                default="eu-central-1",
            )
        )
        g.decide("region", "us-west-2")
        d = g.decisions()
        assert d["region"] == "us-west-2"

    def test_blocked_status_resets_when_condition_changes(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="mode",
                label="Mode",
                question="Mode?",
                options=["safe", "dangerous"],
            )
        )
        g.add(
            Requirement(
                key="feature",
                label="Feature",
                question="Feature?",
                blocked_if={"mode": ["dangerous"]},
            )
        )
        g.decide("mode", "dangerous")
        assert g.status("feature") == RequirementStatus.BLOCKED
        g.decide("mode", "safe")
        assert g.status("feature") == RequirementStatus.PENDING

    def test_multiple_cascades_from_one_decision(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="trigger",
                label="Trigger",
                question="Trigger?",
                cascade={"a": "val_a", "b": "val_b"},
            )
        )
        g.add(Requirement(key="a", label="A", question="A?"))
        g.add(Requirement(key="b", label="B", question="B?"))
        g.decide("trigger", "fired")
        assert g.get("a") == "val_a"
        assert g.get("b") == "val_b"

    def test_cascade_overwrites_prior_decision(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="topology",
                label="Topology",
                question="Topology?",
                cascade={"net_topo": "{value}"},
            )
        )
        g.add(
            Requirement(
                key="net_topo",
                label="Net Topo",
                question="Net topo?",
            )
        )
        g.decide("net_topo", "manual")
        g.decide("topology", "hub-spoke")
        assert g.get("net_topo") == "hub-spoke"

    def test_decide_unknown_key_raises(self):
        g = RequirementGraph()
        import pytest

        with pytest.raises(KeyError):
            g.decide("nonexistent", "value")

    def test_apply_default_without_default_raises(self):
        g = RequirementGraph()
        g.add(Requirement(key="x", label="X", question="X?"))
        import pytest

        with pytest.raises(ValueError):
            g.apply_default("x")

    def test_apply_decisions_serializes_structured_prefill_values(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="regions",
                label="Regions",
                question="Regions?",
                target_type="string_list",
            )
        )
        g.add(
            Requirement(
                key="enabled",
                label="Enabled",
                question="Enabled?",
                target_type="bool",
            )
        )

        applied = g.apply_decisions({"regions": ["eu-central-1", "eu-west-1"], "enabled": True})

        assert applied == ["regions", "enabled"]
        assert g.get("regions") == "eu-central-1,eu-west-1"
        assert g.get("enabled") == "true"

    def test_apply_decisions_respects_applies_if_order(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="network_account",
                label="Network Account",
                question="Network account?",
                applies_if={"topology": ["hub-spoke"]},
            )
        )
        g.add(
            Requirement(
                key="topology",
                label="Topology",
                question="Topology?",
                options=["hub-spoke", "single-vpc"],
            )
        )

        applied = g.apply_decisions({"network_account": "Network", "topology": "hub-spoke"})

        assert applied == ["topology", "network_account"]
        assert g.get("network_account") == "Network"

    def test_typed_decisions_restores_structured_values(self):
        g = RequirementGraph()
        g.add(
            Requirement(
                key="regions",
                label="Regions",
                question="Regions?",
                target_type="string_list",
            )
        )
        g.add(
            Requirement(
                key="enabled",
                label="Enabled",
                question="Enabled?",
                target_type="bool",
            )
        )

        g.apply_decisions({"regions": ["eu-central-1", "eu-west-1"], "enabled": True})

        assert g.typed_decisions() == {
            "regions": ["eu-central-1", "eu-west-1"],
            "enabled": True,
        }
