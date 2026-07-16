"""Render local developer views for graphs, models, dependencies, and results."""

from __future__ import annotations

import argparse
import ast
import html
import re
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import BaseModel

from intent_engine.core.graph_export import graph_to_json, graph_to_mermaid
from intent_engine.core.patterns import GLOBAL_REGISTRY
from intent_engine.core.yaml_utils import read_yaml_mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src" / "intent_engine"
DEFAULT_OUTPUT = REPO_ROOT / "tests" / "results" / "dev-views"
DEFAULT_RESULTS = REPO_ROOT / "tests" / "results"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write local visual developer artifacts for intent-engine."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output directory for generated visual artifacts.",
    )
    parser.add_argument(
        "--pattern",
        action="append",
        dest="patterns",
        help="Pattern to render. Repeatable. Defaults to all registered patterns.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=DEFAULT_RESULTS,
        help="Directory containing golden journey/model benchmark results.",
    )
    args = parser.parse_args()

    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    patterns = args.patterns or GLOBAL_REGISTRY.list()

    rendered_patterns = _render_patterns(patterns, output)
    dependency_graph = _render_module_dependencies(output)
    result_artifacts = _render_result_summaries(args.results_dir, output)
    _write_index(output, rendered_patterns, dependency_graph, result_artifacts)
    print(f"Wrote developer visual artifacts to {output}")
    return 0


def _render_patterns(patterns: list[str], output: Path) -> list[dict[str, str]]:
    rendered: list[dict[str, str]] = []
    graph_dir = output / "graphs"
    model_dir = output / "models"
    graph_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    for pattern_name in patterns:
        pattern = GLOBAL_REGISTRY.get(pattern_name)
        graph = pattern.create_graph()
        graph_json = graph_dir / f"{pattern_name}-requirement-graph.json"
        graph_mmd = graph_dir / f"{pattern_name}-requirement-graph.mmd"
        model_mmd = model_dir / f"{pattern_name}-intent-model.mmd"
        graph_json.write_text(graph_to_json(graph, pattern_name))
        graph_mmd.write_text(graph_to_mermaid(graph, pattern_name))
        model_mmd.write_text(_model_to_mermaid(pattern.intent_factory, pattern_name))
        rendered.append(
            {
                "pattern": pattern_name,
                "graphJson": _relative(output, graph_json),
                "graphMermaid": _relative(output, graph_mmd),
                "modelMermaid": _relative(output, model_mmd),
            }
        )
    return rendered


def _model_to_mermaid(model: Any, pattern_name: str) -> str:
    if not isinstance(model, type) or not issubclass(model, BaseModel):
        return f"---\ntitle: {pattern_name} intent model\n---\nclassDiagram\n"

    lines = [
        "---",
        f"title: {pattern_name} intent model",
        "---",
        "classDiagram",
    ]
    seen: set[type[BaseModel]] = set()
    edges: set[tuple[str, str, str]] = set()
    _append_model_class(model, lines, edges, seen)
    for source, target, field in sorted(edges):
        lines.append(f"  {source} --> {target} : {field}")
    lines.append("")
    return "\n".join(lines)


def _append_model_class(
    model: type[BaseModel],
    lines: list[str],
    edges: set[tuple[str, str, str]],
    seen: set[type[BaseModel]],
) -> None:
    if model in seen:
        return
    seen.add(model)
    class_name = _mermaid_id(model.__name__)
    lines.append(f"  class {class_name} {{")
    for name, field_info in model.model_fields.items():
        annotation = field_info.annotation
        display_type, nested_model = _display_annotation(annotation)
        lines.append(f"    +{display_type} {name}")
        if nested_model is not None:
            target = _mermaid_id(nested_model.__name__)
            edges.add((class_name, target, name))
            _append_model_class(nested_model, lines, edges, seen)
    lines.append("  }")


def _display_annotation(annotation: Any) -> tuple[str, type[BaseModel] | None]:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is not None and type(None) in args:
        annotation = next(arg for arg in args if arg is not type(None))
        origin = get_origin(annotation)
        args = get_args(annotation)

    if origin is list:
        item = args[0] if args else Any
        item_type, nested = _display_annotation(item)
        return f"list[{item_type}]", nested

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation.__name__, annotation
    if isinstance(annotation, type):
        return annotation.__name__, None
    return str(annotation).replace("typing.", ""), None


def _render_module_dependencies(output: Path) -> str:
    code_dir = output / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    path = code_dir / "module-dependencies.mmd"
    path.write_text(_module_dependency_mermaid())
    return _relative(output, path)


def _module_dependency_mermaid() -> str:
    modules = {
        _module_name(path): path
        for path in SRC_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
    }
    edges: set[tuple[str, str]] = set()
    for module, path in modules.items():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            target_names = _import_targets(module, node, modules)
            for target in target_names:
                if target != module:
                    edges.add((module, target))

    lines = [
        "---",
        "title: intent_engine module dependencies",
        "---",
        "flowchart LR",
    ]
    for module in sorted(modules):
        lines.append(f'  {_mermaid_id(module)}["{module}"]')
    for source, target in sorted(edges):
        lines.append(f"  {_mermaid_id(source)} --> {_mermaid_id(target)}")
    lines.append("")
    return "\n".join(lines)


def _module_name(path: Path) -> str:
    rel = path.relative_to(REPO_ROOT / "src").with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _import_targets(
    current_module: str,
    node: ast.AST,
    modules: dict[str, Path],
) -> list[str]:
    if isinstance(node, ast.Import):
        return [
            name.name
            for name in node.names
            if name.name.startswith("intent_engine") and name.name in modules
        ]

    if not isinstance(node, ast.ImportFrom):
        return []
    if node.level:
        base = _relative_import_base(current_module, node.level)
        imported = f"{base}.{node.module}" if node.module else base
    else:
        imported = node.module or ""
    if not imported.startswith("intent_engine"):
        return []
    if imported in modules:
        return [imported]
    targets = [f"{imported}.{alias.name}" for alias in node.names]
    return [target for target in targets if target in modules]


