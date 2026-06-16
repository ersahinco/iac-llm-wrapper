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
    build_impact_report,
    render_impact_report_text,
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
