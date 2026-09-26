"""Neo4j-backed tests.

Skipped unless NEO4J_PASSWORD is set. These wipe the target database, so point
them at the local development instance only:

    docker compose up -d
    NEO4J_PASSWORD=localdevpassword uv run --extra dev pytest tests/test_graph.py
"""

from __future__ import annotations

import os

import pytest

from intent_engine.analysis import review
from intent_engine.graph import GraphConfig, KnowledgeGraph
from intent_engine.ingest import extract_facts, read_document

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
        "- topology: hub-spoke\n"
        "- identity_center_assignments: Admins:PowerUserAccess:Management\n",
        encoding="utf-8",
    )
    _ingest(graph, catalog, path)
    gaps = {gap.decision_key: gap for gap in review(graph, catalog).gaps}

    assert "topology" not in gaps
    assert "network_account" in gaps
    assert gaps["identity_center_permission_sets"].blocks == ["identity_center_assignments"]


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
