"""Typer CLI for iac-llm-wrapper."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import typer

from .core.artifact_review import write_review_html
from .core.bundle_compare import (
    compare_handoff_bundles,
    render_bundle_comparison_text,
    write_bundle_comparison,
    write_bundle_comparison_html,
)
from .core.cli_guidance import (
    blocked_next_step_lines,
    compile_next_step_lines,
    discovery_next_step_lines,
    sample_match_lines,
)
from .core.compiler import (
    CompileError,
    compile_design,
    compile_from_graph,
    compile_incremental_design,
    explain_report,
    generate_template,
    review_reports,
    validate_generated,
)
from .core.contracts import GLOBAL_CONTRACT_REGISTRY, TargetContract
from .core.discovery import DiscoveryEngine, generate_clarifying_questions
from .core.extractor import Extractor
from .core.graph_export import graph_to_json, graph_to_mermaid
from .core.interview import InterviewEngine
from .core.llm_caller import LLMEvidenceStore, auto_detect_llm
from .core.markdown_extractor import extract_from_markdown
from .core.pattern_check import check_pattern
from .core.patterns import GLOBAL_REGISTRY, Pattern
from .core.sample_config import GLOBAL_SAMPLE_REGISTRY, SampleConfig
from .core.suggestion import SuggestionEngine
from .patterns import load_builtin_patterns

load_builtin_patterns()

APP_NAME = "iac-llm-wrapper"
APP_VERSION = "0.1.0"

app = typer.Typer(
    name=APP_NAME,
    help="Intent-to-IaC orchestration for validated handoff artifacts",
)
graph_app = typer.Typer(help="Inspect and export requirement graphs")
app.add_typer(graph_app, name="graph")
pattern_app = typer.Typer(help="Inspect and validate registered patterns")
app.add_typer(pattern_app, name="pattern")

DEFAULT_PATTERN = "aws-lza"


def _available_patterns() -> str:
    return ", ".join(GLOBAL_REGISTRY.list())


def _write_evidence_output(evidence_output: Path | None, evidence_store: LLMEvidenceStore) -> None:
    if not evidence_output or not evidence_store.entries:
        return

    import ruamel.yaml

    evidence_output.parent.mkdir(parents=True, exist_ok=True)
    yaml = ruamel.yaml.YAML(typ="safe")
    with open(evidence_output, "w") as fh:
        yaml.dump(evidence_store.to_dict(), fh)
    typer.echo(f"LLM evidence written to: {evidence_output}")


def _default_evidence_output(
    *,
    llm_caller: object | None,
    evidence_output: Path | None,
    raw_evidence_enabled: bool,
    output: Path,
    dry_run: bool,
) -> Path | None:
    if evidence_output is not None:
        return evidence_output
    if not raw_evidence_enabled:
        return None
    if llm_caller is None or dry_run:
        return None
    return output / "raw-evidence.yaml"


def _get_pattern_or_exit(pattern: str) -> Pattern:
    if pattern not in GLOBAL_REGISTRY.list():
        typer.echo(f"Unknown pattern: {pattern}. Available: {_available_patterns()}", err=True)
        raise typer.Exit(1)
    return GLOBAL_REGISTRY.get(pattern)


def _parse_decisions_or_exit(raw_decisions: str | None) -> dict[str, Any] | None:
    if not raw_decisions:
        return None
    try:
        parsed = json.loads(raw_decisions)
    except json.JSONDecodeError as exc:
        typer.echo(f"Invalid --decisions JSON: {exc.msg}", err=True)
        typer.echo('Example: --decisions "{\\"region\\": \\"eu-central-1\\"}"', err=True)
        raise typer.Exit(1) from exc
    if not isinstance(parsed, dict):
        typer.echo("Invalid --decisions JSON: expected an object at top level", err=True)
        raise typer.Exit(1)
    return parsed


def _contracts_for_pattern_or_exit(pattern: str) -> list[TargetContract]:
    pattern_obj = _get_pattern_or_exit(pattern)
    if not pattern_obj.contracts:
        typer.echo(f"Pattern has no target contracts: {pattern}", err=True)
        raise typer.Exit(1)
    return pattern_obj.contracts


def _selected_contracts_or_exit(
    action: str,
    name: str | None,
    pattern: str | None,
) -> list[TargetContract]:
    if action == "list":
        return [GLOBAL_CONTRACT_REGISTRY.get(n) for n in GLOBAL_CONTRACT_REGISTRY.list()]
    if pattern:
        return _contracts_for_pattern_or_exit(pattern)
    if name:
        try:
            return [GLOBAL_CONTRACT_REGISTRY.get(name)]
        except KeyError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from exc
    typer.echo("Error: --name or --pattern required for show", err=True)
    raise typer.Exit(1)


def _selected_samples_or_exit(
    action: str,
    name: str | None,
    pattern: str | None,
    contract: str | None = None,
    tag: str | None = None,
) -> list[SampleConfig]:
    if action == "list":
        if pattern:
            _get_pattern_or_exit(pattern)
        samples = GLOBAL_SAMPLE_REGISTRY.find(pattern=pattern, contract=contract, tag=tag)
        return samples
    if pattern:
        _get_pattern_or_exit(pattern)
        samples = GLOBAL_SAMPLE_REGISTRY.find(pattern=pattern, contract=contract, tag=tag)
        if not samples:
            typer.echo(f"Pattern has no sample configs: {pattern}", err=True)
            raise typer.Exit(1)
        return samples
    if name:
        try:
            return [GLOBAL_SAMPLE_REGISTRY.get(name)]
        except KeyError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from exc
    typer.echo("Error: --name or --pattern required for show", err=True)
    raise typer.Exit(1)


def _emit_sample_matches(pattern: str, decisions: dict[str, Any]) -> None:
    for line in sample_match_lines(APP_NAME, pattern, decisions):
        typer.echo(line)


def _emit_compile_next_steps(
    *,
    output: Path,
    pattern: str,
    llm_used: bool,
    raw_evidence_path: Path | None,
) -> None:
    for line in compile_next_step_lines(
        APP_NAME,
        output=output,
        pattern=pattern,
        llm_used=llm_used,
        raw_evidence_path=raw_evidence_path,
    ):
        typer.echo(line)


def _emit_incremental_compile_summary(output: Path) -> None:
    report_path = output / "incremental-compile-report.yaml"
    diff_path = output / "input-diff-report.yaml"
    if not report_path.exists():
        return
    import ruamel.yaml

    yaml = ruamel.yaml.YAML(typ="safe")
    data = yaml.load(report_path.read_text()) or {}
    decisions = data.get("decisions", {}) if isinstance(data, dict) else {}
    if not isinstance(decisions, dict):
        return
    changed = decisions.get("changed", []) or []
    added = decisions.get("added", []) or []
    removed = decisions.get("removed", []) or []
    reconfirm = decisions.get("needingReconfirmation", []) or []
    reused = decisions.get("reused", []) or []
    typer.echo("")
    typer.echo("=== Incremental Compile Summary ===")
    typer.echo(f"  Reused decisions: {len(reused)}")
    typer.echo(f"  Changed decisions: {len(changed)}")
    typer.echo(f"  Added decisions: {len(added)}")
    typer.echo(f"  Removed decisions: {len(removed)}")
    typer.echo(f"  Needs re-confirmation: {len(reconfirm)}")
    if changed:
        typer.echo("  Changed keys:")
        for item in changed:
            if isinstance(item, dict):
                typer.echo(f"    - {item.get('key')}: {item.get('before')} -> {item.get('after')}")
    typer.echo(f"  Reports: {diff_path}, {report_path}")


def _emit_blocked_next_steps(output: Path) -> None:
    for line in blocked_next_step_lines(APP_NAME, output):
        typer.echo(line, err=True)


def _emit_discovery_next_steps(*, input: Path, pattern: str, complete: bool) -> None:
    for line in discovery_next_step_lines(
        APP_NAME,
        input_path=input,
        pattern=pattern,
        complete=complete,
    ):
        typer.echo(line)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"{APP_NAME} {APP_VERSION}")
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


@graph_app.command("export")
def graph_export(
    pattern: str = typer.Option(
        DEFAULT_PATTERN,
        "--pattern",
        "-p",
        help=f"Pattern to use. Available: {_available_patterns()}",
    ),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Export format: json, mermaid",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional file path. Defaults to stdout.",
    ),
) -> None:
    """Export a pattern requirement graph as JSON or Mermaid."""
    graph = _get_pattern_or_exit(pattern).create_graph()
    normalized_format = format.lower()
    if normalized_format == "json":
        rendered = graph_to_json(graph, pattern)
    elif normalized_format == "mermaid":
        rendered = graph_to_mermaid(graph, pattern)
    else:
        typer.echo("Unknown graph export format. Use: json, mermaid", err=True)
        raise typer.Exit(1)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered)
        typer.echo(f"Graph exported to: {output}")
        return
    typer.echo(rendered, nl=False)


@pattern_app.command("check")
def pattern_check(
    pattern: str = typer.Option(
        DEFAULT_PATTERN,
        "--pattern",
        "-p",
        help=f"Pattern to check. Available: {_available_patterns()}",
    ),
) -> None:
    """Validate a pattern's graph, contracts, samples, and artifact surface."""
    pattern_obj = _get_pattern_or_exit(pattern)
    result = check_pattern(pattern_obj)
    if result.violations:
        typer.echo(f"Pattern check failed: {pattern}", err=True)
        for violation in result.violations:
            typer.echo(f"  - {violation}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Pattern check passed: {pattern}")
    typer.echo(f"  Requirements: {result.requirements}")
    typer.echo(f"  Contracts: {result.contracts}")
    typer.echo(f"  Expected artifacts: {result.expected_artifacts}")
    typer.echo(f"  Samples: {result.samples}")
    typer.echo(f"  Context rules: {result.context_rules}")


