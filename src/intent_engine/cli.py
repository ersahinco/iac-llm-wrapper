"""Typer CLI for intent-engine."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import typer

from .core.catalog import get_catalog
from .core.compiler import (
    CompileError,
    compile_design,
    compile_from_interview,
    explain_report,
    generate_template,
    review_reports,
    validate_generated,
)
from .core.discovery import DiscoveryEngine, generate_clarifying_questions
from .core.extractor import Extractor
from .core.interview import InterviewEngine
from .core.llm_caller import LLMEvidenceStore, auto_detect_llm
from .core.patterns import ADDON_REGISTRY, GLOBAL_REGISTRY
from .core.suggestion import SuggestionEngine

# Import domain-specific modules for side-effect registration
from .patterns import (
    kubernetes,  # noqa: F401
    lza,  # noqa: F401
)
from .patterns.lza import catalog as _lza_catalog  # noqa: F401
from .patterns.lza import generators as _lza_generators  # noqa: F401

app = typer.Typer(name="intent-engine", help="Knowledge-driven infrastructure decision system")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo("intent-engine 0.1.0")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit",
        is_eager=True,
        callback=_version_callback,
    ),
) -> None:
    pass


@app.command()
def compile(
    input: Path = typer.Option(
        ...,
        "--input",
        "-i",
        help="Markdown design doc or directory",
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Output directory for generated configs",
    ),
    provider: str = typer.Option(
        os.environ.get("INTENT_ENGINE_PROVIDER", "openai"),
        "--provider",
        help="LLM provider: openai, ollama, anthropic",
    ),
    model: str = typer.Option(
        os.environ.get("INTENT_ENGINE_MODEL", ""),
        "--model",
        help="Model name (defaults to provider's default)",
    ),
    base_url: str = typer.Option(
        os.environ.get("INTENT_ENGINE_BASE_URL", ""),
        "--base-url",
        help="Custom endpoint for OpenAI-compatible API",
    ),
    api_key: str = typer.Option(
        os.environ.get("OPENAI_API_KEY", ""),
        "--api-key",
        help="API key for LLM provider",
    ),
    evidence_output: Path = typer.Option(
        None,
        "--evidence-output",
        help="Path to write LLM call evidence JSON",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Extract and validate without generating files",
    ),
    pattern: str = typer.Option(
        "baseline",
        "--pattern",
        "-p",
        help=f"Pattern to use. Available: {', '.join(GLOBAL_REGISTRY.list())}",
    ),
    addon: list[str] = typer.Option(
        [],
        "--addon",
        "-a",
        help="Composable addon to layer (repeatable: --addon pci --addon hipaa)",
    ),
) -> None:
    """Compile Markdown design docs into validated intent artifacts.

    The LLM extracts structured intent from plain Markdown guided by the
    requirement graph (data model). No regex, no rigid format — just
    describe your infrastructure requirements in whatever structure you prefer.
    """
    if not input.exists():
        typer.echo(f"Error: input path does not exist: {input}", err=True)
        raise typer.Exit(1)

    for a in addon:
        if a not in ADDON_REGISTRY.list():
            available = ", ".join(ADDON_REGISTRY.list())
            typer.echo(f"Unknown addon: {a}. Available: {available}", err=True)
            raise typer.Exit(1)

    graph = GLOBAL_REGISTRY.get(pattern).create_graph()
    if addon:
        graph = ADDON_REGISTRY.compose(graph, addon)

    evidence_store = LLMEvidenceStore()
    llm_caller = auto_detect_llm(provider=provider, api_key=api_key, base_url=base_url, model=model)

    try:
        compile_design(
            input,
            output,
            graph=graph,
            llm_caller=llm_caller,
            evidence_store=evidence_store,
            dry_run=dry_run,
            pattern=pattern,
        )
    except CompileError as e:
        typer.echo("Compilation failed with violations:", err=True)
        for v in e.violations:
            typer.echo(f"  [{v.code}] {v.message}", err=True)
        typer.echo(
            "",
            err=True,
        )
        typer.echo(
            "Fix violations in your Markdown and re-run. "
            "Run 'intent-engine template --pattern <pattern>' to generate "
            "a valid starting template.",
            err=True,
        )
        raise typer.Exit(1)

    if dry_run:
        typer.echo("[Dry-run] Validation successful. No files written.")
        if evidence_output and evidence_store.entries:
            import ruamel.yaml

            yaml = ruamel.yaml.YAML(typ="safe")
            with open(evidence_output, "w") as f:
                yaml.dump(evidence_store.to_dict(), f)
            typer.echo(f"LLM evidence written to: {evidence_output}")
        return

    typer.echo(f"Compilation successful. Output written to: {output}")


@app.command()
def discover(
    input: Path = typer.Option(
        ...,
        "--input",
        "-i",
        help="Markdown design doc or directory",
    ),
    decisions: str = typer.Option(
        None,
        "--decisions",
        "-d",
        help="JSON string of pre-filled decisions to simulate",
    ),
    suggest: bool = typer.Option(
        False,
        "--suggest",
        help="Show contextual suggestions for next decisions",
    ),
    path: bool = typer.Option(
        False,
        "--path",
        help="Preview the full decision path with current state",
    ),
    pattern: str = typer.Option(
        "baseline",
        "--pattern",
        "-p",
        help=f"Pattern to use. Available: {', '.join(GLOBAL_REGISTRY.list())}",
    ),
    addon: list[str] = typer.Option(
        [],
        "--addon",
        "-a",
        help="Composable addon to layer (repeatable: --addon pci --addon hipaa)",
    ),
) -> None:
    """Run discovery analysis on a Markdown design doc or decisions.

    Shows requirement gaps, clarifying questions, and next steps.
    Use --decisions to simulate decisions before discovering.
    Use --suggest to see which questions would be asked next.
    Use --path to see the full decision path with statuses.
    """
    if not input.exists():
        typer.echo(f"Error: input path does not exist: {input}", err=True)
        raise typer.Exit(1)

    for a in addon:
        if a not in ADDON_REGISTRY.list():
            available = ", ".join(ADDON_REGISTRY.list())
            typer.echo(f"Unknown addon: {a}. Available: {available}", err=True)
            raise typer.Exit(1)

    graph = GLOBAL_REGISTRY.get(pattern).create_graph()
    if addon:
        graph = ADDON_REGISTRY.compose(graph, addon)

    if input.is_dir():
        texts = []
        for f in sorted(input.glob("*.md")):
            texts.append(f.read_text())
        text = "\n---\n".join(texts)
    else:
        text = input.read_text()

    extractor = Extractor(graph=graph)
    intent = extractor.extract(text)

    engine = InterviewEngine(graph)

    if decisions:
        decision_dict = json.loads(decisions)
        engine.run_from_decisions(decision_dict)

    pattern_obj = GLOBAL_REGISTRY.get(pattern)
    discovery = DiscoveryEngine(
        graph,
        extra_consistency_checks=pattern_obj.extra_consistency_checks or [],
        extra_signal_detectors=pattern_obj.extra_signal_detectors or [],
    )
    result = discovery.discover(intent, text=text)

    typer.echo("=== Discovery Report ===")
    typer.echo("")

    synced = discovery.sync_intent_to_graph(intent)
    if synced:
        typer.echo(f"[+] Synced {len(synced)} values from design doc:")
        for k in synced:
            val = graph.get(k)
            typer.echo(f"    {k} = {val}")
        typer.echo("")

    if result.signals:
        typer.echo("[!] Detected signals from design doc:")
        for sig in result.signals:
            typer.echo(f"  Signal: {sig.signal}")
            typer.echo(f"    Context: {sig.context}")
            typer.echo(f"    Affects: {', '.join(sig.triggered_requirements)}")
        typer.echo("")

    if result.is_complete():
        typer.echo("[+] No gaps found. Design is complete.")
    else:
        typer.echo(f"[!] {result.total_gaps()} gap(s) found:")
        typer.echo("")

        if result.missing:
            for gap in result.missing:
                typer.echo(f"  [{gap.priority}] {gap.label}")
                typer.echo(f"      Reason: {gap.reason}")
                typer.echo(f"      Suggestion: {gap.suggestion}")
                typer.echo("")

        questions = generate_clarifying_questions(result, intent, graph=graph)
        if questions:
            typer.echo("Clarifying questions to ask:")
            for i, q in enumerate(questions, 1):
                opt_str = ""
                if q.get("options"):
                    opt_str = f" | options: {', '.join(q['options'])}"
                def_str = f" | default: {q.get('default', 'none')}" if q.get("default") else ""
                typer.echo(f"  {i}. [{q['key']}]{q['question']}{opt_str}{def_str}")
                if q.get("context"):
                    typer.echo(f"     context: {q['context']}")

    if suggest:
        typer.echo("")
        typer.echo("=== Remaining Questions (after sync) ===")
        suggest_engine = SuggestionEngine(graph)
        suggestions = suggest_engine.suggest_next()
        if not suggestions:
            typer.echo("  All requirements satisfied.")
        else:
            for i, s in enumerate(suggestions, 1):
                opt_str = f" | options: {', '.join(s.options)}" if s.options else ""
                def_str = f" | default: {s.default}" if s.default else ""
                typer.echo(f"  {i}. {s.label}: {s.question}{opt_str}{def_str}")
                if s.context:
                    typer.echo(f"     context: {s.context}")
                if s.hint:
                    typer.echo(f"     hint: {s.hint}")

    if path:
        typer.echo("")
        typer.echo("=== Decision Path Preview ===")
        suggest_engine = SuggestionEngine(graph)
        path_items = suggest_engine.preview_path()
        for item in path_items:
            status_icon = {
                "decided": "✓",
                "defaulted": "✓*",
                "pending": "?",
                "blocked": "✗",
                "skipped": "-",
            }.get(item["status"], "?")
            val = item["value"]
            ctx = f" | {item['context']}" if item["context"] else ""
            typer.echo(f"  {status_icon} {item['key']} = {val}{ctx}")


@app.command()
def interview(
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Output directory for generated configs",
    ),
    decisions: str = typer.Option(
        None,
        "--decisions",
        "-d",
        help="JSON string of pre-filled decisions",
    ),
    no_defaults: bool = typer.Option(
        False,
        "--no-defaults",
        help="Do not auto-apply defaults for unanswered questions",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        help="Run interactive interview mode",
    ),
    pattern: str = typer.Option(
        "baseline",
        "--pattern",
        "-p",
        help=f"Pattern to use. Available: {', '.join(GLOBAL_REGISTRY.list())}",
    ),
    addon: list[str] = typer.Option(
        [],
        "--addon",
        "-a",
        help="Composable addon to layer (repeatable: --addon pci --addon hipaa)",
    ),
) -> None:
    """Run guided interview to collect infrastructure decisions and produce intent artifacts."""
    for a in addon:
        if a not in ADDON_REGISTRY.list():
            available = ", ".join(ADDON_REGISTRY.list())
            typer.echo(f"Unknown addon: {a}. Available: {available}", err=True)
            raise typer.Exit(1)

    graph = GLOBAL_REGISTRY.get(pattern).create_graph()
    if addon:
        graph = ADDON_REGISTRY.compose(graph, addon)
    engine = InterviewEngine(graph)

    if decisions:
        decision_dict = json.loads(decisions)
        engine.run_from_decisions(decision_dict)

    if interactive:
        engine.run_interactive()
    elif not no_defaults:
        engine.apply_defaults_for_remaining()

    try:
        engine.to_intent()
        typer.echo(engine.summary())
        typer.echo("")
        compile_from_interview(
            engine.graph.decisions(),
            output,
            accept_defaults=not no_defaults,
            pattern=pattern,
        )
        typer.echo(f"Compilation successful. Output written to: {output}")
    except CompileError as e:
        typer.echo("Compilation failed with violations:", err=True)
        for v in e.violations:
            typer.echo(f"  [{v.code}] {v.message}", err=True)
        raise typer.Exit(1)


@app.command()
def validate(
    input: Path = typer.Option(..., "--input", "-i", help="Directory containing intent artifacts"),
    pattern: str = typer.Option(
        "baseline",
        "--pattern",
        "-p",
        help=f"Pattern to use. Available: {', '.join(GLOBAL_REGISTRY.list())}",
    ),
) -> None:
    """Validate intent artifacts."""
    if not input.is_dir():
        typer.echo(f"Error: input path is not a directory: {input}", err=True)
        raise typer.Exit(1)

    errors = validate_generated(input, pattern=pattern)
    if errors:
        typer.echo("Validation failed:", err=True)
        for err in errors:
            typer.echo(f"  - {err}", err=True)
        raise typer.Exit(1)

    typer.echo("Validation passed. All required files and controls present.")


@app.command()
def explain(
    report: Path = typer.Option(..., "--report", "-r", help="Path to decision-report.yaml"),
) -> None:
    """Explain a decision report in human-readable format."""
    if not report.exists():
        typer.echo(f"Error: report file does not exist: {report}", err=True)
        raise typer.Exit(1)

    output = explain_report(report)
    typer.echo(output)


@app.command()
def review(
    before: Path = typer.Option(
        ...,
        "--before",
        "-b",
        help="Before decision report (decision-report.yaml)",
    ),
    after: Path = typer.Option(
        ...,
        "--after",
        "-a",
        help="After decision report (decision-report.yaml)",
    ),
) -> None:
    """Diff two decision reports to show what changed between revisions."""
    if not before.exists():
        typer.echo(f"Error: before file does not exist: {before}", err=True)
        raise typer.Exit(1)
    if not after.exists():
        typer.echo(f"Error: after file does not exist: {after}", err=True)
        raise typer.Exit(1)

    diff = review_reports(before, after)

    typer.echo("=== Decision Report Review ===")
    typer.echo("")

    if diff["added"]:
        typer.echo(f"[+] Added ({len(diff['added'])}):")
        for item in diff["added"]:
            typer.echo(f"  {item['key']} = {item['value']}")
        typer.echo("")

    if diff["removed"]:
        typer.echo(f"[-] Removed ({len(diff['removed'])}):")
        for item in diff["removed"]:
            typer.echo(f"  {item['key']} = {item['value']}")
        typer.echo("")

    if diff["changes"]:
        typer.echo(f"[~] Changed ({len(diff['changes'])}):")
        for item in diff["changes"]:
            typer.echo(f"  {item['key']}: {item['before']} -> {item['after']}")
        typer.echo("")

    if not diff["added"] and not diff["removed"] and not diff["changes"]:
        typer.echo("[=] No differences found. Reports are identical.")
        typer.echo("")

    b_wa = diff["wellArchitectedCoverage"]["before"]
    a_wa = diff["wellArchitectedCoverage"]["after"]
    if b_wa or a_wa:
        typer.echo("=== Well-Architected Coverage ===")
        typer.echo(f"  Before: {len(b_wa)} pillars")
        typer.echo(f"  After:  {len(a_wa)} pillars")
        for pillar in sorted(set(b_wa) | set(a_wa)):
            b_count = len(b_wa.get(pillar, []))
            a_count = len(a_wa.get(pillar, []))
            if b_count != a_count:
                typer.echo(f"  [~] {pillar}: {b_count} -> {a_count} decisions")
        typer.echo("")

    audit = diff["audit"]
    typer.echo("=== Decision Audit Trail ===")
    typer.echo(f"  Before: {audit['before_count']} entries")
    typer.echo(f"  After:  {audit['after_count']} entries")
    if audit["new_entries"]:
        typer.echo(f"  [+] {len(audit['new_entries'])} new audit entries:")
        for entry in audit["new_entries"]:
            ts = entry.get("timestamp", "?")
            key = entry.get("key", "?")
            val = entry.get("value", "?")
            how = entry.get("how", "?")
            reason = entry.get("reason", "")
            line = f"    {ts} | {key} = {val} ({how})"
            if reason:
                line += f" | {reason}"
            typer.echo(line)


@app.command()
def catalog(
    action: str = typer.Argument(
        ...,
        help="Action: list, show, diff, apply",
    ),
    entry: str = typer.Option(
        None,
        "--entry",
        "-e",
        help="Catalog entry name (for show, diff, apply)",
    ),
    input: Path = typer.Option(
        None,
        "--input",
        "-i",
        help="Current decision JSON file (for diff)",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Output path (for apply)",
    ),
) -> None:
    """List, show, diff, or apply known-good catalog entries."""
    cat = get_catalog()

    if action == "list":
        typer.echo("=== Config Catalog ===")
        typer.echo("")
        for name in cat.list():
            e = cat.get(name)
            typer.echo(f"  {name}")
            typer.echo(f"    Pattern: {e.pattern}")
            typer.echo(f"    Tags: {', '.join(e.tags)}")
            typer.echo(f"    {e.description}")
            typer.echo("")

    elif action == "show":
        if not entry:
            typer.echo("Error: --entry required for show", err=True)
            raise typer.Exit(1)
        e = cat.get(entry)
        typer.echo(f"=== {e.name} ===")
        typer.echo(f"Description: {e.description}")
        typer.echo(f"Pattern: {e.pattern}")
        typer.echo(f"Tags: {', '.join(e.tags)}")
        typer.echo("")
        typer.echo("Decisions:")
        for k, v in e.decisions.items():
            typer.echo(f"  {k}: {v}")
        if e.notes:
            typer.echo("")
            typer.echo("Notes:")
            for role, note in e.notes.items():
                typer.echo(f"  [{role}] {note}")

    elif action == "diff":
        if not entry:
            typer.echo("Error: --entry required for diff", err=True)
            raise typer.Exit(1)
        if not input:
            typer.echo("Error: --input (decision JSON file) required for diff", err=True)
            raise typer.Exit(1)
        with open(input) as f:
            current = json.load(f)
        result = cat.diff(entry, current)
        typer.echo(f"=== Diff vs {entry} ===")
        typer.echo("")
        if result["same"]:
            typer.echo(f"Same ({len(result['same'])}):")
            for k, v in result["same"].items():
                typer.echo(f"  {k}: {v}")
        if result["different"]:
            typer.echo(f"Different ({len(result['different'])}):")
            for k, diff in result["different"].items():
                typer.echo(f"  {k}: catalog={diff['catalog']}, current={diff['current']}")
        if result["missing_in_current"]:
            typer.echo(f"Missing in current ({len(result['missing_in_current'])}):")
            for k, v in result["missing_in_current"].items():
                typer.echo(f"  {k}: {v}")
        if result["extra_in_current"]:
            typer.echo(f"Extra in current ({len(result['extra_in_current'])}):")
            for k, v in result["extra_in_current"].items():
                typer.echo(f"  {k}: {v}")

    elif action == "apply":
        if not entry:
            typer.echo("Error: --entry required for apply", err=True)
            raise typer.Exit(1)
        if not output:
            typer.echo("Error: --output required for apply", err=True)
            raise typer.Exit(1)
        current: dict[str, Any] = {}
        if input:
            with open(input) as f:
                current = json.load(f)
        merged = cat.apply_as_defaults(entry, current)
        with open(output, "w") as f:
            json.dump(merged, f, indent=2)
        typer.echo(f"Merged decisions written to {output}")
        from_catalog = len(merged) - len(current)
        typer.echo(f"  {len(merged)} total ({len(current)} current, {from_catalog} from catalog)")

    else:
        typer.echo(f"Unknown action: {action}. Use: list, show, diff, apply", err=True)
        raise typer.Exit(1)


@app.command()
def template(
    pattern: str = typer.Option(
        "baseline",
        "--pattern",
        "-p",
        help=f"Pattern to use. Available: {', '.join(GLOBAL_REGISTRY.list())}",
    ),
    addon: list[str] = typer.Option(
        [],
        "--addon",
        "-a",
        help="Composable addon to layer (repeatable: --addon pci --addon hipaa)",
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Output path for the generated Markdown template",
    ),
) -> None:
    """Generate a Markdown design doc scaffold from a pattern."""
    if pattern not in GLOBAL_REGISTRY.list():
        available = ", ".join(GLOBAL_REGISTRY.list())
        typer.echo(f"Unknown pattern: {pattern}. Available: {available}", err=True)
        raise typer.Exit(1)

    for a in addon:
        if a not in ADDON_REGISTRY.list():
            available = ", ".join(ADDON_REGISTRY.list())
            typer.echo(f"Unknown addon: {a}. Available: {available}", err=True)
            raise typer.Exit(1)

    markdown = generate_template(pattern=pattern, addon_names=addon)
    output.write_text(markdown)
    typer.echo(f"Template written to: {output}")
    typer.echo(f"  Pattern: {pattern}")
    if addon:
        typer.echo(f"  Addons: {', '.join(addon)}")


if __name__ == "__main__":
    app()
