"""Product-language guardrails for the registered target configuration promise."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_readme_frames_registered_target_configuration_boundary():
    text = _read("README.md")
    normalized = " ".join(text.split())

    assert "Architect exchange to registered target configuration" in text
    assert "registered-target configuration artifacts" in text
    assert "existing deployment mechanism" in text
    assert "AWS Landing Zone Accelerator is the reference path" in text
    assert "does not generate whole IaC from scratch" in normalized
    assert "official validator may perform read-only AWS account lookup" in text
    assert "does not synth, deploy, clone, install, or call AWS APIs" not in text


def test_agents_context_uses_registered_target_language():
    text = _read("AGENTS.md")

    assert "architect-exchange-to-registered-target" in text
    assert "contract-checked LZA YAML/config files" in text
    assert "target configuration artifacts" in text
    assert "Direct deployment and whole-IaC-from-scratch generation stay out" in text


def test_pattern_authoring_keeps_deployment_invocation_out_of_scope():
    text = _read("docs/PATTERN_AUTHORING.md")

    assert "registered target pattern" in text
    assert "deterministic target configuration artifacts" in text
    assert "deployment target contracts" in text
    assert "Do not invoke cloud APIs, Terraform, CloudFormation, AWS LZA, apply commands" in text
    assert "plan invocation must be registered, plan-only, contract-backed" in text


def test_public_surfaces_avoid_intent_to_iac_positioning():
    public_text = "\n".join(
        _read(path)
        for path in (
            "CONTRIBUTING.md",
            "docs/LLM_SETUP.md",
            "pyproject.toml",
            "src/intent_engine/cli.py",
        )
    ).lower()

    assert "intent-to-iac orchestration" not in public_text
    assert "registered target configuration" in public_text


def test_docs_do_not_claim_direct_deployment_from_prose():
    docs = "\n".join(
        _read(path)
        for path in (
            "README.md",
            "AGENTS.md",
            "docs/ARCHITECTURE.md",
            "docs/ARTIFACTS.md",
            "docs/PATTERN_AUTHORING.md",
            "docs/EXTENSION.md",
        )
    ).lower()

    forbidden_claims = [
        "deploys infrastructure from prose",
        "generates whole iac from scratch",
        "generates arbitrary deployable infrastructure from prose",
        "invokes cloud apis",
        "invokes apply",
        "invokes unregistered deployment pipelines",
    ]
    for claim in forbidden_claims:
        assert claim not in docs
