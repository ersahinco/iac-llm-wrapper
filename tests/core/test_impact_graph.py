"""Impact graph traversal tests."""

from __future__ import annotations

from pathlib import Path

import ruamel.yaml
from typer.testing import CliRunner

from intent_engine.cli import app
from intent_engine.core.bundle_compare import compare_handoff_bundles, render_bundle_comparison_text
from intent_engine.core.compiler import compile_from_interview
from intent_engine.core.impact_graph import (
    ImpactRoot,
    build_bundle_graph_report,
    build_find_report,
    build_impact_report,
    build_neighborhood_report,
    build_path_report,
    render_find_report_text,
    render_impact_report_text,
    render_neighborhood_report_text,
    render_path_report_text,
)

runner = CliRunner()


def _terraform_vpc_bundle(output: Path) -> Path:
    _compile_terraform_vpc_bundle(output, cidr="10.30.0.0/16")
    return output


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
