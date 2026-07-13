"""AWS LZA structured entity recovery tests."""

from __future__ import annotations

from intent_engine.patterns.aws_lza.entities import (
    apply_llm_entities,
    extract_markdown_entities,
    merge_markdown_entities,
)
from intent_engine.patterns.aws_lza.models import AwsLzaIntent, LzaAccount


def test_extracts_ous_and_accounts():
    text = """# Design

## Organizational Units
- Security: Security baseline OU
- Infrastructure: Shared services OU

## Accounts
- Network: ou=Infrastructure, description=Central networking
- Audit: ou=Security, description=Audit and compliance
"""

    result = extract_markdown_entities(text)

    assert result["ous"] == [
        {"name": "Security", "description": "Security baseline OU"},
        {"name": "Infrastructure", "description": "Shared services OU"},
    ]
    assert result["accounts"] == [
        {"name": "Network", "ou": "Infrastructure", "description": "Central networking"},
        {"name": "Audit", "ou": "Security", "description": "Audit and compliance"},
    ]


def test_entity_recovery_ignores_unstructured_and_unrelated_sections():
    text = """## Accounts
- Network: ou=Infrastructure
- This line has no colon separator

## Region
- home_region: eu-central-1
"""

    result = extract_markdown_entities(text)

    assert result == {
        "ous": [],
        "accounts": [{"name": "Network", "ou": "Infrastructure"}],
    }


def test_entity_recovery_supports_h3_headings_and_empty_sections():
    text = """### Organizational Units
- Security: Security baseline OU

## Accounts
"""

    result = extract_markdown_entities(text)

    assert result["ous"] == [{"name": "Security", "description": "Security baseline OU"}]
    assert result["accounts"] == []


def test_applies_structured_llm_entities_to_aws_intent():
    intent = AwsLzaIntent()

    apply_llm_entities(
        {
            "ous": [{"name": "Sandbox", "description": "Development accounts"}],
            "accounts": [{"name": "SandboxDev", "ou": "Sandbox"}],
        },
        intent,
    )

    assert intent.ous[0].name == "Sandbox"
    assert intent.accounts[0].ou == "Sandbox"


def test_markdown_entities_backfill_without_overriding_llm_values():
    intent = AwsLzaIntent(accounts=[LzaAccount(name="SandboxDev", description="LLM description")])

    merge_markdown_entities(
        {
            "accounts": [
                {
                    "name": "SandboxDev",
                    "ou": "Sandbox",
                    "description": "Markdown description",
                }
            ]
        },
        intent,
    )

    assert len(intent.accounts) == 1
    assert intent.accounts[0].ou == "Sandbox"
    assert intent.accounts[0].description == "LLM description"
