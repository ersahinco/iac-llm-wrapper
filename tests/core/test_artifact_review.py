"""Static review context tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import ruamel.yaml

from intent_engine.core.artifact_review import build_review_context, render_review_html
from intent_engine.patterns import load_builtin_patterns


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    yaml = ruamel.yaml.YAML()
    yaml.default_flow_style = False
    with path.open("w") as handle:
        yaml.dump(data, handle)


def _write_review_bundle(
    input_dir: Path,
    *,
    mode: str = "llm",
    raw_evidence_status: str = "requested",
    lza_validation: bool = False,
    parse_error_count: int = 0,
) -> Path:
    input_dir.mkdir(parents=True)
    evidence_path = input_dir / "raw-evidence.yaml"
    if raw_evidence_status != "not-requested":
        evidence_path.write_text("calls: []\n")
    _write_yaml(
        input_dir / "decision-report.yaml",
        {
            "pattern": "example-pattern",
            "organizationName": "Contoso",
            "handoffReadiness": {
                "status": "blocked",
                "handoffAllowed": False,
                "deploymentAllowed": False,
                "blockers": [{"code": "MISSING_NETWORK", "message": "Network missing"}],
                "missingDecisions": [
                    {
                        "key": "network_account",
                        "label": "Network Account",
                        "reason": "Network missing",
                        "question": "Which account owns shared networking?",
                    }
                ],
                "conflictingDecisions": [{"code": "CIDR_CONFLICT"}],
                "safeHandoffPath": ["Resolve network ownership."],
            },
            "deploymentReadiness": {
                "status": "blocked",
                "handoffAllowed": False,
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
            "rawEvidence": {
                "status": raw_evidence_status,
                "path": str(evidence_path)
                if raw_evidence_status != "not-requested"
                else "not-requested",
            },
            "appliedDecisions": {"markdown": ["organization_name"], "llm": []},
        },
    )
    _write_yaml(
        input_dir / "model-benchmark.yaml",
        {
            "run": {"mode": mode, "provider": "ollama", "model": "small"},
            "quality": {
                "acceptedDecisionCount": 1,
                "rawLlmAcceptedCoverageCount": 0,
                "rawLlmMissingAcceptedDecisionCount": 1,
                "rawLlmMissingAcceptedDecisions": ["organization_name"],
                "parseErrorCount": parse_error_count,
            },
            "conformance": {
                "status": "review",
                "reason": "raw LLM missed accepted decisions",
            },
        },
    )
    _write_yaml(
        input_dir / "handoff-plan.yaml",
        {
            "pattern": "example-pattern",
            "readiness": {"status": "ready", "handoffAllowed": True, "deploymentAllowed": True},
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
        input_dir / "target-capability-graph.yaml",
        {
            "selectedTargetPath": ["accelerator", "module-composition"],
            "manualGates": ["Validate target output."],
            "unsupportedGaps": [
                {
                    "key": "bespoke-workload-infrastructure",
                    "recommendedTarget": "module-composition",
                    "reason": "Needs separate module target.",
                }
            ],
            "capabilities": [
                {
                    "key": "example-accelerator",
                    "label": "Example accelerator",
                    "type": "accelerator",
                    "available": True,
                    "producedArtifacts": ["present.yaml"],
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
    if lza_validation:
        _write_yaml(
            input_dir / "lza-validation-evidence.yaml",
            {
                "schemaVersion": "intent-engine/aws-lza-validation-evidence/v1",
                "status": "fail",
                "boundary": {
                    "readOnlyAwsAccountLookupMayOccur": True,
                    "awsAccountLookupBoundary": (
                        "The official AWS LZA validator may perform read-only account "
                        "lookup through the provided AWS/LZA context."
                    ),
                },
                "input": {
                    "configFileDigests": [
                        {
                            "name": "network-config.yaml",
                            "bundlePath": str(input_dir / "network-config.yaml"),
                            "sha256": "abc123",
                        }
                    ]
                },
                "lzaSource": {
                    "requestedPath": "/tmp/landing-zone-accelerator-on-aws",
                    "commandWorkingDirectory": "/tmp/landing-zone-accelerator-on-aws/source",
                    "gitCommit": "abcde12",
                    "packageVersion": "1.15.0",
                },
                "command": {
                    "argv": ["corepack", "yarn", "validate-config", "/tmp/config"],
                    "exitCode": 1,
                    "stdout": (
                        "2026-06-15 | warn | config-validator | "
                        "AccessDeniedException: You don't have permissions to access this "
                        "resource. in accounts-config.yaml config file"
                    ),
                },
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
    assert context["readiness"]["handoffAllowed"] is False
    assert context["readiness"]["deploymentAllowed"] is False
    assert context["readiness"]["allowedNextAction"] == "Resolve blockers."
    assert context["readiness"]["missingDecisions"] == [
        {
            "key": "network_account",
            "label": "Network Account",
            "reason": "Network missing",
            "question": "Which account owns shared networking?",
        }
    ]
    assert context["readiness"]["conflictingDecisions"] == [{"code": "CIDR_CONFLICT"}]
    assert context["readiness"]["safeHandoffPath"] == ["Resolve network ownership."]
    assert context["graphDecisions"] == {
        "pattern": "example-pattern",
        "organizationName": "Contoso",
    }
    assert context["acceptedDecisions"] == {"organization_name": "Contoso"}
    assert context["blockingGaps"] == [{"key": "network_account"}]
    assert context["blockerRows"] == [
        {
            "code": "MISSING_NETWORK",
            "message": "Network missing",
            "requirementKey": "network_account",
            "label": "Network Account",
            "question": "Which account owns shared networking?",
            "resolutionType": "missing",
        }
    ]
    assert context["contractValidation"][0]["name"] == "example-contract"
    assert context["contractStatus"] == "fail"
    assert context["reviewSummary"]["contractStatus"] == "fail"
    assert context["reviewSummary"]["modelParseErrorCount"] == 0
    assert context["reviewSummary"]["selectedTargetPath"] == [
        "accelerator",
        "module-composition",
    ]
    assert context["reviewSummary"]["unsupportedTargetGapCount"] == 1
    assert context["targetCapabilities"]["unsupportedGaps"][0]["key"] == (
        "bespoke-workload-infrastructure"
    )
    assert context["reviewSummary"]["handoffAllowed"] is False
    assert context["reviewSummary"]["deploymentAllowed"] is False
    assert context["reviewSummary"]["blockerCount"] == 1
    assert context["reviewSummary"]["missingDecisionCount"] == 1
    assert context["reviewSummary"]["conflictingDecisionCount"] == 1
    assert context["reviewSummary"]["blockingGapCount"] == 1
    assert context["reviewSummary"]["blockingContradictionCount"] == 0
    assert context["modelQuality"]["rawCoverage"] == "0/1"
    assert context["modelQuality"]["rawMissingCount"] == 1
    assert context["modelQuality"]["missingKeys"] == ["organization_name"]
    assert context["modelQuality"]["conformanceStatus"] == "review"
    assert context["modelQuality"]["conformanceReason"] == "raw LLM missed accepted decisions"
    assert context["modelQuality"]["expectedWeaknesses"] == [
        "Raw LLM missed accepted decisions: organization_name.",
        "Structured Markdown carried the handoff; LLM added no accepted decisions.",
    ]
    assert context["reviewerNextActions"] == [
        "Do not pass target artifacts to the provisioning toolchain yet.",
        "Resolve the blocker traceability rows with the listed requirement questions.",
        "Update the source Markdown, re-run compile, then regenerate this review page.",
        "Treat raw-evidence.yaml as local debug material; do not share it as a service artifact.",
    ]
    assert context["links"]["rawEvidence"] == "raw-evidence.yaml"
    assert context["rawEvidence"].startswith("requested")
    assert {"name": "present.yaml", "status": "present"} in context["artifacts"]
    assert {"name": "missing.yaml", "status": "missing"} in context["artifacts"]
    assert {"name": "lineage-only.yaml", "status": "missing"} in context["artifacts"]


def test_review_context_surfaces_lza_validation_evidence(tmp_path: Path):
    input_dir = tmp_path / "out"
    validation_path = _write_review_bundle(input_dir, lza_validation=True)

    context = build_review_context(
        input_dir,
        link_base_dir=input_dir,
        graph_exports={},
        contract_validation_path=validation_path,
    )

    assert context["reviewSummary"]["lzaValidationStatus"] == "fail"
    assert context["lzaValidationSummary"] == {
        "status": "fail",
        "exitCode": "1",
        "command": "corepack yarn validate-config /tmp/config",
        "sourcePath": "/tmp/landing-zone-accelerator-on-aws",
        "sourceCwd": "/tmp/landing-zone-accelerator-on-aws/source",
        "packageVersion": "1.15.0",
        "gitCommit": "abcde12",
        "awsLookupBoundary": (
            "The official AWS LZA validator may perform read-only account lookup "
            "through the provided AWS/LZA context."
        ),
        "diagnosticCategory": "aws-account-lookup-permission",
        "diagnosticNextAction": (
            "Run with an AWS/LZA validation context that can perform the official "
            "account lookup, or send this failure to the downstream owner."
        ),
        "failureExcerpt": (
            "AccessDeniedException: You don't have permissions to access this resource. "
            "in accounts-config.yaml config file"
        ),
        "configFileDigests": [
            {
                "name": "network-config.yaml",
                "bundlePath": str(input_dir / "network-config.yaml"),
                "sha256": "abc123",
            }
        ],
    }
    assert context["links"]["lzaValidation"] == "lza-validation-evidence.yaml"
    assert (
        "Do not claim downstream AWS LZA validation until lza-validation-evidence.yaml "
        "failures are resolved."
    ) in context["reviewerNextActions"]


def test_review_context_warns_on_llm_parse_errors(tmp_path: Path):
    input_dir = tmp_path / "out"
    validation_path = _write_review_bundle(input_dir, parse_error_count=2)

    context = build_review_context(
        input_dir,
        link_base_dir=input_dir,
        graph_exports={},
        contract_validation_path=validation_path,
    )

    assert context["reviewSummary"]["modelParseErrorCount"] == 2
    assert context["modelQuality"]["parseErrorCount"] == 2
    assert (
        "LLM extraction recorded parse or backend errors; deterministic extraction may "
        "have carried the run."
    ) in context["modelQuality"]["expectedWeaknesses"]
    assert (
        "LLM extraction recorded parse or backend errors; review llm-trace-summary.yaml "
        "and model-benchmark.yaml before trusting model contribution."
    ) in context["reviewerNextActions"]


def test_review_context_maps_pattern_validator_blockers_to_requirement_questions(
    tmp_path: Path,
):
    load_builtin_patterns()
    input_dir = tmp_path / "out"
    input_dir.mkdir()
    _write_yaml(
        input_dir / "decision-report.yaml",
        {
            "pattern": "aws-lza",
            "handoffReadiness": {
                "status": "blocked",
                "handoffAllowed": False,
                "deploymentAllowed": False,
                "blockers": [
                    {
                        "code": "AWS_LZA_INFRASTRUCTURE_OU_REQUIRED",
                        "message": (
                            "Hub-spoke topology requires an Infrastructure OU for the "
                            "network account."
                        ),
                    },
                    {
                        "code": "AWS_LZA_IDENTITY_CENTER_ADMIN_UNKNOWN",
                        "message": (
                            "Identity Center delegated administrator must reference a "
                            "known account."
                        ),
                    },
                    {
                        "code": "AWS_LZA_HOME_REGION_NOT_ENABLED",
                        "message": "Home region must be present in enabled regions.",
                    },
                ],
                "missingDecisions": [],
                "conflictingDecisions": [
                    {"code": "AWS_LZA_IDENTITY_CENTER_ADMIN_UNKNOWN"},
                    {"code": "AWS_LZA_HOME_REGION_NOT_ENABLED"},
                ],
            },
        },
    )
    _write_yaml(
        input_dir / "llm-trace-summary.yaml",
        {
            "acceptedDecisions": {},
            "gaps": {"blocking": [], "resolved": []},
            "contradictions": {"blocking": []},
            "rawEvidence": {"status": "not-requested", "path": "not-requested"},
            "appliedDecisions": {"markdown": [], "llm": []},
        },
    )
    _write_yaml(
        input_dir / "model-benchmark.yaml",
        {
            "run": {"mode": "deterministic"},
            "quality": {"acceptedDecisionCount": 0},
            "conformance": {"status": "not-applicable"},
        },
    )
    validation_path = input_dir / "contract-validation.yaml"
    _write_yaml(
        validation_path,
        {"summary": {"status": "fail", "contractCount": 0, "violationCount": 0}},
    )

    context = build_review_context(
        input_dir,
        link_base_dir=input_dir,
        graph_exports={},
        contract_validation_path=validation_path,
    )

    rows = {row["code"]: row for row in context["blockerRows"]}
    assert rows["AWS_LZA_INFRASTRUCTURE_OU_REQUIRED"] == {
        "code": "AWS_LZA_INFRASTRUCTURE_OU_REQUIRED",
        "message": "Hub-spoke topology requires an Infrastructure OU for the network account.",
        "requirementKey": "organizational_units",
        "label": "Organizational Units",
        "question": "Which OUs are required? Use comma-separated values.",
        "resolutionType": "missing",
    }
    assert rows["AWS_LZA_IDENTITY_CENTER_ADMIN_UNKNOWN"]["requirementKey"] == (
        "identity_center_delegated_admin_account"
    )
    assert rows["AWS_LZA_IDENTITY_CENTER_ADMIN_UNKNOWN"]["question"] == (
        "Which account is delegated administrator for IAM Identity Center?"
    )
    assert rows["AWS_LZA_IDENTITY_CENTER_ADMIN_UNKNOWN"]["resolutionType"] == "conflicting"
    assert rows["AWS_LZA_HOME_REGION_NOT_ENABLED"]["requirementKey"] == "enabled_regions"
    assert rows["AWS_LZA_HOME_REGION_NOT_ENABLED"]["question"] == (
        "Which AWS regions should LZA enable? Use comma-separated values."
    )
    assert all(row["question"] != "unknown" for row in rows.values())


def test_render_review_html_uses_existing_graph_exports(tmp_path: Path):
    input_dir = tmp_path / "out"
    _write_review_bundle(input_dir, lza_validation=True)
    (input_dir / "requirement-graph.json").write_text("{}\n")
    (input_dir / "requirement-graph.mmd").write_text("flowchart TD\n")

    html = render_review_html(input_dir)

    assert "example-pattern handoff review" in html
    assert "Review Summary" in html
    assert "Reviewer Next Actions" in html
    assert "Do not pass target artifacts" in html
    assert "Treat raw-evidence.yaml as local debug material" in html
    assert "Handoff allowed" in html
    assert "Handoff ready" not in html
    assert "Blocker count" in html
    assert "Missing decision count" in html
    assert "Conflicting decision count" in html
    assert "Blocking gap count" in html
    assert "Missing decisions" in html
    assert "Safe handoff path" in html
    assert "Blocker Traceability" in html
    assert "Requirement key" in html
    assert "Which account owns shared networking?" in html
    assert "Contract status" in html
    assert "Target Capability Graph" in html
    assert "Selected target path" in html
    assert "bespoke-workload-infrastructure" in html
    assert "target-capability-graph.yaml" in html
    assert "Model conformance" in html
    assert "Model parse errors" in html
    assert "Parse errors" in html
    assert "review" in html
    assert "Raw LLM coverage" in html
    assert "0/1" in html
    assert "organization_name" in html
    assert "Structured Markdown carried the handoff" in html
    assert "requirement-graph.json" in html
    assert "requirement-graph.mmd" in html
    assert "raw-evidence.yaml" in html
    assert "LZA Validation Evidence" in html
    assert "lza-validation-evidence.yaml" in html
    assert "LZA validation failure" in html
    assert "AccessDeniedException" in html
    assert "network-config.yaml" in html
    assert "abc123" in html


def test_render_review_html_marks_missing_target_capability_graph_as_not_declared(
    tmp_path: Path,
):
    input_dir = tmp_path / "out"
    _write_review_bundle(input_dir)
    (input_dir / "target-capability-graph.yaml").unlink()

    html = render_review_html(input_dir)

    assert "Selected target path</span><strong>not declared</strong>" in html
    assert "No target capability graph declared for this pattern." in html
    assert "Selected target path</span><strong>unknown</strong>" not in html


def test_render_review_html_explains_missing_handoff_plan_for_blocked_bundle(
    tmp_path: Path,
):
    input_dir = tmp_path / "out"
    _write_review_bundle(input_dir)
    (input_dir / "handoff-plan.yaml").unlink()

    html = render_review_html(input_dir)

    assert "Blocked assessment bundles may omit handoff-plan.yaml" in html


def test_review_context_does_not_report_llm_misses_for_deterministic_run(tmp_path: Path):
    input_dir = tmp_path / "out"
    validation_path = _write_review_bundle(input_dir, mode="deterministic")

    context = build_review_context(
        input_dir,
        link_base_dir=input_dir,
        graph_exports={},
        contract_validation_path=validation_path,
    )

    assert context["modelQuality"]["mode"] == "deterministic"
    assert context["modelQuality"]["rawCoverage"] == "not-run"
    assert context["modelQuality"]["rawMissingCount"] == 0
    assert context["modelQuality"]["missingKeys"] == []
    assert context["modelQuality"]["expectedWeaknesses"] == []


def test_review_html_labels_omitted_raw_evidence_as_not_requested(tmp_path: Path):
    input_dir = tmp_path / "out"
    _write_review_bundle(input_dir, raw_evidence_status="not-requested")

    html = render_review_html(input_dir)

    assert "Raw evidence</span><strong>not requested</strong>" in html
    assert "Raw evidence file</span><strong>not requested</strong>" in html
