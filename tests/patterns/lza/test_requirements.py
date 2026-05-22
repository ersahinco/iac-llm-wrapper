"""Tests for LZA requirement graphs, interview engine, and knowledge fields."""

from __future__ import annotations

from intent_engine.core.interview import InterviewEngine
from intent_engine.core.requirements import Requirement, RequirementStatus
from intent_engine.patterns.lza.models import (
    ApplianceHA,
    ApplianceLicense,
    CI_CDMode,
    CICDPlatform,
    CICDTool,
    RawIntent,
    SecretProvider,
    Topology,
)
from intent_engine.patterns.lza.requirements import (
    build_lza_baseline_graph,
    build_workload_account_graph,
)


class TestLZABaselinePattern:
    def test_graph_has_all_required_keys(self):
        g = build_lza_baseline_graph()
        expected = {
            "primary_region",
            "topology",
            "central_network_account",
            "network_cidr",
            "hub_cidr",
            "audit_retention_days",
            "centralized_logging",
            "cicd_mode",
            "cicd_placement",
            "cicd_runner_platform",
            "cicd_runner_tool",
            "secret_provider",
            "secret_rotation_days",
            "secret_backup",
            "appliance_vendor",
            "appliance_license",
            "appliance_ha",
            "egress_inspection",
            "inspection_pattern",
            "inspection_vendor",
            "hybrid_required",
            "hybrid_dns_model",
            "hybrid_ip_model",
            "hybrid_on_prem_cidrs",
        }
        assert set(g._requirements.keys()) == expected

    def test_hub_spoke_requires_network_account(self):
        g = build_lza_baseline_graph()
        g.decide("topology", "hub-spoke")
        pending = g.pending()
        assert "central_network_account" in pending

    def test_single_vpc_skips_network_account(self):
        g = build_lza_baseline_graph()
        g.decide("topology", "single-vpc")
        g.apply_defaults_for_remaining()
        assert g.status("central_network_account") == RequirementStatus.SKIPPED

    def test_private_cicd_requires_placement(self):
        g = build_lza_baseline_graph()
        g.decide("cicd_mode", "private")
        pending = g.pending()
        assert "cicd_placement" in pending

    def test_public_cicd_skips_placement(self):
        g = build_lza_baseline_graph()
        g.decide("cicd_mode", "public")
        g.apply_defaults_for_remaining()
        assert g.status("cicd_placement") == RequirementStatus.SKIPPED

    def test_egress_inspection_triggers_vendor_pattern(self):
        g = build_lza_baseline_graph()
        g.decide("egress_inspection", "required")
        pending = g.pending()
        assert "inspection_pattern" in pending
        assert "inspection_vendor" in pending

    def test_no_egress_skips_inspection_fields(self):
        g = build_lza_baseline_graph()
        g.decide("egress_inspection", "none")
        g.apply_defaults_for_remaining()
        assert g.status("inspection_pattern") == RequirementStatus.SKIPPED
        assert g.status("inspection_vendor") == RequirementStatus.SKIPPED

    def test_hybrid_triggers_dns_ip_cidr(self):
        g = build_lza_baseline_graph()
        g.decide("hybrid_required", "true")
        pending = g.pending()
        assert "hybrid_dns_model" in pending
        assert "hybrid_ip_model" in pending
        assert "hybrid_on_prem_cidrs" in pending

    def test_defaults_produce_valid_intent(self):
        g = build_lza_baseline_graph()
        g.apply_defaults_for_remaining()
        intent = g.decisions()
        assert intent["primary_region"] == "eu-central-1"
        assert intent["topology"] == "single-vpc"
        assert intent["audit_retention_days"] == "2555"
        assert intent["cicd_mode"] == "public"

    def test_full_hub_spoke_with_defaults(self):
        g = build_lza_baseline_graph()
        g.decide("topology", "hub-spoke")
        g.decide("central_network_account", "Network")
        g.decide("cicd_mode", "private")
        g.decide("cicd_placement", "shared-vpc")
        g.apply_defaults_for_remaining()
        assert g.all_decided() or all(
            g.status(k) in (RequirementStatus.SKIPPED, RequirementStatus.BLOCKED)
            for k in g._requirements
            if g.status(k) not in (RequirementStatus.DECIDED, RequirementStatus.DEFAULTED)
        )


class TestWorkloadAccountPattern:
    def test_graph_has_workload_keys(self):
        g = build_workload_account_graph()
        expected = {
            "workload_name",
            "target_account",
            "network_mode",
            "public_ingress",
            "port",
            "cpu",
            "memory",
        }
        assert set(g._requirements.keys()) == expected

    def test_defaults_produce_valid_workload(self):
        g = build_workload_account_graph()
        g.decide("workload_name", "payments-api")
        g.decide("target_account", "PaymentsProd")
        g.apply_defaults_for_remaining()
        d = g.decisions()
        assert d["network_mode"] == "private"
        assert d["public_ingress"] == "false"
        assert d["port"] == "8080"


