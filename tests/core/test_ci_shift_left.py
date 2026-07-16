"""CI guardrails for shift-left handoff bundle checks."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_github_actions_runs_golden_journey_shift_left_check():
    ci = _read(".github/workflows/ci.yml")
    pr_template = _read(".github/pull_request_template.md")

    command = "uv run --locked --extra dev python scripts/evaluate-golden-journey.py"
    assert "Golden journey shift-left check" in ci
    assert command in ci
    assert command in pr_template


def test_github_actions_do_not_run_infrastructure_deploy_commands():
    workflow_dir = ROOT / ".github/workflows"
    workflows = "\n".join(path.read_text().lower() for path in workflow_dir.glob("*.yml"))

    forbidden_commands = (
        "terraform apply",
        "terragrunt apply",
        "aws cloudformation deploy",
        "cdk deploy",
        "kubectl apply",
        "pulumi up",
    )
    for command in forbidden_commands:
        assert command not in workflows
