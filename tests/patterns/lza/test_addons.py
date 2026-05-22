"""Tests for the composable addon system."""

from pathlib import Path

from intent_engine.core.patterns import ADDON_REGISTRY, GLOBAL_REGISTRY
from intent_engine.patterns.lza.requirements import build_lza_baseline_graph


class TestAddonRegistry:
    def test_list_contains_builtin_addons(self):
        names = ADDON_REGISTRY.list()
        assert "pci-compliance" in names
        assert "hipaa" in names

    def test_get_returns_addon(self):
        addon = ADDON_REGISTRY.get("pci-compliance")
        assert addon.name == "pci-compliance"
        assert len(addon.requirements) == 3

    def test_get_unknown_raises(self):
        try:
            ADDON_REGISTRY.get("nonexistent")
            assert False, "Should have raised"
        except KeyError:
            pass

    def test_list_returns_sorted(self):
        names = ADDON_REGISTRY.list()
        assert names == sorted(names)


class TestAddonComposition:
    def test_compose_adds_requirements(self):
        base = build_lza_baseline_graph()
        n_before = len(base._requirements)
        composed = ADDON_REGISTRY.compose(base, ["pci-compliance"])
        n_after = len(composed._requirements)
        assert n_after == n_before + 3
        assert "data_residency" in composed._requirements
        assert "encryption_key_management" in composed._requirements
        assert "network_segmentation" in composed._requirements

    def test_compose_hipaa_adds_requirements(self):
        base = build_lza_baseline_graph()
        n_before = len(base._requirements)
        composed = ADDON_REGISTRY.compose(base, ["hipaa"])
        n_after = len(composed._requirements)
        assert n_after == n_before + 3
        assert "phi_encryption" in composed._requirements
        assert "audit_access_logging" in composed._requirements
        assert "business_associate_agreements" in composed._requirements

    def test_compose_multiple_addons(self):
        base = build_lza_baseline_graph()
        n_before = len(base._requirements)
        composed = ADDON_REGISTRY.compose(base, ["pci-compliance", "hipaa"])
        n_after = len(composed._requirements)
        assert n_after == n_before + 6

    def test_compose_preserves_base_requirements(self):
        base = build_lza_baseline_graph()
        composed = ADDON_REGISTRY.compose(base, ["pci-compliance"])
        assert "primary_region" in composed._requirements
        assert "topology" in composed._requirements
        assert "network_cidr" in composed._requirements

    def test_compose_does_not_mutate_base(self):
        base = build_lza_baseline_graph()
        n_before = len(base._requirements)
        ADDON_REGISTRY.compose(base, ["pci-compliance"])
        n_after = len(base._requirements)
        assert n_after == n_before


class TestAddonEquivalence:
    """Verify that addon-based composition matches hardcoded patterns."""

    def test_baseline_plus_pci_equals_financial(self):
        financial = GLOBAL_REGISTRY.get("financial-services").create_graph()
        composed = ADDON_REGISTRY.compose(
            GLOBAL_REGISTRY.get("baseline").create_graph(),
            ["pci-compliance"],
        )
        fin_keys = set(financial._requirements.keys())
        comp_keys = set(composed._requirements.keys())
        assert fin_keys == comp_keys

    def test_baseline_plus_hipaa_equals_healthcare(self):
        healthcare = GLOBAL_REGISTRY.get("healthcare").create_graph()
        composed = ADDON_REGISTRY.compose(
            GLOBAL_REGISTRY.get("baseline").create_graph(),
            ["hipaa"],
        )
        hlth_keys = set(healthcare._requirements.keys())
        comp_keys = set(composed._requirements.keys())
        assert hlth_keys == comp_keys


class TestAddonFieldMaps:
    def test_get_field_map_returns_merged(self):
        field_map = ADDON_REGISTRY.get_field_map(["pci-compliance"])
        assert "data_residency" in field_map
        assert "encryption_key_management" in field_map
        assert "network_segmentation" in field_map

    def test_get_section_map_returns_merged(self):
        section_map = ADDON_REGISTRY.get_section_map(["pci-compliance"])
        assert section_map["data_residency"] == ("Security", "data_residency")
        assert section_map["encryption_key_management"] == ("Security", "encryption_key_management")
        assert section_map["network_segmentation"] == ("Network", "network_segmentation")


