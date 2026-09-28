"""Native vector retrieval and GraphRAG with real Neo4j and controlled model output."""

import hashlib
import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from intent_engine.cli import app
from intent_engine.graph import GraphConfig, KnowledgeGraph
from intent_engine.rag import LlmError, ask_case, index_case

pytestmark = pytest.mark.skipif(
    not os.environ.get("NEO4J_PASSWORD"), reason="set NEO4J_PASSWORD for isolated graph tests"
)
SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "organisation"


@pytest.fixture
def graph():
    with KnowledgeGraph(GraphConfig.from_env()) as connected:
        yield connected


@pytest.fixture
def models(monkeypatch):
    from neo4j_graphrag.embeddings.ollama import OllamaEmbeddings
    from neo4j_graphrag.llm import OllamaLLM
    from neo4j_graphrag.llm.types import LLMResponse

    calls = []

    def embed(self, text, **kwargs):
        relevant = "identity provider" in text.lower() or text == "identity"
        jitter = int(hashlib.sha256(text.encode()).hexdigest()[:4], 16) / 655360
        return [1.0, 0.1, 0.01 + jitter] if relevant else [0.1, 1.0, 0.01 + jitter]

    def invoke(self, input, **kwargs):
        calls.append(input)
        prompt = input[-1]["content"] if isinstance(input, list) else input
        provider = "Okta" if "Okta" in prompt else "Microsoft Entra ID"
        source = next(
            s
            for line in prompt.splitlines()
            if line.startswith('{"score":')
            for s in json.loads(line)["evidence"]
            if "existing workforce identity provider" in s["text"]
        )
        return LLMResponse(
            content=f"The stated identity provider is {provider} [{source['citation']}]."
        )

    monkeypatch.setattr(OllamaEmbeddings, "embed_query", embed)
    monkeypatch.setattr(OllamaLLM, "invoke", invoke)
    return calls


def ingest(packet, organisation=None):
    args = ["ingest", str(packet)]
    if organisation:
        args += ["--organisation", str(organisation)]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output


def test_native_pipeline_changes_with_input_not_code(graph, models, tmp_path):
    """Same question/implementation, different estate; retrieval and answer both change."""
    ingest(SAMPLE / "client.md", SAMPLE / "organisation.yaml")
    count = index_case(graph, "controlled-embedding", "http://unused")
    assert count > 0
    before_facts = graph.facts()
    original = ask_case(graph, "Which identity provider is stated?", "controlled", "http://unused")
    assert "Microsoft Entra ID" in original["answer"]
    assert any(s["id"] == "reference:estate:3" for s in original["sources"])
    assert any("workforce_federation:" in s["text"] for s in original["sources"])
    assert all(len(s["sha256"]) == 64 for s in original["sources"])
    assert original["advisory"] is True
    assert graph.facts() == before_facts
    assert [g["decision_key"] for g in original["findings"]["gaps"]] == ["hybrid_connection"]
    blocked = CliRunner().invoke(app, ["emit", "--out", str(tmp_path / "blocked")])
    assert blocked.exit_code == 2
    assert not (tmp_path / "blocked").exists()

    # Keep the identical model, catalog and queries. Only caller-supplied inputs change.
    for path in SAMPLE.iterdir():
        if path.is_file():
            text = (
                path.read_text()
                .replace("Microsoft Entra ID", "Okta")
                .replace("Entra ID", "Okta")
                .replace("entra-saml-scim", "okta-saml-scim")
            )
            if path.name == "client.md":
                text += "\nhybrid_connection: direct-connect\n"
            (tmp_path / path.name).write_text(text)
    ingest(tmp_path / "client.md", tmp_path / "organisation.yaml")
    with pytest.raises(LlmError, match="index this case"):
        ask_case(graph, "Which identity provider is stated?", "controlled", "http://unused")
    assert len(models) == 1
    index_case(graph, "controlled-embedding", "http://unused")
    changed = ask_case(graph, "Which identity provider is stated?", "controlled", "http://unused")
    assert "Okta" in changed["answer"]
    assert changed["findings"]["gaps"] == []
    assert any("hybrid_connection: direct-connect" in s["text"] for s in changed["sources"])
    original_source = next(s for s in original["sources"] if s["id"] == "reference:estate:3")
    changed_source = next(s for s in changed["sources"] if s["id"] == "reference:estate:3")
    assert original_source["sha256"] != changed_source["sha256"]
    assert "Okta" in changed_source["text"]
    assert graph.organisation().references[0].sha256 == changed_source["sha256"]
    # Retrieval is from the frozen case, not mutable host files.
    (tmp_path / "estate.md").unlink()
    assert (
        ask_case(graph, "Which identity provider is stated?", "controlled", "http://unused")[
            "sources"
        ]
        == changed["sources"]
    )


def test_index_failure_preserves_sources_and_existing_index(graph, models, monkeypatch):
    from neo4j_graphrag.embeddings.ollama import OllamaEmbeddings

    ingest(SAMPLE / "client.md", SAMPLE / "organisation.yaml")
    index_case(graph, "controlled-embedding", "http://unused")
    sources = graph.organisation()
    facts = graph.facts()

    def unavailable(*args, **kwargs):
        raise TimeoutError("embedding service unavailable")

    monkeypatch.setattr(OllamaEmbeddings, "embed_query", unavailable)
    with pytest.raises(TimeoutError):
        index_case(graph, "unavailable", "http://unused")
    assert graph.organisation() == sources
    assert graph.facts() == facts
    assert graph._run("MATCH (d:Document) RETURN d.embedding_model AS model") == [
        {"model": "controlled-embedding"}
    ]