@app.command()
def compile(
    input: Path = typer.Option(
        None,
        "--input",
        "-i",
        help="Markdown design doc or directory with .md files",
    ),
    baseline_bundle: Path = typer.Option(
        None,
        "--baseline-bundle",
        help="Previous generated handoff bundle for diff-aware incremental compile",
    ),
    changed_doc: Path = typer.Option(
        None,
        "--changed-doc",
        help="Changed Markdown design doc for diff-aware incremental compile",
    ),
    baseline_doc: Path = typer.Option(
        None,
        "--baseline-doc",
        help="Optional previous Markdown doc for precise document diff context",
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
        help="LLM provider: openai, ollama, bedrock",
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
        help=(
            "Path to write LLM call evidence YAML. Defaults to "
            "<output>/raw-evidence.yaml for LLM compiles."
        ),
    ),
    raw_evidence: bool = typer.Option(
        True,
        "--raw-evidence/--no-raw-evidence",
        help=(
            "Write raw LLM prompt/response evidence for local development. "
            "Use --no-raw-evidence for service-style runs that keep only "
            "trace and benchmark summaries."
        ),
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Extract and validate without generating files",
    ),
    pattern: str = typer.Option(
        DEFAULT_PATTERN,
        "--pattern",
        "-p",
        help=f"Pattern to use. Available: {_available_patterns()}",
    ),
) -> None:
    """Compile Markdown design docs into validated intent artifacts.

    The LLM extracts structured intent from plain Markdown guided by the
    requirement graph (data model). No regex, no rigid format — just
    describe your infrastructure requirements in whatever structure you prefer.
    """
    incremental = baseline_bundle is not None or changed_doc is not None
    if incremental:
        if baseline_bundle is None or changed_doc is None:
            typer.echo(
                "Error: incremental compile requires --baseline-bundle and --changed-doc",
                err=True,
            )
            raise typer.Exit(1)
        if not baseline_bundle.is_dir():
            typer.echo(f"Error: baseline bundle is not a directory: {baseline_bundle}", err=True)
            raise typer.Exit(1)
        if not changed_doc.exists():
            typer.echo(f"Error: changed doc does not exist: {changed_doc}", err=True)
            raise typer.Exit(1)
        if baseline_doc is not None and not baseline_doc.exists():
            typer.echo(f"Error: baseline doc does not exist: {baseline_doc}", err=True)
            raise typer.Exit(1)
    elif input is None:
        typer.echo(
            "Error: --input is required unless --baseline-bundle/--changed-doc are used",
            err=True,
        )
        raise typer.Exit(1)
    elif not input.exists():
        typer.echo(f"Error: input path does not exist: {input}", err=True)
        raise typer.Exit(1)

    graph = _get_pattern_or_exit(pattern).create_graph()

    evidence_store = LLMEvidenceStore()
    llm_caller = auto_detect_llm(provider=provider, api_key=api_key, base_url=base_url, model=model)
    if llm_caller is None:
        typer.echo(
            "WARNING: No LLM available — extracting from Markdown only. "
            "Set OPENAI_API_KEY or run Ollama locally for LLM-powered extraction.",
            err=True,
        )
    evidence_path = _default_evidence_output(
        llm_caller=llm_caller,
        evidence_output=evidence_output,
        raw_evidence_enabled=raw_evidence,
        output=output,
        dry_run=dry_run,
    )

    try:
        if incremental:
            assert baseline_bundle is not None
            assert changed_doc is not None
            compile_incremental_design(
                baseline_bundle=baseline_bundle,
                changed_doc=changed_doc,
                output_dir=output,
                baseline_doc=baseline_doc,
                graph=graph,
                llm_caller=llm_caller,
                evidence_store=evidence_store,
                raw_evidence_path=evidence_path,
                dry_run=dry_run,
                pattern=pattern,
            )
        else:
            assert input is not None
            compile_design(
                input,
                output,
                graph=graph,
                llm_caller=llm_caller,
                evidence_store=evidence_store,
                raw_evidence_path=evidence_path,
                dry_run=dry_run,
                pattern=pattern,
            )
    except CompileError as e:
        typer.echo("Compilation failed: handoff is blocked.", err=True)
        typer.echo("Violations:", err=True)
        for v in e.violations:
            typer.echo(f"  [{v.code}] {v.message}", err=True)
        if e.readiness and not dry_run:
            typer.echo(
                "Safe assessment artifacts written to output: "
                "decision-report.yaml, llm-trace-summary.yaml, model-benchmark.yaml",
                err=True,
            )
        _write_evidence_output(evidence_path, evidence_store)
        _emit_blocked_next_steps(output)
        typer.echo(
            "Fix violations in your Markdown and re-run. "
            f"Run '{APP_NAME} template --pattern {pattern}' to generate "
            "a valid starting template.",
            err=True,
        )
        raise typer.Exit(1) from None

    if dry_run:
        typer.echo("[Dry-run] Validation successful. No files written.")
        _write_evidence_output(evidence_path, evidence_store)
        return

    typer.echo(f"Compilation successful. Output written to: {output}")
    if incremental:
        _emit_incremental_compile_summary(output)

    _emit_sample_matches(pattern, graph.typed_decisions())
    _write_evidence_output(evidence_path, evidence_store)
    _emit_compile_next_steps(
        output=output,
        pattern=pattern,
        llm_used=llm_caller is not None,
        raw_evidence_path=evidence_path,
    )


