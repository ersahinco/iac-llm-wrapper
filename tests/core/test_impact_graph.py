"""Impact graph traversal tests."""

from __future__ import annotations

from pathlib import Path

import ruamel.yaml
from typer.testing import CliRunner

from intent_engine.cli import app
from intent_engine.core.bundle_compare import compare_handoff_bundles, render_bundle_comparison_text
from intent_engine.core.compiler import compile_from_interview
from intent_engine.core.contract_validation import write_contract_validation
from intent_engine.core.impact_graph import (
    ImpactRoot,
    build_bundle_graph_report,
    build_find_report,
    build_graph_diff_report,
    build_impact_report,
    build_neighborhood_report,
    build_path_report,
    render_find_report_text,
    render_graph_diff_text,
    render_impact_report_text,
    render_neighborhood_report_text,
    render_path_report_text,
)

runner = CliRunner()


def _terraform_vpc_bundle(output: Path) -> Path:
    _compile_terraform_vpc_bundle(output, cidr="10.30.0.0/16")
    return output


def _terraform_vpc_validated_bundle(output: Path) -> Path:
    bundle = _terraform_vpc_bundle(output)
    write_contract_validation(bundle)
    return bundle


def _terraform_vpc_bundle_with_checkov_evidence(output: Path) -> Path:
    bundle = _terraform_vpc_bundle(output)
    (bundle / "shift-left-evidence.yaml").write_text(
        "\n".join(
            [
                "schemaVersion: intent-engine/shift-left-checkov/v1",
                "tool:",
                "  name: checkov",
                "  available: true",
                "  version: 3.2.0",
                "input:",
                "  scanPath: /owner/module",
                "  iacKind: terraform",
                "result:",
                "  status: fail",
                "  exitCode: 1",
                "summary:",
                "  passed: 0",
                "  failed: 2",
                "findings:",
                "  - checkId: CKV_CUSTOM_VPC_001",
                "    checkName: VPC CIDR policy",
                "    filePath: /main.tf",
                "    resource: module.vpc",
                "    guideline: https://example.test/vpc",
                "  - checkId: CKV_OTHER",
                "    checkName: Other policy",
                "    filePath: /other.tf",
                "    resource: module.other",
                "mappedControls:",
                "  - policyPack: regulated-vpc-baseline-v1",
                "    controlId: VPC-NETWORK-001",
                "    controlTitle: VPC network shape",
                "    frameworks: [SOC2]",
                "    checkId: CKV_CUSTOM_VPC_001",
                "    resource: module.vpc",
                "    filePath: /main.tf",
                "    status: fail",
                "unmappedFindings:",
                "  - checkId: CKV_OTHER",
                "    checkName: Other policy",
                "    filePath: /other.tf",
                "    resource: module.other",
            ]
        )
        + "\n"
    )
    return bundle


def _compile_terraform_vpc_bundle(output: Path, *, cidr: str) -> None:
    compile_from_interview(
        {
            "vpc_name": "orders-vpc",
            "primary_region": "eu-central-1",
            "cidr": cidr,
            "az_count": "2",
            "public_subnet_cidrs": "10.30.0.0/24,10.30.1.0/24",
            "private_subnet_cidrs": "10.30.10.0/24,10.30.11.0/24",
            "enable_nat_gateway": "true",
            "single_nat_gateway": "false",
            "enable_dns_hostnames": "true",
            "target_account_id": "111122223333",
            "deployment_pipeline_ref": "github://platform-networking/vpc-deploy",
        },
        output,
        pattern="terraform-vpc",
    )


def _yaml_load(path: Path) -> dict:
    yaml = ruamel.yaml.YAML(typ="safe")
    return yaml.load(path.read_text())


