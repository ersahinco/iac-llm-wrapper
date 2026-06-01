"""Static review context tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import ruamel.yaml

from intent_engine.core.artifact_review import build_review_context, render_review_html


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    with path.open("w") as handle:
        yaml.dump(data, handle)


def _write_review_bundle(input_dir: Path) -> Path:
    input_dir.mkdir(parents=True)
    evidence_path = input_dir / "raw-evidence.yaml"
    evidence_path.write_text("calls: []\n")
    _write_yaml(
        input_dir / "decision-report.yaml",
        {
            "pattern": "example-pattern",
            "organizationName": "Contoso",
            "deploymentReadiness": {
                "status": "blocked",
                "deploymentAllowed": False,
                "blockers": [{"code": "MISSING_NETWORK", "message": "Network missing"}],
            },
        },
    )
    _write_yaml(
        input_dir / "llm-trace-summary.yaml",
        {
            "acceptedDecisions": {"organization_name": "Contoso"},
            "gaps": {"blocking": [{"key": "network_account"}], "resolved": []},
            "contradictions": {"blocking": []},
            "rawEvidence": {"status": "captured", "path": str(evidence_path)},
        },
    )
    _write_yaml(
        input_dir / "model-benchmark.yaml",
        {
            "run": {"mode": "deterministic", "provider": "none", "model": "none"},
            "quality": {"acceptedDecisionCount": 1},
        },
    )
    _write_yaml(
        input_dir / "handoff-plan.yaml",
        {
            "pattern": "example-pattern",
            "readiness": {"status": "ready", "deploymentAllowed": True},
            "allowedNextAction": "Resolve blockers.",
            "targetContracts": [
                {
                    "name": "example-contract",
                    "requiredArtifacts": ["present.yaml", "missing.yaml"],
                }
            ],
        },
    )
    _write_yaml(
        input_dir / "lineage-manifest.yaml",
        {"artifacts": [{"name": "lineage-only.yaml", "required": True}]},
    )
    _write_yaml(input_dir / "present.yaml", {"ok": True})
    validation_path = input_dir / "contract-validation.yaml"
    _write_yaml(
        validation_path,
        {
            "summary": {"status": "fail", "contractCount": 1, "violationCount": 1},
            "contracts": [
                {
                    "name": "example-contract",
                    "kind": "yaml",
                    "status": "fail",
                    "violations": [{"code": "MISSING", "message": "missing.yaml missing"}],
                }
            ],
        },
    )
    return validation_path


def test_build_review_context_uses_report_readiness_and_artifact_rows(tmp_path: Path):
    input_dir = tmp_path / "out"
    validation_path = _write_review_bundle(input_dir)

    context = build_review_context(
        input_dir,
        link_base_dir=input_dir,
        graph_exports={"json": "requirement-graph.json"},
        contract_validation_path=validation_path,
    )

    assert context["pattern"] == "example-pattern"
    assert context["readiness"]["status"] == "blocked"
    assert context["readiness"]["deploymentAllowed"] is False
    assert context["readiness"]["allowedNextAction"] == "Resolve blockers."
    assert context["graphDecisions"] == {
        "pattern": "example-pattern",
        "organizationName": "Contoso",
    }
    assert context["acceptedDecisions"] == {"organization_name": "Contoso"}
    assert context["blockingGaps"] == [{"key": "network_account"}]
    assert context["contractValidation"][0]["name"] == "example-contract"
    assert context["links"]["rawEvidence"] == "raw-evidence.yaml"
    assert context["rawEvidence"].startswith("captured")
    assert {"name": "present.yaml", "status": "present"} in context["artifacts"]
    assert {"name": "missing.yaml", "status": "missing"} in context["artifacts"]
    assert {"name": "lineage-only.yaml", "status": "missing"} in context["artifacts"]


def test_render_review_html_uses_existing_graph_exports(tmp_path: Path):
    input_dir = tmp_path / "out"
    _write_review_bundle(input_dir)
    (input_dir / "requirement-graph.json").write_text("{}\n")
    (input_dir / "requirement-graph.mmd").write_text("flowchart TD\n")

    html = render_review_html(input_dir)

    assert "example-pattern handoff review" in html
    assert "requirement-graph.json" in html
    assert "requirement-graph.mmd" in html
    assert "raw-evidence.yaml" in html
