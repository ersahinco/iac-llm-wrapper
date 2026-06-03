"""Small CLI guidance renderers for human next steps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .sample_config import GLOBAL_SAMPLE_REGISTRY


def review_html_command(app_name: str, output: Path) -> str:
    return f"{app_name} review html --input {output} --output {output / 'handoff-review.html'}"


def sample_match_lines(app_name: str, pattern: str, decisions: dict[str, Any]) -> list[str]:
    matches = GLOBAL_SAMPLE_REGISTRY.find_best_matches(decisions, pattern=pattern, limit=3)
    if not matches:
        return []

    lines = ["", "=== Sample Match ==="]
    for idx, match in enumerate(matches, 1):
        sample = match.sample
        lines.append(
            "  "
            f"{idx}. {sample.name} | same {match.same_count}/{match.total_sample_decisions}"
            f" | different {match.different_count}"
            f" | missing {match.missing_count}"
        )
        if sample.source_contract:
            lines.append(f"     Contract: {sample.source_contract}")
        if sample.upstream_variant:
            lines.append(f"     Variant: {sample.upstream_variant}")
        if sample.tags:
            lines.append(f"     Tags: {', '.join(sample.tags)}")

    lines.append(f"  Run '{app_name} sample show --name {matches[0].sample.name}' for details.")
    return lines


def compile_next_step_lines(
    app_name: str,
    *,
    output: Path,
    pattern: str,
    llm_used: bool,
    raw_evidence_path: Path | None,
) -> list[str]:
    lines = [
        "",
        "Next steps:",
        f"  1. Generate the review page: {review_html_command(app_name, output)}",
        f"  2. Open {output / 'handoff-plan.yaml'} for owners, gates, and allowed action.",
        "  3. Review target artifacts and samples before using the downstream toolchain.",
        f"  Pattern: {pattern}",
    ]
    if llm_used and raw_evidence_path:
        lines.append(
            "  Raw LLM evidence captured for local debugging. "
            "Use --no-raw-evidence for service-style customer packet runs."
        )
    elif llm_used:
        lines.append(
            "  Raw LLM prompt/response evidence omitted; use llm-trace-summary.yaml "
            "and model-benchmark.yaml for review."
        )
    return lines


def blocked_next_step_lines(app_name: str, output: Path) -> list[str]:
    return [
        "",
        "Next steps:",
        f"  1. Generate the blocked review page: {review_html_command(app_name, output)}",
        "  2. Resolve the blocker questions in decision-report.yaml or the review page.",
        "  3. Re-run compile after updating the source Markdown.",
    ]


def discovery_next_step_lines(
    app_name: str,
    *,
    input_path: Path,
    pattern: str,
    complete: bool,
) -> list[str]:
    lines = ["", "=== Next Steps ==="]
    if complete:
        lines.extend(
            [
                "  Compile service-style handoff artifacts without raw prompt/response storage:",
                (
                    f"    {app_name} compile --input {input_path} --output out/ "
                    f"--pattern {pattern} --no-raw-evidence"
                ),
                f"  Then create the review page: {review_html_command(app_name, Path('out/'))}",
            ]
        )
        return lines

    lines.extend(
        [
            "  Add answers for the clarifying questions to the Markdown source.",
            (
                "  Re-run discovery until no gaps remain, then compile "
                "service-style handoff artifacts:"
            ),
            (
                f"    {app_name} compile --input {input_path} --output out/ "
                f"--pattern {pattern} --no-raw-evidence"
            ),
            f"  Then create the review page: {review_html_command(app_name, Path('out/'))}",
        ]
    )
    return lines