class TestAddonResolveOrder:
    def test_resolve_order_no_deps(self):
        order = ADDON_REGISTRY.resolve_order(["hipaa", "pci-compliance"])
        # No deps between these, so order should be stable
        assert len(order) == 2
        assert "pci-compliance" in order
        assert "hipaa" in order

    def test_resolve_order_preserves_input(self):
        order = ADDON_REGISTRY.resolve_order(["pci-compliance"])
        assert order == ["pci-compliance"]

    def test_resolve_order_empty(self):
        order = ADDON_REGISTRY.resolve_order([])
        assert order == []


class TestAddonTemplateIntegration:
    def test_template_with_addon_includes_fields(self, tmp_path: Path):
        from intent_engine.core.compiler import generate_template

        markdown = generate_template(pattern="baseline", addon_names=["pci-compliance"])
        assert "data_residency" in markdown
        assert "encryption_key_management" in markdown
        assert "network_segmentation" in markdown

    def test_template_with_addon_hipaa_includes_fields(self, tmp_path: Path):
        from intent_engine.core.compiler import generate_template

        markdown = generate_template(pattern="minimal", addon_names=["hipaa"])
        assert "phi_encryption" in markdown
        assert "audit_access_logging" in markdown
        assert "business_associate_agreements" in markdown

    def test_template_without_addon_excludes_addon_fields(self):
        from intent_engine.core.compiler import generate_template

        markdown = generate_template(pattern="minimal")
        assert "data_residency" not in markdown
        assert "phi_encryption" not in markdown

    def test_template_with_multiple_addons(self, tmp_path: Path):
        from intent_engine.core.compiler import generate_template

        markdown = generate_template(
            pattern="baseline",
            addon_names=["pci-compliance", "hipaa"],
        )
        assert "data_residency" in markdown
        assert "phi_encryption" in markdown


class TestTemplateValidation:
    def test_template_baseline_validates_clean(self):
        from intent_engine.core.compiler import generate_template, validate_template_output

        markdown = generate_template(pattern="baseline")
        warnings = validate_template_output(markdown, pattern="baseline")
        assert not warnings, f"Expected no warnings: {warnings}"

    def test_template_minimal_validates_clean(self):
        from intent_engine.core.compiler import generate_template, validate_template_output

        markdown = generate_template(pattern="minimal")
        warnings = validate_template_output(markdown, pattern="minimal")
        assert not warnings, f"Expected no warnings: {warnings}"

    def test_template_with_pci_addon_validates_clean(self):
        from intent_engine.core.compiler import generate_template, validate_template_output

        markdown = generate_template(pattern="baseline", addon_names=["pci-compliance"])
        warnings = validate_template_output(
            markdown, pattern="baseline", addon_names=["pci-compliance"]
        )
        assert not warnings, f"Expected no warnings: {warnings}"

    def test_template_with_both_addons_validates_clean(self):
        from intent_engine.core.compiler import generate_template, validate_template_output

        markdown = generate_template(pattern="baseline", addon_names=["pci-compliance", "hipaa"])
        warnings = validate_template_output(
            markdown, pattern="baseline", addon_names=["pci-compliance", "hipaa"]
        )
        assert not warnings, f"Expected no warnings: {warnings}"

    def test_workload_template_validates_clean(self):
        from intent_engine.core.compiler import generate_template, validate_template_output

        markdown = generate_template(pattern="workload")
        warnings = validate_template_output(markdown, pattern="workload")
        assert not warnings, f"Expected no warnings: {warnings}"


class TestNewDomainAddons:
    def test_self_hosted_cicd_addon_registered(self):
        assert "self-hosted-cicd" in ADDON_REGISTRY.list()

    def test_self_hosted_cicd_adds_requirements(self):
        base = build_lza_baseline_graph()
        composed = ADDON_REGISTRY.compose(base, ["self-hosted-cicd"])
        assert "cicd_runner_platform" in composed._requirements
        # Should override default to self-hosted
        assert composed._requirements["cicd_runner_platform"].default == "self-hosted"

    def test_self_hosted_cicd_tool_default_jenkins(self):
        base = build_lza_baseline_graph()
        composed = ADDON_REGISTRY.compose(base, ["self-hosted-cicd"])
        assert composed._requirements["cicd_runner_tool"].default == "jenkins"

    def test_hashicorp_vault_addon_registered(self):
        assert "hashicorp-vault" in ADDON_REGISTRY.list()

    def test_hashicorp_vault_changes_default(self):
        base = build_lza_baseline_graph()
        composed = ADDON_REGISTRY.compose(base, ["hashicorp-vault"])
        assert composed._requirements["secret_provider"].default == "hashicorp-vault"
        assert composed._requirements["secret_rotation_days"].default == "30"

    def test_paloalto_fw_addon_registered(self):
        assert "paloalto-fw" in ADDON_REGISTRY.list()

    def test_paloalto_fw_changes_defaults(self):
        base = build_lza_baseline_graph()
        composed = ADDON_REGISTRY.compose(base, ["paloalto-fw"])
        assert composed._requirements["appliance_vendor"].default == "paloalto"
        assert composed._requirements["appliance_license"].default == "byol"

    def test_template_all_new_addons(self, tmp_path):
        from intent_engine.core.compiler import generate_template

        markdown = generate_template(
            pattern="baseline",
            addon_names=["self-hosted-cicd", "hashicorp-vault", "paloalto-fw"],
        )
        assert "runner_platform" in markdown
        assert "runner_tool" in markdown
        assert "secret_provider" in markdown
        assert "appliance_vendor" in markdown
        assert "appliance_license" in markdown