@app.command()
def discover(
    input: Path = typer.Option(
        ...,
        "--input",
        "-i",
        help="Markdown design doc or directory with .md files",
    ),
    decisions: str = typer.Option(
        None,
        "--decisions",
        "-d",
        help='JSON object of pre-filled decisions, e.g. {"region":"eu-central-1"}',
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
        DEFAULT_PATTERN,
        "--pattern",
        "-p",
        help=f"Pattern to use. Available: {_available_patterns()}",
    ),
    provider: str = typer.Option(
        os.environ.get("INTENT_ENGINE_PROVIDER", "openai"),
        "--provider",
        help="LLM provider: openai, ollama, bedrock",
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
        help="Path to write LLM call evidence YAML",
    ),
    no_llm: bool = typer.Option(
        False,
        "--no-llm",
        help="Disable LLM extraction (defaults plus structured Markdown entities)",
    ),
    resume: Path = typer.Option(
        None,
        "--resume",
        help="Resume from a previously saved interview state file",
    ),
) -> None:
    """Run discovery analysis on a Markdown design doc or decisions.

    Shows requirement gaps, clarifying questions, and next steps.
    Use --decisions to simulate decisions before discovering.
    Use --suggest to see which questions would be asked next.
    Use --path to see the full decision path with statuses.

    When an LLM is available, the design doc prose is extracted first
    to auto-fill decisions before gap analysis. Use --no-llm to skip.
    """
    if not input.exists():
        typer.echo(f"Error: input path does not exist: {input}", err=True)
        raise typer.Exit(1)

    if resume:
        resumed = InterviewEngine.load_state(resume)
        graph = resumed.graph
        pattern = resumed.pattern
    else:
        graph = _get_pattern_or_exit(pattern).create_graph()

    if input.is_dir():
        texts = []
        for f in sorted(input.glob("*.md")):
            texts.append(f.read_text())
        text = "\n---\n".join(texts)
    else:
        text = input.read_text()

    markdown_decisions = extract_from_markdown(text, graph)
    if markdown_decisions:
        graph.apply_decisions(markdown_decisions)

    evidence_store = LLMEvidenceStore()
    llm_caller = None
    if not no_llm:
        llm_caller = auto_detect_llm(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
            task="reason",
        )

    if llm_caller is not None:
        from .core.compiler import LLMContextProvider

        llm_provider = LLMContextProvider(
            prose=text,
            graph=graph,
            llm_caller=llm_caller,
            evidence_store=evidence_store,
        )
        llm_result = llm_provider.run()
        if llm_result.decisions:
            graph.apply_decisions(llm_result.decisions)
        if llm_result.signal_decisions:
            graph.apply_decisions(llm_result.signal_decisions)

    decision_dict = _parse_decisions_or_exit(decisions)
    simulated_decisions: list[str] = []
    if decision_dict:
        simulated_decisions = graph.apply_decisions(decision_dict)

    extractor = Extractor(graph=graph)
    intent = extractor.extract(text)

    discovery = DiscoveryEngine(graph)
    result = discovery.discover(intent, text=text)

    typer.echo("=== Discovery Report ===")
    typer.echo("")

    synced = result.synced
    if synced:
        source_label = "design doc and simulated decisions" if simulated_decisions else "design doc"
        typer.echo(f"[+] Synced {len(synced)} values from {source_label}:")
        for k in synced:
            val = graph.get(k)
            typer.echo(f"    {k} = {val}")
        typer.echo("")

    if simulated_decisions:
        typer.echo(f"[+] Applied {len(simulated_decisions)} simulated decision(s):")
        for key in simulated_decisions:
            typer.echo(f"    {key} = {graph.get(key)}")
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
            for index, gap in enumerate(result.missing, 1):
                typer.echo(f"  [{index}] {gap.label}")
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
                typer.echo(f"  {i}. [{q['key']}] {q['question']}{opt_str}{def_str}")
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

    _write_evidence_output(evidence_output, evidence_store)
    _emit_discovery_next_steps(input=input, pattern=pattern, complete=result.is_complete())


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
        help='JSON object of pre-filled decisions, e.g. {"region":"eu-central-1"}',
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
        DEFAULT_PATTERN,
        "--pattern",
        "-p",
        help=f"Pattern to use. Available: {_available_patterns()}",
    ),
    save: Path = typer.Option(
        None,
        "--save",
        help="Save interview state to JSON file for later resume",
    ),
    resume: Path = typer.Option(
        None,
        "--resume",
        help="Resume interview from a previously saved state file",
    ),
    transcript: Path = typer.Option(
        None,
        "--transcript",
        help="Write interview transcript as Markdown design document",
    ),
) -> None:
    """Run guided interview to collect infrastructure decisions and produce intent artifacts."""
    from .core.interview import InterviewEngine

    if resume:
        engine = InterviewEngine.load_state(resume)
        actual_pattern = engine.pattern
        if pattern != DEFAULT_PATTERN:
            typer.echo("Warning: --pattern ignored when --resume is used", err=True)
    else:
        graph = _get_pattern_or_exit(pattern).create_graph()
        engine = InterviewEngine(graph, pattern=pattern)
        actual_pattern = pattern

    decision_dict = _parse_decisions_or_exit(decisions)
    if decision_dict:
        engine.run_from_decisions(decision_dict)

    if interactive:
        engine.run_interactive()
    elif not no_defaults:
        engine.apply_defaults_for_remaining()

    if save:
        engine.save_state(save)
        typer.echo(f"Interview state saved to: {save}")

    if transcript:
        Path(transcript).write_text(engine.to_markdown())
        typer.echo(f"Interview transcript written to: {transcript}")

    try:
        engine.to_intent()
        typer.echo(engine.summary())
        typer.echo("")
        compile_from_graph(engine.graph, output, pattern=actual_pattern)
        typer.echo(f"Compilation successful. Output written to: {output}")
        _emit_sample_matches(actual_pattern, engine.graph.typed_decisions())
        _emit_compile_next_steps(
            output=output,
            pattern=actual_pattern,
            llm_used=False,
            raw_evidence_path=None,
        )
    except CompileError as e:
        typer.echo("Compilation failed with violations:", err=True)
        for v in e.violations:
            typer.echo(f"  [{v.code}] {v.message}", err=True)
        raise typer.Exit(1)


