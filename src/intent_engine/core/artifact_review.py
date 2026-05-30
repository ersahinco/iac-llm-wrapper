"""Static handoff review page generation."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

import ruamel.yaml


def write_review_html(input_dir: Path, output: Path) -> None:
    """Write a portable static HTML review page for a generated handoff bundle."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_review_html(input_dir))


def render_review_html(input_dir: Path) -> str:
    """Render a static HTML review page from generated handoff artifacts."""
    report = _read_yaml(input_dir / "decision-report.yaml")
    trace = _read_yaml(input_dir / "llm-trace-summary.yaml")
    handoff = _read_yaml(input_dir / "handoff-plan.yaml")
    lineage = _read_yaml(input_dir / "lineage-manifest.yaml")
    readiness = _readiness(report, handoff)
    artifacts = _artifact_names(input_dir, handoff, lineage)

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{escape(str(report.get('pattern', 'handoff')))} handoff review</title>",
            "<style>",
            _CSS,
            "</style>",
            "</head>",
            "<body>",
            "<main>",
            "<header>",
            "<p>iac-llm-wrapper static review</p>",
            f"<h1>{escape(str(report.get('pattern', 'handoff')))} handoff review</h1>",
            f'<div class="status {escape(readiness["status"])}">'
            f"{escape(readiness['status'])}</div>",
            "</header>",
            _section(
                "Readiness",
                [
                    _kv("Deployment allowed", str(readiness["deploymentAllowed"])),
                    _kv("Allowed next action", readiness["allowedNextAction"]),
                    _list_block("Blockers", readiness["blockers"]),
                ],
            ),
            _section("Accepted Decisions", [_mapping_table(_accepted_decisions(trace))]),
            _section("Graph Decisions", [_mapping_table(_graph_decisions(report))]),
            _section(
                "Gaps And Contradictions",
                [
                    _list_block("Blocking gaps", _trace_list(trace, "gaps", "blocking")),
                    _list_block("Resolved gaps", _trace_list(trace, "gaps", "resolved")),
                    _list_block(
                        "Blocking contradictions",
                        _trace_list(trace, "contradictions", "blocking"),
                    ),
                ],
            ),
            _section("Target Artifacts", [_artifact_table(input_dir, artifacts)]),
            _section("Handoff Plan", [_handoff_steps(handoff)]),
            _section(
                "Trace Summary",
                [
                    _kv("Provider", str(trace.get("provider", "unknown"))),
                    _kv("Model", str(trace.get("model", "unknown"))),
                    _kv("Call count", str(trace.get("callCount", "0"))),
                    _kv("Raw evidence", _raw_evidence(trace)),
                    _details("Raw trace summary", _yaml_dump(trace)),
                ],
            ),
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    yaml = ruamel.yaml.YAML(typ="safe")
    data = yaml.load(path.read_text())
    return data if isinstance(data, dict) else {}


def _yaml_dump(data: Any) -> str:
    from io import StringIO

    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    buf = StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()


def _readiness(report: dict[str, Any], handoff: dict[str, Any]) -> dict[str, Any]:
    report_readiness = report.get("deploymentReadiness")
    if not isinstance(report_readiness, dict):
        report_readiness = {}
    handoff_readiness = handoff.get("readiness")
    if not isinstance(handoff_readiness, dict):
        handoff_readiness = {}
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


def _accepted_decisions(trace: dict[str, Any]) -> dict[str, Any]:
    accepted = trace.get("acceptedDecisions")
    return accepted if isinstance(accepted, dict) else {}


def _graph_decisions(report: dict[str, Any]) -> dict[str, Any]:
    ignored = {"deploymentReadiness"}
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


def _raw_evidence(trace: dict[str, Any]) -> str:
    raw = trace.get("rawEvidence")
    if not isinstance(raw, dict):
        return "unknown"
    status = raw.get("status", "unknown")
    path = raw.get("path")
    return f"{status} ({path})" if path else str(status)


def _section(title: str, body: list[str]) -> str:
    return "\n".join(
        [
            "<section>",
            f"<h2>{escape(title)}</h2>",
            *body,
            "</section>",
        ]
    )


def _kv(label: str, value: str) -> str:
    return f'<div class="kv"><span>{escape(label)}</span><strong>{escape(value)}</strong></div>'


