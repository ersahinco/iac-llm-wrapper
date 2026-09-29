"""CLI configuration uses native option/environment precedence."""

import pytest
from typer.testing import CliRunner

from intent_engine.cli import app
from intent_engine.graph import GraphConfig, GraphEmpty


@pytest.mark.parametrize(
    "environment,options,expected",
    [
        ({}, [], GraphConfig("bolt://127.0.0.1:7687", "neo4j", "")),
        (
            {
                "URI": "bolt://env-host:7687",
                "USER": "env-user",
                "PASSWORD": "test-env",
                "DATABASE": "env-db",
            },
            [],
            GraphConfig("bolt://env-host:7687", "env-user", "test-env", "env-db"),
        ),
        (
            {
                "URI": "bolt://env-host:7687",
                "USER": "env-user",
                "PASSWORD": "test-env",
                "DATABASE": "env-db",
            },
            [
                "--uri",
                "bolt://flag-host:7687",
                "--user",
                "flag-user",
                "--password",
                "test-flag",
                "--database",
                "flag-db",
            ],
            GraphConfig("bolt://flag-host:7687", "flag-user", "test-flag", "flag-db"),
        ),
        (
            {"PASSWORD": "test-env"},
            ["--password", ""],
            GraphConfig("bolt://127.0.0.1:7687", "neo4j", ""),
        ),
    ],
)
def test_connection_options_override_environment(monkeypatch, environment, options, expected):
    for name in ("URI", "USER", "PASSWORD", "DATABASE"):
        monkeypatch.delenv(f"NEO4J_{name}", raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(f"NEO4J_{name}", value)
    seen = []

    def connect(config):
        seen.append(config)
        raise GraphEmpty("test case is empty")

    monkeypatch.setattr("intent_engine.cli.KnowledgeGraph", connect)
    result = CliRunner().invoke(app, ["status", *options])
    assert result.exit_code == 2
    assert seen == [expected]
    assert "test-env" not in result.output and "test-flag" not in result.output
