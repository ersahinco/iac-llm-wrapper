"""Emission, scanning, and the optional LLM guide."""

from __future__ import annotations

import shutil

import pytest
from ruamel.yaml import YAML

from intent_engine import scan
from intent_engine.emit import EmitBlocked, emit_bundle, resolve
from intent_engine.llm import LlmConfig, LlmError, _content, deterministic_questions
from intent_engine.models import Conflict, Fact
from intent_engine.scan import ScanError, _parse_checkov, _parse_opa, _parse_trivy, bundle_input

_YAML = YAML(typ="safe")


def _drop(facts, *keys):
    return [fact for fact in facts if fact.decision_key not in keys]


def _add(facts, **pairs):
    return _drop(facts, *pairs) + [
        Fact(decision_key=key, value=value, section="test", line=1)
        for key, value in pairs.items()
    ]


def _load(path):
    return _YAML.load(path.read_text("utf-8"))


# emit ----------------------------------------------------------------------


def test_bundle_matches_the_accepted_decisions(catalog, sample_facts, make_review, tmp_path):
    review = make_review(sample_facts)
    written = emit_bundle(resolve(catalog, review, sample_facts), review, tmp_path)

    assert {path.name for path in written} == {
        "organization-config.yaml",
        "accounts-config.yaml",
        "global-config.yaml",
        "iam-config.yaml",
        "network-config.yaml",
        "security-config.yaml",
        "decision-trace.yaml",
    }

    global_config = _load(tmp_path / "global-config.yaml")
    assert global_config["homeRegion"] == "eu-central-1"
    assert global_config["controlTower"]["enable"] is True

    accounts = _load(tmp_path / "accounts-config.yaml")
    assert {a["name"] for a in accounts["mandatoryAccounts"]} == {
        "Management",
        "LogArchive",
        "Audit",
        "SecurityTooling",
        "NetworkShared",
    }
    assert all(a["email"] for a in accounts["workloadAccounts"])

    network = _load(tmp_path / "network-config.yaml")
    assert network["transitGateways"][0]["account"] == "NetworkShared"
    assert network["vpcs"][0]["cidrs"] == ["10.64.0.0/16"]

    security = _load(tmp_path / "security-config.yaml")
    assert security["centralSecurityServices"]["guardduty"]["enable"] is True


def test_every_value_is_traceable_to_the_document(catalog, sample_facts, make_review, tmp_path):
    review = make_review(sample_facts)
    emit_bundle(resolve(catalog, review, sample_facts), review, tmp_path)

    assert review.sha256 in (tmp_path / "global-config.yaml").read_text("utf-8")
    trace = _load(tmp_path / "decision-trace.yaml")
    entries = {entry["decision"]: entry for entry in trace["decisions"]}
    assert trace["sourceDocument"] == review.document
    assert entries["topology"]["origin"] == "document"
    assert entries["network_cidr"]["evidence"].startswith("Network:")


def test_single_vpc_drops_the_transit_gateway(catalog, sample_facts, make_review, tmp_path):
    facts = _add(_drop(sample_facts, "network_account"), topology="single-vpc")
    review = make_review(facts)
    emit_bundle(resolve(catalog, review, facts), review, tmp_path)

    network = _load(tmp_path / "network-config.yaml")
    assert "transitGateways" not in network
    assert network["vpcs"][0]["account"] == "DigitalBankingProd"


def test_conflicts_block_emission(catalog, sample_facts, make_review):
    conflict = Conflict(code="HOME_REGION_NOT_ENABLED", message="x", decision_keys=[])
    review = make_review(sample_facts, conflicts=[conflict])
    with pytest.raises(EmitBlocked, match="HOME_REGION_NOT_ENABLED"):
        resolve(catalog, review, sample_facts)


def test_unanswered_decision_blocks_emission(catalog, sample_facts, make_review):
    facts = _drop(sample_facts, "network_cidr")
    with pytest.raises(EmitBlocked, match="network_cidr"):
        resolve(catalog, make_review(facts), facts)


def test_defaults_need_opt_in_and_are_recorded(catalog, sample_facts, make_review):
    facts = _drop(sample_facts, "compliance_overlay")
    resolution = resolve(catalog, make_review(facts), facts, allow_defaults=True)
    defaulted = [e["decision"] for e in resolution.trace if e["origin"] == "default"]
    assert defaulted == ["compliance_overlay"]
    assert resolution.values["compliance_overlay"] == "none"