class TestHybridChallengesAddon:
    def test_addon_registered(self):
        assert "hybrid-challenges" in ADDON_REGISTRY.list()

    def test_addon_adds_requirements(self):
        base = build_lza_baseline_graph()
        composed = ADDON_REGISTRY.compose(base, ["hybrid-challenges"])
        assert "dx_redundancy" in composed._requirements
        assert "vpn_failover" in composed._requirements
        assert "hybrid_identity" in composed._requirements

    def test_addon_applies_only_when_hybrid(self):
        base = build_lza_baseline_graph()
        composed = ADDON_REGISTRY.compose(base, ["hybrid-challenges"])
        # Without hybrid_required=true, these should be skipped
        composed.apply_defaults_for_remaining()
        assert composed.status("dx_redundancy").value == "skipped"
        assert composed.status("vpn_failover").value == "skipped"
        assert composed.status("hybrid_identity").value == "skipped"

    def test_addon_active_when_hybrid_enabled(self):
        base = build_lza_baseline_graph()
        composed = ADDON_REGISTRY.compose(base, ["hybrid-challenges"])
        composed.decide("hybrid_required", "true")
        composed.decide("hybrid_dns_model", "route53-resolver")
        composed.decide("hybrid_ip_model", "bring-your-own")
        composed.decide("hybrid_on_prem_cidrs", "10.0.0.0/8")
        composed.apply_defaults_for_remaining()
        assert composed.status("dx_redundancy").value == "defaulted"
        assert composed.status("vpn_failover").value == "defaulted"
        assert composed.status("hybrid_identity").value == "defaulted"


class TestAddonFieldMapWiring:
    """Verify addon field_map is merged into graph for sync_intent_to_graph."""

    def test_compose_merges_field_map_into_graph(self):
        base = build_lza_baseline_graph()
        composed = ADDON_REGISTRY.compose(base, ["pci-compliance"])
        assert "data_residency" in composed._field_map
        assert "encryption_key_management" in composed._field_map

    def test_addon_target_field_syncs_to_intent(self):
        from intent_engine.core.discovery import DiscoveryEngine
        from intent_engine.patterns.lza.models import CICDPlatform, CICDTool, RawIntent

        base = build_lza_baseline_graph()
        composed = ADDON_REGISTRY.compose(base, ["self-hosted-cicd"])
        intent = RawIntent()
        intent.cicd.runner.platform = CICDPlatform.SELF_HOSTED
        intent.cicd.runner.tool = CICDTool.JENKINS

        engine = DiscoveryEngine(composed)
        synced = engine.sync_intent_to_graph(intent)
        assert "cicd_runner_platform" in synced
        assert "cicd_runner_tool" in synced
        assert composed.get("cicd_runner_platform") == "self-hosted"
        assert composed.get("cicd_runner_tool") == "jenkins"

    def test_addon_field_map_fallback_for_custom_mapping(self):
        from intent_engine.core.requirements import Requirement, RequirementGraph

        g = RequirementGraph()
        g.add(
            Requirement(
                key="custom_addon_field",
                label="Custom Field",
                question="A custom field?",
            )
        )
        # Simulate an addon that maps this key to a custom intent path
        g._field_map["custom_addon_field"] = "primary_region"

        from intent_engine.core.discovery import DiscoveryEngine
        from intent_engine.patterns.lza.models import RawIntent

        intent = RawIntent(primary_region="eu-west-1")
        engine = DiscoveryEngine(g)
        synced = engine.sync_intent_to_graph(intent)
        assert "custom_addon_field" in synced
        assert g.get("custom_addon_field") == "eu-west-1"
