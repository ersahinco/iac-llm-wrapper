"""Tests for deterministic Markdown pre-processor."""

from __future__ import annotations

from intent_engine.core.markdown_extractor import (
    MarkdownExtractor,
    extract_entities_from_markdown,
)
from intent_engine.core.requirements import Requirement, RequirementGraph


def test_extracts_simple_key_value():
    g = RequirementGraph()
    g.add(
        Requirement(
            key="primary_region",
            target_field="primary_region",
            label="Primary Region",
            question="Which region?",
        )
    )
    extractor = MarkdownExtractor(g)
    text = "## Region\n- primary_region: eu-west-1\n"
    decisions = extractor.extract(text)
    assert decisions == {"primary_region": "eu-west-1"}


def test_extracts_multiple_fields():
    g = RequirementGraph()
    g.add(Requirement(key="name", target_field="name", label="Name", question="Name?"))
    g.add(Requirement(key="version", target_field="version", label="Version", question="Version?"))
    extractor = MarkdownExtractor(g)
    text = "- name: prod-k8s\n- version: 1.30\n"
    decisions = extractor.extract(text)
    assert decisions["name"] == "prod-k8s"
    assert decisions["version"] == "1.30"


def test_skips_comments():
    g = RequirementGraph()
    g.add(Requirement(key="name", target_field="name", label="Name", question="Name?"))
    extractor = MarkdownExtractor(g)
    text = "# - name: should-skip\n- name: real-value\n"
    decisions = extractor.extract(text)
    assert decisions == {"name": "real-value"}


def test_validates_options():
    g = RequirementGraph()
    g.add(
        Requirement(
            key="topology",
            target_field="topology",
            label="Topology",
            question="Topology?",
            options=["hub-spoke", "single-vpc"],
        )
    )
    extractor = MarkdownExtractor(g)
    text = "- topology: HUB-SPOKE\n"
    decisions = extractor.extract(text)
    assert decisions["topology"] == "hub-spoke"


def test_returns_empty_for_no_matches():
    g = RequirementGraph()
    g.add(Requirement(key="name", target_field="name", label="Name", question="Name?"))
    extractor = MarkdownExtractor(g)
    decisions = extractor.extract("Some prose with no keys.")
    assert decisions == {}


# ---------------------------------------------------------------------------
# Entity extraction tests (deterministic accounts/OUs/workloads)
# ---------------------------------------------------------------------------


def test_extract_ous():
    text = """# Design

## Organizational Units
- Security: Security baseline OU
- Infrastructure: Shared services OU
"""
    result = extract_entities_from_markdown(text)
    assert result["ous"] == [
        {"name": "Security", "description": "Security baseline OU"},
        {"name": "Infrastructure", "description": "Shared services OU"},
    ]


def test_extract_accounts():
    text = """# Design

## Accounts
- Network: ou=Infrastructure, description=Central networking
- Audit: ou=Security, description=Audit and compliance
"""
    result = extract_entities_from_markdown(text)
    assert result["accounts"] == [
        {"name": "Network", "ou": "Infrastructure", "description": "Central networking"},
        {"name": "Audit", "ou": "Security", "description": "Audit and compliance"},
    ]


def test_extract_workloads():
    text = """# Design

## Workloads
- payments-api: target_account=PaymentsProd, network_mode=private, port=8080, cpu=512, memory=1024
"""
    result = extract_entities_from_markdown(text)
    assert len(result["workloads"]) == 1
    wl = result["workloads"][0]
    assert wl["name"] == "payments-api"
    assert wl["target_account"] == "PaymentsProd"
    assert wl["port"] == 8080
    assert isinstance(wl["port"], int)
    assert wl["cpu"] == 512
    assert isinstance(wl["cpu"], int)
    assert wl["memory"] == 1024


def test_extract_workloads_boolean_ingress():
    text = """# Design

## Workloads
- web-portal: target_account=WebPortal, network_mode=public, public_ingress=true
"""
    result = extract_entities_from_markdown(text)
    assert len(result["workloads"]) == 1
    assert result["workloads"][0]["public_ingress"] is True


def test_extract_workloads_boolean_false():
    text = """# Design

## Workloads
- api: target_account=Prod, public_ingress=false
"""
    result = extract_entities_from_markdown(text)
    assert result["workloads"][0]["public_ingress"] is False


def test_extract_all_entities():
    text = """# Design Document

## Organizational Units
- Security: Security baseline OU
- Infrastructure: Shared services OU

## Accounts
- Network: ou=Infrastructure, description=Central networking

## Workloads
- api: target_account=Network, network_mode=private, port=8080

## Region
- primary_region: eu-west-1
"""
    result = extract_entities_from_markdown(text)
    assert len(result["ous"]) == 2
    assert len(result["accounts"]) == 1
    assert len(result["workloads"]) == 1
    assert result["ous"][0]["name"] == "Security"
    assert result["accounts"][0]["name"] == "Network"
    assert result["workloads"][0]["name"] == "api"


def test_extract_entities_no_sections():
    result = extract_entities_from_markdown("# Some prose without entity sections")
    assert result == {"ous": [], "accounts": [], "workloads": []}


def test_extract_entities_malformed_lines_skipped():
    text = """## Accounts
- Network: ou=Infrastructure, description=Central networking
- This line has no colon separator
- Audit: ou=Security
"""
    result = extract_entities_from_markdown(text)
    assert len(result["accounts"]) == 2
    assert result["accounts"][0]["name"] == "Network"
    assert result["accounts"][1]["name"] == "Audit"


def test_extract_entities_h3_heading():
    text = """### Organizational Units
- Security: Security baseline OU
"""
    result = extract_entities_from_markdown(text)
    assert len(result["ous"]) == 1
    assert result["ous"][0]["name"] == "Security"


def test_extract_entities_account_no_description():
    text = """## Accounts
- Network: ou=Infrastructure
"""
    result = extract_entities_from_markdown(text)
    assert result["accounts"] == [{"name": "Network", "ou": "Infrastructure"}]


def test_extract_workloads_network_mode_str():
    text = """## Workloads
- api: target_account=Prod, network_mode=public
"""
    result = extract_entities_from_markdown(text)
    assert result["workloads"][0]["network_mode"] == "public"


def test_extract_entities_empty_section():
    text = """## Accounts

## Workloads
"""
    result = extract_entities_from_markdown(text)
    assert result["accounts"] == []
    assert result["workloads"] == []
