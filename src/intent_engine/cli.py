"""Command line interface.

ingest   read a whole document into the knowledge graph (replaces it)
status   show what the graph currently holds
review   deterministic gaps and conflicts, optionally narrated by a model
emit     write AWS LZA configuration from accepted decisions
scan     run OPA, Checkov, and Trivy over an emitted bundle
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from .analysis import review as build_review
from .catalog import CatalogError, load_catalog
from .contract import LZA_VERSION
from .emit import EmitBlocked, emit_bundle, resolve
from .extraction import extract_architecture
from .graph import GraphConfig, GraphEmpty, GraphUnavailable, KnowledgeGraph
from .ingest import IngestError, extract_facts, read_document
from .llm import LlmConfig, LlmError, deterministic_questions, narrate
from .models import Decision, Review
from .organisation import load_organisation, organisation_catalog
from .scan import ScanError, scan_bundle
from .tfvars import emit_tfvars

app = typer.Typer(add_completion=False, help=__doc__)

_KNOWN_FAILURES = (CatalogError, IngestError, GraphUnavailable, GraphEmpty, EmitBlocked, ScanError)


def _fail(message: str) -> None:
    typer.secho(message, fg=typer.colors.RED, err=True)
    raise typer.Exit(code=2)


def _graph(
    uri: str | None, user: str | None, password: str | None, database: str | None
) -> KnowledgeGraph:
    base = GraphConfig.from_env()
    return KnowledgeGraph(
        GraphConfig(
            uri=uri or base.uri,
            user=user or base.user,
            password=password or base.password,
            database=database or base.database,
        )
    )


def _catalog(path: Path | None) -> dict[str, Decision]:
    return load_catalog(path)


_URI = typer.Option(None, "--uri", help="Neo4j bolt URI (default $NEO4J_URI).")
_USER = typer.Option(None, "--user", help="Neo4j user (default $NEO4J_USER).")
_PASSWORD = typer.Option(None, "--password", help="Neo4j password (default $NEO4J_PASSWORD).")
_DATABASE = typer.Option(None, "--database", help="Neo4j database (default $NEO4J_DATABASE).")
_CATALOG = typer.Option(None, "--catalog", help="Override the packaged decision catalog.")


@app.command()
def ingest(
    document: Path = typer.Argument(..., help="Architecture document to ingest in full."),
    catalog: Path | None = _CATALOG,
    organisation: Path | None = typer.Option(
        None, "--organisation", help="Selected organisation references and integration questions."
    ),
    without_organisation: bool = typer.Option(
        False,
        "--without-organisation",
        help="Start a case without the previous organisation snapshot.",
    ),
    extract_model: str | None = typer.Option(
        None, "--extract-model", help="Opt-in GraphRAG extraction using this Ollama model."
    ),
    base_url: str = typer.Option("http://localhost:11434", "--base-url"),
    uri: str | None = _URI,
    user: str | None = _USER,
    password: str | None = _PASSWORD,
    database: str | None = _DATABASE,
) -> None:
    """Replace the graph with the decision catalog and one complete document."""
    try:
        if organisation and without_organisation:
            raise IngestError("choose --organisation or --without-organisation, not both")
        base_catalog = _catalog(catalog)
        parsed = read_document(document)
        with _graph(uri, user, password, database) as graph:
            # Corrections keep the selected reference snapshot unless explicitly refreshed.
            org = (
                load_organisation(organisation, base_catalog)
                if organisation
                else graph.organisation()
            )
            if without_organisation:
                org = None
            decisions = organisation_catalog(base_catalog, org)
            facts = extract_facts(parsed, decisions)
            architecture = (
                extract_architecture(parsed, decisions, extract_model, base_url)
                if extract_model
                else None
            )
            graph.replace(decisions, parsed, facts, architecture, org)
            counts = graph.counts()
    except _KNOWN_FAILURES as exc:
        _fail(str(exc))
        return

    typer.echo(f"ingested {parsed.path} (sha256 {parsed.sha256[:12]})")
    typer.echo(f"statements: {len(parsed.statements)}  facts: {len(facts)}")
    typer.echo("graph: " + ", ".join(f"{label}={total}" for label, total in counts.items()))


@app.command()
def status(
    uri: str | None = _URI,
    user: str | None = _USER,
    password: str | None = _PASSWORD,
    database: str | None = _DATABASE,
) -> None:
    """Show the ingested document and node counts."""
    try:
        with _graph(uri, user, password, database) as graph:
            path, sha256 = graph.document()
            counts = graph.counts()
    except _KNOWN_FAILURES as exc:
        _fail(str(exc))
        return
    typer.echo(f"document: {path} (sha256 {sha256[:12]})")
    typer.echo("graph: " + ", ".join(f"{label}={total}" for label, total in counts.items()))


@app.command()
def review(
    catalog: Path | None = _CATALOG,
    as_json: bool = typer.Option(False, "--json", help="Emit the review as JSON."),
    llm_provider: str | None = typer.Option(
        None, "--llm", help="Narrate the review with 'openai' or 'ollama'."
    ),
    model: str | None = typer.Option(
        None, "--model", help="Explicit model name. Required with --llm."
    ),
    base_url: str = typer.Option("http://localhost:11434", "--base-url", help="Provider base URL."),
    api_key: str | None = typer.Option(None, "--api-key", help="Provider API key when required."),
    uri: str | None = _URI,
    user: str | None = _USER,
    password: str | None = _PASSWORD,
    database: str | None = _DATABASE,
) -> None:
    """Report gaps and conflicts found deterministically in the graph."""
    try:
        with _graph(uri, user, password, database) as graph:
            decisions = graph.catalog()
            if catalog is not None:
                selected = organisation_catalog(_catalog(catalog), graph.organisation())
                if selected != decisions:
                    raise CatalogError("catalog differs from the ingested snapshot; ingest again")
            result = build_review(graph, decisions)
    except _KNOWN_FAILURES as exc:
        _fail(str(exc))
        return

    if as_json:
        typer.echo(result.model_dump_json(indent=2))
    else:
        _render(result, decisions)

    if llm_provider:
        _narrate(result, decisions, llm_provider, model, base_url, api_key)
    if not result.clean:
        raise typer.Exit(code=1)


def _render(result: Review, decisions: dict[str, Decision]) -> None:
    typer.echo(f"document: {result.document} (sha256 {result.sha256[:12]})")
    typer.echo(
        f"applicable decisions: {len(result.applicable)}  answered: {len(result.answered)}  "
        f"gaps: {len(result.gaps)}  conflicts: {len(result.conflicts)}"
    )
    _render_context(result)
    for warning in result.architecture.warnings:
        typer.echo(f"extraction: {warning}")
    if result.architecture.nodes:
        typer.echo("\nextracted proposals — confirm answers in the document and ingest again:")
        for node in result.architecture.nodes:
            props = node.properties
            summary = (
                f"{props['decision_key']}: {props['value']}"
                if node.label == "Candidate"
                else props["name"]
            )
            typer.echo(f"  - {summary} [{props['statement_id']}]: {props['quote']}")
    if result.gaps:
        typer.secho("\ngaps", fg=typer.colors.YELLOW)
        for gap in result.gaps:
            default = f"  [default available: {gap.default}]" if gap.default else ""
            blocks = f"  [blocks: {', '.join(gap.blocks)}]" if gap.blocks else ""
            typer.echo(f"  - {gap.decision_key}: {gap.question}{default}{blocks}")
            for evidence in gap.evidence:
                typer.echo(f"      evidence: {evidence}")
    if result.conflicts:
        typer.secho("\nconflicts", fg=typer.colors.RED)
        for conflict in result.conflicts:
            typer.echo(f"  - {conflict.code}: {conflict.message}")
            for line in conflict.evidence:
                typer.echo(f"      evidence: {line}")
    if result.clean:
        typer.secho("\nno gaps, no conflicts", fg=typer.colors.GREEN)
    else:
        typer.echo("\nquestions to take to the client:")
        for line in deterministic_questions(result, decisions):
            typer.echo(f"  - {line}")


def _render_context(result: Review) -> None:
    if result.organisation:
        typer.echo(f"organisation: {result.organisation.name} (selected reference snapshot)")
        for system in result.organisation.systems:
            typer.echo(f"  {system.lifecycle}: {system.name}")
        for assessment in result.assessments:
            typer.echo(
                f"  policy {assessment.policy_id}: {assessment.status} — {assessment.message}"
            )
    if result.integration_context:
        typer.echo("\nIntegration work for the consuming teams:")
        layers = result.integration_context.get("layers", {})
        if isinstance(layers, dict):
            for name, layer in layers.items():
                typer.echo(f"  {name}: {layer['ownerAction']}")


def _narrate(
    result: Review,
    decisions: dict[str, Decision],
    provider: str,
    model: str | None,
    base_url: str,
    api_key: str | None,
) -> None:
    try:
        config = LlmConfig(provider=provider, model=model or "", base_url=base_url, api_key=api_key)
        agenda = narrate(result, decisions, config)
    except LlmError as exc:
        typer.secho(f"llm narration unavailable: {exc}", fg=typer.colors.YELLOW, err=True)
        return
    typer.secho("\nmodel agenda (advisory, not a decision source)", fg=typer.colors.CYAN)
    typer.echo(agenda)


@app.command()
def emit(
    out: Path = typer.Option(..., "--out", help="Directory to write the LZA bundle into."),
    catalog: Path | None = _CATALOG,
    allow_defaults: bool = typer.Option(
        False, "--allow-defaults", help="Fill unanswered decisions from catalog defaults."
    ),
    network_config: Path | None = typer.Option(
        None, "--network-config", help="Owner's LZA network configuration; replaces the skeleton."
    ),
    uri: str | None = _URI,
    user: str | None = _USER,
    password: str | None = _PASSWORD,
    database: str | None = _DATABASE,
) -> None:
    """Write AWS LZA configuration. Blocked by any gap or conflict."""
    try:
        with _graph(uri, user, password, database) as graph:
            decisions = graph.catalog()
            if catalog is not None:
                selected = organisation_catalog(_catalog(catalog), graph.organisation())
                if selected != decisions:
                    raise CatalogError("catalog differs from the ingested snapshot; ingest again")
            result = build_review(graph, decisions)
            facts = graph.facts()
        resolution = resolve(decisions, result, facts, allow_defaults=allow_defaults)
        written = emit_bundle(resolution, result, out, network_config=network_config)
    except _KNOWN_FAILURES as exc:
        _fail(str(exc))
        return
    defaulted = [entry["decision"] for entry in resolution.trace if entry["origin"] == "default"]
    for path in written:
        typer.echo(f"wrote {path}")
    typer.echo(f"LZA {LZA_VERSION} schemas passed; integration context is in decision-trace.yaml")
    if defaulted:
        typer.secho(f"filled from catalog defaults: {', '.join(defaulted)}", fg=typer.colors.YELLOW)


@app.command("emit-tfvars")
def export_tfvars(
    contract: Path = typer.Option(
        ..., "--contract", help="Module JSON Schema with decision mappings."
    ),
    out: Path = typer.Option(..., "--out"),
    catalog: Path | None = _CATALOG,
    uri: str | None = _URI,
    user: str | None = _USER,
    password: str | None = _PASSWORD,
    database: str | None = _DATABASE,
) -> None:
    """Export confirmed values and evidence. No Terraform resources or execution."""
    try:
        with _graph(uri, user, password, database) as graph:
            decisions = graph.catalog()
            if catalog is not None:
                selected = organisation_catalog(_catalog(catalog), graph.organisation())
                if selected != decisions:
                    raise CatalogError("catalog differs from the ingested snapshot; ingest again")
            result = build_review(graph, decisions)
            facts = graph.facts()
        resolution = resolve(decisions, result, facts)
        paths = emit_tfvars(resolution, result, contract, out)
    except _KNOWN_FAILURES as exc:
        _fail(str(exc))
        return
    for path in paths:
        typer.echo(f"wrote {path}")
    typer.echo("module input contract passed; downstream Terraform validation remains required")


@app.command()
def scan(
    bundle: Path = typer.Argument(..., help="Emitted bundle directory."),
    policy: Path | None = typer.Option(None, "--policy", help="Override the packaged rego policy."),
    as_json: bool = typer.Option(False, "--json", help="Emit results as JSON."),
) -> None:
    """Run OPA, Checkov, and Trivy over an emitted bundle."""
    try:
        results = scan_bundle(bundle, policy)
    except _KNOWN_FAILURES as exc:
        _fail(str(exc))
        return

    if as_json:
        payload: list[dict[str, Any]] = [
            {
                "tool": result.tool,
                "status": result.status,
                "detail": result.detail,
                "findings": result.findings,
            }
            for result in results
        ]
        typer.echo(json.dumps(payload, indent=2))
    else:
        for result in results:
            colour = {
                "passed": typer.colors.GREEN,
                "findings": typer.colors.RED,
                "not-installed": typer.colors.YELLOW,
                "not-assessed": typer.colors.YELLOW,
                "error": typer.colors.RED,
            }[result.status]
            typer.secho(f"{result.tool}: {result.status} — {result.detail}", fg=colour)
            for finding in result.findings:
                typer.echo(f"    {finding}")

    if any(result.blocking for result in results):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