def test_decision_impact_traverses_contract_module_and_policy_edges(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")

    report = build_impact_report(bundle, roots=[ImpactRoot(kind="decision", key="cidr")])

    assert report["summary"]["status"] == "matched"
    assert "decision-report.yaml" in report["affectedArtifacts"]
    assert "module-inputs.yaml" in report["affectedArtifacts"]
    assert "cidr" in report["affectedModuleVariables"]
    assert "VPC-NETWORK-001" in report["affectedPolicyControls"]
    assert "VPC-ATTACHMENT-001" in report["affectedPolicyControls"]
    assert "CKV_CUSTOM_VPC_001" in report["affectedChecks"]
    assert "CKV_CUSTOM_VPC_ATTACHMENT_001" in report["affectedChecks"]
    path_targets = {item["target"]["id"] for item in report["impactPaths"]}
    assert "policy_control:VPC-NETWORK-001" in path_targets
    assert "artifact:decision-report.yaml" in path_targets
    network_path = next(
        item
        for item in report["impactPaths"]
        if item["target"]["id"] == "policy_control:VPC-NETWORK-001"
    )
    assert network_path["hops"][0]["from"]["id"] == "decision:cidr"
    assert network_path["hops"][-1]["to"]["id"] == "policy_control:VPC-NETWORK-001"
    rendered = render_impact_report_text(report)
    assert "Impact Analysis" in rendered
    assert "Impact paths:" in rendered
    assert "decision:cidr --mapped-to-control--> policy_control:VPC-NETWORK-001" in rendered


def test_policy_control_root_reports_mapped_artifacts_and_checks(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")

    report = build_impact_report(
        bundle,
        roots=[ImpactRoot(kind="policy_control", key="VPC-NETWORK-001")],
    )

    assert report["summary"]["status"] == "matched"
    assert "decision-report.yaml" in report["affectedArtifacts"]
    assert "module-inputs.yaml" in report["affectedArtifacts"]
    assert "CKV_CUSTOM_VPC_001" in report["affectedChecks"]


def test_unknown_root_returns_no_match_report(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")

    report = build_impact_report(bundle, roots=[ImpactRoot(kind="decision", key="missing")])

    assert report["summary"]["status"] == "no-match"
    assert report["unmatchedRoots"] == [{"kind": "decision", "key": "missing"}]
    assert "No matching graph roots" in report["reviewFocus"][0]


def test_changed_report_roots_drive_impact(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")
    changed_report = tmp_path / "input-diff-report.yaml"
    changed_report.write_text(
        "\n".join(
            [
                "schemaVersion: intent-engine/input-diff/v1",
                "likelyImpactedRequirements:",
                "  - key: cidr",
                "    label: VPC CIDR",
                "    reason: changed text mentions requirement language",
            ]
        )
        + "\n"
    )

    report = build_impact_report(bundle, roots=[], changed_report=changed_report)

    assert report["summary"]["status"] == "matched"
    assert "cidr" in {item["key"] for item in report["selectedRoots"]}
    assert "VPC-NETWORK-001" in report["affectedPolicyControls"]


def test_graph_impact_cli_writes_report(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")
    output = tmp_path / "impact-report.yaml"

    result = runner.invoke(
        app,
        [
            "graph",
            "impact",
            "--bundle",
            str(bundle),
            "--decision",
            "cidr",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Impact Analysis" in result.output
    assert "VPC-NETWORK-001" in result.output
    report = _yaml_load(output)
    assert report["schemaVersion"] == "intent-engine/impact-report/v1"
    assert "module-inputs.yaml" in report["affectedArtifacts"]


def test_bundle_graph_report_exports_queryable_nodes_and_edges(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")

    report = build_bundle_graph_report(bundle)

    assert report["schemaVersion"] == "intent-engine/bundle-graph/v1"
    node_ids = {item["id"] for item in report["nodes"]}
    assert "decision:cidr" in node_ids
    assert "module_variable:cidr" in node_ids
    assert "policy_control:VPC-NETWORK-001" in node_ids
    assert report["summary"]["nodeKinds"]["decision"] >= 11
    assert report["summary"]["relationships"]["mapped-to-control"] >= 1
    assert {
        "from": "decision:cidr",
        "to": "policy_control:VPC-NETWORK-001",
        "relationship": "mapped-to-control",
    } in report["edges"]
    assert "decision" in report["queryHints"]["rootKinds"]
    assert "graph path" in report["queryHints"]["pathCommand"]
    assert "graph find" in report["queryHints"]["findCommand"]


def test_bundle_graph_report_exports_readiness_and_contract_validation_nodes(tmp_path: Path):
    bundle = _terraform_vpc_validated_bundle(tmp_path / "bundle")

    report = build_bundle_graph_report(bundle)

    node_ids = {item["id"] for item in report["nodes"]}
    assert "handoff_readiness:handoffReadiness" in node_ids
    assert "contract_validation:contract-validation.yaml" in node_ids
    assert "contract_result:terraform-aws-vpc-module" in node_ids
    assert "artifact:contract-validation.yaml" in node_ids
    assert "handoff_readiness" in report["queryHints"]["rootKinds"]
    assert "contract_validation" in report["queryHints"]["rootKinds"]
    assert {
        "from": "decision:cidr",
        "to": "handoff_readiness:handoffReadiness",
        "relationship": "contributes-to-readiness",
    } in report["edges"]
    assert {
        "from": "handoff_readiness:handoffReadiness",
        "to": "contract_validation:contract-validation.yaml",
        "relationship": "validated-by",
    } in report["edges"]
    assert {
        "from": "target_contract:terraform-aws-vpc-module",
        "to": "contract_result:terraform-aws-vpc-module",
        "relationship": "validated-by-result",
    } in report["edges"]


def test_decision_impact_reports_readiness_and_contract_validation(tmp_path: Path):
    bundle = _terraform_vpc_validated_bundle(tmp_path / "bundle")

    report = build_impact_report(bundle, roots=[ImpactRoot(kind="decision", key="cidr")])

    assert report["affectedReadiness"] == ["handoffReadiness"]
    assert report["affectedContractValidation"] == ["contract-validation.yaml"]
    assert "terraform-aws-vpc-module" in report["affectedContractResults"]
    assert "contract-validation.yaml" in report["affectedArtifacts"]
    path_targets = {item["target"]["id"] for item in report["impactPaths"]}
    assert "handoff_readiness:handoffReadiness" in path_targets
    assert "contract_validation:contract-validation.yaml" in path_targets
    rendered = render_impact_report_text(report)
    assert "Affected readiness:" in rendered
    assert "Affected contract validation:" in rendered


def test_bundle_graph_report_exports_semantic_model_nodes_and_edges():
    bundle = Path("fixtures/aws-lza-standard-v1")

    report = build_bundle_graph_report(bundle)

    node_ids = {item["id"] for item in report["nodes"]}
    assert "semantic_entity:account:management" in node_ids
    assert "semantic_entity:control:security-hub" in node_ids
    assert "semantic_entity:artifact:security-config.yaml" in node_ids
    assert "semantic_constraint:security-ou-present" in node_ids
    assert report["summary"]["nodeKinds"]["semantic_entity"] >= 20
    assert report["summary"]["nodeKinds"]["semantic_constraint"] >= 10
    assert {
        "from": "semantic_entity:control:security-hub",
        "to": "semantic_entity:artifact:security-config.yaml",
        "relationship": "semantic:produces_artifact",
    } in report["edges"]
    assert {
        "from": "semantic_entity:artifact:security-config.yaml",
        "to": "artifact:security-config.yaml",
        "relationship": "describes-artifact",
    } in report["edges"]
    assert "semantic_entity" in report["queryHints"]["rootKinds"]
    assert "semantic_constraint" in report["queryHints"]["rootKinds"]


def test_graph_find_reports_matching_candidate_roots():
    report = build_find_report(
        Path("fixtures/aws-lza-standard-v1"),
        query="security hub",
        kinds=["semantic_entity"],
    )

    assert report["schemaVersion"] == "intent-engine/graph-find/v1"
    assert report["summary"]["status"] == "matched"
    assert report["summary"]["matchCount"] == 1
    assert report["matches"][0]["node"]["id"] == "semantic_entity:control:security-hub"
    assert "label" in report["matches"][0]["matchedFields"]
    rendered = render_find_report_text(report)
    assert "Graph Find" in rendered
    assert "semantic_entity:control:security-hub" in rendered


def test_graph_find_can_match_properties_and_limit_results():
    report = build_find_report(
        Path("fixtures/aws-lza-standard-v1"),
        query="security",
        limit=2,
    )

    assert report["summary"]["status"] == "matched"
    assert report["summary"]["returnedCount"] == 2
    assert report["summary"]["matchCount"] > 2


def test_graph_find_no_match_is_reported_without_failure():
    report = build_find_report(
        Path("fixtures/aws-lza-standard-v1"),
        query="definitely-missing-node",
        kinds=["semantic_entity"],
    )

    assert report["summary"]["status"] == "no-match"
    assert report["matches"] == []
    assert "No graph nodes matched" in report["reviewFocus"][0]


def test_graph_find_cli_writes_report(tmp_path: Path):
    output = tmp_path / "graph-find.yaml"

    result = runner.invoke(
        app,
        [
            "graph",
            "find",
            "--bundle",
            "fixtures/aws-lza-standard-v1",
            "--query",
            "security hub",
            "--kind",
            "semantic_entity",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Graph Find" in result.output
    report = _yaml_load(output)
    assert report["summary"]["status"] == "matched"
    assert report["matches"][0]["node"]["id"] == "semantic_entity:control:security-hub"


def test_bundle_graph_report_exports_shift_left_evidence_nodes(tmp_path: Path):
    bundle = _terraform_vpc_bundle_with_checkov_evidence(tmp_path / "bundle")

    report = build_bundle_graph_report(bundle)

    finding_key = "CKV_CUSTOM_VPC_001|module.vpc|/main.tf"
    unmapped_key = "CKV_OTHER|module.other|/other.tf"
    node_ids = {item["id"] for item in report["nodes"]}
    assert "shift_left_evidence:shift-left-evidence.yaml" in node_ids
    assert f"checkov_finding:{finding_key}" in node_ids
    assert f"checkov_finding:{unmapped_key}" in node_ids
    assert "scan_file:/main.tf" in node_ids
    assert "checkov_finding" in report["summary"]["nodeKinds"]
    assert "shift_left_evidence" in report["queryHints"]["rootKinds"]
    assert {
        "from": f"checkov_finding:{finding_key}",
        "to": "policy_control:VPC-NETWORK-001",
        "relationship": "maps-to-control",
    } in report["edges"]
    assert {
        "from": "policy_control:VPC-NETWORK-001",
        "to": f"checkov_finding:{finding_key}",
        "relationship": "has-finding",
    } in report["edges"]


def test_policy_control_impact_reports_shift_left_findings(tmp_path: Path):
    bundle = _terraform_vpc_bundle_with_checkov_evidence(tmp_path / "bundle")

    report = build_impact_report(
        bundle,
        roots=[ImpactRoot(kind="policy_control", key="VPC-NETWORK-001")],
    )

    finding_key = "CKV_CUSTOM_VPC_001|module.vpc|/main.tf"
    assert finding_key in report["affectedCheckovFindings"]
    assert "CKV_CUSTOM_VPC_001" in report["affectedChecks"]
    assert "shift-left-evidence.yaml" in report["affectedArtifacts"]
    rendered = render_impact_report_text(report)
    assert "Affected Checkov findings:" in rendered
    assert finding_key in rendered


def test_graph_impact_cli_accepts_generic_typed_root_for_checkov_finding(tmp_path: Path):
    bundle = _terraform_vpc_bundle_with_checkov_evidence(tmp_path / "bundle")

    result = runner.invoke(
        app,
        [
            "graph",
            "impact",
            "--bundle",
            str(bundle),
            "--root",
            "checkov_finding:CKV_CUSTOM_VPC_001|module.vpc|/main.tf",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Impact Analysis" in result.output
    assert "VPC-NETWORK-001" in result.output
    assert "shift-left-evidence.yaml" in result.output


def test_checkov_finding_path_explains_mapped_policy_control(tmp_path: Path):
    bundle = _terraform_vpc_bundle_with_checkov_evidence(tmp_path / "bundle")

    report = build_path_report(
        bundle,
        source=ImpactRoot(
            kind="checkov_finding",
            key="CKV_CUSTOM_VPC_001|module.vpc|/main.tf",
        ),
        target=ImpactRoot(kind="policy_control", key="VPC-NETWORK-001"),
        direction="downstream",
    )

    assert report["summary"]["status"] == "matched"
    assert report["path"][0]["relationship"] == "maps-to-control"


def test_semantic_entity_root_reports_affected_artifact():
    bundle = Path("fixtures/aws-lza-standard-v1")

    report = build_impact_report(
        bundle,
        roots=[ImpactRoot(kind="semantic_entity", key="control:security-hub")],
    )

    assert report["summary"]["status"] == "matched"
    assert "security-config.yaml" in report["affectedArtifacts"]
    assert "artifact:security-config.yaml" in report["affectedSemanticEntities"]
    path_targets = {item["target"]["id"] for item in report["impactPaths"]}
    assert "artifact:security-config.yaml" in path_targets
    rendered = render_impact_report_text(report)
    assert "Affected semantic entities:" in rendered
    assert "semantic_entity:control:security-hub" in rendered


def test_semantic_constraint_root_reports_checked_entity():
    bundle = Path("fixtures/aws-lza-standard-v1")

    report = build_impact_report(
        bundle,
        roots=[ImpactRoot(kind="semantic_constraint", key="security-ou-present")],
    )

    assert report["summary"]["status"] == "matched"
    assert "ou:security" in report["affectedSemanticEntities"]
    assert report["affectedArtifacts"] == []
    assert "semantic_constraint:security-ou-present" in report["reviewFocus"][0]


def test_graph_impact_cli_accepts_semantic_roots():
    result = runner.invoke(
        app,
        [
            "graph",
            "impact",
            "--bundle",
            "fixtures/aws-lza-standard-v1",
            "--semantic-entity",
            "control:security-hub",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "security-config.yaml" in result.output
    assert "Affected semantic entities:" in result.output


def test_graph_path_reports_semantic_route_to_artifact():
    report = build_path_report(
        Path("fixtures/aws-lza-standard-v1"),
        source=ImpactRoot(kind="semantic_entity", key="control:security-hub"),
        target=ImpactRoot(kind="artifact", key="security-config.yaml"),
    )

    assert report["schemaVersion"] == "intent-engine/graph-path/v1"
    assert report["summary"]["status"] == "matched"
    assert report["summary"]["hopCount"] == 2
    assert [item["relationship"] for item in report["path"]] == [
        "semantic:produces_artifact",
        "describes-artifact",
    ]
    assert [item["direction"] for item in report["path"]] == ["downstream", "downstream"]
    rendered = render_path_report_text(report)
    assert "Graph Path" in rendered
    assert "semantic_entity:control:security-hub --semantic:produces_artifact" in rendered


def test_graph_path_can_traverse_reverse_when_direction_is_either():
    report = build_path_report(
        Path("fixtures/aws-lza-standard-v1"),
        source=ImpactRoot(kind="artifact", key="security-config.yaml"),
        target=ImpactRoot(kind="semantic_entity", key="control:security-hub"),
        direction="either",
    )

    assert report["summary"]["status"] == "matched"
    assert report["summary"]["hopCount"] == 2
    assert [item["direction"] for item in report["path"]] == ["upstream", "upstream"]


def test_graph_path_no_match_is_reported_without_failure():
    report = build_path_report(
        Path("fixtures/aws-lza-standard-v1"),
        source=ImpactRoot(kind="semantic_entity", key="missing"),
        target=ImpactRoot(kind="artifact", key="security-config.yaml"),
    )

    assert report["summary"]["status"] == "no-match"
    assert report["unmatchedRoots"] == [
        {"role": "source", "kind": "semantic_entity", "key": "missing"}
    ]
    assert "not found" in report["reviewFocus"][0]


def test_graph_path_cli_writes_report(tmp_path: Path):
    output = tmp_path / "graph-path.yaml"

    result = runner.invoke(
        app,
        [
            "graph",
            "path",
            "--bundle",
            "fixtures/aws-lza-standard-v1",
            "--from",
            "semantic_entity:control:security-hub",
            "--to",
            "artifact:security-config.yaml",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Graph Path" in result.output
    report = _yaml_load(output)
    assert report["summary"]["status"] == "matched"
    assert report["summary"]["hopCount"] == 2


def test_graph_neighborhood_reports_bounded_semantic_context():
    report = build_neighborhood_report(
        Path("fixtures/aws-lza-standard-v1"),
        root=ImpactRoot(kind="semantic_entity", key="control:security-hub"),
        depth=2,
        kinds=["artifact"],
    )

    assert report["schemaVersion"] == "intent-engine/graph-neighborhood/v1"
    assert report["summary"]["status"] == "matched"
    assert report["summary"]["depth"] == 2
    assert report["summary"]["neighborCount"] == 1
    assert report["neighbors"][0]["id"] == "artifact:security-config.yaml"
    assert report["neighbors"][0]["depth"] == 2
    assert [item["relationship"] for item in report["edges"]] == [
        "semantic:produces_artifact",
        "describes-artifact",
    ]
    rendered = render_neighborhood_report_text(report)
    assert "Graph Neighborhood" in rendered
    assert "depth 2: artifact:security-config.yaml" in rendered


def test_graph_neighborhood_depth_limits_results():
    report = build_neighborhood_report(
        Path("fixtures/aws-lza-standard-v1"),
        root=ImpactRoot(kind="semantic_entity", key="control:security-hub"),
        depth=1,
    )

    neighbor_ids = {item["id"] for item in report["neighbors"]}
    assert "semantic_entity:artifact:security-config.yaml" in neighbor_ids
    assert "artifact:security-config.yaml" not in neighbor_ids


def test_graph_neighborhood_no_match_is_reported_without_failure():
    report = build_neighborhood_report(
        Path("fixtures/aws-lza-standard-v1"),
        root=ImpactRoot(kind="semantic_entity", key="missing"),
        depth=2,
    )

    assert report["summary"]["status"] == "no-match"
    assert report["neighbors"] == []
    assert report["unmatchedRoots"] == [
        {"role": "root", "kind": "semantic_entity", "key": "missing"}
    ]


def test_graph_neighbors_cli_writes_report(tmp_path: Path):
    output = tmp_path / "graph-neighborhood.yaml"

    result = runner.invoke(
        app,
        [
            "graph",
            "neighbors",
            "--bundle",
            "fixtures/aws-lza-standard-v1",
            "--root",
            "semantic_entity:control:security-hub",
            "--depth",
            "2",
            "--kind",
            "artifact",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Graph Neighborhood" in result.output
    report = _yaml_load(output)
    assert report["summary"]["status"] == "matched"
    assert report["summary"]["neighborCount"] == 1


def test_graph_bundle_cli_writes_queryable_report(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")
    output = tmp_path / "bundle-graph.yaml"

    result = runner.invoke(
        app,
        [
            "graph",
            "bundle",
            "--bundle",
            str(bundle),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Bundle Graph" in result.output
    assert "Node kinds:" in result.output
    report = _yaml_load(output)
    assert report["schemaVersion"] == "intent-engine/bundle-graph/v1"
    assert "policy_control" in report["summary"]["nodeKinds"]


def test_graph_diff_reports_changed_decision_and_module_nodes(tmp_path: Path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    _compile_terraform_vpc_bundle(before, cidr="10.30.0.0/16")
    _compile_terraform_vpc_bundle(after, cidr="10.31.0.0/16")

    report = build_graph_diff_report(before, after)

    changed_ids = {item["id"] for item in report["changedNodes"]}
    assert report["schemaVersion"] == "intent-engine/graph-diff/v1"
    assert report["summary"]["status"] == "changed"
    assert "decision:cidr" in changed_ids
    assert "module_variable:cidr" in changed_ids
    assert report["summary"]["nodeChangedCount"] >= 2
    rendered = render_graph_diff_text(report)
    assert "Graph Diff" in rendered
    assert "decision:cidr" in rendered


def test_graph_diff_reports_added_shift_left_evidence_nodes(tmp_path: Path):
    before = _terraform_vpc_bundle(tmp_path / "before")
    after = _terraform_vpc_bundle_with_checkov_evidence(tmp_path / "after")

    report = build_graph_diff_report(before, after)

    added_ids = {item["id"] for item in report["addedNodes"]}
    assert "shift_left_evidence:shift-left-evidence.yaml" in added_ids
    assert "checkov_finding:CKV_CUSTOM_VPC_001|module.vpc|/main.tf" in added_ids
    assert report["summary"]["nodeKindsAdded"]["checkov_finding"] == 2
    assert report["summary"]["edgeAddedCount"] >= 1


def test_graph_diff_cli_writes_report(tmp_path: Path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    output = tmp_path / "graph-diff.yaml"
    _compile_terraform_vpc_bundle(before, cidr="10.30.0.0/16")
    _compile_terraform_vpc_bundle(after, cidr="10.31.0.0/16")

    result = runner.invoke(
        app,
        [
            "graph",
            "diff",
            "--before",
            str(before),
            "--after",
            str(after),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Graph Diff" in result.output
    report = _yaml_load(output)
    assert report["schemaVersion"] == "intent-engine/graph-diff/v1"
    assert report["summary"]["status"] == "changed"


def test_bundle_compare_includes_impact_traversal(tmp_path: Path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    _compile_terraform_vpc_bundle(before, cidr="10.30.0.0/16")
    _compile_terraform_vpc_bundle(after, cidr="10.31.0.0/16")

    report = compare_handoff_bundles(before, after)

    traversal = report["impactTraversal"]
    assert traversal["summary"]["status"] == "matched"
    assert "decision-report.yaml" in traversal["affectedArtifacts"]
    assert "VPC-NETWORK-001" in traversal["affectedPolicyControls"]
    rendered = render_bundle_comparison_text(report)
    assert "Impact traversal:" in rendered
    assert "affected policy controls: VPC-ATTACHMENT-001, VPC-NETWORK-001" in rendered
    assert "impact paths: artifact:decision-report.yaml:" in rendered
    graph_diff = report["graphDiff"]
    assert graph_diff["summary"]["status"] == "changed"
    assert graph_diff["summary"]["nodeChangedCount"] >= 2
    assert "Graph diff:" in rendered
