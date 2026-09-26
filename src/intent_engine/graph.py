"""Neo4j knowledge graph.

The graph owns four kinds of node:

    (:Decision)  a question a human must answer, from the catalog
    (:Document)  the ingested source document
    (:Statement) one prose line of that document
    (:Fact)      an accepted answer, bound to the statement that carries it

    (:Decision)-[:REQUIRES]->(:Decision)
    (:Decision)-[:GATED_BY {equals}]->(:Decision)
    (:Statement)-[:FROM]->(:Document)
    (:Fact)-[:ANSWERS]->(:Decision)
    (:Fact)-[:EVIDENCE]->(:Statement)

This module owns the whole database it connects to. Ingest replaces every node.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from neo4j import Driver, GraphDatabase
from neo4j.exceptions import (
    AuthError,
    ConfigurationError,
    Neo4jError,
    ServiceUnavailable,
)

from .models import Conflict, Decision, Document, Fact, Gap

_CONSTRAINT = (
    "CREATE CONSTRAINT decision_key IF NOT EXISTS "
    "FOR (d:Decision) REQUIRE d.key IS UNIQUE"
)


class GraphUnavailable(Exception):
    """Neo4j could not be reached or refused the credentials."""


class GraphEmpty(Exception):
    """Neo4j is reachable but no document has been ingested."""


@dataclass(frozen=True)
class GraphConfig:
    uri: str
    user: str
    password: str
    database: str | None = None

    @classmethod
    def from_env(cls) -> GraphConfig:
        # 127.0.0.1, not localhost: the container binds IPv4 only, and localhost
        # makes the driver try ::1 first and report a second, irrelevant failure.
        return cls(
            uri=os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687"),
            user=os.environ.get("NEO4J_USER", "neo4j"),
            password=os.environ.get("NEO4J_PASSWORD", ""),
            database=os.environ.get("NEO4J_DATABASE") or None,
        )


class KnowledgeGraph:
    def __init__(self, config: GraphConfig) -> None:
        self._config = config
        if not config.password:
            raise GraphUnavailable("NEO4J_PASSWORD is not set; refusing to connect anonymously")
        try:
            driver: Driver = GraphDatabase.driver(config.uri, auth=(config.user, config.password))
        except (ValueError, ConfigurationError) as exc:
            raise GraphUnavailable(f"{config.uri}: not a usable Bolt URI: {exc}") from exc

        # A rejected password and an absent database need different fixes, so they
        # get different messages. Close the driver either way; a leaked driver
        # warns from its destructor long after the real error is gone.
        try:
            driver.verify_connectivity()
        except AuthError as exc:
            driver.close()
            raise GraphUnavailable(
                f"{config.uri}: Neo4j rejected the credentials for user '{config.user}'"
            ) from exc
        except (ServiceUnavailable, Neo4jError) as exc:
            driver.close()
            raise GraphUnavailable(
                f"{config.uri}: nothing is answering Bolt there. Start the database with "
                f"`docker compose up -d --wait`, then retry. ({exc})"
            ) from exc
        self._driver = driver

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> KnowledgeGraph:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        try:
            records, _, _ = self._driver.execute_query(
                query, parameters_=params, database_=self._config.database
            )
        except Neo4jError as exc:
            raise GraphUnavailable(f"query failed: {exc}") from exc
        return [record.data() for record in records]

    # ------------------------------------------------------------------ write

    def replace(
        self, catalog: dict[str, Decision], document: Document, facts: list[Fact]
    ) -> None:
        """Wipe the database and load the catalog plus one complete document."""
        self._run("MATCH (n) DETACH DELETE n")
        self._run(_CONSTRAINT)
        self._load_catalog(catalog)
        self._load_document(document)
        self._load_facts(facts)

    def _load_catalog(self, catalog: dict[str, Decision]) -> None:
        self._run(
            """
            UNWIND $decisions AS d
            MERGE (n:Decision {key: d.key})
            SET n.label = d.label, n.category = d.category, n.type = d.type,
                n.question = d.question, n.options = d.options,
                n.default = d.default, n.hint = d.hint
            """,
            decisions=[
                {
                    "key": d.key,
                    "label": d.label,
                    "category": d.category,
                    "type": d.type,
                    "question": d.question,
                    "options": d.options,
                    "default": d.default,
                    "hint": d.hint,
                }
                for d in catalog.values()
            ],
        )
        self._run(
            """
            UNWIND $edges AS e
            MATCH (d:Decision {key: e.source})
            MATCH (dep:Decision {key: e.target})
            MERGE (d)-[:REQUIRES]->(dep)
            """,
            edges=[
                {"source": d.key, "target": required}
                for d in catalog.values()
                for required in d.requires
            ],
        )
        self._run(
            """
            UNWIND $edges AS e
            MATCH (d:Decision {key: e.source})
            MATCH (p:Decision {key: e.target})
            MERGE (d)-[:GATED_BY {equals: e.equals}]->(p)
            """,
            edges=[
                {"source": d.key, "target": d.gate.decision, "equals": d.gate.equals}
                for d in catalog.values()
                if d.gate is not None
            ],
        )

    def _load_document(self, document: Document) -> None:
        self._run(
            """
            CREATE (doc:Document {path: $path, sha256: $sha256, ingested_at: $ingested_at})
            WITH doc
            UNWIND $statements AS s
            CREATE (st:Statement {id: s.id, text: s.text, section: s.section, line: s.line})
            CREATE (st)-[:FROM]->(doc)
            """,
            path=document.path,
            sha256=document.sha256,
            ingested_at=datetime.now(UTC).isoformat(timespec="seconds"),
            statements=[s.model_dump() for s in document.statements],
        )

    def _load_facts(self, facts: list[Fact]) -> None:
        if not facts:
            return
        self._run(
            """
            UNWIND $facts AS f
            MATCH (d:Decision {key: f.decision_key})
            CREATE (fa:Fact {value: f.value, section: f.section, line: f.line,
                             origin: f.origin})
            CREATE (fa)-[:ANSWERS]->(d)
            WITH fa, f
            OPTIONAL MATCH (st:Statement {id: f.statement_id})
            FOREACH (evidence IN CASE WHEN st IS NULL THEN [] ELSE [st] END |
                CREATE (fa)-[:EVIDENCE]->(evidence))
            """,
            facts=[f.model_dump() for f in facts],
        )

    # ------------------------------------------------------------------- read

    def document(self) -> tuple[str, str]:
        rows = self._run("MATCH (d:Document) RETURN d.path AS path, d.sha256 AS sha256")
        if not rows:
            raise GraphEmpty("no document in the graph; run `ingest` first")
        return rows[0]["path"], rows[0]["sha256"]

    def facts(self) -> list[Fact]:
        rows = self._run(
            """
            MATCH (f:Fact)-[:ANSWERS]->(d:Decision)
            RETURN d.key AS decision_key, f.value AS value, f.section AS section,
                   f.line AS line, f.origin AS origin
            ORDER BY d.key, f.line
            """
        )
        return [Fact.model_validate(row) for row in rows]

    def gaps(self, applicable: list[str]) -> list[Gap]:
        """Applicable decisions with no answering fact, plus what they block."""
        rows = self._run(
            """
            UNWIND $applicable AS key
            MATCH (d:Decision {key: key})
            WHERE NOT EXISTS { MATCH (:Fact)-[:ANSWERS]->(d) }
            OPTIONAL MATCH (blocked:Decision)-[:REQUIRES]->(d)
            RETURN d.key AS decision_key, d.question AS question, d.category AS category,
                   d.default AS default, collect(DISTINCT blocked.key) AS blocks
            ORDER BY category, decision_key
            """,
            applicable=applicable,
        )
        return [
            Gap(
                decision_key=row["decision_key"],
                question=row["question"],
                category=row["category"],
                default=row["default"],
                blocks=sorted(key for key in row["blocks"] if key),
            )
            for row in rows
        ]

    def contradictions(self) -> list[Conflict]:
        """Two statements answering one decision with different values."""
        rows = self._run(
            """
            MATCH (f1:Fact)-[:ANSWERS]->(d:Decision)<-[:ANSWERS]-(f2:Fact)
            WHERE elementId(f1) < elementId(f2) AND f1.value <> f2.value
            RETURN d.key AS key, d.label AS label,
                   f1.value AS first_value, f1.section AS first_section, f1.line AS first_line,
                   f2.value AS second_value, f2.section AS second_section, f2.line AS second_line
            ORDER BY d.key
            """
        )
        return [
            Conflict(
                code="CONTRADICTORY_STATEMENTS",
                message=(
                    f"{row['label']} is stated twice with different values: "
                    f"'{row['first_value']}' and '{row['second_value']}'"
                ),
                decision_keys=[row["key"]],
                evidence=[
                    f"{row['first_section']}:{row['first_line']} -> {row['first_value']}",
                    f"{row['second_section']}:{row['second_line']} -> {row['second_value']}",
                ],
            )
            for row in rows
        ]

    def counts(self) -> dict[str, int]:
        rows = self._run(
            """
            MATCH (n)
            UNWIND labels(n) AS label
            RETURN label, count(*) AS total
            ORDER BY label
            """
        )
        return {row["label"]: row["total"] for row in rows}