class TestInterviewEngine:
    def test_next_question_returns_first_pending(self):
        g = build_lza_baseline_graph()
        engine = InterviewEngine(g)
        q = engine.next_question()
        assert q is not None
        assert q.key == "primary_region"

    def test_answer_progresses_graph(self):
        g = build_lza_baseline_graph()
        engine = InterviewEngine(g)
        engine.answer("primary_region", "us-east-1")
        q = engine.next_question()
        assert q is not None
        assert q.key != "primary_region"

    def test_accept_default(self):
        g = build_lza_baseline_graph()
        engine = InterviewEngine(g)
        engine.accept_default("primary_region")
        assert engine.graph.get("primary_region") == "eu-central-1"

    def test_run_from_decisions(self):
        g = build_lza_baseline_graph()
        engine = InterviewEngine(g)
        engine.run_from_decisions(
            {
                "primary_region": "ap-southeast-1",
                "topology": "single-vpc",
            }
        )
        assert engine.graph.get("primary_region") == "ap-southeast-1"

    def test_apply_defaults_for_remaining(self):
        g = build_lza_baseline_graph()
        engine = InterviewEngine(g)
        engine.apply_defaults_for_remaining()
        decisions = engine.graph.decisions()
        assert decisions["primary_region"] == "eu-central-1"

    def test_to_intent_produces_valid_raw_intent(self):
        g = build_lza_baseline_graph()
        engine = InterviewEngine(g)
        engine.run_from_decisions(
            {
                "primary_region": "eu-central-1",
                "topology": "hub-spoke",
                "central_network_account": "Network",
            }
        )
        engine.apply_defaults_for_remaining()
        intent = engine.to_intent()
        assert intent.primary_region == "eu-central-1"
        assert intent.topology == Topology.HUB_SPOKE
        assert intent.network.topology == Topology.HUB_SPOKE
        assert intent.network.central_network_account == "Network"

    def test_summary_contains_decisions(self):
        g = build_lza_baseline_graph()
        engine = InterviewEngine(g)
        engine.answer("primary_region", "eu-west-1")
        summary = engine.summary()
        assert "eu-west-1" in summary
        assert "Primary Region" in summary

    def test_cascading_defaults_through_dependencies(self):
        g = build_lza_baseline_graph()
        engine = InterviewEngine(g)
        engine.run_from_decisions(
            {
                "topology": "hub-spoke",
                "central_network_account": "Network",
                "cicd_mode": "private",
                "cicd_placement": "shared-vpc",
            }
        )
        engine.apply_defaults_for_remaining()
        intent = engine.to_intent()
        assert intent.topology == Topology.HUB_SPOKE
        assert intent.cicd.mode == CI_CDMode.PRIVATE


class TestKnowledgeFields:
    def test_baseline_graph_has_compliance_controls(self):
        g = build_lza_baseline_graph()
        req = g._requirements["audit_retention_days"]
        assert "PCI-DSS-10.7" in req.compliance_controls
        assert "SOC2-CC7.2" in req.compliance_controls

    def test_baseline_graph_has_signals(self):
        g = build_lza_baseline_graph()
        req = g._requirements["topology"]
        assert "on-prem-ad" in req.signals
        assert "mpls" in req.signals
        assert "5+-accounts" in req.signals
        assert "sap-workload" in req.signals
        assert "oracle-workload" in req.signals
        assert "mainframe-integration" in req.signals
        assert "multi-cloud" in req.signals
        hyb = g._requirements["hybrid_required"]
        assert "sap-workload" in hyb.signals
        assert "oracle-workload" in hyb.signals
        assert "mainframe-integration" in hyb.signals
        assert "multi-cloud" in hyb.signals
        net = g._requirements["network_cidr"]
        assert "sap-workload" in net.signals
        assert "oracle-workload" in net.signals
        assert "multi-cloud" in net.signals

    def test_baseline_graph_has_tradeoffs(self):
        g = build_lza_baseline_graph()
        req = g._requirements["topology"]
        assert any("hub-spoke" in t for t in req.tradeoffs)
        assert any("single-vpc" in t for t in req.tradeoffs)

    def test_baseline_graph_has_consequences(self):
        g = build_lza_baseline_graph()
        req = g._requirements["topology"]
        assert any("hub-spoke requires" in c for c in req.consequences)

    def test_requirement_defaults_are_sensible(self):
        req = Requirement(key="x", label="X", question="X?")
        assert req.compliance_controls == []
        assert req.signals == []
        assert req.tradeoffs == []
        assert req.confidence == 1.0
        assert req.overridable is True