@app.command()
def validate(
    input: Path = typer.Option(..., "--input", "-i", help="Directory containing intent artifacts"),
    pattern: str = typer.Option(
        DEFAULT_PATTERN,
        "--pattern",
        "-p",
        help=f"Pattern to use. Available: {_available_patterns()}",
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
def contract(
    action: str = typer.Argument(
        ...,
        help="Action: list, show",
    ),
    name: str = typer.Option(
        None,
        "--name",
        "-n",
        help="Contract name (for show)",
    ),
    pattern: str = typer.Option(
        None,
        "--pattern",
        "-p",
        help="Show contracts attached to a pattern",
    ),
) -> None:
    """Inspect target contracts: required decisions, artifacts, and lineage."""
    if action not in {"list", "show"}:
        typer.echo(f"Unknown action: {action}. Use: list, show", err=True)
        raise typer.Exit(1)

    contracts = _selected_contracts_or_exit(action, name, pattern)

    if action == "list":
        typer.echo("=== Target Contracts ===")
        typer.echo("")
        for contract_obj in contracts:
            typer.echo(f"  {contract_obj.name}")
            typer.echo(f"    Kind: {contract_obj.kind}")
            typer.echo(f"    Required artifacts: {len(contract_obj.required_artifacts)}")
            typer.echo(f"    Optional artifacts: {len(contract_obj.optional_artifacts)}")
            typer.echo(f"    Required decisions: {len(contract_obj.required_decisions)}")
            typer.echo(f"    Source: {contract_obj.source_url}")
            typer.echo("")
        return

    for contract_obj in contracts:
        typer.echo(f"=== {contract_obj.name} ===")
        typer.echo(f"Kind: {contract_obj.kind}")
        typer.echo(f"Source: {contract_obj.source_url}")
        typer.echo("")
        typer.echo("Required artifacts:")
        for artifact in contract_obj.artifacts:
            if not artifact.required:
                continue
            schema_hint = ""
            if artifact.required_paths:
                schema_hint = f" | paths: {', '.join(artifact.required_paths)}"
            assertion_hint = ""
            if artifact.value_assertions:
                paths = ", ".join(item.path for item in artifact.value_assertions)
                assertion_hint = f" | assertions: {paths}"
            typer.echo(f"  - {artifact.name}{schema_hint}{assertion_hint}")
        if contract_obj.optional_artifacts:
            typer.echo("")
            typer.echo("Optional artifacts:")
            for artifact in contract_obj.artifacts:
                if artifact.required:
                    continue
                schema_hint = ""
                if artifact.required_paths:
                    schema_hint = f" | paths: {', '.join(artifact.required_paths)}"
                assertion_hint = ""
                if artifact.value_assertions:
                    paths = ", ".join(item.path for item in artifact.value_assertions)
                    assertion_hint = f" | assertions: {paths}"
                typer.echo(f"  - {artifact.name}{schema_hint}{assertion_hint}")
        typer.echo("")
        typer.echo("Required decisions:")
        for decision in contract_obj.required_decisions:
            typer.echo(f"  - {decision}")
        if contract_obj.lineage:
            typer.echo("")
            typer.echo("Lineage:")
            for item in contract_obj.lineage:
                typer.echo(f"  - {item.decision} -> {item.artifact}:{item.path}")


@app.command()
def sample(
    action: str = typer.Argument(
        ...,
        help="Action: list, show",
    ),
    name: str = typer.Option(
        None,
        "--name",
        "-n",
        help="Sample config name (for show)",
    ),
    pattern: str = typer.Option(
        None,
        "--pattern",
        "-p",
        help="List or show sample configs attached to a pattern",
    ),
    contract: str = typer.Option(
        None,
        "--contract",
        help="Filter sample configs by source contract",
    ),
    tag: str = typer.Option(
        None,
        "--tag",
        help="Filter sample configs by metadata tag",
    ),
) -> None:
    """Inspect versioned sample configs: decisions, metadata, and module refs."""
    if action not in {"list", "show"}:
        typer.echo(f"Unknown action: {action}. Use: list, show", err=True)
        raise typer.Exit(1)

    samples = _selected_samples_or_exit(action, name, pattern, contract, tag)
    if action == "list" and not samples:
        typer.echo("No sample configs matched current filters.", err=True)
        raise typer.Exit(1)

    if action == "list":
        typer.echo("=== Sample Configs ===")
        typer.echo("")
        for sample_obj in samples:
            typer.echo(f"  {sample_obj.name}")
            typer.echo(f"    Pattern: {sample_obj.pattern}")
            typer.echo(f"    Version: {sample_obj.version}")
            typer.echo(f"    Release: {sample_obj.release_date}")
            if sample_obj.upstream_variant:
                typer.echo(f"    Variant: {sample_obj.upstream_variant}")
            if sample_obj.source_contract:
                typer.echo(f"    Contract: {sample_obj.source_contract}")
            typer.echo(f"    Source: {sample_obj.source_url}")
            typer.echo("")
        return

    for sample_obj in samples:
        typer.echo(f"=== {sample_obj.name} ===")
        typer.echo(f"Pattern: {sample_obj.pattern}")
        typer.echo(f"Version: {sample_obj.version}")
        typer.echo(f"Release: {sample_obj.release_date}")
        if sample_obj.description:
            typer.echo(f"Description: {sample_obj.description}")
        if sample_obj.upstream_variant:
            typer.echo(f"Upstream variant: {sample_obj.upstream_variant}")
        if sample_obj.source_contract:
            typer.echo(f"Source contract: {sample_obj.source_contract}")
        if sample_obj.tags:
            typer.echo(f"Tags: {', '.join(sample_obj.tags)}")
        typer.echo(f"Source: {sample_obj.source_url}")
        typer.echo("")
        typer.echo("Decisions:")
        for key, value in sample_obj.decisions.items():
            typer.echo(f"  - {key} = {value}")
        if sample_obj.module_refs:
            typer.echo("")
            typer.echo("Module refs:")
            for ref in sample_obj.module_refs:
                summary = f"{ref.module_name} | {ref.source} | {ref.version}"
                if ref.description:
                    summary += f" | {ref.description}"
                typer.echo(f"  - {summary}")
        if sample_obj.requires:
            typer.echo("")
            typer.echo("Requires:")
            for dependency in sample_obj.requires:
                typer.echo(f"  - {dependency}")


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
    action: str = typer.Argument(
        "diff",
        help="Action: diff, compare, html",
    ),
    before: Path = typer.Option(
        None,
        "--before",
        "-b",
        help="Before decision report for diff or artifact directory for compare",
    ),
    after: Path = typer.Option(
        None,
        "--after",
        "-a",
        help="After decision report for diff or artifact directory for compare",
    ),
    input: Path = typer.Option(
        None,
        "--input",
        "-i",
        help="Generated artifact directory for html review",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Output path for html review",
    ),
    html_output: Path = typer.Option(
        None,
        "--html-output",
        help="Optional static HTML output path for review compare",
    ),
) -> None:
    """Review generated artifacts: diff reports, compare bundles, or write static HTML."""
    if action == "html":
        if input is None or output is None:
            typer.echo("Error: review html requires --input and --output", err=True)
            raise typer.Exit(1)
        if not input.is_dir():
            typer.echo(f"Error: input path is not a directory: {input}", err=True)
            raise typer.Exit(1)
        write_review_html(input, output)
        typer.echo(f"Review HTML written to: {output}")
        return

    if action == "compare":
        if before is None or after is None:
            typer.echo("Error: review compare requires --before and --after directories", err=True)
            raise typer.Exit(1)
        if not before.is_dir():
            typer.echo(f"Error: before path is not a directory: {before}", err=True)
            raise typer.Exit(1)
        if not after.is_dir():
            typer.echo(f"Error: after path is not a directory: {after}", err=True)
            raise typer.Exit(1)
        comparison = compare_handoff_bundles(before, after)
        typer.echo(render_bundle_comparison_text(comparison), nl=False)
        if output is not None:
            write_bundle_comparison(comparison, output)
            typer.echo(f"Comparison report written to: {output}")
        if html_output is not None:
            write_bundle_comparison_html(comparison, html_output)
            typer.echo(f"Comparison HTML written to: {html_output}")
        return

    if action != "diff":
        typer.echo("Unknown review action. Use: diff, compare, html", err=True)
        raise typer.Exit(1)
    if before is None or after is None:
        typer.echo("Error: review diff requires --before and --after", err=True)
        raise typer.Exit(1)
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
def template(
    pattern: str = typer.Option(
        DEFAULT_PATTERN,
        "--pattern",
        "-p",
        help=f"Pattern to use. Available: {_available_patterns()}",
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Output path for the generated Markdown template",
    ),
) -> None:
    """Generate a Markdown design doc scaffold from a pattern."""
    _get_pattern_or_exit(pattern)

    markdown = generate_template(pattern=pattern)
    output.write_text(markdown)
    typer.echo(f"Template written to: {output}")
    typer.echo(f"  Pattern: {pattern}")


if __name__ == "__main__":
    app()
