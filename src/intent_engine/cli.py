"""Typer CLI for iac-llm-wrapper."""

from __future__ import annotations

import json
import os
import tempfile
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
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
from .core.checkov_evidence import (
    build_invalid_scan_path_evidence,
    checkov_status_is_failure,
    run_checkov_evidence,
    scan_path_is_tfvars_only,
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
    validate_generated,
)
from .core.contracts import TargetContract
from .core.discovery import DiscoveryEngine, DiscoveryResult, generate_clarifying_questions
from .core.extractor import Extractor
from .core.git_incremental import (
    bundle_path_for_doc,
    git_changed_design_paths,
    git_show_text,
)
from .core.graph_export import graph_to_json, graph_to_mermaid
from .core.interview import InterviewEngine
from .core.llm_caller import LLMCaller, LLMEvidenceStore, create_llm_caller
from .core.markdown_extractor import extract_from_markdown
from .core.pattern_check import check_pattern
from .core.patterns import GLOBAL_REGISTRY, Pattern
from .core.policy import PolicyPack
from .core.sample_config import SampleConfig
from .core.yaml_utils import read_yaml_mapping, write_yaml_artifact
from .patterns import load_builtin_patterns
from .patterns.aws_lza.validation import (
    LZA_VALIDATION_EVIDENCE,
    LzaValidationError,
    validate_lza_config_bundle,
)

load_builtin_patterns()

APP_NAME = "iac-llm-wrapper"


def _installed_version() -> str:
    try:
        return distribution_version(APP_NAME)
    except PackageNotFoundError:
        return "0+unknown"


APP_VERSION = _installed_version()

app = typer.Typer(
    name=APP_NAME,
    help="Architect intent to registered target configuration handoff artifacts",
)
graph_app = typer.Typer(help="Inspect and export requirement graphs")
app.add_typer(graph_app, name="graph")
pattern_app = typer.Typer(help="Inspect and validate registered patterns")
app.add_typer(pattern_app, name="pattern")
lza_app = typer.Typer(help="AWS LZA validation-only evidence helpers")
app.add_typer(lza_app, name="lza")
shift_left_app = typer.Typer(help="Shift-left evidence helpers")
app.add_typer(shift_left_app, name="shift-left")

DEFAULT_PATTERN = "aws-lza"


def _available_patterns() -> str:
    return ", ".join(GLOBAL_REGISTRY.list())


def _write_evidence_output(evidence_output: Path | None, evidence_store: LLMEvidenceStore) -> None:
    if not evidence_output or not evidence_store.entries:
        return

    write_yaml_artifact(evidence_output, evidence_store.to_dict(), "", indent=False)
    typer.echo(f"LLM evidence written to: {evidence_output}")