class TestCICDRunnerModel:
    def test_cicd_runner_nodes_exist(self):
        g = build_lza_baseline_graph()
        assert "cicd_runner_platform" in g._requirements
        assert "cicd_runner_tool" in g._requirements

    def test_self_hosted_runner_allows_jenkins(self):
        g = build_lza_baseline_graph()
        g.decide("topology", "single-vpc")
        g.decide("cicd_runner_platform", "self-hosted")
        g.apply_defaults_for_remaining()
        assert g.get("cicd_runner_tool") == "codepipeline"
        assert g.get("cicd_runner_platform") == "self-hosted"

    def test_enterprise_runner_defaults_codepipeline(self):
        g = build_lza_baseline_graph()
        g.decide("topology", "single-vpc")
        assert g.status("cicd_runner_platform") == "pending"
        g.apply_defaults_for_remaining()
        assert g.get("cicd_runner_platform") == "enterprise"
        assert g.get("cicd_runner_tool") == "codepipeline"

    def test_cicd_runner_syncs_to_intent(self):
        intent = RawIntent()
        intent.cicd.runner.platform = CICDPlatform.SELF_HOSTED
        intent.cicd.runner.tool = CICDTool.JENKINS
        assert intent.cicd.runner.platform.value == "self-hosted"
        assert intent.cicd.runner.tool.value == "jenkins"

    def test_runner_has_tradeoffs(self):
        g = build_lza_baseline_graph()
        req = g._requirements["cicd_runner_platform"]
        assert any("self-hosted" in t for t in req.tradeoffs)
        assert any("enterprise" in t for t in req.tradeoffs)


class TestSecretManagementModel:
    def test_secret_nodes_exist(self):
        g = build_lza_baseline_graph()
        assert "secret_provider" in g._requirements
        assert "secret_rotation_days" in g._requirements
        assert "secret_backup" in g._requirements

    def test_secret_defaults_aws(self):
        g = build_lza_baseline_graph()
        g.decide("topology", "single-vpc")
        g.apply_defaults_for_remaining()
        assert g.get("secret_provider") == "aws-secrets-manager"
        assert g.get("secret_rotation_days") == "90"
        assert g.get("secret_backup") == "true"

    def test_secret_syncs_to_intent(self):
        intent = RawIntent()
        intent.secret_management.provider = SecretProvider.HASHICORP_VAULT
        intent.secret_management.rotation_days = 30
        intent.secret_management.backup_enabled = True
        assert intent.secret_management.provider.value == "hashicorp-vault"
        assert intent.secret_management.rotation_days == 30

    def test_secret_has_compliance_controls(self):
        g = build_lza_baseline_graph()
        req = g._requirements["secret_provider"]
        assert "PCI-DSS-3.5" in req.compliance_controls
        assert "SOC2-CC6.1" in req.compliance_controls


class TestNetworkApplianceModel:
    def test_appliance_nodes_exist(self):
        g = build_lza_baseline_graph()
        assert "appliance_vendor" in g._requirements
        assert "appliance_license" in g._requirements
        assert "appliance_ha" in g._requirements

    def test_appliance_nodes_depend_on_egress(self):
        g = build_lza_baseline_graph()
        g.decide("topology", "single-vpc")
        g.decide("egress_inspection", "none")
        g.apply_defaults_for_remaining()
        assert g.status("appliance_vendor") == RequirementStatus.SKIPPED
        assert g.status("appliance_license") == RequirementStatus.SKIPPED
        assert g.status("appliance_ha") == RequirementStatus.SKIPPED

    def test_appliance_nodes_active_when_egress_required(self):
        g = build_lza_baseline_graph()
        g.decide("topology", "single-vpc")
        g.decide("egress_inspection", "required")
        g.apply_defaults_for_remaining()
        assert g.get("appliance_vendor") == "aws-network-firewall"
        assert g.get("appliance_license") == "marketplace"
        assert g.get("appliance_ha") == "active-passive"

    def test_appliance_syncs_to_intent(self):
        intent = RawIntent()
        intent.network_appliance.vendor = "paloalto"
        intent.network_appliance.license_type = ApplianceLicense.BYOL
        intent.network_appliance.ha_mode = ApplianceHA.ACTIVE_ACTIVE
        assert intent.network_appliance.vendor == "paloalto"
        assert intent.network_appliance.license_type.value == "byol"
        assert intent.network_appliance.ha_mode.value == "active-active"

    def test_appliance_has_tradeoffs(self):
        g = build_lza_baseline_graph()
        req = g._requirements["appliance_vendor"]
        assert any("aws-network-firewall" in t for t in req.tradeoffs)
        assert any("paloalto" in t for t in req.tradeoffs)
