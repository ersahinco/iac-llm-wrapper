"""Small HTML renderer for static handoff reviews."""

from __future__ import annotations

from html import escape
from typing import Any

import ruamel.yaml


def render_review_html(context: dict[str, Any]) -> str:
    """Render a static HTML review page from a prepared context."""
    pattern = str(context.get("pattern", "handoff"))
    readiness = _dict(context.get("readiness"))
    graph_exports = _dict(context.get("graphExports"))
    trace = _dict(context.get("trace"))
    benchmark = _dict(context.get("benchmark"))
    links = _dict(context.get("links"))
    review_summary = _dict(context.get("reviewSummary"))
    model_quality = _dict(context.get("modelQuality"))

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{escape(pattern)} handoff review</title>",
            "<style>",
            _CSS,
            "</style>",
            "</head>",
            "<body>",
            "<main>",
            "<header>",
            "<p>iac-llm-wrapper static review</p>",
            f"<h1>{escape(pattern)} handoff review</h1>",
            f'<div class="status {escape(str(readiness.get("status", "unknown")))}">'
            f"{escape(str(readiness.get('status', 'unknown')))}</div>",
            "</header>",
            _section(
                "Review Summary",
                [
                    _kv("Readiness", str(review_summary.get("readiness", "unknown"))),
                    _kv(
                        "Deployment allowed",
                        str(review_summary.get("deploymentAllowed", False)),
                    ),
                    _kv("Blocker count", str(review_summary.get("blockerCount", 0))),
                    _kv(
                        "Missing decision count",
                        str(review_summary.get("missingDecisionCount", 0)),
                    ),
                    _kv(
                        "Conflicting decision count",
                        str(review_summary.get("conflictingDecisionCount", 0)),
                    ),
                    _kv(
                        "Blocking gap count",
                        str(review_summary.get("blockingGapCount", 0)),
                    ),
                    _kv(
                        "Blocking contradiction count",
                        str(review_summary.get("blockingContradictionCount", 0)),
                    ),
                    _kv("Contract status", str(review_summary.get("contractStatus", "unknown"))),
                    _kv(
                        "Allowed next action",
                        str(review_summary.get("allowedNextAction", "")),
                    ),
                    _kv("Model mode", str(model_quality.get("mode", "unknown"))),
                    _kv("Model", str(model_quality.get("model", "unknown"))),
                    _kv("Raw LLM coverage", str(model_quality.get("rawCoverage", "not-run"))),
                    _kv("Raw missing decisions", str(model_quality.get("rawMissingCount", 0))),
                    _list_block("Missing raw decision keys", model_quality.get("missingKeys", [])),
                    _list_block(
                        "Expected weaknesses",
                        model_quality.get("expectedWeaknesses", []),
                    ),
                ],
            ),
            _section(
                "Handoff Readiness",
                [
                    _kv("Handoff ready", str(readiness.get("deploymentAllowed", False))),
                    _kv("Allowed next action", str(readiness.get("allowedNextAction", ""))),
                    _blocker_table(_coerce_list(context.get("blockerRows"))),
                    _list_block("Blockers", _coerce_list(readiness.get("blockers"))),
                    _list_block(
                        "Missing decisions",
                        _coerce_list(readiness.get("missingDecisions")),
                    ),
                    _list_block(
                        "Conflicting decisions",
                        _coerce_list(readiness.get("conflictingDecisions")),
                    ),
                    _list_block(
                        "Safe handoff path",
                        _coerce_list(readiness.get("safeHandoffPath")),
                    ),
                ],
            ),
            _section(
                "Requirement Graph",
                [
                    _link_list(
                        [
                            ("JSON export", str(graph_exports.get("json", ""))),
                            ("Mermaid export", str(graph_exports.get("mermaid", ""))),
                        ]
                    ),
                ],
            ),
            _section(
                "Accepted Decisions", [_mapping_table(_dict(context.get("acceptedDecisions")))]
            ),
            _section("Graph Decisions", [_mapping_table(_dict(context.get("graphDecisions")))]),
            _section(
                "Gaps And Contradictions",
                [
                    _list_block("Blocking gaps", _coerce_list(context.get("blockingGaps"))),
                    _list_block("Resolved gaps", _coerce_list(context.get("resolvedGaps"))),
                    _list_block(
                        "Blocking contradictions",
                        _coerce_list(context.get("blockingContradictions")),
                    ),
                ],
            ),
            _section(
                "Contract Validation",
                [
                    _contract_table(_coerce_list(context.get("contractValidation"))),
                    _details(
                        "Raw contract validation",
                        _yaml_dump(context.get("contractValidationArtifact", {})),
                    ),
                ],
            ),
            _section("Target Artifacts", [_artifact_table(_coerce_list(context.get("artifacts")))]),
            _section("Handoff Plan", [_handoff_steps(_dict(context.get("handoff")))]),
            _section(
                "Trace Summary",
                [
                    _kv("Provider", str(trace.get("provider", "unknown"))),
                    _kv("Model", str(trace.get("model", "unknown"))),
                    _kv("Call count", str(trace.get("callCount", "0"))),
                    _kv("Raw evidence", str(context.get("rawEvidence", "unknown"))),
                    _artifact_link_row("LLM trace summary", links.get("llmTrace")),
                    _artifact_link_row("Raw evidence file", links.get("rawEvidence")),
                    _details("Raw trace summary", _yaml_dump(trace)),
                ],
            ),
            _section(
                "Model Benchmark",
                [
                    _kv("Mode", _nested_str(benchmark, "run", "mode")),
                    _kv("Latency total", f"{_nested_str(benchmark, 'latency', 'totalMs')} ms"),
                    _kv("Tokens", _token_summary(benchmark)),
                    _kv("Cost", _nested_str(benchmark, "cost", "status")),
                    _kv(
                        "Accepted decisions",
                        _nested_str(benchmark, "quality", "acceptedDecisionCount"),
                    ),
                    _kv("Raw LLM coverage", str(model_quality.get("rawCoverage", "0/0"))),
                    _kv("Raw missing decisions", str(model_quality.get("rawMissingCount", 0))),
                    _artifact_link_row("Model benchmark", links.get("modelBenchmark")),
                    _artifact_link_row("Contract validation", links.get("contractValidation")),
                    _details("Raw model benchmark", _yaml_dump(benchmark)),
                ],
            ),
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _yaml_dump(data: Any) -> str:
    from io import StringIO

    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    buf = StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()


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


