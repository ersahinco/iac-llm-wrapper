"""Neo4j-backed tests.

Skipped unless NEO4J_PASSWORD is set. These wipe the target database;
use the dedicated test project described in CONTRIBUTING.md.
"""

from __future__ import annotations

import json
import os

import pytest
from ruamel.yaml import YAML
from typer.testing import CliRunner

from intent_engine.analysis import review
from intent_engine.cli import app
from intent_engine.graph import GraphConfig, KnowledgeGraph
from intent_engine.ingest import extract_facts, read_document
from intent_engine.models import Architecture

pytestmark = pytest.mark.skipif(
    not os.environ.get("NEO4J_PASSWORD"),
    reason="set NEO4J_PASSWORD to run the Neo4j tests",
)


@pytest.fixture
def graph():
    with KnowledgeGraph(GraphConfig.from_env()) as connected:
        yield connected


def _ingest(graph, catalog, path):
    document = read_document(path)
    facts = extract_facts(document, catalog)
    graph.replace(catalog, document, facts)
    return document, facts


def test_query_advisories_are_quiet_but_query_errors_still_fail(graph, caplog):
    from intent_engine.graph import GraphUnavailable

    with caplog.at_level("WARNING", logger="neo4j.notifications"):
        assert graph._run("MATCH (n:AbsentOptionalSystem) RETURN n") == []
    assert not [r for r in caplog.records if r.name == "neo4j.notifications"]
    with pytest.raises(GraphUnavailable, match="query failed"):
        graph._run("RETURN 1 +")


def test_extracted_candidate_has_evidence_but_does_not_answer_gap(graph, catalog, tmp_path):
    packet = tmp_path / "prose.md"
    packet.write_text("The planned VPC uses 10.42.0.0/16.\n")
    document = read_document(packet)
    architecture = Architecture.model_validate(
        {
            "nodes": [
                {
                    "id": "s",
                    "label": "System",
                    "properties": {
                        "name": "VPC",
                        "lifecycle": "planned",
                        "statement_id": "s1",
                        "quote": "The planned VPC uses 10.42.0.0/16.",
                    },
                },
                {
                    "id": "c",
                    "label": "Candidate",
                    "properties": {
                        "decision_key": "network_cidr",
                        "value": "10.42.0.0/16",
                        "statement_id": "s1",
                        "quote": "10.42.0.0/16",
                    },
                },
            ],
            "relationships": [{"start_node_id": "c", "end_node_id": "s", "type": "ABOUT"}],
        }
    )
    graph.replace(catalog, document, [], architecture)
    result = review(graph, catalog)
    assert {n.id: n for n in result.architecture.nodes} == {n.id: n for n in architecture.nodes}
    assert result.architecture.relationships == architecture.relationships
    assert "network_cidr" in {gap.decision_key for gap in result.gaps}
    assert not graph.facts()
    evidence = graph._run("MATCH (:Candidate)-[:EVIDENCE]->(s:Statement) RETURN s.line AS line")
    assert evidence == [{"line": 1}]
    packet.write_text("network_cidr: 10.42.0.0/16\n")
    _ingest(graph, catalog, packet)
    assert not graph.architecture().nodes
    assert "network_cidr" not in {gap.decision_key for gap in review(graph, catalog).gaps}


def test_tfvars_cli_uses_confirmed_decisions(graph, tmp_path):
    from pathlib import Path

    sample = Path(__file__).resolve().parents[1] / "samples" / "vpc"
    runner = CliRunner()
    catalog_args = ["--catalog", str(sample / "decisions.yaml")]
    assert (
        runner.invoke(app, ["ingest", str(sample / "requirements.md"), *catalog_args]).exit_code
        == 0
    )
    output = tmp_path / "variables"
    command = [
        "emit-tfvars",
        "--contract",
        str(sample / "module-inputs.json"),
        "--out",
        str(output),
        *catalog_args,
    ]
    assert runner.invoke(app, command).exit_code == 2
    assert not output.exists()
    assert (
        runner.invoke(app, ["ingest", str(sample / "confirmed.md"), *catalog_args]).exit_code == 0
    )
    emitted = runner.invoke(app, command)
    assert emitted.exit_code == 0, emitted.output
    assert json.loads((output / "terraform.tfvars.json").read_text())["cidr"] == "10.42.0.0/16"


