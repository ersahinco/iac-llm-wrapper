"""End-to-end and CLI integration tests."""

from __future__ import annotations

from pathlib import Path

import ruamel.yaml

from intent_engine.core.compiler import CompileError, compile_from_interview
from intent_engine.core.interview import InterviewEngine
from intent_engine.core.requirements import RequirementGraph, RequirementStatus
from intent_engine.patterns.lza.requirements import (
    build_lza_baseline_graph,
    build_workload_account_graph,
)


def _load_yaml(path: Path):
    yaml = ruamel.yaml.YAML(typ="safe")
    with open(path) as f:
        return yaml.load(f)


class TestInterviewToCompilePipeline:
    def test_full_hub_spoke_interview_compiles(self, tmp_path: Path):
        g = build_lza_baseline_graph()
        engine = InterviewEngine(g)
        engine.run_from_decisions(
            {
                "primary_region": "eu-central-1",
                "topology": "hub-spoke",
                "central_network_account": "Network",
                "cicd_mode": "private",
                "cicd_placement": "shared-vpc",
            }
        )
        engine.apply_defaults_for_remaining()

        output = tmp_path / "output"
        compile_from_interview(engine.graph.decisions(), output)

        assert (output / "organization-config.yaml").exists()
        assert (output / "accounts-config.yaml").exists()
        assert (output / "network-config.yaml").exists()
        net = _load_yaml(output / "network-config.yaml")["network"]
        assert net["topology"] == "hub-spoke"
        assert net["centralNetworkAccount"] == "Network"

    def test_single_vpc_interview_compiles(self, tmp_path: Path):
        g = build_lza_baseline_graph()
        engine = InterviewEngine(g)
        engine.run_from_decisions(
            {
                "primary_region": "us-west-2",
                "topology": "single-vpc",
            }
        )
        engine.apply_defaults_for_remaining()

        output = tmp_path / "output"
        compile_from_interview(engine.graph.decisions(), output)

        net = _load_yaml(output / "network-config.yaml")["network"]
        assert net["topology"] == "single-vpc"
        assert "centralNetworkAccount" not in net

    def test_interview_with_no_decisions_uses_all_defaults(self, tmp_path: Path):
        g = build_lza_baseline_graph()
        engine = InterviewEngine(g)
        engine.apply_defaults_for_remaining()

        output = tmp_path / "output"
        compile_from_interview(engine.graph.decisions(), output)

        report = _load_yaml(output / "decision-report.yaml")
        assert report["primaryRegion"] == "eu-central-1"
        assert report["topology"] == "single-vpc"

    def test_interview_missing_required_decision_fails(self, tmp_path: Path):
        g = build_lza_baseline_graph()
        engine = InterviewEngine(g)
        engine.run_from_decisions(
            {
                "topology": "hub-spoke",
            }
        )
        engine.apply_defaults_for_remaining()

        output = tmp_path / "output"
        try:
            compile_from_interview(engine.graph.decisions(), output)
            assert False, "Should have raised CompileError"
        except CompileError as e:
            codes = {v.code for v in e.violations}
            assert "HUB_SPOKE_NETWORK_ACCOUNT_REQUIRED" in codes

    def test_cascade_propagates_through_intent(self, tmp_path: Path):
        g = build_lza_baseline_graph()
        engine = InterviewEngine(g)
        engine.run_from_decisions(
            {
                "topology": "hub-spoke",
                "central_network_account": "Network",
            }
        )
        engine.apply_defaults_for_remaining()
        intent = engine.to_intent()

        assert intent.topology.value == "hub-spoke"
        assert intent.network.topology.value == "hub-spoke"
        assert intent.network.central_network_account == "Network"


class TestInteractiveInterview:
    def test_interactive_mode_with_input_fn(self):
        g = build_lza_baseline_graph()
        engine = InterviewEngine(g)

        answers: dict[str, str] = {}
        call_order: list[str] = []

        def fake_input(prompt: str) -> str:
            q = engine.next_question()
            if q is None:
                return ""
            call_order.append(q.key)
            req = g._requirements[q.key]
            return answers.get(q.key, req.default or "skip-value")

        outputs: list[str] = []

        def fake_output(msg: str) -> None:
            outputs.append(msg)

        answers["primary_region"] = "eu-central-1"
        answers["topology"] = "single-vpc"

        engine.run_interactive(input_fn=fake_input, output_fn=fake_output)

        assert len(outputs) > 0
        assert engine.graph.get("primary_region") == "eu-central-1"
        assert engine.graph.get("topology") == "single-vpc"

    def test_interactive_accepts_default_on_empty(self):
        g = build_lza_baseline_graph()
        engine = InterviewEngine(g)

        call_order: list[str] = []

        def fake_input(prompt: str) -> str:
            q = engine.next_question()
            if q is None:
                return ""
            call_order.append(q.key)
            req = g._requirements[q.key]
            if req.default:
                return ""
            return "skip"

        outputs: list[str] = []

        def fake_output(msg: str) -> None:
            outputs.append(msg)

        engine.run_interactive(input_fn=fake_input, output_fn=fake_output)

        assert engine.graph.get("primary_region") == "eu-central-1"


class TestWorkloadAccountInterview:
    def test_workload_interview_produces_intent(self):
        g = build_workload_account_graph()
        engine = InterviewEngine(g)
        engine.run_from_decisions(
            {
                "workload_name": "payments-api",
                "target_account": "PaymentsProd",
            }
        )
        engine.apply_defaults_for_remaining()

        d = engine.graph.decisions()
        assert d["workload_name"] == "payments-api"
        assert d["target_account"] == "PaymentsProd"
        assert d["network_mode"] == "private"
        assert d["public_ingress"] == "false"
        assert d["port"] == "8080"


class TestRequirementGraphEdgeCases:
    def test_decide_unknown_key_raises(self):
        g = RequirementGraph()
        import pytest

        with pytest.raises(KeyError):
            g.decide("nonexistent", "value")

    def test_apply_default_without_default_raises(self):
        g = RequirementGraph()
        from intent_engine.core.requirements import Requirement

        g.add(Requirement(key="x", label="X", question="X?"))
        import pytest

        with pytest.raises(ValueError):
            g.apply_default("x")

    def test_cascade_overwrites_prior_decision(self):
        g = RequirementGraph()
        from intent_engine.core.requirements import Requirement

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

    def test_multiple_cascades_from_one_decision(self):
        g = RequirementGraph()
        from intent_engine.core.requirements import Requirement

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

    def test_blocked_status_resets_when_condition_changes(self):
        g = RequirementGraph()
        from intent_engine.core.requirements import Requirement

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
