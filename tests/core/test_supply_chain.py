"""Supply-chain configuration contracts."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def _project() -> dict[str, object]:
    return tomllib.loads(_read("pyproject.toml"))


def test_dependency_ranges_match_the_tested_compatibility_policy():
    project = _project()
    runtime = project["project"]["dependencies"]  # type: ignore[index]
    dev = project["project"]["optional-dependencies"]["dev"]  # type: ignore[index]

    assert runtime == [
        "pydantic>=2.13.4,<3",
        "typer>=0.27.0,<1",
        "ruamel.yaml>=0.19.1,<0.20",
        "requests>=2.34.2,<3",
    ]
    assert dev == [
        "build>=1.5.0,<2",
        "pytest>=9.1.1,<10",
        "pytest-cov>=7.1.0,<8",
        "ruff>=0.15.21,<0.16",
        "mypy>=2.3.0,<3",
        "pyright>=1.1.411,<2",
        "pip-audit>=2.10.1,<3",
        "bandit>=1.9.4,<2",
        "prek>=0.4.10,<0.5",
    ]


def test_uv_version_has_one_repository_source():
    project = _project()
    workflows = "\n".join(path.read_text() for path in (ROOT / ".github/workflows").glob("*.yml"))

    assert project["tool"]["uv"]["required-version"] == "==0.11.29"  # type: ignore[index]
    assert 'version: "0.11.29"' not in workflows
    assert 'version: "0.11.8"' not in workflows


def test_build_backend_is_constrained_by_version_and_hash():
    constraint = _read("build-constraints.txt")
    workflows = _read(".github/workflows/ci.yml") + _read(".github/workflows/release.yml")

    assert constraint.startswith("setuptools==83.0.0")
    assert constraint.count("--hash=sha256:") == 2
    assert (
        workflows.count("uv build --build-constraint build-constraints.txt --require-hashes") == 2
    )


def test_wheel_smoke_uses_locked_hashed_runtime_and_no_deps_install():
    for path in (".github/workflows/ci.yml", ".github/workflows/release.yml"):
        workflow = _read(path)
        assert "uv export --locked --no-dev --no-emit-project" in workflow
        assert "uv pip install --require-hashes" in workflow
        assert "uv pip install --no-deps" in workflow
        assert ".package-smoke/bin/iac-llm-wrapper --version" in workflow
        assert ".package-smoke/bin/intent-engine --version" in workflow


def test_release_rejects_mismatched_tags_and_keeps_sbom_out_of_pypi():
    release = _read(".github/workflows/release.yml")

    assert 'test "v$(uv version --short)" = "$GITHUB_REF_NAME"' in release
    assert "name: release-sbom" in release
    assert "packages-dir: dist/" in release
    assert "release-evidence/*" in release


def test_workflows_use_least_privilege_checkout_and_timeouts():
    for path in (
        ".github/workflows/ci.yml",
        ".github/workflows/pre-commit.yml",
        ".github/workflows/release.yml",
    ):
        workflow = _read(path)
        assert "permissions:\n  contents: read" in workflow
        assert "persist-credentials: false" in workflow
        assert "timeout-minutes:" in workflow


def test_dependabot_tracks_uv_without_grouping_major_updates():
    dependabot = _read(".github/dependabot.yml")

    assert "package-ecosystem: uv" in dependabot
    assert "compatible-updates:" in dependabot
    assert "- minor" in dependabot
    assert "- patch" in dependabot
    assert "- major" not in dependabot


def test_terraform_plan_root_is_packaged_and_ci_validated_with_exact_toolchain():
    project = _project()
    package_data = project["tool"]["setuptools"]["package-data"]  # type: ignore[index]
    assert package_data["intent_engine.patterns.terraform_vpc.plan_root"] == [
        "main.tf",
        "variables.tf",
        ".terraform.lock.hcl",
    ]

    workflows = _read(".github/workflows/ci.yml") + _read(".github/workflows/release.yml")
    action = "hashicorp/setup-terraform@dfe3c3f87815947d99a8997f908cb6525fc44e9e # v4.0.1"
    assert workflows.count(action) == 2
    assert workflows.count('terraform_version: "1.15.8"') == 2
    assert workflows.count("terraform_wrapper: false") == 2
    assert workflows.count("python scripts/validate-terraform-vpc-plan-root.py") == 2


def test_terraform_root_and_lock_pin_the_approved_module_and_provider():
    main = _read("src/intent_engine/patterns/terraform_vpc/plan_root/main.tf")
    lock = _read("src/intent_engine/patterns/terraform_vpc/plan_root/.terraform.lock.hcl")

    assert 'required_version = "= 1.15.8"' in main
    assert 'source  = "terraform-aws-modules/vpc/aws"' in main
    assert 'version = "6.6.1"' in main
    assert 'source  = "hashicorp/aws"' in main
    assert 'version = "= 6.53.0"' in main
    assert 'provider "registry.terraform.io/hashicorp/aws"' in lock
    assert 'version     = "6.53.0"' in lock
    assert lock.count('"h1:') == 4