def _list_block(title: str, items: list[Any]) -> str:
    if not items:
        return f'<h3>{escape(title)}</h3><p class="muted">None</p>'
    rendered = "".join(f"<li>{escape(_summarize(item))}</li>" for item in items)
    return f"<h3>{escape(title)}</h3><ul>{rendered}</ul>"


def _mapping_table(data: dict[str, Any]) -> str:
    if not data:
        return '<p class="muted">None</p>'
    rows = []
    for key, value in sorted(data.items()):
        rows.append(
            f"<tr><th>{escape(str(key))}</th><td><pre>{escape(_summarize(value))}</pre></td></tr>"
        )
    return "<table>" + "".join(rows) + "</table>"


def _artifact_table(input_dir: Path, artifacts: list[str]) -> str:
    if not artifacts:
        return '<p class="muted">No artifacts found.</p>'
    rows = []
    for name in artifacts:
        path = input_dir / name
        status = "present" if path.exists() else "missing"
        rows.append(f'<tr><th>{escape(name)}</th><td class="{status}">{status}</td></tr>')
    return "<table>" + "".join(rows) + "</table>"


def _handoff_steps(handoff: dict[str, Any]) -> str:
    steps = handoff.get("steps")
    if not isinstance(steps, list) or not steps:
        return '<p class="muted">No handoff plan found.</p>'
    items = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        title = str(step.get("title", step.get("id", "step")))
        owner = str(step.get("owner", "unknown"))
        depends = ", ".join(str(item) for item in _coerce_list(step.get("dependsOn", [])))
        gate = "manual gate" if step.get("manualGate") else "automated"
        items.append(
            "<li>"
            f"<strong>{escape(title)}</strong>"
            f"<span>Owner: {escape(owner)} | {escape(gate)}</span>"
            f"<span>Depends on: {escape(depends or 'none')}</span>"
            "</li>"
        )
    return '<ol class="steps">' + "".join(items) + "</ol>"


def _details(title: str, content: str) -> str:
    return f"<details><summary>{escape(title)}</summary><pre>{escape(content)}</pre></details>"


def _coerce_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _summarize(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return _yaml_dump(value).strip()
    return str(value)


_CSS = """
:root {
  color-scheme: light;
  --bg: #f7f7f4;
  --panel: #ffffff;
  --text: #1f2933;
  --muted: #667085;
  --line: #d9d9d0;
  --ok: #0f766e;
  --warn: #a16207;
  --bad: #b42318;
}
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
main {
  max-width: 1120px;
  margin: 0 auto;
  padding: 32px 20px 48px;
}
header {
  display: grid;
  gap: 8px;
  margin-bottom: 24px;
}
header p {
  color: var(--muted);
  margin: 0;
  text-transform: uppercase;
  letter-spacing: .08em;
  font-size: 12px;
}
h1, h2, h3 { margin: 0; }
h1 { font-size: 32px; }
h2 { font-size: 20px; margin-bottom: 14px; }
h3 { font-size: 15px; margin: 16px 0 8px; }
section {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 18px;
  margin: 14px 0;
}
.status {
  justify-self: start;
  padding: 4px 10px;
  border-radius: 999px;
  background: #e7f8f5;
  color: var(--ok);
  font-weight: 700;
}
.status.blocked { background: #fff4ed; color: var(--bad); }
.kv {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 16px;
  border-top: 1px solid var(--line);
  padding: 10px 0;
}
.kv span, .muted { color: var(--muted); }
table {
  width: 100%;
  border-collapse: collapse;
}
th, td {
  border-top: 1px solid var(--line);
  padding: 9px 8px;
  text-align: left;
  vertical-align: top;
}
th { width: 280px; font-weight: 650; }
pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
ul, ol { margin: 0; padding-left: 22px; }
.steps li {
  margin: 10px 0;
}
.steps span {
  display: block;
  color: var(--muted);
}
.present { color: var(--ok); font-weight: 700; }
.missing { color: var(--bad); font-weight: 700; }
details {
  border-top: 1px solid var(--line);
  padding-top: 12px;
}
summary {
  cursor: pointer;
  font-weight: 700;
  margin-bottom: 10px;
}
@media (max-width: 720px) {
  .kv { grid-template-columns: 1fr; gap: 4px; }
  th { width: auto; display: block; border-top: 1px solid var(--line); }
  td { display: block; border-top: 0; }
}
"""