def _relative_import_base(current_module: str, level: int) -> str:
    parts = current_module.split(".")
    package_parts = parts if current_module.endswith("__init__") else parts[:-1]
    keep = max(len(package_parts) - level + 1, 1)
    return ".".join(package_parts[:keep])


def _render_result_summaries(results_dir: Path, output: Path) -> dict[str, str]:
    result_dir = output / "results"
    result_dir.mkdir(parents=True, exist_ok=True)
    golden_path = result_dir / "golden-journeys.md"
    benchmark_path = result_dir / "model-benchmarks.md"
    golden_path.write_text(_golden_results_markdown(results_dir))
    benchmark_path.write_text(_benchmarks_markdown(results_dir))
    return {
        "goldenJourneys": _relative(output, golden_path),
        "modelBenchmarks": _relative(output, benchmark_path),
    }


def _golden_results_markdown(results_dir: Path) -> str:
    rows: list[list[str]] = []
    for path in sorted(results_dir.glob("golden-journey*.yaml")):
        data = _yaml_load(path)
        summary = data.get("summary", {})
        for scenario in data.get("scenarios", []):
            rows.append(
                [
                    path.name,
                    str(data.get("provider", "")),
                    str(data.get("model", "")),
                    str(scenario.get("scenario", "")),
                    str(scenario.get("status", "")),
                    str(scenario.get("readiness", "")),
                    str(scenario.get("rawCoverage", "")),
                    str(scenario.get("conformance", "")),
                    str(summary.get("status", "")),
                ]
            )
    return _markdown_table(
        "Golden Journey Results",
        [
            "artifact",
            "provider",
            "model",
            "scenario",
            "status",
            "readiness",
            "rawCoverage",
            "conformance",
            "summary",
        ],
        rows,
    )


def _benchmarks_markdown(results_dir: Path) -> str:
    rows: list[list[str]] = []
    for path in sorted(results_dir.glob("**/model-benchmark.yaml")):
        data = _yaml_load(path)
        run = data.get("run", {})
        readiness = data.get("readiness", {})
        latency = data.get("latency", {})
        tokens = data.get("tokens", {})
        quality = data.get("quality", {})
        conformance = data.get("conformance", {})
        accepted = quality.get("acceptedDecisionCount", 0)
        coverage = f"{quality.get('rawLlmAcceptedCoverageCount', 0)}/{accepted}"
        rows.append(
            [
                str(path.relative_to(results_dir)),
                str(run.get("provider", "")),
                str(run.get("model", "")),
                str(readiness.get("status", "")),
                str(latency.get("totalMs", "")),
                str(tokens.get("totalTokens", "")),
                coverage,
                str(quality.get("rawLlmMissingAcceptedDecisionCount", "")),
                str(conformance.get("status", "")),
            ]
        )
    return _markdown_table(
        "Model Benchmarks",
        [
            "artifact",
            "provider",
            "model",
            "readiness",
            "latencyMs",
            "tokens",
            "rawCoverage",
            "rawMissing",
            "conformance",
        ],
        rows,
    )


def _write_index(
    output: Path,
    patterns: list[dict[str, str]],
    dependency_graph: str,
    result_artifacts: dict[str, str],
) -> None:
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(item['pattern'])}</td>"
        f'<td><a href="{item["graphMermaid"]}">requirement graph Mermaid</a></td>'
        f'<td><a href="{item["graphJson"]}">requirement graph JSON</a></td>'
        f'<td><a href="{item["modelMermaid"]}">intent model Mermaid</a></td>'
        "</tr>"
        for item in patterns
    )
    index = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>intent-engine developer views</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; line-height: 1.5; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0 2rem; }}
    th, td {{ border: 1px solid #d0d7de; padding: 0.5rem; text-align: left; }}
    th {{ background: #f6f8fa; }}
    code {{ background: #f6f8fa; padding: 0.1rem 0.25rem; }}
  </style>
</head>
<body>
  <h1>intent-engine developer views</h1>
  <p>Generated local artifacts for visual inspection. Open Mermaid files in VS Code
  with a Mermaid preview extension, or paste them into any Mermaid viewer.</p>

  <h2>Pattern Graphs and Data Models</h2>
  <table>
    <thead>
      <tr><th>Pattern</th><th>Graph</th><th>Graph Data</th><th>Data Model</th></tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>

  <h2>Code Dependencies</h2>
  <p><a href="{dependency_graph}">intent_engine module dependency graph</a></p>

  <h2>Test and Model Results</h2>
  <ul>
    <li><a href="{result_artifacts["goldenJourneys"]}">Golden journey results</a></li>
    <li><a href="{result_artifacts["modelBenchmarks"]}">Model benchmarks</a></li>
  </ul>
</body>
</html>
"""
    (output / "index.html").write_text(index)


def _yaml_load(path: Path) -> dict[str, Any]:
    return read_yaml_mapping(path)


def _markdown_table(title: str, headers: list[str], rows: list[list[str]]) -> str:
    lines = [f"# {title}", ""]
    if not rows:
        lines.append("No local artifacts found.")
        lines.append("")
        return "\n".join(lines)
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(_escape_markdown_cell(value) for value in row) + " |")
    lines.append("")
    return "\n".join(lines)


def _escape_markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _relative(base: Path, path: Path) -> str:
    return path.relative_to(base).as_posix()


def _mermaid_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", value)


if __name__ == "__main__":
    raise SystemExit(main())