def _contract_table(results: list[Any]) -> str:
    if not results:
        return '<p class="muted">No contract validation available.</p>'
    rows = []
    for result in results:
        if not isinstance(result, dict):
            continue
        status = str(result.get("status", "unknown"))
        count = str(result.get("violationCount", "0"))
        rows.append(
            "<tr>"
            f"<th>{escape(str(result.get('name', 'unknown')))}</th>"
            f'<td class="{escape(status)}">{escape(status)}</td>'
            f"<td>{escape(count)} violation(s)</td>"
            "</tr>"
        )
    return "<table>" + "".join(rows) + "</table>"


def _blocker_table(rows: list[Any]) -> str:
    if not rows:
        return '<p class="muted">No blocker traceability rows.</p>'
    rendered = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rendered.append(
            "<tr>"
            f"<th>{escape(str(row.get('code', 'unknown')))}</th>"
            f"<td>{escape(str(row.get('resolutionType', 'blocker')))}</td>"
            f"<td>{escape(str(row.get('requirementKey', 'unknown')))}</td>"
            f"<td>{escape(str(row.get('question', 'unknown')))}</td>"
            f"<td>{escape(str(row.get('message', '')))}</td>"
            "</tr>"
        )
    if not rendered:
        return '<p class="muted">No blocker traceability rows.</p>'
    header = (
        "<tr><th>Code</th><th>Type</th><th>Requirement key</th>"
        "<th>Question</th><th>Message</th></tr>"
    )
    return "<h3>Blocker Traceability</h3><table>" + header + "".join(rendered) + "</table>"


def _artifact_table(artifacts: list[Any]) -> str:
    if not artifacts:
        return '<p class="muted">No artifacts found.</p>'
    rows = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        status = str(artifact.get("status", "missing"))
        rows.append(
            "<tr>"
            f"<th>{escape(str(artifact.get('name', 'unknown')))}</th>"
            f'<td class="{escape(status)}">{escape(status)}</td>'
            "</tr>"
        )
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
        depends = ", ".join(str(item) for item in _coerce_list(step.get("dependsOn")))
        gate = "manual gate" if step.get("manualGate") else "automated"
        items.append(
            "<li>"
            f"<strong>{escape(title)}</strong>"
            f"<span>Owner: {escape(owner)} | {escape(gate)}</span>"
            f"<span>Depends on: {escape(depends or 'none')}</span>"
            "</li>"
        )
    return '<ol class="steps">' + "".join(items) + "</ol>"


def _artifact_link_row(label: str, href: Any) -> str:
    if not href:
        return _kv(label, "missing")
    value = str(href)
    name = value.rsplit("/", 1)[-1]
    return (
        f'<div class="kv"><span>{escape(label)}</span>'
        f'<strong><a href="{escape(value)}">{escape(name)}</a></strong></div>'
    )


def _details(title: str, content: str) -> str:
    return f"<details><summary>{escape(title)}</summary><pre>{escape(content)}</pre></details>"


def _link_list(links: list[tuple[str, str]]) -> str:
    active = [(label, href) for label, href in links if href]
    if not active:
        return '<p class="muted">No graph export files found.</p>'
    items = "".join(
        f'<li><a href="{escape(href)}">{escape(label)}</a></li>' for label, href in active
    )
    return f"<ul>{items}</ul>"


def _nested_str(data: dict[str, Any], section: str, key: str) -> str:
    value = data.get(section)
    if not isinstance(value, dict):
        return "unknown"
    return str(value.get(key, "unknown"))


def _token_summary(benchmark: dict[str, Any]) -> str:
    tokens = benchmark.get("tokens")
    if not isinstance(tokens, dict):
        return "unknown"
    status = tokens.get("status", "unknown")
    total = tokens.get("totalTokens", 0)
    return f"{status}, total={total}"


def _coerce_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _summarize(value: Any) -> str:
    if isinstance(value, dict | list):
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
.pass { color: var(--ok); font-weight: 700; }
.missing { color: var(--bad); font-weight: 700; }
.fail { color: var(--bad); font-weight: 700; }
a { color: #155eef; }
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
