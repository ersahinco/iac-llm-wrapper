"""Tests for deterministic Markdown pre-processor."""

from __future__ import annotations

from intent_engine.core.markdown_extractor import MarkdownExtractor
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