def _configured_llm_or_exit(
    *, provider: str, api_key: str, base_url: str, model: str
) -> LLMCaller | None:
    try:
        return create_llm_caller(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
    except ValueError as exc:
        typer.echo(f"Invalid LLM configuration: {exc}", err=True)
        raise typer.Exit(1) from exc


def _emit_llm_fallback_warning(evidence_store: LLMEvidenceStore) -> None:
    failures = [
        str(entry.get("parse_error"))
        for entry in evidence_store.entries
        if entry.get("parse_error")
    ]
    if not failures:
        return
    typer.echo(
        "WARNING: LLM extraction failed; deterministic Markdown/default extraction continued.",
        err=True,
    )
    typer.echo(f"  First LLM error: {failures[0]}", err=True)


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


def _bundle_pattern(bundle: Path) -> Pattern | None:
    report = read_yaml_mapping(bundle / "decision-report.yaml")
    manifest = read_yaml_mapping(bundle / "context-manifest.yaml")
    pattern_name = str(report.get("pattern") or manifest.get("pattern") or "")
    if not pattern_name:
        return None
    return _get_pattern_or_exit(pattern_name)


def _selected_policy_packs_or_exit(
    pattern: Pattern | None,
    names: list[str] | None,
) -> list[PolicyPack]:
    requested = names or []
    if pattern is None:
        if requested:
            typer.echo(
                "Error: --policy-pack requires a bundle with a declared pattern.",
                err=True,
            )
            raise typer.Exit(1)
        return []
    packs_by_name = {pack.name: pack for pack in pattern.policy_packs}
    if not requested:
        return list(packs_by_name.values())
    selected = []
    missing: list[str] = []
    for name in requested:
        pack = packs_by_name.get(name)
        if pack is None:
            missing.append(name)
        elif pack not in selected:
            selected.append(pack)
    if missing:
        typer.echo(
            "Unknown policy pack(s) for pattern "
            f"{pattern.name}: {', '.join(missing)}. Available: "
            f"{', '.join(sorted(packs_by_name)) or 'none'}",
            err=True,
        )
        raise typer.Exit(1)
    return selected


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
        return GLOBAL_REGISTRY.contracts()
    if pattern:
        return _contracts_for_pattern_or_exit(pattern)
    if name:
        try:
            return [GLOBAL_REGISTRY.contract(name)]
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
        samples = GLOBAL_REGISTRY.find_samples(pattern=pattern, contract=contract, tag=tag)
        return samples
    if pattern:
        _get_pattern_or_exit(pattern)
        samples = GLOBAL_REGISTRY.find_samples(pattern=pattern, contract=contract, tag=tag)
        if not samples:
            typer.echo(f"Pattern has no sample configs: {pattern}", err=True)
            raise typer.Exit(1)
        return samples
    if name:
        try:
            return [GLOBAL_REGISTRY.sample(name)]
        except KeyError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from exc
    typer.echo("Error: --name or --pattern required for show", err=True)
    raise typer.Exit(1)


def _echo_contract_artifact(artifact: Any) -> None:
    schema_hint = (
        f" | paths: {', '.join(artifact.required_paths)}" if artifact.required_paths else ""
    )
    assertion_hint = ""
    if artifact.value_assertions:
        assertion_hint = " | assertions: " + ", ".join(
            item.path for item in artifact.value_assertions
        )
    typer.echo(f"  - {artifact.name}{schema_hint}{assertion_hint}")


def _echo_contract_list(contracts: list[TargetContract]) -> None:
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


def _echo_contract_details(contract_obj: TargetContract) -> None:
    typer.echo(f"=== {contract_obj.name} ===")
    typer.echo(f"Kind: {contract_obj.kind}")
    typer.echo(f"Source: {contract_obj.source_url}")
    typer.echo("")
    typer.echo("Required artifacts:")
    for artifact in contract_obj.artifacts:
        if artifact.required:
            _echo_contract_artifact(artifact)
    if contract_obj.optional_artifacts:
        typer.echo("")
        typer.echo("Optional artifacts:")
        for artifact in contract_obj.artifacts:
            if not artifact.required:
                _echo_contract_artifact(artifact)
    typer.echo("")
    typer.echo("Required decisions:")
    for decision in contract_obj.required_decisions:
        typer.echo(f"  - {decision}")
    if contract_obj.lineage:
        typer.echo("")
        typer.echo("Lineage:")
        for item in contract_obj.lineage:
            typer.echo(f"  - {item.decision} -> {item.artifact}:{item.path}")


def _echo_sample_list(samples: list[SampleConfig]) -> None:
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


def _echo_sample_details(sample_obj: SampleConfig) -> None:
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

    decisions = read_yaml_mapping(report_path).get("decisions", {})
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


def _read_design_text(input_path: Path) -> str:
    if input_path.is_dir():
        return "\n---\n".join(path.read_text() for path in sorted(input_path.glob("*.md")))
    return input_path.read_text()


def _apply_discovery_llm(
    *,
    text: str,
    graph: Any,
    pattern: str,
    llm_caller: LLMCaller | None,
    evidence_store: LLMEvidenceStore,
) -> None:
    if llm_caller is None:
        return
    from .core.compiler import LLMContextProvider

    llm_result = LLMContextProvider(
        prose=text,
        graph=graph,
        pattern=pattern,
        llm_caller=llm_caller,
        evidence_store=evidence_store,
    ).run()
    if llm_result.decisions:
        graph.apply_decisions(llm_result.decisions)
    if llm_result.signal_decisions:
        graph.apply_decisions(llm_result.signal_decisions)


def _echo_discovery_sync(
    result: DiscoveryResult,
    graph: Any,
    simulated_decisions: list[str],
) -> None:
    if result.synced:
        source_label = "design doc and simulated decisions" if simulated_decisions else "design doc"
        typer.echo(f"[+] Synced {len(result.synced)} values from {source_label}:")
        for key in result.synced:
            typer.echo(f"    {key} = {graph.get(key)}")
        typer.echo("")
    if simulated_decisions:
        typer.echo(f"[+] Applied {len(simulated_decisions)} simulated decision(s):")
        for key in simulated_decisions:
            typer.echo(f"    {key} = {graph.get(key)}")
        typer.echo("")


def _echo_discovery_signals(result: DiscoveryResult) -> None:
    if not result.signals:
        return
    typer.echo("[!] Detected signals from design doc:")
    for signal in result.signals:
        typer.echo(f"  Signal: {signal.signal}")
        typer.echo(f"    Context: {signal.context}")
        typer.echo(f"    Affects: {', '.join(signal.triggered_requirements)}")
    typer.echo("")


def _echo_discovery_gaps(result: DiscoveryResult, graph: Any) -> None:
    if result.is_complete():
        typer.echo("[+] No gaps found. Design is complete.")
        return

    typer.echo(f"[!] {result.total_gaps()} gap(s) found:")
    typer.echo("")
    for index, gap in enumerate(result.missing, 1):
        typer.echo(f"  [{index}] {gap.label}")
        typer.echo(f"      Reason: {gap.reason}")
        typer.echo(f"      Suggestion: {gap.suggestion}")
        typer.echo("")

    questions = generate_clarifying_questions(result, graph=graph)
    if questions:
        typer.echo("Clarifying questions to ask:")
    for index, question in enumerate(questions, 1):
        options = f" | options: {', '.join(question['options'])}" if question.get("options") else ""
        default = (
            f" | default: {question.get('default', 'none')}" if question.get("default") else ""
        )
        typer.echo(f"  {index}. [{question['key']}] {question['question']}{options}{default}")
        if question.get("context"):
            typer.echo(f"     context: {question['context']}")


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
    typer.echo(f"  Policy packs: {result.policy_packs}")
    typer.echo(f"  Context rules: {result.context_rules}")


@lza_app.command("validate")
def lza_validate(
    bundle: Path = typer.Option(
        ...,
        "--bundle",
        "-b",
        help="Generated AWS LZA handoff bundle containing LZA config YAML files",
    ),
    lza_source: Path = typer.Option(
        ...,
        "--lza-source",
        help=(
            "Local AWS LZA repository root or source directory. The command does not "
            "clone, install, synth, deploy, or mutate AWS."
        ),
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Evidence YAML path. Defaults to <bundle>/lza-validation-evidence.yaml",
    ),
) -> None:
    """Run the official AWS LZA config validator and write evidence only."""
    evidence_path = output or bundle / LZA_VALIDATION_EVIDENCE
    try:
        evidence = validate_lza_config_bundle(
            bundle_dir=bundle,
            lza_source=lza_source,
            output=output,
        )
    except LzaValidationError as exc:
        typer.echo(str(exc), err=True)
        if exc.evidence:
            typer.echo(f"Validation evidence written to: {evidence_path}", err=True)
            typer.echo(
                f"Exit code: {exc.evidence['command']['exitCode']}",
                err=True,
            )
            _echo_lza_diagnostic(exc.evidence)
        raise typer.Exit(1) from None

    typer.echo("AWS LZA config validation passed.")
    typer.echo(f"Validation evidence written to: {evidence_path}")
    typer.echo(f"Command: {' '.join(evidence['command']['argv'])}")


def _echo_lza_diagnostic(evidence: dict[str, Any]) -> None:
    diagnostic = evidence.get("diagnostic")
    if not isinstance(diagnostic, dict):
        return
    category = diagnostic.get("category")
    summary = diagnostic.get("summary")
    next_action = diagnostic.get("nextAction")
    if category:
        typer.echo(f"Diagnostic: {category}", err=True)
    if summary:
        typer.echo(f"Summary: {summary}", err=True)
    if next_action:
        typer.echo(f"Next action: {next_action}", err=True)


@shift_left_app.command("checkov")
def shift_left_checkov(
    bundle: Path = typer.Option(..., "--bundle", help="Generated handoff bundle directory."),
    scan_path: Path = typer.Option(
        ...,
        "--scan-path",
        help="Owner-provided IaC, module, or pipeline path to scan with Checkov.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Evidence output path. Defaults to <bundle>/shift-left-evidence.yaml.",
    ),
    require_pass: bool = typer.Option(
        False,
        "--require-pass",
        help="Exit non-zero when Checkov evidence is not pass.",
    ),
    policy_pack: list[str] | None = typer.Option(
        None,
        "--policy-pack",
        help="Registered policy pack to map Checkov findings against. Repeatable.",
    ),
    external_checks_dir: list[Path] | None = typer.Option(
        None,
        "--external-checks-dir",
        help="Owner-provided Checkov custom checks directory. Repeatable.",
    ),
    iac_kind: str = typer.Option(
        "",
        "--iac-kind",
        help="IaC kind for evidence classification: terraform, opentofu, or cloudformation.",
    ),
    checkov_framework: str = typer.Option(
        "",
        "--checkov-framework",
        help="Optional Checkov --framework value for owner filtering.",
    ),
    checkov_bin: str = typer.Option("checkov", "--checkov-bin", help="Checkov executable name."),
) -> None:
    """Record optional Checkov shift-left evidence without deploying anything."""
    if not bundle.is_dir():
        typer.echo(f"Error: bundle is not a directory: {bundle}", err=True)
        raise typer.Exit(1)
    if not scan_path.exists():
        typer.echo(f"Error: scan path does not exist: {scan_path}", err=True)
        raise typer.Exit(1)
    external_checks_dirs = external_checks_dir or []
    for checks_dir in external_checks_dirs:
        if not checks_dir.is_dir():
            typer.echo(f"Error: external checks dir is not a directory: {checks_dir}", err=True)
            raise typer.Exit(1)
    if iac_kind and iac_kind not in {"terraform", "opentofu", "cloudformation"}:
        typer.echo(
            "Error: --iac-kind must be one of terraform, opentofu, cloudformation.",
            err=True,
        )
        raise typer.Exit(1)
    pattern_obj = _bundle_pattern(bundle)
    selected_policy_packs = _selected_policy_packs_or_exit(pattern_obj, policy_pack)

    evidence_path = output or (bundle / "shift-left-evidence.yaml")
    if scan_path_is_tfvars_only(scan_path):
        evidence = build_invalid_scan_path_evidence(
            bundle=bundle,
            scan_path=scan_path,
            policy_packs=selected_policy_packs,
            external_checks_dirs=external_checks_dirs,
            iac_kind=iac_kind,
            checkov_framework=checkov_framework,
        )
        write_yaml_artifact(evidence_path, evidence, "")
        typer.echo(
            "Checkov evidence written with invalid-input status; "
            "provide an owner IaC/module path instead of terraform.tfvars.",
            err=True,
        )
        raise typer.Exit(1)

    evidence = run_checkov_evidence(
        bundle=bundle,
        scan_path=scan_path,
        checkov_bin=checkov_bin,
        policy_packs=selected_policy_packs,
        external_checks_dirs=external_checks_dirs,
        iac_kind=iac_kind,
        checkov_framework=checkov_framework,
    )
    write_yaml_artifact(evidence_path, evidence, "")
    status = str(evidence.get("result", {}).get("status", "unknown"))
    typer.echo(f"Checkov evidence written to: {evidence_path}")
    typer.echo(f"Checkov status: {status}")
    if require_pass and checkov_status_is_failure(evidence):
        raise typer.Exit(1)


def _compile_git_document(
    doc: dict[str, Any],
    *,
    repo_root: Path,
    base_ref: str,
    bundle_root: Path,
    output_root: Path,
    pattern: str,
    dry_run: bool,
    llm_caller: LLMCaller | None,
) -> tuple[dict[str, Any], bool]:
    doc_path = Path(str(doc["path"]))
    relative_path = str(doc["relativePath"])
    baseline_bundle = bundle_path_for_doc(bundle_root, relative_path)
    output_bundle = bundle_path_for_doc(output_root, relative_path)
    repo_relative_path = str(doc["repoRelativePath"])
    baseline_text = git_show_text(repo_root, base_ref, repo_relative_path)
    entry: dict[str, Any] = {
        "path": str(doc_path),
        "relativePath": relative_path,
        "repoRelativePath": repo_relative_path,
        "baselineDocumentAvailable": baseline_text is not None,
        "baselineBundle": str(baseline_bundle),
        "baselineBundleAvailable": baseline_bundle.is_dir(),
        "outputBundle": str(output_bundle),
        "status": "planned",
        "mode": "incremental" if baseline_text is not None else "full",
    }
    if not doc_path.exists():
        entry.update(
            status="skipped",
            reason="changed document is not present in the working tree",
        )
        return entry, True
    if dry_run:
        entry["status"] = (
            "planned-incremental"
            if baseline_text is not None and baseline_bundle.is_dir()
            else "planned-full"
            if baseline_text is None
            else "planned-skip"
        )
        return entry, False
    if baseline_text is None:
        try:
            compile_design(
                doc_path,
                output_bundle,
                pattern=pattern,
                llm_caller=llm_caller,
                evidence_store=LLMEvidenceStore(),
            )
        except CompileError as exc:
            entry["status"] = "blocked"
            entry["violations"] = [
                {"code": violation.code, "message": violation.message}
                for violation in exc.violations
            ]
            return entry, True
        entry["status"] = "compiled-full"
        return entry, False
    if not baseline_bundle.is_dir():
        entry.update(status="skipped", reason="baseline bundle is missing")
        return entry, True

    with tempfile.TemporaryDirectory() as temp_dir:
        baseline_doc = Path(temp_dir) / doc_path.name
        baseline_doc.write_text(baseline_text)
        try:
            compile_incremental_design(
                baseline_bundle=baseline_bundle,
                changed_doc=doc_path,
                output_dir=output_bundle,
                baseline_doc=baseline_doc,
                pattern=pattern,
                llm_caller=llm_caller,
                evidence_store=LLMEvidenceStore(),
            )
        except CompileError as exc:
            entry["status"] = "blocked"
            entry["violations"] = [
                {"code": violation.code, "message": violation.message}
                for violation in exc.violations
            ]
            return entry, True
    entry["status"] = "compiled-incremental"
    return entry, False


@app.command("compile-git")
def compile_git(
    base_ref: str = typer.Option(..., "--base-ref", help="Git ref for the previous design state."),
    doc_root: Path = typer.Option(..., "--doc-root", help="Directory containing design docs."),
    bundle_root: Path = typer.Option(
        ...,
        "--bundle-root",
        help="Directory containing baseline bundles, mirroring doc relative paths.",
    ),
    output_root: Path = typer.Option(
        ...,
        "--output-root",
        help="Directory for regenerated bundles and git-incremental-plan.yaml.",
    ),
    pattern: str = typer.Option(
        DEFAULT_PATTERN,
        "--pattern",
        "-p",
        help=f"Pattern to use. Available: {_available_patterns()}",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Plan affected bundles without compiling them.",
    ),
) -> None:
    """Compile only git-changed Markdown design docs into affected bundles."""
    if not doc_root.is_dir():
        typer.echo(f"Error: doc root is not a directory: {doc_root}", err=True)
        raise typer.Exit(1)
    if not bundle_root.is_dir():
        typer.echo(f"Error: bundle root is not a directory: {bundle_root}", err=True)
        raise typer.Exit(1)
    _get_pattern_or_exit(pattern)

    try:
        discovered = git_changed_design_paths(base_ref, doc_root)
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    llm_caller = _configured_llm_or_exit(
        provider=os.environ.get("INTENT_ENGINE_PROVIDER", ""),
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        base_url=os.environ.get("INTENT_ENGINE_BASE_URL", ""),
        model=os.environ.get("INTENT_ENGINE_MODEL", ""),
    )
    output_root.mkdir(parents=True, exist_ok=True)
    repo_root = Path(str(discovered["repoRoot"]))
    plan: dict[str, Any] = {
        "schemaVersion": "intent-engine/git-incremental-plan/v1",
        "baseRef": base_ref,
        "pattern": pattern,
        "repoRoot": str(repo_root),
        "docRoot": str(Path(str(discovered["docRoot"]))),
        "bundleRoot": str(bundle_root),
        "outputRoot": str(output_root),
        "changedDocuments": [],
        "skippedDocuments": discovered["skippedDocuments"],
    }
    failure_count = 0
    for doc in discovered["changedDocuments"]:
        entry, failed = _compile_git_document(
            doc,
            repo_root=repo_root,
            base_ref=base_ref,
            bundle_root=bundle_root,
            output_root=output_root,
            pattern=pattern,
            dry_run=dry_run,
            llm_caller=llm_caller,
        )
        failure_count += int(failed)
        plan["changedDocuments"].append(entry)

    plan["summary"] = {
        "changedDocumentCount": len(plan["changedDocuments"]),
        "skippedDocumentCount": len(plan["skippedDocuments"])
        + sum(1 for item in plan["changedDocuments"] if item.get("status") == "skipped"),
        "failureCount": failure_count,
        "dryRun": dry_run,
    }
    plan_path = output_root / "git-incremental-plan.yaml"
    write_yaml_artifact(plan_path, plan, "")
    typer.echo(f"Git incremental plan written to: {plan_path}")
    typer.echo(f"Changed documents: {plan['summary']['changedDocumentCount']}")
    if failure_count:
        typer.echo(f"Failures/skips: {failure_count}", err=True)
        raise typer.Exit(1)


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
        os.environ.get("INTENT_ENGINE_PROVIDER", ""),
        "--provider",
        help="LLM provider: openai, ollama, bedrock. Unset means deterministic extraction.",
    ),
    model: str = typer.Option(
        os.environ.get("INTENT_ENGINE_MODEL", ""),
        "--model",
        help="Pinned model name; required when an LLM provider is configured",
    ),
    base_url: str = typer.Option(
        os.environ.get("INTENT_ENGINE_BASE_URL", ""),
        "--base-url",
        help="Custom endpoint for OpenAI-compatible API",
    ),
    api_key: str = typer.Option(
        os.environ.get("OPENAI_API_KEY", ""),
        "--api-key",
        help="API key for LLM provider; prefer OPENAI_API_KEY to avoid shell history exposure",
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

    Structured Markdown and graph defaults form the deterministic baseline.
    An explicitly configured, pinned LLM can additionally extract prose intent.
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
    llm_caller = _configured_llm_or_exit(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
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
        _emit_llm_fallback_warning(evidence_store)
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
        _emit_llm_fallback_warning(evidence_store)
        _write_evidence_output(evidence_path, evidence_store)
        return

    typer.echo(f"Compilation successful. Output written to: {output}")
    _emit_llm_fallback_warning(evidence_store)
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
    pattern: str = typer.Option(
        DEFAULT_PATTERN,
        "--pattern",
        "-p",
        help=f"Pattern to use. Available: {_available_patterns()}",
    ),
    provider: str = typer.Option(
        os.environ.get("INTENT_ENGINE_PROVIDER", ""),
        "--provider",
        help="LLM provider: openai, ollama, bedrock. Unset means deterministic extraction.",
    ),
    model: str = typer.Option(
        os.environ.get("INTENT_ENGINE_MODEL", ""),
        "--model",
        help="Pinned model name; required when an LLM provider is configured",
    ),
    base_url: str = typer.Option(
        os.environ.get("INTENT_ENGINE_BASE_URL", ""),
        "--base-url",
        help="Custom endpoint for OpenAI-compatible API",
    ),
    api_key: str = typer.Option(
        os.environ.get("OPENAI_API_KEY", ""),
        "--api-key",
        help="API key for LLM provider; prefer OPENAI_API_KEY to avoid shell history exposure",
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
    When an LLM provider and model are configured, prose is extracted first
    to fill decisions before gap analysis. Use --no-llm to override environment config.
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

    text = _read_design_text(input)

    markdown_decisions = extract_from_markdown(text, graph)
    if markdown_decisions:
        graph.apply_decisions(markdown_decisions)

    evidence_store = LLMEvidenceStore()
    llm_caller = None
    if not no_llm:
        llm_caller = _configured_llm_or_exit(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )

    _apply_discovery_llm(
        text=text,
        graph=graph,
        pattern=pattern,
        llm_caller=llm_caller,
        evidence_store=evidence_store,
    )

    decision_dict = _parse_decisions_or_exit(decisions)
    simulated_decisions: list[str] = []
    if decision_dict:
        simulated_decisions = graph.apply_decisions(decision_dict)

    extractor = Extractor(graph=graph, pattern=pattern)
    intent = extractor.extract()

    discovery = DiscoveryEngine(graph)
    result = discovery.discover(intent, text=text)

    typer.echo("=== Discovery Report ===")
    typer.echo("")

    _echo_discovery_sync(result, graph, simulated_decisions)
    _echo_discovery_signals(result)
    _echo_discovery_gaps(result, graph)

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
        raise typer.Exit(1) from None


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
        _echo_contract_list(contracts)
        return

    for contract_obj in contracts:
        _echo_contract_details(contract_obj)


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
        _echo_sample_list(samples)
        return

    for sample_obj in samples:
        _echo_sample_details(sample_obj)


@app.command()
def explain(
    report: Path = typer.Option(..., "--report", "-r", help="Path to decision-report.yaml"),
) -> None:
    """Explain a decision report in human-readable format."""
    if not report.exists():
        typer.echo(f"Error: report file does not exist: {report}", err=True)
        raise typer.Exit(1)

    try:
        output = explain_report(report)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(output)


@app.command()
def review(
    action: str = typer.Argument(
        ...,
        help="Action: compare, html",
    ),
    before: Path = typer.Option(
        None,
        "--before",
        "-b",
        help="Before artifact directory for compare",
    ),
    after: Path = typer.Option(
        None,
        "--after",
        "-a",
        help="After artifact directory for compare",
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
    """Review generated artifacts: compare bundles or write static HTML."""
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

    typer.echo("Unknown review action. Use: compare, html", err=True)
    raise typer.Exit(1)


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