def test_invented_citation_and_model_failure_are_not_answers(graph, models, monkeypatch):
    from neo4j_graphrag.llm import OllamaLLM
    from neo4j_graphrag.llm.types import LLMResponse

    ingest(SAMPLE / "client.md", SAMPLE / "organisation.yaml")
    index_case(graph, "controlled-embedding", "http://unused")
    facts = graph.facts()
    for text, error in (
        ("Approved [S999].", "outside the retrieved evidence"),
        ("Approved.", "no evidence citations"),
        ("", "no usable answer"),
    ):
        monkeypatch.setattr(OllamaLLM, "invoke", lambda *a, **kw: LLMResponse(content=text))
        with pytest.raises(LlmError, match=error):
            ask_case(graph, "identity", "controlled", "http://unused")

    def unavailable(*args, **kwargs):
        raise TimeoutError("answer service unavailable")

    monkeypatch.setattr(OllamaLLM, "invoke", unavailable)
    response = CliRunner().invoke(app, ["ask", "identity", "--model", "controlled"])
    assert response.exit_code == 2
    assert "answer unavailable" in response.output
    assert graph.facts() == facts


def test_cli_requires_models_and_returns_evidence_json(graph, models):
    runner = CliRunner()
    assert runner.invoke(app, ["index"]).exit_code == 2
    assert runner.invoke(app, ["ask", "identity"]).exit_code == 2
    ingest(SAMPLE / "client.md", SAMPLE / "organisation.yaml")
    assert runner.invoke(app, ["index", "--embedding-model", "controlled"]).exit_code == 0
    answered = runner.invoke(app, ["ask", "identity", "--model", "controlled", "--json"])
    assert answered.exit_code == 0, answered.output
    result = json.loads(answered.output)
    assert result["sources"] and result["findings"]["gaps"]
    assert result["embedding_model"] == "controlled"


@pytest.mark.parametrize("vector", [[], [0.0, 0.0], [float("nan"), 1.0]])
def test_unusable_embeddings_never_publish_an_index(graph, models, monkeypatch, vector):
    from neo4j_graphrag.embeddings.ollama import OllamaEmbeddings

    ingest(SAMPLE / "client.md", SAMPLE / "organisation.yaml")
    monkeypatch.setattr(OllamaEmbeddings, "embed_query", lambda *args, **kwargs: vector)
    with pytest.raises(LlmError, match="unusable vectors"):
        index_case(graph, "bad", "http://unused")
    with pytest.raises(LlmError, match="index this case"):
        ask_case(graph, "identity", "controlled", "http://unused")


def test_excessive_context_stops_before_generation(graph, models, tmp_path):
    packet = tmp_path / "long.md"
    packet.write_text(
        "\n".join("An identity provider statement " + str(i) + "x" * 3900 for i in range(12))
    )
    result = CliRunner().invoke(app, ["ingest", str(packet), "--without-organisation"])
    assert result.exit_code == 0, result.output
    index_case(graph, "controlled", "http://unused")
    with pytest.raises(LlmError, match="reduce --top-k"):
        ask_case(graph, "identity", "controlled", "http://unused")
    assert models == []


def test_custom_scenario_and_module_contract_need_no_case_specific_code(graph, models, tmp_path):
    """Caller-defined question/input names work without the packaged LZA catalog."""
    packet = tmp_path / "client.md"
    packet.write_text(
        "runtime_site: datacentre\nOkta is the existing workforce identity provider.\n"
    )
    catalog = tmp_path / "questions.json"
    catalog.write_text(
        json.dumps(
            [
                {
                    "key": "runtime_site",
                    "label": "Runtime site",
                    "category": "application",
                    "type": "enum",
                    "options": ["edge", "datacentre"],
                    "question": "Where will this run?",
                }
            ]
        )
    )
    contract = tmp_path / "module.json"
    contract.write_text(
        json.dumps(
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["site"],
                "x-module": {"source": "caller/runtime", "version": "1.0"},
                "properties": {
                    "site": {
                        "type": "string",
                        "enum": ["edge", "datacentre"],
                        "x-decision": "runtime_site",
                    }
                },
            }
        )
    )
    organisation = tmp_path / "references.json"
    organisation.write_text(
        json.dumps(
            {
                "name": "Caller-supplied runtime scenario",
                "references": [{"id": "module", "path": "module.json", "kind": "context"}],
                "systems": [],
                "integrations": [],
                "questions": [],
                "policies": [],
            }
        )
    )
    runner = CliRunner()
    loaded = runner.invoke(
        app, ["ingest", str(packet), "--catalog", str(catalog), "--organisation", str(organisation)]
    )
    assert loaded.exit_code == 0, loaded.output
    index_case(graph, "controlled", "http://unused")
    result = ask_case(graph, "Which identity provider is stated?", "controlled", "http://unused")
    assert "Okta" in result["answer"]
    assert result["findings"]["answered"] == ["runtime_site"]
    assert result["findings"]["integration_context"] == {}
    assert not result["findings"]["gaps"] and not result["findings"]["conflicts"]
    out = tmp_path / "variables"
    emitted = runner.invoke(app, ["emit-tfvars", "--contract", str(contract), "--out", str(out)])
    assert emitted.exit_code == 0, emitted.output
    assert json.loads((out / "terraform.tfvars.json").read_text()) == {"site": "datacentre"}
    assert len(graph.facts()) == 1  # The model's identity answer did not create a Fact.
