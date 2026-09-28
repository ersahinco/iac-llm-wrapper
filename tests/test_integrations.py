"""Exercise upstream graph extraction and the module input boundary offline."""

import asyncio
import json
from pathlib import Path

import pytest

from intent_engine.catalog import load_catalog
from intent_engine.emit import EmitBlocked, resolve
from intent_engine.extraction import build_architecture, extract_architecture, validate_architecture
from intent_engine.ingest import IngestError, extract_facts, read_document
from intent_engine.models import Architecture, Review
from intent_engine.tfvars import emit_tfvars

VPC = Path(__file__).resolve().parents[1] / "samples" / "vpc"


@pytest.fixture
def proposal():
    return {
        "nodes": [
            {
                "id": "vpc",
                "label": "System",
                "properties": {
                    "name": "AWS landing zone",
                    "lifecycle": "planned",
                    "statement_id": "s4",
                    "quote": (
                        "The planned AWS landing zone must connect "
                        "to the existing enterprise network."
                    ),
                },
            },
            {
                "id": "cidr",
                "label": "Candidate",
                "properties": {
                    "decision_key": "network_cidr",
                    "value": "10.42.0.0/16",
                    "statement_id": "s7",
                    "quote": "The approved VPC address range is 10.42.0.0/16.",
                },
            },
        ],
        "relationships": [{"start_node_id": "cidr", "end_node_id": "vpc", "type": "ABOUT"}],
    }


@pytest.mark.parametrize("bad_link", [False, True])
def test_real_graphrag_component_with_controlled_model(proposal, bad_link):
    pytest.importorskip("neo4j_graphrag")
    from neo4j_graphrag.llm import LLMInterface
    from neo4j_graphrag.llm.types import LLMResponse

    if bad_link:
        proposal["relationships"][0]["end_node_id"] = "absent"

    class ControlledModel(LLMInterface):
        def invoke(self, input, **kwargs):
            assert "network_cidr" in input and "[s7]" in input
            return LLMResponse(content=json.dumps(proposal))

        async def ainvoke(self, input, **kwargs):
            return self.invoke(input, **kwargs)

    document = read_document(VPC / "requirements.md")
    catalog = load_catalog(VPC / "decisions.yaml")
    result = asyncio.run(build_architecture(document, catalog, ControlledModel("test")))
    assert len(result.nodes) == 2
    if bad_link:
        assert result.relationships == []
        assert result.warnings
    else:
        assert result.relationships[0].end_node_id == result.nodes[0].id
        assert not result.warnings
    assert extract_facts(document, catalog) == []  # proposals are not confirmed answers


def test_ollama_adapter_preserves_structured_format(monkeypatch, proposal):
    pytest.importorskip("neo4j_graphrag")
    from neo4j_graphrag.llm import OllamaLLM
    from neo4j_graphrag.llm.types import LLMResponse

    def respond(self, input, **kwargs):
        assert self.model_params["format"]["type"] == "object"
        assert self.model_params["options"]["temperature"] == 0
        return LLMResponse(content=json.dumps(proposal))

    monkeypatch.setattr(OllamaLLM, "invoke", respond)
    result = extract_architecture(
        read_document(VPC / "requirements.md"),
        load_catalog(VPC / "decisions.yaml"),
        "explicit-model",
        "http://localhost:11434",
    )
    assert len(result.nodes) == 2


@pytest.mark.parametrize("change", ["quote", "key", "endpoint", "label", "duplicate"])
def test_bad_extraction_is_rejected(proposal, change):
    if change == "quote":
        proposal["nodes"][1]["properties"]["quote"] = "Invented bank approval"
    elif change == "key":
        proposal["nodes"][1]["properties"]["decision_key"] = "invented_decision"
    elif change == "endpoint":
        proposal["relationships"][0]["end_node_id"] = "absent"
    elif change == "label":
        proposal["relationships"][0]["type"] = "CONNECTS_TO"
    else:
        proposal["nodes"].append(proposal["nodes"][0])
    with pytest.raises(IngestError):
        validate_architecture(
            Architecture.model_validate(proposal),
            read_document(VPC / "requirements.md"),
            load_catalog(VPC / "decisions.yaml"),
        )


def vpc_resolution():
    catalog = load_catalog(VPC / "decisions.yaml")
    doc = read_document(VPC / "confirmed.md")
    facts = extract_facts(doc, catalog)
    review = Review(
        document=doc.path,
        sha256=doc.sha256,
        applicable=list(catalog),
        answered=list(catalog),
        gaps=[],
        conflicts=[],
        facts=facts,
    )
    return resolve(catalog, review, facts), review


def test_export_community_vpc_inputs_and_provenance(tmp_path):
    resolution, review = vpc_resolution()
    paths = emit_tfvars(resolution, review, VPC / "module-inputs.json", tmp_path)
    values = json.loads(paths[0].read_text())
    assert values == {
        "name": "banking-app",
        "cidr": "10.42.0.0/16",
        "azs": ["eu-central-1a", "eu-central-1b"],
        "private_subnets": ["10.42.1.0/24", "10.42.2.0/24"],
    }
    trace = json.loads(paths[1].read_text())
    assert trace["module"]["version"] == "6.7.3"
    assert trace["sourceSha256"] == review.sha256
    assert trace["variables"]["cidr"]["decision"] == "network_cidr"
    assert len(trace["contractSha256"]) == 64


@pytest.mark.parametrize("change", ["type", "mapping", "module", "remote_ref", "required"])
def test_invalid_module_contract_blocks_before_writing(tmp_path, change):
    schema = json.loads((VPC / "module-inputs.json").read_text())
    if change == "type":
        schema["properties"]["cidr"]["type"] = "boolean"
    elif change == "mapping":
        schema["properties"]["cidr"]["x-decision"] = "missing"
    elif change == "module":
        del schema["x-module"]
    elif change == "remote_ref":
        schema["properties"]["cidr"]["$ref"] = "https://invalid.example/schema"
    else:
        schema["required"].append("missing_input")
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps(schema))
    resolution, review = vpc_resolution()
    with pytest.raises(EmitBlocked):
        emit_tfvars(resolution, review, contract, tmp_path / "output")
    assert not (tmp_path / "output").exists()
