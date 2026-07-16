"""Incremental compilation trust-boundary tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from intent_engine.core.compiler import CompileError, compile_design, compile_incremental_design
from intent_engine.core.llm_caller import LLMBackend, LLMCaller
from intent_engine.core.yaml_utils import load_yaml_mapping


class _StaticBackend(LLMBackend):
    def __init__(self, response: str) -> None:
        self.response = response

    def complete(self, prompt: str, **kwargs) -> str:
        return self.response


def _aws_baseline(tmp_path: Path) -> tuple[Path, Path]:
    source = Path("fixtures/eval/aws-lza-standard-handoff.md")
    bundle = tmp_path / "aws-baseline"
    compile_design(source, bundle)
    return bundle, source


def test_incremental_compile_rejects_wrong_pattern_baseline(tmp_path: Path):
    baseline = tmp_path / "terraform-baseline"
    compile_design(
        Path("fixtures/usability/byom-terraform-vpc.md"),
        baseline,
        pattern="terraform-vpc",
    )

    with pytest.raises(CompileError) as exc_info:
        compile_incremental_design(
            baseline_bundle=baseline,
            changed_doc=Path("fixtures/eval/aws-lza-standard-handoff.md"),
            output_dir=tmp_path / "output",
            pattern="aws-lza",
        )

    assert [item.code for item in exc_info.value.violations] == [
        "INCREMENTAL_BASELINE_PATTERN_MISMATCH"
    ]


def test_incremental_compile_rejects_malformed_baseline_report(tmp_path: Path):
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    (baseline / "decision-report.yaml").write_text("pattern: [unterminated\n")
    changed_doc = tmp_path / "changed.md"
    changed_doc.write_text("# Change\n")

    with pytest.raises(CompileError) as exc_info:
        compile_incremental_design(
            baseline_bundle=baseline,
            changed_doc=changed_doc,
            output_dir=tmp_path / "output",
        )

    assert exc_info.value.violations[0].code == "INCREMENTAL_BASELINE_INVALID"


def test_incremental_compile_rejects_symlinked_baseline_report(tmp_path: Path):
    baseline, source = _aws_baseline(tmp_path)
    report = baseline / "decision-report.yaml"
    outside = tmp_path / "outside-report.yaml"
    report.replace(outside)
    report.symlink_to(outside)

    with pytest.raises(CompileError) as exc_info:
        compile_incremental_design(
            baseline_bundle=baseline,
            baseline_doc=source,
            changed_doc=source,
            output_dir=tmp_path / "output",
        )

    assert exc_info.value.violations[0].code == "INCREMENTAL_BASELINE_INVALID"
    assert "symlink" in exc_info.value.violations[0].message


def test_incremental_compile_rejects_incomplete_generated_baseline(tmp_path: Path):
    baseline, source = _aws_baseline(tmp_path)
    (baseline / "accounts-config.yaml").unlink()

    with pytest.raises(CompileError) as exc_info:
        compile_incremental_design(
            baseline_bundle=baseline,
            baseline_doc=source,
            changed_doc=source,
            output_dir=tmp_path / "output",
        )

    assert any(
        item.code == "INCREMENTAL_BASELINE_REQUIRED_ARTIFACT_MISSING"
        for item in exc_info.value.violations
    )


def test_incremental_compile_rejects_inconsistent_baseline_pattern_metadata(tmp_path: Path):
    baseline, source = _aws_baseline(tmp_path)
    benchmark = baseline / "model-benchmark.yaml"
    benchmark.write_text(
        benchmark.read_text().replace("pattern: aws-lza", "pattern: terraform-vpc")
    )

    with pytest.raises(CompileError) as exc_info:
        compile_incremental_design(
            baseline_bundle=baseline,
            baseline_doc=source,
            changed_doc=source,
            output_dir=tmp_path / "output",
        )

    assert exc_info.value.violations[0].code == "INCREMENTAL_BASELINE_INVALID"


def test_incremental_precedence_is_markdown_llm_signal_baseline_default(tmp_path: Path):
    baseline, source = _aws_baseline(tmp_path)
    changed_doc = tmp_path / "changed.md"
    changed_doc.write_text(source.read_text().replace("- network_cidr: 10.50.0.0/16\n", ""))
    response = json.dumps(
        {
            "decisions": {"network_cidr": "10.77.0.0/16"},
            "signal_decisions": {"network_cidr": "10.88.0.0/16"},
        }
    )
    output = tmp_path / "output"

    compile_incremental_design(
        baseline_bundle=baseline,
        baseline_doc=source,
        changed_doc=changed_doc,
        output_dir=output,
        llm_caller=LLMCaller(_StaticBackend(response)),
    )

    trace = load_yaml_mapping(output / "llm-trace-summary.yaml")
    assert trace["acceptedDecisions"]["network_cidr"] == "10.77.0.0/16"
    assert trace["appliedDecisions"]["llm"] == ["network_cidr"]
    assert trace["appliedDecisions"]["signals"] == []
