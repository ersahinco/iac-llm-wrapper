"""Impact graph traversal tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import ruamel.yaml
from typer.testing import CliRunner

from intent_engine.cli import app
from intent_engine.core.bundle_compare import (
    compare_handoff_bundles,
    render_bundle_comparison_html,
    render_bundle_comparison_text,
)
from intent_engine.core.compiler import compile_from_interview
from intent_engine.core.contract_validation import write_contract_validation
from intent_engine.core.impact_graph import (
    ImpactRoot,
    build_bundle_graph_report,
    build_find_report,
    build_graph_diff_report,
    build_impact_matrix_report,
    build_impact_report,
    build_neighborhood_report,
    build_path_report,
    build_recommended_impact_matrix_report,
    build_roots_report,
    changed_graph_diff_root_reasons,
    changed_graph_diff_roots,
    render_bundle_graph_text,
    render_find_report_text,
    render_graph_diff_text,
    render_impact_matrix_text,
    render_impact_report_text,
    render_neighborhood_report_text,
    render_path_report_text,
    render_roots_report_text,
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
    assert "terraform-aws-vpc-module" in report["affectedTargetContracts"]
    assert "cidr" in report["affectedModuleVariables"]
    assert "VPC-NETWORK-001" in report["affectedPolicyControls"]
    assert "VPC-ATTACHMENT-001" in report["affectedPolicyControls"]
    assert "CKV_CUSTOM_VPC_001" in report["affectedChecks"]
    assert "CKV_CUSTOM_VPC_ATTACHMENT_001" in report["affectedChecks"]
    checklist_categories = [item["category"] for item in report["reviewChecklist"]]
    assert checklist_categories[:2] == ["target-contracts", "policy-controls"]
    policy_step = next(
        item for item in report["reviewChecklist"] if item["category"] == "policy-controls"
    )
    assert policy_step["targetRootKind"] == "policy_control"
    assert (
        "iac-llm-wrapper graph path --bundle <bundle> --from decision:cidr "
        "--to policy_control:VPC-NETWORK-001"
    ) in policy_step["pathQueries"]
    assert report["summary"]["reviewChecklistCount"] == len(report["reviewChecklist"])
    assert report["summary"]["upstreamDependencyPathCount"] == len(report["dependencyPaths"])
    source_dependency_path = next(
        item for item in report["dependencyPaths"] if item["dependency"]["kind"] == "source_context"
    )
    assert source_dependency_path["root"]["id"] == "decision:cidr"
    assert source_dependency_path["hops"][-1]["relationship"] == "provides-decision-context"
    path_targets = {item["target"]["id"] for item in report["impactPaths"]}
    assert "policy_control:VPC-NETWORK-001" in path_targets
    assert "artifact:decision-report.yaml" in path_targets
    network_path = next(
        item
        for item in report["impactPaths"]
        if item["target"]["id"] == "policy_control:VPC-NETWORK-001"
    )
    assert network_path["hops"][0]["from"]["id"] == "decision:cidr"
    assert network_path["hops"][0]["relationshipDescription"] == (
        "Decision, module variable, or finding maps to a policy control."
    )
    assert network_path["hops"][-1]["to"]["id"] == "policy_control:VPC-NETWORK-001"
    rendered = render_impact_report_text(report)
    assert "Impact Analysis" in rendered
    assert "Review checklist:" in rendered
    assert "Dependency paths:" in rendered
    assert "Affected target contracts:" in rendered
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


def test_decision_impact_reports_target_capabilities_and_samples():
    bundle = Path("fixtures/aws-lza-standard-v1")

    report = build_impact_report(
        bundle,
        roots=[ImpactRoot(kind="decision", key="network_account")],
    )

    assert report["summary"]["status"] == "matched"
    assert "aws-lza-sample-config" in report["affectedTargetCapabilities"]
    assert "approved-workload-modules" in report["affectedTargetCapabilities"]
    assert "aws-lza-standard-v1" in report["affectedSamples"]
    assert "sample-recommendations.yaml" in report["affectedArtifacts"]
    assert report["summary"]["affectedTargetCapabilityCount"] >= 2
    assert report["summary"]["affectedSampleCount"] >= 1
    assert any("Review affected target capabilities:" in item for item in report["reviewFocus"])
    assert any("Review affected sample recommendations:" in item for item in report["reviewFocus"])
    path_targets = {item["target"]["id"] for item in report["impactPaths"]}
    assert "target_capability:aws-lza-sample-config" in path_targets
    assert "sample:aws-lza-standard-v1" in path_targets
    rendered = render_impact_report_text(report)
    assert "Affected target capabilities:" in rendered
    assert "Affected samples:" in rendered


def test_unknown_root_returns_no_match_report(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")

    report = build_impact_report(bundle, roots=[ImpactRoot(kind="decision", key="cid")])

    assert report["summary"]["status"] == "no-match"
    assert report["unmatchedRoots"][0]["kind"] == "decision"
    assert report["unmatchedRoots"][0]["key"] == "cid"
    assert report["unmatchedRoots"][0]["suggestedRoots"][0]["root"] == "decision:cidr"
    assert "No matching graph roots" in report["reviewFocus"][0]
    rendered = render_impact_report_text(report)
    assert "suggested roots: decision:cidr" in rendered


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


def test_graph_impact_matrix_compares_multiple_roots(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")

    report = build_impact_matrix_report(
        bundle,
        roots=[
            ImpactRoot(kind="decision", key="cidr"),
            ImpactRoot(kind="policy_control", key="VPC-NETWORK-001"),
            ImpactRoot(kind="decision", key="missing"),
        ],
    )

    assert report["schemaVersion"] == "intent-engine/graph-impact-matrix/v1"
    assert report["summary"]["rootCount"] == 3
    assert report["summary"]["matchedRootCount"] == 2
    assert report["summary"]["highestReviewPrioritySeverity"] == "medium"
    assert "policy-controls" in report["summary"]["reviewChecklistCategories"]
    assert report["summary"]["reviewChecklistCategoryCounts"]["target-contracts"] >= 1
    assert "source_context" in report["summary"]["upstreamDependencyKinds"]
    assert report["summary"]["upstreamDependencyKindCounts"]["source_context"] >= 1
    assert "module-inputs.yaml" in report["affectedArtifacts"]
    assert "terraform-aws-vpc-module" in report["affectedTargetContracts"]
    assert "VPC-NETWORK-001" in report["affectedPolicyControls"]
    assert "CKV_CUSTOM_VPC_001" in report["affectedChecks"]
    assert "cidr" in report["affectedModuleVariables"]
    assert report["summary"]["affectedModuleVariableCount"] >= 1
    statuses = {row["root"]["id"]: row["summary"]["status"] for row in report["rows"]}
    assert statuses["decision:cidr"] == "matched"
    assert statuses["policy_control:VPC-NETWORK-001"] == "matched"
    assert statuses["decision:missing"] == "no-match"
    cidr_row = next(row for row in report["rows"] if row["root"]["id"] == "decision:cidr")
    assert cidr_row["reviewChecklist"][0]["category"] == "target-contracts"
    assert cidr_row["summary"]["upstreamDependencyPathCount"] >= 1
    assert cidr_row["summary"]["upstreamDependencyKindCounts"]["source_context"] >= 1
    rendered = render_impact_matrix_text(report)
    assert "Graph Impact Matrix" in rendered
    assert "Review checklist categories:" in rendered
    assert "target-contracts:" in rendered
    assert "Upstream dependency kinds:" in rendered
    assert "source_context:" in rendered
    assert "Affected module variables:" in rendered
    assert "cidr" in rendered
    assert "decision:cidr" in rendered
    assert "policy_control:VPC-NETWORK-001" in rendered
    assert "decision:missing" in rendered


def test_graph_impact_matrix_cli_writes_report(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")
    output = tmp_path / "graph-impact-matrix.yaml"

    result = runner.invoke(
        app,
        [
            "graph",
            "matrix",
            "--bundle",
            str(bundle),
            "--root",
            "decision:cidr",
            "--root",
            "policy_control:VPC-NETWORK-001",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Graph Impact Matrix" in result.output
    report = _yaml_load(output)
    assert report["schemaVersion"] == "intent-engine/graph-impact-matrix/v1"
    assert report["summary"]["matchedRootCount"] == 2


def test_recommended_graph_impact_matrix_uses_review_roots(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")
    (bundle / "input-diff-report.yaml").write_text(
        "\n".join(
            [
                "schemaVersion: intent-engine/input-diff/v1",
                "source:",
                "  mode: document-diff",
                "  baselineDocumentAvailable: true",
                "changedStructuredDecisionLines:",
                "  - key: cidr",
                "    before: 10.30.0.0/16",
                "    after: 10.31.0.0/16",
            ]
        )
        + "\n"
    )

    report = build_recommended_impact_matrix_report(bundle, kinds=["source_change"])

    assert report["summary"]["rootSource"] == "recommended"
    assert report["summary"]["recommendedRootCount"] == 1
    assert report["rows"][0]["root"]["id"] == "source_change:structured:cidr"
    assert "Source change" in report["rows"][0]["recommendationReason"]
    assert report["rows"][0]["upstreamSourceChanges"] == ["structured:cidr"]
    assert report["upstreamSourceChanges"] == ["structured:cidr"]
    assert "module-inputs.yaml" in report["affectedArtifacts"]
    rendered = render_impact_matrix_text(report)
    assert "Root source: recommended" in rendered
    assert "reason: Source change" in rendered
    assert "sourceChanges=1" in rendered


def test_graph_impact_matrix_cli_uses_recommended_roots(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")
    (bundle / "input-diff-report.yaml").write_text(
        "\n".join(
            [
                "schemaVersion: intent-engine/input-diff/v1",
                "changedStructuredDecisionLines:",
                "  - key: cidr",
                "    before: 10.30.0.0/16",
                "    after: 10.31.0.0/16",
            ]
        )
        + "\n"
    )
    output = tmp_path / "graph-impact-matrix.yaml"

    result = runner.invoke(
        app,
        [
            "graph",
            "matrix",
            "--bundle",
            str(bundle),
            "--recommended",
            "--kind",
            "source_change",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Root source: recommended" in result.output
    report = _yaml_load(output)
    assert report["summary"]["rootSource"] == "recommended"
    assert report["rows"][0]["root"]["id"] == "source_change:structured:cidr"


def test_graph_impact_matrix_cli_uses_changed_report_roots(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")
    changed_report = tmp_path / "input-diff-report.yaml"
    changed_report.write_text(
        "\n".join(
            [
                "schemaVersion: intent-engine/input-diff/v1",
                "likelyImpactedRequirements:",
                "  - key: enable_dns_hostnames",
                "    label: DNS hostnames",
                "    reason: source text changed DNS requirements",
            ]
        )
        + "\n"
    )
    output = tmp_path / "graph-impact-matrix.yaml"

    result = runner.invoke(
        app,
        [
            "graph",
            "matrix",
            "--bundle",
            str(bundle),
            "--changed-report",
            str(changed_report),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Root source: changed-report" in result.output
    report = _yaml_load(output)
    assert report["summary"]["rootSource"] == "changed-report"
    assert report["rows"][0]["root"]["id"] == "decision:enable_dns_hostnames"


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
    topology = report["summary"]["topology"]
    assert topology["rootSelectableNodeCount"] >= report["summary"]["nodeKinds"]["decision"]
    assert topology["connectedNodeCount"] == report["summary"]["nodeCount"] - 1
    assert topology["isolatedNodeCount"] == 1
    assert topology["isolatedNodes"] == ["manual_gate:Confirm captured decisions and blockers"]
    assert any(node.startswith("source_context:") for node in topology["sourceNodes"])
    assert "artifact:decision-report.yaml" in topology["sinkNodes"]
    assert "decision:cidr" in topology["branchingNodes"]
    assert "policy_control:VPC-NETWORK-001" in topology["joinNodes"]
    assert {
        "from": "decision:cidr",
        "to": "policy_control:VPC-NETWORK-001",
        "relationship": "mapped-to-control",
    } in report["edges"]
    assert "decision:cidr" in report["indexes"]["nodesByKind"]["decision"]
    assert {
        "to": "policy_control:VPC-NETWORK-001",
        "relationship": "mapped-to-control",
    } in report["indexes"]["outgoing"]["decision:cidr"]
    assert {
        "from": "decision:cidr",
        "relationship": "mapped-to-control",
    } in report["indexes"]["incoming"]["policy_control:VPC-NETWORK-001"]
    assert {
        "from": "decision:cidr",
        "to": "policy_control:VPC-NETWORK-001",
        "relationship": "mapped-to-control",
    } in report["indexes"]["edgesByRelationship"]["mapped-to-control"]
    assert "decision:cidr" in report["indexes"]["rootSelectorsByKind"]["decision"]
    assert "decision" in report["queryHints"]["rootKinds"]
    assert "graph path" in report["queryHints"]["pathCommand"]
    assert "graph find" in report["queryHints"]["findCommand"]
    assert "graph matrix" in report["queryHints"]["matrixCommand"]
    assert "--recommended" in report["queryHints"]["recommendedMatrixCommand"]
    assert "graph diff" in report["queryHints"]["diffCommand"]
    rendered = render_bundle_graph_text(report)
    assert "Topology:" in rendered
    assert "rootSelectableNodeCount:" in rendered
    assert "isolatedNodeCount: 1" in rendered


def test_graph_roots_report_lists_concrete_traversal_roots(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")

    report = build_roots_report(bundle)

    assert report["schemaVersion"] == "intent-engine/graph-roots/v1"
    assert report["summary"]["status"] == "matched"
    assert "decision:cidr" in report["rootsByKind"]["decision"]
    assert "policy_control:VPC-NETWORK-001" in report["rootsByKind"]["policy_control"]
    root = next(item for item in report["roots"] if item["root"] == "decision:cidr")
    assert root["commands"]["impact"].endswith("--root decision:cidr")
    assert root["commands"]["neighbors"].endswith("--root decision:cidr")
    rendered = render_roots_report_text(report)
    assert "Graph Roots" in rendered
    assert "Root kinds:" in rendered


def test_graph_roots_report_recommends_source_change_roots(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")
    (bundle / "input-diff-report.yaml").write_text(
        "\n".join(
            [
                "schemaVersion: intent-engine/input-diff/v1",
                "source:",
                "  mode: document-diff",
                "  baselineDocumentAvailable: true",
                "changedStructuredDecisionLines:",
                "  - key: cidr",
                "    before: 10.30.0.0/16",
                "    after: 10.31.0.0/16",
            ]
        )
        + "\n"
    )

    report = build_roots_report(bundle, kinds=["source_change"])

    assert report["summary"]["kindFilter"] == ["source_change"]
    assert report["rootsByKind"]["source_change"] == ["source_change:structured:cidr"]
    assert report["recommendedReviewRoots"][0]["root"] == "source_change:structured:cidr"
    assert "Source change" in report["recommendedReviewRoots"][0]["reason"]


def test_graph_roots_cli_writes_report(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")
    output = tmp_path / "graph-roots.yaml"

    result = runner.invoke(
        app,
        [
            "graph",
            "roots",
            "--bundle",
            str(bundle),
            "--kind",
            "decision",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Graph Roots" in result.output
    report = _yaml_load(output)
    assert report["schemaVersion"] == "intent-engine/graph-roots/v1"
    assert "decision:cidr" in report["rootsByKind"]["decision"]
    assert report["summary"]["kindFilter"] == ["decision"]


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


def test_bundle_graph_report_exports_catalog_for_agents(tmp_path: Path):
    bundle = _terraform_vpc_validated_bundle(tmp_path / "bundle")

    report = build_bundle_graph_report(bundle)

    catalog = report["catalog"]
    assert catalog["rootSelectorSyntax"] == "<kind>:<key>"
    node_kinds = {item["kind"]: item for item in catalog["nodeKinds"]}
    assert node_kinds["decision"]["rootSelectable"] is True
    assert node_kinds["decision"]["description"] == "Accepted or expected graph decision value."
    assert node_kinds["target_contract"]["nodeCount"] >= 1
    relationships = {item["relationship"]: item for item in catalog["relationships"]}
    assert relationships["required-by-contract"]["description"] == (
        "Decision is required by a target contract."
    )
    assert "decision" in relationships["required-by-contract"]["sourceKinds"]
    assert "target_contract" in relationships["required-by-contract"]["targetKinds"]
    assert relationships["mapped-to-control"]["edgeCount"] >= 1
    assert report["queryHints"]["rootSelectorSyntax"] == "<kind>:<key>"


def test_bundle_graph_artifact_nodes_include_file_digests(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")

    report = build_bundle_graph_report(bundle)

    artifacts = {item["key"]: item for item in report["nodes"] if item["kind"] == "artifact"}
    module_inputs = artifacts["module-inputs.yaml"]
    expected_sha = hashlib.sha256((bundle / "module-inputs.yaml").read_bytes()).hexdigest()
    assert module_inputs["properties"]["existsInBundle"] is True
    assert module_inputs["properties"]["sha256"] == expected_sha
    assert module_inputs["properties"]["sizeBytes"] > 0
    assert module_inputs["properties"]["digestSource"] == "bundle-file"


def test_bundle_graph_artifact_nodes_include_replay_digests():
    bundle = Path("fixtures/aws-lza-standard-v1")

    report = build_bundle_graph_report(bundle)

    artifacts = {item["key"]: item for item in report["nodes"] if item["kind"] == "artifact"}
    accounts = artifacts["accounts-config.yaml"]
    expected_sha = hashlib.sha256((bundle / "accounts-config.yaml").read_bytes()).hexdigest()
    assert accounts["properties"]["sha256"] == expected_sha
    assert accounts["properties"]["replaySha256"] == expected_sha
    assert accounts["properties"]["replayDigestMatches"] is True


def test_bundle_graph_report_exports_source_context_nodes(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")

    report = build_bundle_graph_report(bundle)

    source_nodes = [item for item in report["nodes"] if item["kind"] == "source_context"]
    assert len(source_nodes) == 1
    source_node = source_nodes[0]
    assert source_node["properties"]["mode"] == "interview"
    assert "source_context" in report["queryHints"]["rootKinds"]
    assert {
        "from": source_node["id"],
        "to": "decision:cidr",
        "relationship": "provides-decision-context",
    } in report["edges"]
    assert {
        "from": source_node["id"],
        "to": "artifact:context-manifest.yaml",
        "relationship": "recorded-in",
    } in report["edges"]


def test_source_context_impact_reaches_decisions_and_outputs(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")
    graph_report = build_bundle_graph_report(bundle)
    source_key = next(
        item["key"] for item in graph_report["nodes"] if item["kind"] == "source_context"
    )

    report = build_impact_report(
        bundle,
        roots=[ImpactRoot(kind="source_context", key=source_key)],
    )

    assert report["summary"]["status"] == "matched"
    assert "cidr" in {item["key"] for item in report["downstreamImpacts"]}
    assert "module-inputs.yaml" in report["affectedArtifacts"]
    assert "VPC-NETWORK-001" in report["affectedPolicyControls"]
    path_targets = {item["target"]["id"] for item in report["impactPaths"]}
    assert "module_variable:cidr" in path_targets


def test_input_diff_node_drives_changed_decision_impact(tmp_path: Path):
    bundle = _terraform_vpc_bundle(tmp_path / "bundle")
    (bundle / "input-diff-report.yaml").write_text(
        "\n".join(
            [
                "schemaVersion: intent-engine/input-diff/v1",
                "source:",
                "  mode: document-diff",
                "  baselineDocumentAvailable: true",
                "changedLineCount: 4",
                "changedStructuredDecisionLines:",
                "  - key: cidr",
                "    before: 10.30.0.0/16",
                "    after: 10.31.0.0/16",
                "likelyImpactedRequirements:",
                "  - key: cidr",
                "    label: VPC CIDR",
                "    reason: changed structured decision",
                "changedHeadings:",
                "  - Network",
            ]
        )
        + "\n"
    )

    graph_report = build_bundle_graph_report(bundle)
    node_ids = {item["id"] for item in graph_report["nodes"]}
    assert "input_diff:input-diff-report.yaml" in node_ids
    assert "source_change:structured:cidr" in node_ids
    assert "source_change:likely-impacted:cidr" in node_ids
    assert {
        "from": "source_change:structured:cidr",
        "to": "decision:cidr",
        "relationship": "changes-decision",
    } in graph_report["edges"]

    report = build_impact_report(
        bundle,
        roots=[ImpactRoot(kind="input_diff", key="input-diff-report.yaml")],
    )

    assert report["summary"]["status"] == "matched"
    assert "structured:cidr" in report["affectedSourceChanges"]
    assert "cidr" in report["affectedModuleVariables"]
    assert "module-inputs.yaml" in report["affectedArtifacts"]
    assert "terraform-aws-vpc-module" in report["affectedTargetContracts"]
    assert "VPC-NETWORK-001" in report["affectedPolicyControls"]
    rendered = render_impact_report_text(report)
    assert "Affected source changes:" in rendered
    assert "structured:cidr" in rendered


def test_decision_impact_reports_readiness_and_contract_validation(tmp_path: Path):
    bundle = _terraform_vpc_validated_bundle(tmp_path / "bundle")

    report = build_impact_report(bundle, roots=[ImpactRoot(kind="decision", key="cidr")])

    assert report["affectedReadiness"] == ["handoffReadiness"]
    assert "terraform-aws-vpc-module" in report["affectedTargetContracts"]
    assert report["affectedContractValidation"] == ["contract-validation.yaml"]
    assert "terraform-aws-vpc-module" in report["affectedContractResults"]
    assert "contract-validation.yaml" in report["affectedArtifacts"]
    priority_categories = {item["category"] for item in report["reviewPriorities"]}
    assert "module-variables" in priority_categories
    assert "artifacts" in priority_categories
    assert "policy-controls" in priority_categories
    assert report["summary"]["highestReviewPrioritySeverity"] == "medium"
    severity_counts = report["summary"]["reviewPrioritySeverityCounts"]
    assert severity_counts["critical"] == 0
    assert severity_counts["high"] == 0
    assert severity_counts["medium"] >= 1
    assert severity_counts["low"] >= 2
    item_counts = report["summary"]["reviewPriorityItemCountsBySeverity"]
    assert item_counts["medium"] >= len(report["affectedPolicyControls"])
    assert item_counts["low"] >= len(report["affectedArtifacts"])
    path_targets = {item["target"]["id"] for item in report["impactPaths"]}
    assert "handoff_readiness:handoffReadiness" in path_targets
    assert "contract_validation:contract-validation.yaml" in path_targets
    rendered = render_impact_report_text(report)
    assert "Review priorities:" in rendered
    assert "Review severity: highest=medium" in rendered
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
    semantic_relationships = {
        item["relationship"]: item for item in report["catalog"]["relationships"]
    }
    assert semantic_relationships["semantic:produces_artifact"]["description"] == (
        "Typed relationship emitted by the pattern semantic model."
    )


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
    assert report["matches"][0]["root"]["root"] == "semantic_entity:control:security-hub"
    assert report["matches"][0]["root"]["commands"]["impact"].endswith(
        "--root semantic_entity:control:security-hub"
    )
    assert report["matches"][0]["root"]["commands"]["neighbors"].endswith(
        "--root semantic_entity:control:security-hub"
    )
    rendered = render_find_report_text(report)
    assert "Graph Find" in rendered
    assert "semantic_entity:control:security-hub" in rendered
    assert "root=semantic_entity:control:security-hub" in rendered


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
    checkov_priority = next(
        item for item in report["reviewPriorities"] if item["category"] == "checkov-findings"
    )
    assert checkov_priority["severity"] == "high"
    assert finding_key in checkov_priority["items"]
    assert report["summary"]["highestReviewPrioritySeverity"] == "high"
    assert report["summary"]["reviewPrioritySeverityCounts"]["high"] >= 1
    rendered = render_impact_report_text(report)
    assert "Review severity: highest=high" in rendered
    assert "Affected Checkov findings:" in rendered
    assert finding_key in rendered


def test_graph_impact_matrix_rolls_up_shift_left_findings(tmp_path: Path):
    bundle = _terraform_vpc_bundle_with_checkov_evidence(tmp_path / "bundle")

    report = build_impact_matrix_report(
        bundle,
        roots=[ImpactRoot(kind="policy_control", key="VPC-NETWORK-001")],
    )

    finding_key = "CKV_CUSTOM_VPC_001|module.vpc|/main.tf"
    unmapped_key = "CKV_OTHER|module.other|/other.tf"
    assert report["summary"]["status"] == "matched"
    assert report["summary"]["affectedCheckovFindingCount"] == 2
    assert finding_key in report["affectedCheckovFindings"]
    assert unmapped_key in report["affectedCheckovFindings"]
    rendered = render_impact_matrix_text(report)
    assert "Affected Checkov findings:" in rendered
    assert finding_key in rendered
    assert unmapped_key in rendered
    assert "findings=2" in rendered


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
    assert report["path"][0]["relationshipDescription"] == (
        "Typed relationship emitted by the pattern semantic model."
    )
    assert [item["direction"] for item in report["path"]] == ["downstream", "downstream"]
    rendered = render_path_report_text(report)
    assert "Graph Path" in rendered
    assert "semantic_entity:control:security-hub --semantic:produces_artifact" in rendered
    assert "Typed relationship emitted by the pattern semantic model." in rendered


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
    assert report["unmatchedRoots"][0]["role"] == "source"
    assert report["unmatchedRoots"][0]["kind"] == "semantic_entity"
    assert report["unmatchedRoots"][0]["key"] == "missing"
    assert report["unmatchedRoots"][0]["suggestedRoots"]
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
    assert report["edges"][1]["relationshipDescription"] == (
        "Semantic entity describes a generated artifact."
    )
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
    assert report["unmatchedRoots"][0]["role"] == "root"
    assert report["unmatchedRoots"][0]["kind"] == "semantic_entity"
    assert report["unmatchedRoots"][0]["key"] == "missing"
    assert report["unmatchedRoots"][0]["suggestedRoots"]


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
    assert "artifact:module-inputs.yaml" in changed_ids
    decision_change = next(item for item in report["changedNodes"] if item["id"] == "decision:cidr")
    decision_paths = {item["path"] for item in decision_change["changedProperties"]}
    assert "properties.value" in decision_paths
    artifact_change = next(
        item for item in report["changedNodes"] if item["id"] == "artifact:module-inputs.yaml"
    )
    assert "properties" in artifact_change["changedFields"]
    artifact_paths = {item["path"] for item in artifact_change["changedProperties"]}
    assert "properties.sha256" in artifact_paths
    assert "properties.value" in report["summary"]["changedPropertyPaths"]
    assert "properties.sha256" in report["summary"]["changedPropertyPaths"]
    assert (
        artifact_change["before"]["properties"]["sha256"]
        != artifact_change["after"]["properties"]["sha256"]
    )
    assert report["summary"]["nodeChangedCount"] >= 2
    rendered = render_graph_diff_text(report)
    assert "Graph Diff" in rendered
    assert "decision:cidr" in rendered
    assert "properties.value" in rendered
    graph_roots = changed_graph_diff_roots(report, kinds=["artifact", "module_variable"])
    assert ImpactRoot(kind="artifact", key="module-inputs.yaml") in graph_roots
    assert ImpactRoot(kind="module_variable", key="cidr") in graph_roots
    assert ImpactRoot(kind="decision", key="cidr") not in graph_roots
    graph_root_reasons = changed_graph_diff_root_reasons(
        report,
        kinds=["artifact", "module_variable"],
    )
    assert graph_root_reasons["artifact:module-inputs.yaml"] == (
        "Graph node changed between compared bundles: properties.sha256."
    )


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
    assert "terraform-aws-vpc-module" in traversal["affectedTargetContracts"]
    assert "VPC-NETWORK-001" in traversal["affectedPolicyControls"]
    assert traversal["summary"]["highestReviewPrioritySeverity"] == "medium"
    assert traversal["summary"]["reviewPrioritySeverityCounts"]["medium"] >= 1
    rendered = render_bundle_comparison_text(report)
    assert "Impact traversal:" in rendered
    assert "review priority severity: highest=medium" in rendered
    assert "affected target contracts: terraform-aws-vpc-module" in rendered
    assert "affected policy controls: VPC-ATTACHMENT-001, VPC-NETWORK-001" in rendered
    assert "affected artifacts: decision-report.yaml" in rendered
    matrix = report["impactMatrix"]
    assert matrix["schemaVersion"] == "intent-engine/graph-impact-matrix/v1"
    assert matrix["summary"]["rootSource"] == "bundle-compare"
    assert matrix["summary"]["matchedRootCount"] >= 3
    matrix_roots = {row["root"]["id"] for row in matrix["rows"]}
    assert "decision:cidr" in matrix_roots
    assert "artifact:module-inputs.yaml" in matrix_roots
    assert "module_variable:cidr" in matrix_roots
    reasons = {row["root"]["id"]: row.get("recommendationReason") for row in matrix["rows"]}
    assert reasons["decision:cidr"] == "Accepted decision was changed between compared bundles."
    assert reasons["artifact:module-inputs.yaml"] == (
        "Graph node changed between compared bundles: properties.sha256."
    )
    assert "Impact matrix:" in rendered
    assert "decision:cidr: status=matched" in rendered
    assert "reason=Accepted decision was changed between compared bundles." in rendered
    assert "artifact:module-inputs.yaml: status=matched" in rendered
    assert "reason=Graph node changed between compared bundles: properties." in rendered
    html = render_bundle_comparison_html(report)
    assert "reason=Accepted decision was changed between compared bundles." in html
    assert "reason=Graph node changed between compared bundles: properties." in html
    graph_diff = report["graphDiff"]
    assert graph_diff["summary"]["status"] == "changed"
    assert graph_diff["summary"]["nodeChangedCount"] >= 2
    assert "Graph diff:" in rendered


def test_bundle_compare_matrix_includes_input_diff_roots(tmp_path: Path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    _compile_terraform_vpc_bundle(before, cidr="10.30.0.0/16")
    _compile_terraform_vpc_bundle(after, cidr="10.30.0.0/16")
    (after / "input-diff-report.yaml").write_text(
        "\n".join(
            [
                "schemaVersion: intent-engine/input-diff/v1",
                "likelyImpactedRequirements:",
                "  - key: enable_dns_hostnames",
                "    label: DNS hostnames",
                "    reason: source text changed DNS requirements",
            ]
        )
        + "\n"
    )

    report = compare_handoff_bundles(before, after)

    selected = {item["key"] for item in report["impactTraversal"]["selectedRoots"]}
    assert "enable_dns_hostnames" in selected
    matrix_roots = {row["root"]["id"] for row in report["impactMatrix"]["rows"]}
    assert "decision:enable_dns_hostnames" in matrix_roots
    row = next(
        item
        for item in report["impactMatrix"]["rows"]
        if item["root"]["id"] == "decision:enable_dns_hostnames"
    )
    assert row["recommendationReason"] == (
        "Input diff report identified this requirement as changed or likely impacted."
    )
    assert row["upstreamSourceChanges"] == ["likely-impacted:enable_dns_hostnames"]
    assert report["impactMatrix"]["upstreamSourceChanges"] == [
        "likely-impacted:enable_dns_hostnames"
    ]
    rendered = render_bundle_comparison_text(report)
    assert "decision:enable_dns_hostnames: status=matched" in rendered
    assert "sourceChanges=1" in rendered