def test_ingest_replaces_the_previous_document(graph, catalog, tmp_path):
    first = tmp_path / "first.md"
    first.write_text("- home_region: eu-west-1\n", encoding="utf-8")
    _ingest(graph, catalog, first)

    second = tmp_path / "second.md"
    second.write_text("- home_region: eu-central-1\n", encoding="utf-8")
    _ingest(graph, catalog, second)

    counts = graph.counts()
    assert (counts["Document"], counts["Fact"]) == (1, 1)
    assert [fact.value for fact in graph.facts()] == ["eu-central-1"]
    assert graph.document()[0] == str(second)


def test_sample_packet_leaves_nothing_open(graph, catalog, sample_path):
    document, facts = _ingest(graph, catalog, sample_path)
    result = review(graph, catalog)
    assert result.gaps == []
    assert result.conflicts == []
    assert result.sha256 == document.sha256
    assert len(result.answered) == len(facts)


def test_gaps_report_gating_and_blocking(graph, catalog, tmp_path):
    path = tmp_path / "partial.md"
    path.write_text(
        "- topology: hub-spoke\n- identity_center_assignments: Admins:PowerUserAccess:Management\n",
        encoding="utf-8",
    )
    _ingest(graph, catalog, path)
    gaps = {gap.decision_key: gap for gap in review(graph, catalog).gaps}

    assert "topology" not in gaps
    assert "network_account" in gaps
    assert gaps["identity_center_permission_sets"].blocks == [
        "identity_center_assignments",
        "identity_center_policy_mappings",
    ]


def test_gated_decision_disappears_under_single_vpc(graph, catalog, tmp_path):
    path = tmp_path / "single.md"
    path.write_text("- topology: single-vpc\n", encoding="utf-8")
    _ingest(graph, catalog, path)
    assert "network_account" not in {gap.decision_key for gap in review(graph, catalog).gaps}


def test_two_statements_for_one_decision_contradict(graph, catalog, tmp_path):
    path = tmp_path / "contradiction.md"
    path.write_text(
        "## Kickoff\n\n- home_region: eu-central-1\n\n"
        "## Later Review\n\n- home_region: eu-west-1\n",
        encoding="utf-8",
    )
    _ingest(graph, catalog, path)
    conflicts = graph.contradictions()

    assert [conflict.code for conflict in conflicts] == ["CONTRADICTORY_STATEMENTS"]
    assert len(conflicts[0].evidence) == 2
    assert any("Later Review" in line for line in conflicts[0].evidence)


@pytest.mark.parametrize("stage", ["_load_catalog", "_load_document", "_load_facts"])
def test_failed_replacement_preserves_previous_graph(
    graph, catalog, sample_path, tmp_path, monkeypatch, stage
):
    from intent_engine.graph import GraphUnavailable

    _ingest(graph, catalog, sample_path)
    original = (graph.document(), graph.facts(), graph.counts(), review(graph, catalog))
    load = getattr(graph, stage)

    def fail_after_load(tx, data):
        load(tx, data)
        # A real database failure after destructive work must roll the transaction back.
        tx.run("CREATE (:Decision {key: 'home_region'})").consume()

    monkeypatch.setattr(graph, stage, fail_after_load)
    changed = tmp_path / "replacement.md"
    changed.write_text("- home_region: eu-west-1\n", encoding="utf-8")
    with pytest.raises(GraphUnavailable, match="graph replacement failed"):
        _ingest(graph, catalog, changed)
    assert (graph.document(), graph.facts(), graph.counts(), review(graph, catalog)) == original


