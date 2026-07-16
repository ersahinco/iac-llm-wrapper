"""Battle summary verdict tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import ruamel.yaml

from intent_engine.core.battle_summary import (
    BattleCaseInput,
    BattleCompileResult,
    build_battle_summary,
    write_battle_summary,
)
from intent_engine.core.yaml_utils import write_yaml_artifact


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    write_yaml_artifact(path, data, header="")


def _case(
    repo_root: Path,
    *,
    expected_compile: str = "pass",
    expected_artifacts: tuple[str, ...] = ("accounts-config.yaml",),
    expected_violations: tuple[str, ...] = (),
) -> BattleCaseInput:
    input_path = repo_root / "fixtures" / "eval" / "case.md"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text("# Case\n")
    return BattleCaseInput(
        name="case",
        input_path=input_path,
        pattern="aws-lza",
        expected_compile=expected_compile,
        expected_artifacts=expected_artifacts,
        expected_violations=expected_violations,
    )


def _compile_result(*, returncode: int = 0, stderr: str = "") -> BattleCompileResult:
    return BattleCompileResult(returncode=returncode, stdout="", stderr=stderr)


def _write_ready_bundle(output_dir: Path, *, artifacts: tuple[str, ...]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for artifact in artifacts:
        (output_dir / artifact).write_text("ok: true\n")
    _write_yaml(
        output_dir / "llm-trace-summary.yaml",
        {
            "acceptedDecisions": {
                "audit_account": "Audit",
                "baseline": "standard",
                "centralized_logging": True,
                "enabled_regions": ["eu-central-1"],
                "home_region": "eu-central-1",
                "identity_center_delegated_admin_account": "SecurityTooling",
                "network_account": "Network",
                "identity_center_permission_sets": ["SecurityAdmin"],
                "identity_center_assignments": ["SecurityAdmin->Platform"],
                "log_archive_account": "LogArchive",
                "org_mode": "organizations",
                "organizational_units": ["Security", "Infrastructure", "Workloads"],
                "security_tooling_account": "SecurityTooling",
                "topology": "hub-spoke",
            },
            "rawLlmDecisions": {},
            "appliedDecisions": {"markdown": ["network_account"], "llm": []},
            "gaps": {"raw": [], "blocking": []},
            "contradictions": {"blocking": []},
        },
    )
    _write_yaml(
        output_dir / "model-benchmark.yaml",
        {
            "run": {"mode": "deterministic", "provider": "none", "model": "none"},
            "readiness": {"status": "ready"},
            "latency": {"totalMs": 0},
            "tokens": {"totalTokens": 0},
            "quality": {"acceptedDecisionCount": 14, "parseErrorCount": 0},
        },
    )
    _write_yaml(output_dir / "contract-validation.yaml", {"summary": {"status": "pass"}})
    _write_yaml(output_dir / "handoff-plan.yaml", {"allowedNextAction": "review artifacts"})
    _write_yaml(output_dir / "decision-report.yaml", {"readiness": "ready"})
    (output_dir / "handoff-review.html").write_text(
        "<h1>Readiness</h1><h2>Contract Validation</h2><h2>Model Benchmark</h2>"
    )


def _summary(
    tmp_path: Path,
    *,
    case: BattleCaseInput | None = None,
    output_dir: Path | None = None,
    use_llm: bool = False,
    compile_result: BattleCompileResult | None = None,
) -> dict[str, Any]:
    repo_root = tmp_path / "repo"
    case = case or _case(repo_root)
    output_dir = output_dir or repo_root / "tests" / "results" / "case"
    compile_result = compile_result or _compile_result()
    return build_battle_summary(
        case=case,
        output_dir=output_dir,
        command=["python3", "scripts/battle-test.py"],
        use_llm=use_llm,
        compile_result=compile_result,
        repo_root=repo_root,
        git_commit="abc123",
    )


def test_expected_pass_missing_artifact_fails(tmp_path: Path):
    repo_root = tmp_path / "repo"
    output_dir = repo_root / "out"
    _write_ready_bundle(output_dir, artifacts=())
    summary = _summary(tmp_path, case=_case(repo_root), output_dir=output_dir)

    assert summary["verdict"] == "fail"
    assert summary["confidence"]["handoff"] == "fail"
    assert summary["findings"] == [
        {
            "type": "fail",
            "area": "handoff",
            "message": "Expected artifacts missing: accounts-config.yaml.",
        }
    ]


def test_expected_blocked_compile_failure_with_violation_passes(tmp_path: Path):
    repo_root = tmp_path / "repo"
    output_dir = repo_root / "out"
    _write_ready_bundle(output_dir, artifacts=())
    case = _case(
        repo_root,
        expected_compile="fail",
        expected_artifacts=(),
        expected_violations=("NETWORK_ACCOUNT_REQUIRED",),
    )

    summary = _summary(
        tmp_path,
        case=case,
        output_dir=output_dir,
        compile_result=_compile_result(
            returncode=1,
            stderr="NETWORK_ACCOUNT_REQUIRED: network account is required",
        ),
    )

    assert summary["verdict"] == "pass"
    assert summary["actualCompile"] == "fail"
    assert summary["confidence"]["safety"] == "pass"


def test_compile_result_mismatch_fails(tmp_path: Path):
    repo_root = tmp_path / "repo"
    output_dir = repo_root / "out"
    _write_ready_bundle(output_dir, artifacts=("accounts-config.yaml",))

    summary = _summary(
        tmp_path,
        case=_case(repo_root, expected_compile="fail", expected_artifacts=()),
        output_dir=output_dir,
    )

    assert summary["verdict"] == "fail"
    assert {
        "type": "fail",
        "area": "safety",
        "message": "Compile result mismatch: expected fail, got pass.",
    } in summary["findings"]


def test_review_page_missing_required_section_fails(tmp_path: Path):
    repo_root = tmp_path / "repo"
    output_dir = repo_root / "out"
    _write_ready_bundle(output_dir, artifacts=("accounts-config.yaml",))
    (output_dir / "handoff-review.html").write_text("<h1>Readiness</h1>")

    summary = _summary(tmp_path, case=_case(repo_root), output_dir=output_dir)

    assert summary["verdict"] == "fail"
    assert {
        "type": "fail",
        "area": "handoff",
        "message": "Review page missing section: Contract Validation.",
    } in summary["findings"]


def test_raw_invented_llm_decision_is_improvement_not_failure(tmp_path: Path):
    repo_root = tmp_path / "repo"
    output_dir = repo_root / "out"
    _write_ready_bundle(output_dir, artifacts=("accounts-config.yaml",))
    trace = ruamel.yaml.YAML(typ="safe").load((output_dir / "llm-trace-summary.yaml").read_text())
    trace["rawLlmDecisions"] = {"made_up_feature": True}
    _write_yaml(output_dir / "llm-trace-summary.yaml", trace)

    summary = _summary(tmp_path, case=_case(repo_root), output_dir=output_dir)

    assert summary["verdict"] == "pass"
    assert summary["confidence"]["extraction"] == "improvement"
    assert summary["improvementItems"] == [
        {
            "type": "improvement",
            "area": "extraction",
            "message": "Raw LLM decisions were not accepted by graph: made_up_feature.",
        }
    ]


def test_llm_missing_token_usage_is_expected_weakness(tmp_path: Path):
    repo_root = tmp_path / "repo"
    output_dir = repo_root / "out"
    _write_ready_bundle(output_dir, artifacts=("accounts-config.yaml",))
    (output_dir / "raw-evidence.yaml").write_text("requests: []\n")
    benchmark = ruamel.yaml.YAML(typ="safe").load((output_dir / "model-benchmark.yaml").read_text())
    benchmark["run"] = {"mode": "llm", "provider": "openai-compatible", "model": "small"}
    benchmark["latency"] = {"totalMs": 100}
    benchmark["tokens"] = {"totalTokens": 0}
    _write_yaml(output_dir / "model-benchmark.yaml", benchmark)

    summary = _summary(tmp_path, case=_case(repo_root), output_dir=output_dir, use_llm=True)

    assert summary["verdict"] == "pass"
    assert summary["confidence"]["model"] == "expected-weakness"
    assert {
        "type": "expected-weakness",
        "area": "model",
        "message": "Provider did not report token usage.",
    } in summary["improvementItems"]


def test_llm_raw_decision_gap_is_expected_weakness(tmp_path: Path):
    repo_root = tmp_path / "repo"
    output_dir = repo_root / "out"
    _write_ready_bundle(output_dir, artifacts=("accounts-config.yaml",))
    (output_dir / "raw-evidence.yaml").write_text("requests: []\n")
    trace = ruamel.yaml.YAML(typ="safe").load((output_dir / "llm-trace-summary.yaml").read_text())
    trace["rawLlmDecisions"] = {
        key: value
        for key, value in trace["acceptedDecisions"].items()
        if key
        not in {
            "identity_center_assignments",
            "identity_center_permission_sets",
            "network_account",
        }
    }
    _write_yaml(output_dir / "llm-trace-summary.yaml", trace)
    benchmark = ruamel.yaml.YAML(typ="safe").load((output_dir / "model-benchmark.yaml").read_text())
    benchmark["latency"] = {"totalMs": 100}
    benchmark["tokens"] = {"totalTokens": 10}
    _write_yaml(output_dir / "model-benchmark.yaml", benchmark)

    summary = _summary(tmp_path, case=_case(repo_root), output_dir=output_dir, use_llm=True)

    assert summary["verdict"] == "pass"
    assert {
        "type": "expected-weakness",
        "area": "model",
        "message": (
            "Raw LLM missed accepted decisions: identity_center_assignments, "
            "identity_center_permission_sets, network_account."
        ),
    } in summary["improvementItems"]


def test_llm_missing_raw_evidence_fails(tmp_path: Path):
    repo_root = tmp_path / "repo"
    output_dir = repo_root / "out"
    _write_ready_bundle(output_dir, artifacts=("accounts-config.yaml",))
    benchmark = ruamel.yaml.YAML(typ="safe").load((output_dir / "model-benchmark.yaml").read_text())
    benchmark["latency"] = {"totalMs": 100}
    benchmark["tokens"] = {"totalTokens": 10}
    _write_yaml(output_dir / "model-benchmark.yaml", benchmark)

    summary = _summary(tmp_path, case=_case(repo_root), output_dir=output_dir, use_llm=True)

    assert summary["verdict"] == "fail"
    assert {
        "type": "fail",
        "area": "safety",
        "message": "Raw LLM evidence was not preserved.",
    } in summary["findings"]


def test_missing_model_benchmark_is_reported_once(tmp_path: Path):
    repo_root = tmp_path / "repo"
    output_dir = repo_root / "out"
    _write_ready_bundle(output_dir, artifacts=("accounts-config.yaml",))
    (output_dir / "model-benchmark.yaml").unlink()

    summary = _summary(tmp_path, case=_case(repo_root), output_dir=output_dir)

    matching = [
        finding
        for finding in summary["findings"]
        if finding["message"] == "model-benchmark.yaml missing."
    ]
    assert matching == [
        {"type": "fail", "area": "model", "message": "model-benchmark.yaml missing."}
    ]


def test_aws_lza_deployable_scaffold_fails(tmp_path: Path):
    repo_root = tmp_path / "repo"
    output_dir = repo_root / "out"
    _write_ready_bundle(output_dir, artifacts=("accounts-config.yaml",))
    (output_dir / "main.tf").write_text('resource "aws_vpc" "bad" {}\n')

    summary = _summary(tmp_path, case=_case(repo_root), output_dir=output_dir)

    assert summary["verdict"] == "fail"
    assert {
        "type": "fail",
        "area": "safety",
        "message": "Unexpected forbidden artifact emitted: main.tf.",
    } in summary["findings"]


def test_write_battle_summary_avoids_yaml_anchors(tmp_path: Path):
    output_path = tmp_path / "battle-summary.yaml"

    write_battle_summary(
        output_path,
        {
            "schemaVersion": "intent-engine/battle-summary/v1",
            "findings": [{"type": "expected-weakness"}],
            "improvementItems": [{"type": "expected-weakness"}],
        },
    )

    written = output_path.read_text()
    assert "&id" not in written
    assert "*id" not in written
