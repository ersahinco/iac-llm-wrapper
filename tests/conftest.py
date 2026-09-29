from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest

from intent_engine.analysis import applicable_keys
from intent_engine.catalog import load_catalog
from intent_engine.graph import GraphConfig, KnowledgeGraph
from intent_engine.ingest import extract_facts, read_document
from intent_engine.models import Conflict, Decision, Document, Fact, Review

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "banking-packet.md"


@pytest.fixture
def graph():
    config = GraphConfig(
        uri=os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687"),
        user=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", ""),
        database=os.environ.get("NEO4J_DATABASE") or None,
    )
    if not config.password:
        pytest.skip("set NEO4J_PASSWORD for isolated graph tests")
    with KnowledgeGraph(config) as connected:
        yield connected


@pytest.fixture(scope="session")
def sample_path() -> Path:
    return SAMPLE


@pytest.fixture(scope="session")
def catalog() -> dict[str, Decision]:
    return load_catalog()


@pytest.fixture(scope="session")
def sample_document() -> Document:
    return read_document(SAMPLE)


@pytest.fixture(scope="session")
def sample_facts(sample_document: Document, catalog: dict[str, Decision]) -> list[Fact]:
    return extract_facts(sample_document, catalog)


@pytest.fixture
def make_review(catalog: dict[str, Decision]) -> Callable[..., Review]:
    """A review as the graph would report it, without needing Neo4j."""

    def factory(facts: list[Fact], conflicts: Iterable[Conflict] = ()) -> Review:
        return Review(
            document=str(SAMPLE),
            sha256="0" * 64,
            applicable=sorted(applicable_keys(catalog, facts)),
            answered=sorted({fact.decision_key for fact in facts}),
            gaps=[],
            conflicts=list(conflicts),
            facts=facts,
        )

    return factory
