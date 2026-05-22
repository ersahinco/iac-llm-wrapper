"""Tests for discovery engine and suggestion engine."""

from __future__ import annotations

from intent_engine.core.discovery import DiscoveryEngine, generate_clarifying_questions
from intent_engine.core.suggestion import SuggestionEngine
from intent_engine.patterns.lza.models import CI_CDMode, EgressInspection, RawIntent, Topology
from intent_engine.patterns.lza.requirements import (
    build_lza_baseline_graph,
    build_workload_account_graph,
)


def _make_intent(**kwargs) -> RawIntent:
    intent = RawIntent()
    for k, v in kwargs.items():
        if "." in k:
            parts = k.split(".")
            obj = intent
            for p in parts[:-1]:
                obj = getattr(obj, p)
            setattr(obj, parts[-1], v)
        else:
            setattr(intent, k, v)
    return intent


class TestDiscoveryEngine:
    def test_complete_design_has_no_gaps(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = _make_intent(
            primary_region="eu-central-1",
            topology=Topology.SINGLE_VPC,
        )
        result = engine.discover(intent)
        assert result.is_complete()

    def test_hub_spoke_without_network_account(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = _make_intent(
            primary_region="eu-central-1",
            topology=Topology.HUB_SPOKE,
        )
        result = engine.discover(intent)
        assert not result.is_complete()
        gap_keys = [g.key for g in result.missing]
        assert "central_network_account" in gap_keys

    def test_private_cicd_without_placement(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = _make_intent(
            primary_region="eu-central-1",
            topology=Topology.SINGLE_VPC,
        )
        intent.cicd.mode = CI_CDMode.PRIVATE
        result = engine.discover(intent)
        assert not result.is_complete()
        gap_keys = [g.key for g in result.missing]
        assert "cicd_placement" in gap_keys

    def test_egress_inspection_missing_pattern_and_vendor(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = _make_intent(
            primary_region="eu-central-1",
            topology=Topology.SINGLE_VPC,
        )
        intent.security.egress_inspection = EgressInspection.REQUIRED
        result = engine.discover(intent)
        # inspection_pattern and inspection_vendor have required_when_applicable=False
        # in the graph (vendor OR pattern satisfies), so the data-driven engine
        # respects this and does not flag them as required gaps.
        assert result.is_complete()

    def test_hybrid_without_dns_ip_cidrs(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = _make_intent(
            primary_region="eu-central-1",
            topology=Topology.SINGLE_VPC,
        )
        intent.hybrid.required = True
        result = engine.discover(intent)
        assert not result.is_complete()
        gap_keys = [g.key for g in result.missing]
        # Data-driven engine reports the specific missing sub-fields
        assert "hybrid_dns_model" in gap_keys
        assert "hybrid_ip_model" in gap_keys
        assert "hybrid_on_prem_cidrs" in gap_keys

    def test_workload_without_target_account(self):
        # Note: data-driven discovery does not inspect list-of-model fields
        # (workloads, accounts) because they are not represented as graph nodes.
        # The validator still catches missing target_account via
        # WORKLOAD_TARGET_ACCOUNT_REQUIRED. This test verifies the graph-driven
        # engine reports no gaps for list items.
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = _make_intent(
            primary_region="eu-central-1",
            topology=Topology.SINGLE_VPC,
        )
        from intent_engine.patterns.lza.models import Workload

        intent.workloads.append(Workload(name="api"))
        result = engine.discover(intent)
        assert result.is_complete()

    def test_gaps_sorted_by_priority(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = _make_intent(topology=Topology.HUB_SPOKE)
        intent.cicd.mode = CI_CDMode.PRIVATE
        result = engine.discover(intent)
        priorities = [g.priority for g in result.missing]
        assert priorities == sorted(priorities)


class TestGenerateClarifyingQuestions:
    def test_generates_questions_for_hub_spoke_gap(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = _make_intent(topology=Topology.HUB_SPOKE)
        result = engine.discover(intent)
        questions = generate_clarifying_questions(result, intent, graph=graph)
        assert len(questions) > 0
        keys = [q["key"] for q in questions]
        assert "central_network_account" in keys

    def test_question_has_type_and_options(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = _make_intent(
            topology=Topology.SINGLE_VPC,
        )
        intent.cicd.mode = CI_CDMode.PRIVATE
        result = engine.discover(intent)
        questions = generate_clarifying_questions(result, intent, graph=graph)
        cicd_q = next(q for q in questions if q["key"] == "cicd_placement")
        assert "type" in cicd_q
        assert "question" in cicd_q

    def test_inspection_questions_are_select_type(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = _make_intent(topology=Topology.SINGLE_VPC)
        intent.security.egress_inspection = EgressInspection.REQUIRED
        result = engine.discover(intent)
        questions = generate_clarifying_questions(result, intent, graph=graph)
        pattern_q = next((q for q in questions if q["key"] == "inspection_pattern"), None)
        vendor_q = next((q for q in questions if q["key"] == "inspection_vendor"), None)
        # With required_when_applicable=False, these are not gaps, so no questions
        assert pattern_q is None
        assert vendor_q is None


class TestSuggestionEngine:
    def test_suggest_next_returns_pending(self):
        graph = build_lza_baseline_graph()
        engine = SuggestionEngine(graph)
        suggestions = engine.suggest_next()
        assert len(suggestions) > 0
        keys = [s.key for s in suggestions]
        assert "primary_region" in keys

    def test_suggestions_include_context_and_hint(self):
        graph = build_lza_baseline_graph()
        engine = SuggestionEngine(graph)
        suggestions = engine.suggest_next()
        s = next(s for s in suggestions if s.key == "primary_region")
        assert s.default == "eu-central-1"
        assert s.hint is not None

    def test_suggest_for_given_triggers_downstream(self):
        graph = build_lza_baseline_graph()
        engine = SuggestionEngine(graph)
        suggestions = engine.suggest_for_given("topology", "hub-spoke")
        triggered_keys = [s.key for s in suggestions]
        assert "central_network_account" in triggered_keys

    def test_preview_path_shows_all_requirements(self):
        graph = build_lza_baseline_graph()
        engine = SuggestionEngine(graph)
        path = engine.preview_path()
        assert len(path) >= 16
        keys = [p["key"] for p in path]
        assert "topology" in keys
        assert "central_network_account" in keys

    def test_preview_path_with_decisions(self):
        graph = build_lza_baseline_graph()
        engine = SuggestionEngine(graph)
        graph.decide("topology", "hub-spoke")
        graph.decide("central_network_account", "Network")
        path = engine.preview_path()
        topo_item = next(p for p in path if p["key"] == "topology")
        assert topo_item["status"] == "decided"
        assert topo_item["value"] == "hub-spoke"
        cna_item = next(p for p in path if p["key"] == "central_network_account")
        assert cna_item["status"] == "decided"

    def test_suggestions_respect_applies_if(self):
        graph = build_lza_baseline_graph()
        engine = SuggestionEngine(graph)
        graph.decide("topology", "single-vpc")
        suggestions = engine.suggest_next()
        pending_keys = [s.key for s in suggestions]
        assert "central_network_account" not in pending_keys


class TestDiscoveryWithWorkloadGraph:
    def test_workload_graph_detects_missing_target_account(self):
        graph = build_workload_account_graph()
        engine = DiscoveryEngine(graph)
        intent = RawIntent()
        from intent_engine.patterns.lza.models import Workload

        intent.workloads.append(Workload(name="api"))
        result = engine.discover(intent)
        assert not result.is_complete()
        gap_keys = [g.key for g in result.missing]
        # Data-driven engine reports the graph requirement key, not compound keys
        assert "target_account" in gap_keys


class TestSignalDetection:
    def test_detects_active_directory_signal(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = RawIntent()
        text = "We have an on-prem Active Directory domain that needs to be extended."
        result = engine.discover(intent, text=text)
        signals = [s.signal for s in result.signals]
        assert "on-prem-ad" in signals

    def test_detects_mpls_signal(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = RawIntent()
        text = "Our current MPLS backbone connects to AWS via Direct Connect."
        result = engine.discover(intent, text=text)
        signals = [s.signal for s in result.signals]
        assert "mpls" in signals

    def test_detects_pci_compliance_signal(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = RawIntent()
        text = "This is a regulated financial services environment requiring PCI-DSS compliance."
        result = engine.discover(intent, text=text)
        signals = [s.signal for s in result.signals]
        assert "regulated-industry" in signals

    def test_detects_many_accounts_signal(self):
        graph = build_lza_baseline_graph()
        from intent_engine.patterns.lza.discovery import detect_lza_legacy_signals

        engine = DiscoveryEngine(graph, extra_signal_detectors=[detect_lza_legacy_signals])
        intent = RawIntent()
        for i in range(6):
            from intent_engine.patterns.lza.models import Account

            intent.accounts.append(Account(name=f"acct{i}", ou="Workloads"))
        result = engine.discover(intent)
        signals = [s.signal for s in result.signals]
        assert "5+-accounts" in signals

    def test_no_signal_when_hybrid_already_enabled(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = RawIntent()
        intent.hybrid.required = True
        text = "We have Active Directory on-prem."
        result = engine.discover(intent, text=text)
        signals = [s.signal for s in result.signals]
        assert "on-prem-ad" not in signals

    # -- Enterprise migration signals --

    def test_detects_sap_signal(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = RawIntent()
        text = "We are migrating our SAP S/4HANA landscape to AWS."
        result = engine.discover(intent, text=text)
        signals = [s.signal for s in result.signals]
        assert "sap-workload" in signals

    def test_detects_sap_signal_via_hana(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = RawIntent()
        text = "We will run SAP HANA on dedicated EC2 instances."
        result = engine.discover(intent, text=text)
        signals = [s.signal for s in result.signals]
        assert "sap-workload" in signals

    def test_no_sap_signal_when_topology_hub_spoke_and_hybrid(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = RawIntent()
        intent.topology = Topology.HUB_SPOKE
        intent.hybrid.required = True
        text = "Our SAP landscape is ready for migration."
        result = engine.discover(intent, text=text)
        signals = [s.signal for s in result.signals]
        assert "sap-workload" not in signals

    def test_detects_oracle_signal(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = RawIntent()
        text = "We need to migrate our Oracle RAC database to AWS."
        result = engine.discover(intent, text=text)
        signals = [s.signal for s in result.signals]
        assert "oracle-workload" in signals

    def test_no_oracle_signal_when_all_config(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = RawIntent()
        intent.topology = Topology.HUB_SPOKE
        intent.hybrid.required = True
        text = "Oracle E-Business Suite will run on AWS."
        result = engine.discover(intent, text=text)
        signals = [s.signal for s in result.signals]
        assert "oracle-workload" not in signals

    def test_detects_mainframe_signal(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = RawIntent()
        text = "Our mainframe workload runs on z/OS and requires low-latency access."
        result = engine.discover(intent, text=text)
        signals = [s.signal for s in result.signals]
        assert "mainframe-integration" in signals

    def test_detects_mainframe_cics_signal(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = RawIntent()
        text = "CICS transactions need to be extended to AWS."
        result = engine.discover(intent, text=text)
        signals = [s.signal for s in result.signals]
        assert "mainframe-integration" in signals

    def test_no_mainframe_signal_when_hybrid_and_hub_spoke(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = RawIntent()
        intent.topology = Topology.HUB_SPOKE
        intent.hybrid.required = True
        text = "Mainframe decommissioning plan approved."
        result = engine.discover(intent, text=text)
        signals = [s.signal for s in result.signals]
        assert "mainframe-integration" not in signals

    def test_detects_multi_cloud_signal(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = RawIntent()
        text = "We follow a multi-cloud strategy with Azure and GCP."
        result = engine.discover(intent, text=text)
        signals = [s.signal for s in result.signals]
        assert "multi-cloud" in signals

    def test_detects_multi_cloud_gcp_signal(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = RawIntent()
        text = "Our GCP interconnect connects to AWS through Direct Connect."
        result = engine.discover(intent, text=text)
        signals = [s.signal for s in result.signals]
        assert "multi-cloud" in signals

    def test_no_multi_cloud_signal_when_configured(self):
        graph = build_lza_baseline_graph()
        engine = DiscoveryEngine(graph)
        intent = RawIntent()
        intent.topology = Topology.HUB_SPOKE
        intent.hybrid.required = True
        text = "Azure ExpressRoute is already connected."
        result = engine.discover(intent, text=text)
        signals = [s.signal for s in result.signals]
        assert "multi-cloud" not in signals
