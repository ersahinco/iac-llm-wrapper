"""Static handoff review page orchestration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import ruamel.yaml

from .contract_validation import build_contract_validation, write_contract_validation
from .graph_export import graph_to_json, graph_to_mermaid
from .patterns import GLOBAL_REGISTRY
from .review_renderer import render_review_html as render_review_html_context


def write_review_html(input_dir: Path, output: Path) -> None:
    """Write a portable static HTML review page for a generated handoff bundle."""
    output.parent.mkdir(parents=True, exist_ok=True)
    graph_exports = _write_graph_exports(input_dir)
    contract_validation_path = write_contract_validation(input_dir)
    context = build_review_context(
        input_dir,
        link_base_dir=output.parent,
        graph_exports=_relative_graph_exports(input_dir, output.parent, graph_exports),
        contract_validation_path=contract_validation_path,
    )
    output.write_text(render_review_html_context(context))


def render_review_html(
    input_dir: Path,
    graph_exports: dict[str, str] | None = None,
    link_base_dir: Path | None = None,
) -> str:
    """Render a static HTML review page from generated handoff artifacts."""
    context = build_review_context(
        input_dir,
        link_base_dir=link_base_dir or input_dir,
        graph_exports=graph_exports or _existing_graph_exports(input_dir),
        contract_validation_path=None,
    )
    return render_review_html_context(context)


def build_review_context(
    input_dir: Path,
    *,
    link_base_dir: Path,
    graph_exports: dict[str, str],
    contract_validation_path: Path | None,
) -> dict[str, Any]:
    """Read generated artifacts and return renderer-ready review context."""
    report = _read_yaml(input_dir / "decision-report.yaml")
    trace = _read_yaml(input_dir / "llm-trace-summary.yaml")
    benchmark = _read_yaml(input_dir / "model-benchmark.yaml")
    handoff = _read_yaml(input_dir / "handoff-plan.yaml")
    lineage = _read_yaml(input_dir / "lineage-manifest.yaml")
    readiness = _readiness(report, handoff)
    contract_validation = (
        _read_yaml(contract_validation_path)
        if contract_validation_path is not None
        else build_contract_validation(input_dir)
    )

    return {
        "pattern": str(report.get("pattern", handoff.get("pattern", "handoff"))),
        "readiness": readiness,
        "graphExports": graph_exports,
        "acceptedDecisions": _dict(trace.get("acceptedDecisions")),
        "graphDecisions": _graph_decisions(report),
        "blockingGaps": _trace_list(trace, "gaps", "blocking"),
        "resolvedGaps": _trace_list(trace, "gaps", "resolved"),
        "blockingContradictions": _trace_list(trace, "contradictions", "blocking"),
        "contractValidation": _coerce_list(contract_validation.get("contracts")),
        "contractValidationArtifact": contract_validation,
        "artifacts": _artifact_rows(input_dir, _artifact_names(input_dir, handoff, lineage)),
        "handoff": handoff,
        "trace": trace,
        "benchmark": benchmark,
        "rawEvidence": _raw_evidence(trace),
        "links": {
            "llmTrace": _artifact_href(input_dir, link_base_dir, "llm-trace-summary.yaml"),
            "rawEvidence": _raw_evidence_href(link_base_dir, trace),
            "modelBenchmark": _artifact_href(input_dir, link_base_dir, "model-benchmark.yaml"),
            "contractValidation": _href(link_base_dir, contract_validation_path)
            if contract_validation_path is not None
            else None,
        },
    }


def _write_graph_exports(input_dir: Path) -> dict[str, str]:
    report = _read_yaml(input_dir / "decision-report.yaml")
    pattern = str(report.get("pattern", "") or "")
    if not pattern:
        return _existing_graph_exports(input_dir)
    try:
        graph = GLOBAL_REGISTRY.get(pattern).create_graph()
    except KeyError:
        return _existing_graph_exports(input_dir)

    json_name = "requirement-graph.json"
    mermaid_name = "requirement-graph.mmd"
    (input_dir / json_name).write_text(graph_to_json(graph, pattern))
    (input_dir / mermaid_name).write_text(graph_to_mermaid(graph, pattern))
    return {"json": json_name, "mermaid": mermaid_name}


def _existing_graph_exports(input_dir: Path) -> dict[str, str]:
    exports: dict[str, str] = {}
    if (input_dir / "requirement-graph.json").exists():
        exports["json"] = "requirement-graph.json"
    if (input_dir / "requirement-graph.mmd").exists():
        exports["mermaid"] = "requirement-graph.mmd"
    return exports


def _relative_graph_exports(
    input_dir: Path,
    link_base_dir: Path,
    graph_exports: dict[str, str],
) -> dict[str, str]:
    return {
        key: _href_required(link_base_dir, input_dir / value)
        for key, value in graph_exports.items()
        if value
    }


def _read_yaml(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    yaml = ruamel.yaml.YAML(typ="safe")
    data = yaml.load(path.read_text())
    return data if isinstance(data, dict) else {}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _readiness(report: dict[str, Any], handoff: dict[str, Any]) -> dict[str, Any]:
    report_readiness = _dict(report.get("handoffReadiness") or report.get("deploymentReadiness"))
    handoff_readiness = _dict(handoff.get("readiness"))
    allowed = bool(
        report_readiness.get(
            "deploymentAllowed",
            handoff_readiness.get("deploymentAllowed", True),
        )
    )
    return {
        "status": str(
            report_readiness.get("status", handoff_readiness.get("status", "ready"))
        ).lower(),
        "deploymentAllowed": allowed,
        "allowedNextAction": str(
            handoff.get(
                "allowedNextAction",
                "Review generated artifacts with the owning teams before handoff.",
            )
        ),
        "blockers": _coerce_list(
            report_readiness.get("blockers", handoff_readiness.get("blockers", []))
        ),
    }


def _graph_decisions(report: dict[str, Any]) -> dict[str, Any]:
    ignored = {"deploymentReadiness", "handoffReadiness"}
    return {key: value for key, value in report.items() if key not in ignored}


def _trace_list(trace: dict[str, Any], section: str, key: str) -> list[Any]:
    value = trace.get(section)
    if not isinstance(value, dict):
        return []
    return _coerce_list(value.get(key, []))


def _artifact_names(input_dir: Path, handoff: dict[str, Any], lineage: dict[str, Any]) -> list[str]:
    names: list[str] = []
    contracts = handoff.get("targetContracts")
    if isinstance(contracts, list):
        for contract in contracts:
            if isinstance(contract, dict):
                names.extend(
                    str(item) for item in _coerce_list(contract.get("requiredArtifacts", []))
                )
    artifacts = lineage.get("artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if isinstance(artifact, dict) and artifact.get("required", True):
                names.append(str(artifact.get("name", "")))
    names.extend(path.name for path in sorted(input_dir.iterdir()) if path.is_file())
    return sorted(dict.fromkeys(name for name in names if name))


def _artifact_rows(input_dir: Path, artifacts: list[str]) -> list[dict[str, str]]:
    return [
        {
            "name": artifact,
            "status": "present" if (input_dir / artifact).exists() else "missing",
        }
        for artifact in artifacts
    ]


def _raw_evidence(trace: dict[str, Any]) -> str:
    raw = trace.get("rawEvidence")
    if not isinstance(raw, dict):
        return "unknown"
    status = raw.get("status", "unknown")
    path = raw.get("path")
    return f"{status} ({path})" if path else str(status)


def _artifact_href(input_dir: Path, link_base_dir: Path, artifact_name: str) -> str | None:
    path = input_dir / artifact_name
    if not path.exists():
        return None
    return _href(link_base_dir, path)


def _raw_evidence_href(link_base_dir: Path, trace: dict[str, Any]) -> str | None:
    raw = trace.get("rawEvidence")
    if not isinstance(raw, dict):
        return None
    path = str(raw.get("path", ""))
    if not path or path == "not-requested":
        return None
    evidence_path = Path(path)
    return _href(link_base_dir, evidence_path) if evidence_path.exists() else path


def _href(link_base_dir: Path, target: Path | None) -> str | None:
    if target is None:
        return None
    return _href_required(link_base_dir, target)


def _href_required(link_base_dir: Path, target: Path) -> str:
    return Path(os.path.relpath(target, link_base_dir)).as_posix()


def _coerce_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
