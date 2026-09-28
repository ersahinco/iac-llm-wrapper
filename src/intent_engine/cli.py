"""Command line interface.

ingest   read a whole document into the knowledge graph (replaces it)
status   show what the graph currently holds
review   deterministic gaps, conflicts and advisory security findings
index    embed the current case for local GraphRAG retrieval
ask      retrieve evidence and answer an architecture question (advisory)
emit     write AWS LZA configuration from accepted decisions
scan     report security warnings over owner IaC or an emitted bundle
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import typer

from .analysis import review as build_review
from .catalog import CatalogError, load_catalog
from .contract import LZA_VERSION
from .emit import EmitBlocked, emit_bundle, resolve
from .extraction import extract_architecture
from .graph import GraphConfig, GraphEmpty, GraphUnavailable, KnowledgeGraph
from .ingest import IngestError, extract_facts, read_document
from .models import Assessment, Decision, Review
from .organisation import evidence_text, load_organisation, organisation_catalog
from .rag import ask_case, index_case
from .scan import ScanError, ToolResult, scan_bundle
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


_URI = typer.Option(None, "--uri", help="Neo4j bolt URI (default $NEO4J_URI).")
_USER = typer.Option(None, "--user", help="Neo4j user (default $NEO4J_USER).")
_PASSWORD = typer.Option(None, "--password", help="Neo4j password (default $NEO4J_PASSWORD).")
_DATABASE = typer.Option(None, "--database", help="Neo4j database (default $NEO4J_DATABASE).")
_CATALOG = typer.Option(None, "--catalog", help="Override the packaged decision catalog.")


def _review(graph: KnowledgeGraph, catalog: Path | None) -> tuple[Review, dict[str, Decision]]:
    decisions = graph.catalog()
    if catalog is not None:
        selected = organisation_catalog(load_catalog(catalog), graph.organisation())
        if selected != decisions:
            raise CatalogError("catalog differs from the ingested snapshot; ingest again")
    return build_review(graph, decisions), decisions


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
        base_catalog = load_catalog(catalog)
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
    if org is not None:
        action = "loaded" if organisation else "reused"
        typer.echo(f"organisation references: {action} snapshot — {org.name}")
    elif without_organisation:
        typer.echo("organisation references: cleared (--without-organisation)")
    else:
        typer.echo("organisation references: none")
    typer.echo(f"statements: {len(parsed.statements)}  facts: {len(facts)}")
    typer.echo("graph: " + ", ".join(f"{label}={total}" for label, total in counts.items()))


@app.command()
def index(
    embedding_model: str = typer.Option(
        ..., "--embedding-model", help="Installed Ollama embedding model."
    ),
    base_url: str = typer.Option("http://localhost:11434", "--base-url"),
    uri: str | None = _URI,
    user: str | None = _USER,
    password: str | None = _PASSWORD,
    database: str | None = _DATABASE,
) -> None:
    """Embed the ingested client and selected references for advisory questions."""
    try:
        with _graph(uri, user, password, database) as graph:
            count = index_case(graph, embedding_model, base_url)
    except Exception as exc:
        _fail(f"index unavailable: {exc}")
        return
    typer.echo(f"indexed {count} source statements with {embedding_model}; re-index after ingest")


@app.command()
def ask(
    question: str = typer.Argument(..., help="Architecture question about this ingested case."),
    model: str = typer.Option(..., "--model", help="Installed Ollama answer model."),
    base_url: str = typer.Option("http://localhost:11434", "--base-url"),
    top_k: int = typer.Option(4, "--top-k", min=1, max=10),
    as_json: bool = typer.Option(False, "--json"),
    uri: str | None = _URI,
    user: str | None = _USER,
    password: str | None = _PASSWORD,
    database: str | None = _DATABASE,
) -> None:
    """Retrieve case evidence and answer with native GraphRAG; answers are advisory."""
    try:
        with _graph(uri, user, password, database) as graph:
            result = ask_case(graph, question, model, base_url, top_k)
    except Exception as exc:
        _fail(f"answer unavailable: {exc}")
        return
    if as_json:
        typer.echo(json.dumps(result, indent=2))
        return
    findings = result["findings"]
    typer.echo(f"review: {len(findings['gaps'])} gaps, {len(findings['conflicts'])} conflicts")
    for assessment in findings["assessments"]:
        typer.echo(f"policy {assessment['policy_id']}: {assessment['status']}")
    typer.echo("\nDocument answers (may still have conflicts):")
    for fact in findings["facts"]:
        typer.echo(
            f"  {fact['decision_key']}: {fact['value']} ({result['document']}:{fact['line']})"
        )
    if not findings["facts"]:
        typer.echo("  none")
    typer.echo("\nMissing questions (deterministic review):")
    for gap in findings["gaps"]:
        typer.echo(f"  {gap['decision_key']}: {gap['question']}")
    if not findings["gaps"]:
        typer.echo("  none")
    typer.echo("\nadvisory answer — confirm decisions in the document and ingest again:\n")
    typer.echo(result["answer"])
    typer.echo("\nRetrieved evidence (retrieval is not proof of relevance):")
    for source in result["sources"]:
        typer.echo(
            f"  [{source['citation']}] {source['path']}:{source['line']} "
            f"(sha256 {source['sha256'][:12]}) — {source['text']}"
        )


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
    scan_path: Path | None = typer.Option(
        None, "--scan", help="Also scan an owner IaC directory or LZA bundle for security warnings."
    ),
    uri: str | None = _URI,
    user: str | None = _USER,
    password: str | None = _PASSWORD,
    database: str | None = _DATABASE,
) -> None:
    """Report gaps and conflicts found deterministically in the graph."""
    try:
        with _graph(uri, user, password, database) as graph:
            result, decisions = _review(graph, catalog)
        scans = scan_bundle(scan_path) if scan_path is not None else []
    except _KNOWN_FAILURES as exc:
        _fail(str(exc))
        return

    if as_json:
        payload = result.model_dump()
        if scan_path is not None:
            payload["security_scans"] = [asdict(scan) for scan in scans]
        typer.echo(json.dumps(payload, indent=2))
    else:
        _render(result, decisions)
        _render_scans(scans)

    if not result.clean or any(scan.blocking for scan in scans):
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
            if hint := decisions[gap.decision_key].hint:
                typer.echo(f"      hint: {hint}")
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


def _render_context(result: Review) -> None:
    if result.organisation:
        typer.echo(f"organisation: {result.organisation.name} (selected reference snapshot)")
        for system in result.organisation.systems:
            typer.echo(f"  {system.lifecycle}: {system.name}")
        for assessment in result.assessments:
            typer.echo(f"  policy {assessment.policy_id}: {assessment.status}")
        _render_policy_warnings(result, result.assessments)
    if result.integration_context:
        typer.echo("\nIntegration work for the consuming teams:")
        layers = result.integration_context.get("layers", {})
        if isinstance(layers, dict):
            for name, layer in layers.items():
                typer.echo(f"  {name}: {layer['ownerAction']}")


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
            result, decisions = _review(graph, catalog)
        resolution = resolve(decisions, result, allow_defaults=allow_defaults)
        written = emit_bundle(resolution, result, out, network_config=network_config)
    except _KNOWN_FAILURES as exc:
        _fail(str(exc))
        return
    defaulted = [entry["decision"] for entry in resolution.trace if entry["origin"] == "default"]
    for path in written:
        typer.echo(f"wrote {path}")
    _render_policy_warnings(result, resolution.assessments)
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
            result, decisions = _review(graph, catalog)
        resolution = resolve(decisions, result)
        paths = emit_tfvars(resolution, result, contract, out)
    except _KNOWN_FAILURES as exc:
        _fail(str(exc))
        return
    for path in paths:
        typer.echo(f"wrote {path}")
    _render_policy_warnings(result, resolution.assessments)
    typer.echo("module input contract passed; downstream Terraform validation remains required")


def _render_policy_warnings(result: Review, assessments: list[Assessment]) -> None:
    for assessment in assessments:
        if assessment.status != "warning":
            continue
        typer.secho(
            f"warning [{assessment.policy_id}]: {assessment.message}", fg=typer.colors.YELLOW
        )
        if result.organisation:
            policy = next(p for p in result.organisation.policies if p.id == assessment.policy_id)
            typer.echo(f"  evidence: {evidence_text(result.organisation, policy.evidence)}")


def _render_scans(results: list[ToolResult]) -> None:
    for result in results:
        status = "warning" if result.status == "findings" and not result.blocking else result.status
        colour = (
            typer.colors.RED
            if result.blocking
            else (
                typer.colors.YELLOW if result.findings or result.exceptions else typer.colors.GREEN
            )
        )
        typer.secho(f"{result.tool}: {status} — {result.detail}", fg=colour)
        for finding in result.findings:
            typer.echo(f"    {finding}")
        for exception in result.exceptions:
            typer.secho(f"    exception (still review): {exception}", fg=typer.colors.YELLOW)


@app.command()
def scan(
    bundle: Path = typer.Argument(..., help="Owner IaC directory or emitted LZA bundle."),
    policy: Path | None = typer.Option(None, "--policy", help="Override the LZA Rego policy."),
    as_json: bool = typer.Option(False, "--json", help="Emit results as JSON."),
    strict: bool = typer.Option(False, "--strict", help="Return exit 1 for security warnings too."),
) -> None:
    """Report security warnings and native exceptions; missing coverage is never a pass."""
    try:
        results = scan_bundle(bundle, policy)
    except _KNOWN_FAILURES as exc:
        _fail(str(exc))
        return
    if as_json:
        typer.echo(json.dumps([asdict(result) for result in results], indent=2))
    else:
        _render_scans(results)
    if any(result.blocking or (strict and result.status != "passed") for result in results):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