def test_client_discussion_to_owner_handoff(sample_path, tmp_path, monkeypatch):
    """Exercise actual CLI commands and Neo4j, including the unanswered-to-resolved loop."""
    runner = CliRunner()
    packet = tmp_path / "client.md"
    packet.write_text("- home_region: eu-central-1\n", encoding="utf-8")
    assert runner.invoke(app, ["ingest", str(packet)]).exit_code == 0
    open_review = runner.invoke(app, ["review", "--json"])
    assert open_review.exit_code == 1
    assert "application_owner" in {
        gap["decision_key"] for gap in json.loads(open_review.stdout)["gaps"]
    }
    out = tmp_path / "bundle"
    assert runner.invoke(app, ["emit", "--out", str(out)]).exit_code == 2
    assert not out.exists()

    packet.write_text(sample_path.read_text("utf-8"), encoding="utf-8")
    assert runner.invoke(app, ["ingest", str(packet)]).exit_code == 0
    assert runner.invoke(app, ["review"]).exit_code == 0
    assert runner.invoke(app, ["emit", "--out", str(out)]).exit_code == 0

    yaml = YAML(typ="safe")
    network = yaml.load((out / "network-config.yaml").read_text("utf-8"))
    # A representative owner edit, not a claim of a complete bank network design.
    network["vpcs"][0]["routeTables"] = [{"name": "OwnerPrivateRoutes", "routes": []}]
    owner_file = tmp_path / "owner-network.yaml"
    with owner_file.open("w") as handle:
        yaml.dump(network, handle)
    original = owner_file.read_bytes()
    emitted = runner.invoke(app, ["emit", "--out", str(out), "--network-config", str(owner_file)])
    assert emitted.exit_code == 0, emitted.output
    assert owner_file.read_bytes() == original
    assert yaml.load((out / "network-config.yaml").read_text("utf-8")) == network
    handoff = yaml.load((out / "decision-trace.yaml").read_text("utf-8"))["integrationContext"]
    assert handoff["layers"]["network"]["source"]["origin"] == "owner-file"
    assert handoff["status"] == "requires-owner-validation"

    # Local schema validation is always available; absent external tools remain visible.
    monkeypatch.setattr("intent_engine.scan.shutil.which", lambda _: None)
    scanned = runner.invoke(app, ["scan", str(out), "--json"])
    assert scanned.exit_code == 1
    reports = json.loads(scanned.stdout)
    assert reports[0]["tool"] == "lza-schema" and reports[0]["status"] == "passed"
    assert all(report["status"] == "not-installed" for report in reports[1:])


def test_organisation_discussion_then_lza_export(graph, tmp_path):
    """Real CLI, Neo4j and OPA: references survive the corrected document reload."""
    import shutil
    from pathlib import Path

    from typer.testing import CliRunner

    from intent_engine.cli import app

    if shutil.which("opa") is None:
        pytest.skip("OPA not installed")
    sample = Path(__file__).resolve().parents[1] / "samples" / "organisation"
    runner = CliRunner()
    loaded = runner.invoke(
        app,
        ["ingest", str(sample / "client.md"), "--organisation", str(sample / "organisation.yaml")],
    )
    assert loaded.exit_code == 0, loaded.output
    reviewed = runner.invoke(app, ["review", "--json"])
    assert reviewed.exit_code == 1, reviewed.output
    result = json.loads(reviewed.output)
    assert [gap["decision_key"] for gap in result["gaps"]] == ["hybrid_connection"]
    assert "estate.md:5" in result["gaps"][0]["evidence"][0]
    assert [c["code"] for c in result["conflicts"]] == ["ORG_POLICY_CONFLICT"]
    assert "us-east-1" in result["conflicts"][0]["message"]
    assert any("policy.rego:3" in e for e in result["conflicts"][0]["evidence"])
    out = tmp_path / "lza"
    blocked = runner.invoke(app, ["emit", "--out", str(out)])
    assert blocked.exit_code == 2
    assert not out.exists()
    assert graph.counts()["System"] == 4
    assert graph.counts()["Integration"] == 2
    assert graph.counts()["Assessment"] == 1

    # No repeated organisation flag: corrections preserve its selected snapshot.
    loaded = runner.invoke(app, ["ingest", str(sample / "confirmed.md")])
    assert loaded.exit_code == 0, loaded.output
    reviewed = runner.invoke(app, ["review", "--json"])
    assert reviewed.exit_code == 0, reviewed.output
    clean = json.loads(reviewed.output)
    assert clean["organisation"] == result["organisation"]
    assert clean["assessments"][0]["status"] == "passed"
    assert clean["assessments"][0]["input_sha256"] != result["assessments"][0]["input_sha256"]
    emitted = runner.invoke(app, ["emit", "--out", str(out)])
    assert emitted.exit_code == 0, emitted.output
    assert len(list(out.glob("*.yaml"))) == 7
    assert not (out / "handoff.yaml").exists()
    trace = YAML(typ="safe").load((out / "decision-trace.yaml").read_text())
    assert trace["organisation"]["name"] == result["organisation"]["name"]
    assert trace["policyAssessments"][0]["status"] == "passed"
    assert trace["integrationContext"]["status"] == "requires-owner-validation"

    cleared = runner.invoke(app, ["ingest", str(sample / "confirmed.md"), "--without-organisation"])
    assert cleared.exit_code == 0, cleared.output
    assert graph.organisation() is None
    assert "System" not in graph.counts()