def test_account_without_an_approved_email_blocks_emission(
    catalog, sample_facts, make_review, tmp_path
):
    facts = _add(sample_facts, account_emails="Management=aws-management@example.com")
    review = make_review(facts)
    with pytest.raises(EmitBlocked, match="no approved root email"):
        emit_bundle(resolve(catalog, review, facts), review, tmp_path)


# scan ----------------------------------------------------------------------


def test_bundle_input_merges_every_config_file(catalog, sample_facts, make_review, tmp_path):
    review = make_review(sample_facts)
    emit_bundle(resolve(catalog, review, sample_facts), review, tmp_path)

    document = bundle_input(tmp_path)
    assert set(document) == {"organization", "accounts", "global", "iam", "network", "security"}
    assert document["global"]["homeRegion"] == "eu-central-1"


def test_missing_bundle_file_names_the_path(tmp_path):
    with pytest.raises(ScanError, match="expected bundle file is missing"):
        bundle_input(tmp_path)


def test_tool_output_parsing():
    assert _parse_opa({"result": [{"expressions": [{"value": ["b", "a"]}]}]}) == ["a", "b"]
    assert _parse_opa({"result": [{"expressions": [{"value": []}]}]}) == []
    assert _parse_checkov(
        {"results": {"failed_checks": [{"file_path": "/a.yaml", "check_id": "CKV_SECRET_1"}]}}
    ) == ["/a.yaml: CKV_SECRET_1"]
    assert _parse_trivy(
        {"Results": [{"Target": "a.yaml", "Secrets": [{"RuleID": "aws-access-key-id"}]}]}
    ) == ["a.yaml: secret aws-access-key-id"]


def test_undefined_policy_is_not_a_pass():
    with pytest.raises(ScanError, match="is undefined"):
        _parse_opa({"result": []})


def test_unexpected_policy_result_is_not_a_pass():
    with pytest.raises(ScanError, match="expected a set of messages"):
        _parse_opa({"result": [{"expressions": [{"value": "nope"}]}]})


@pytest.mark.skipif(shutil.which("opa") is None, reason="opa is not installed")
def test_policy_denies_a_weakened_bundle(catalog, sample_facts, make_review, tmp_path):
    """A passing policy has to be able to fail. Prove it against the real binary."""
    review = make_review(sample_facts)
    emit_bundle(resolve(catalog, review, sample_facts), review, tmp_path)
    assert scan.run_opa(tmp_path).status == "passed"

    weakened = tmp_path / "global-config.yaml"
    weakened.write_text(
        weakened.read_text("utf-8").replace(
            "terminationProtection: true", "terminationProtection: false"
        ),
        encoding="utf-8",
    )
    result = scan.run_opa(tmp_path)
    assert result.status == "findings"
    assert any("terminationProtection" in finding for finding in result.findings)


@pytest.mark.parametrize(
    ("runner", "tool"),
    [(scan.run_opa, "opa"), (scan.run_checkov, "checkov"), (scan.run_trivy, "trivy")],
)
def test_absent_tool_is_not_reported_as_a_pass(monkeypatch, tmp_path, runner, tool):
    monkeypatch.setattr(scan.shutil, "which", lambda _: None)
    result = runner(tmp_path)
    assert result.status == "not-installed"
    assert result.blocking is False
    assert tool in result.detail


# llm -----------------------------------------------------------------------


def test_frontier_questions_need_no_model(catalog, sample_facts, make_review):
    conflict = Conflict(
        code="OVERLAY_REQUIRES_DETECTION", message="detection off", decision_keys=[]
    )
    review = make_review(sample_facts, conflicts=[conflict])
    lines = deterministic_questions(review, catalog)
    assert lines == ["[conflict:OVERLAY_REQUIRES_DETECTION] detection off"]


def test_provider_and_model_must_be_explicit():
    with pytest.raises(LlmError, match="unknown provider"):
        LlmConfig(provider="guess", model="m", base_url="http://localhost")
    with pytest.raises(LlmError, match="requires an explicit model"):
        LlmConfig(provider="ollama", model="", base_url="http://localhost")


def test_both_provider_shapes_are_read_and_empty_text_fails():
    assert _content({"choices": [{"message": {"content": "agenda"}}]}, "u") == "agenda"
    assert _content({"message": {"content": "agenda"}}, "u") == "agenda"
    with pytest.raises(LlmError, match="no usable text"):
        _content({"message": {"content": " "}}, "u")
