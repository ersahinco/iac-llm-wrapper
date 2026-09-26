"""Catalog, ingest, and deterministic analysis."""

from __future__ import annotations

import pytest

from intent_engine.analysis import applicable_keys, semantic_conflicts
from intent_engine.catalog import CatalogError, coerce, load_catalog
from intent_engine.ingest import IngestError, extract_facts, read_document
from intent_engine.models import Decision, Fact


def _facts(**pairs: str) -> list[Fact]:
    return [
        Fact(decision_key=key, value=value, section="test", line=index + 1)
        for index, (key, value) in enumerate(pairs.items())
    ]


def _override(base: list[Fact], **pairs: str) -> list[Fact]:
    return [fact for fact in base if fact.decision_key not in pairs] + _facts(**pairs)


def _codes(conflicts) -> set[str]:
    return {conflict.code for conflict in conflicts}


# catalog -------------------------------------------------------------------


def test_catalog_references_resolve(catalog):
    for decision in catalog.values():
        assert all(required in catalog for required in decision.requires)
        if decision.gate:
            assert decision.gate.decision in catalog


def test_broken_catalog_names_the_defect(tmp_path):
    path = tmp_path / "decisions.yaml"
    path.write_text(
        "- key: a\n  label: A\n  category: x\n  type: string\n  question: q\n"
        "  gate: {decision: nope, equals: y}\n",
        encoding="utf-8",
    )
    with pytest.raises(CatalogError, match="gated by unknown"):
        load_catalog(path)


@pytest.mark.parametrize(
    ("kwargs", "raw", "expected"),
    [
        ({"type": "bool"}, "true", True),
        ({"type": "bool"}, "disabled", False),
        ({"type": "string_list"}, "a, b ,, c", ["a", "b", "c"]),
    ],
)
def test_coercion(kwargs, raw, expected):
    base = {"key": "k", "label": "K", "category": "c", "type": "string", "question": "q"}
    assert coerce(Decision.model_validate(base | kwargs), raw) == expected


def test_malformed_bool_is_rejected_not_defaulted(catalog):
    with pytest.raises(ValueError, match="is not a boolean"):
        coerce(catalog["centralized_logging"], "probably")


def test_unapproved_option_is_rejected(catalog):
    with pytest.raises(ValueError, match="not an approved option"):
        coerce(catalog["topology"], "mesh")


# ingest --------------------------------------------------------------------


def test_sample_answers_every_decision(sample_facts, catalog, sample_document):
    values = {fact.decision_key: fact.value for fact in sample_facts}
    assert set(values) == set(catalog)
    assert values["topology"] == "hub-spoke"
    assert len(sample_document.sha256) == 64


def test_facts_carry_evidence(sample_facts):
    fact = next(f for f in sample_facts if f.decision_key == "network_cidr")
    assert (fact.section, fact.origin) == ("Network", "document")
    assert fact.line > 0 and fact.statement_id


def test_prose_and_fenced_code_are_not_facts(catalog, tmp_path):
    path = tmp_path / "doc.md"
    path.write_text(
        "# Notes\n\nApproved accounts:\n- confirm the pipeline owner\n- something: else\n"
        "```\n- home_region: eu-west-1\n```\n- Network Topology: single-vpc\n",
        encoding="utf-8",
    )
    facts = extract_facts(read_document(path), catalog)
    assert [(f.decision_key, f.value) for f in facts] == [("topology", "single-vpc")]


def test_missing_and_empty_documents_are_different_errors(tmp_path):
    with pytest.raises(IngestError, match="document not found"):
        read_document(tmp_path / "absent.md")
    empty = tmp_path / "empty.md"
    empty.write_text("\n\n", encoding="utf-8")
    with pytest.raises(IngestError, match="document is empty"):
        read_document(empty)


# analysis ------------------------------------------------------------------


def test_sample_packet_is_conflict_free(catalog, sample_facts):
    assert semantic_conflicts(catalog, sample_facts) == []


def test_gate_uses_stated_value_then_default(catalog):
    assert "network_account" not in applicable_keys(catalog, _facts(topology="single-vpc"))
    assert "network_account" in applicable_keys(catalog, [])


def test_unusable_value_is_not_a_gap(catalog):
    conflicts = semantic_conflicts(catalog, _facts(centralized_logging="probably"))
    assert _codes(conflicts) == {"UNUSABLE_VALUE"}
    assert conflicts[0].evidence == ["test:1"]


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"home_region": "us-east-1"}, "HOME_REGION_NOT_ENABLED"),
        ({"topology": "single-vpc"}, "NETWORK_ACCOUNT_NOT_APPLICABLE"),
        ({"network_cidr": "1.2.3.0/24"}, "NETWORK_CIDR_NOT_PRIVATE"),
        ({"network_cidr": "10.0.0.0/33"}, "NETWORK_CIDR_MALFORMED"),
        ({"centralized_logging": "false"}, "OVERLAY_REQUIRES_CENTRAL_LOGGING"),
        ({"guardduty_enabled": "false"}, "OVERLAY_REQUIRES_DETECTION"),
        ({"organizational_units": "Security, Infrastructure"}, "WORKLOAD_OU_MISSING"),
        ({"workload_accounts": "CardsProd, Audit"}, "ACCOUNT_NAME_RESERVED"),
        ({"workload_accounts": "CardsProd, NewThing"}, "ACCOUNT_EMAIL_MISSING"),
        ({"identity_center_assignments": "A:SecurityAudit:Ghost"}, "ASSIGNMENT_UNKNOWN_ACCOUNT"),
        ({"identity_center_assignments": "A:GodMode:Audit"}, "ASSIGNMENT_UNKNOWN_PERMISSION_SET"),
        ({"identity_center_assignments": "A-SecurityAudit-Audit"}, "ASSIGNMENT_MALFORMED"),
    ],
)
def test_each_rule_names_its_own_cause(catalog, sample_facts, overrides, expected):
    conflicts = semantic_conflicts(catalog, _override(sample_facts, **overrides))
    assert expected in _codes(conflicts)
