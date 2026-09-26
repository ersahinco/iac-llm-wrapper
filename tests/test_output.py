"""Emission, scanning, and the optional LLM guide."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest
from ruamel.yaml import YAML
from typer.testing import CliRunner

from intent_engine import scan
from intent_engine.analysis import semantic_conflicts
from intent_engine.cli import app
from intent_engine.contract import CONFIG_FILES, LZA_VERSION, validate_configs
from intent_engine.emit import EmitBlocked, emit_bundle, resolve
from intent_engine.llm import LlmConfig, LlmError, _content, deterministic_questions
from intent_engine.models import Conflict, Fact
from intent_engine.scan import ScanError, _parse_checkov, _parse_opa, _parse_trivy, bundle_input

_YAML = YAML(typ="safe")


def _drop(facts, *keys):
    return [fact for fact in facts if fact.decision_key not in keys]


def _add(facts, **pairs):
    return _drop(facts, *pairs) + [
        Fact(decision_key=key, value=value, section="test", line=1) for key, value in pairs.items()
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
        "handoff.yaml",
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


def test_stated_decisions_are_traceable_to_the_document(
    catalog, sample_facts, make_review, tmp_path
):
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
    facts = [
        fact.model_copy(
            update={
                "value": ", ".join(
                    item for item in fact.value.split(", ") if not item.startswith("NetworkShared=")
                )
            }
        )
        if fact.decision_key == "account_emails"
        else fact
        for fact in facts
    ]
    facts = [
        fact.model_copy(
            update={
                "value": ", ".join(
                    item for item in fact.value.split(", ") if not item.endswith(":NetworkShared")
                )
            }
        )
        if fact.decision_key == "identity_center_assignments"
        else fact
        for fact in facts
    ]
    review = make_review(facts)
    emit_bundle(resolve(catalog, review, facts), review, tmp_path)

    network = _load(tmp_path / "network-config.yaml")
    assert network["transitGateways"] == []
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
    with pytest.raises(EmitBlocked, match="ACCOUNT_EMAIL_MISSING"):
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
        {
            "summary": {"passed": 0, "failed": 1, "parsing_errors": 0},
            "results": {"failed_checks": [{"file_path": "/a.yaml", "check_id": "CKV_SECRET_1"}]},
        }
    ) == (["/a.yaml: CKV_SECRET_1"], 1)
    assert _parse_trivy(
        {
            "SchemaVersion": 2,
            "ArtifactType": "filesystem",
            "ArtifactName": "/bundle",
            "Results": [{"Target": "a.yaml", "Secrets": [{"RuleID": "aws-access-key-id"}]}],
        }
    ) == (["a.yaml: secret aws-access-key-id"], 1)


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
    assert result.blocking is True
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


# Regression checks for the first banking milestone --------------------------


def test_defaults_are_revalidated_for_conflicts(catalog, sample_facts, make_review):
    catalog = dict(catalog)
    catalog["compliance_overlay"] = catalog["compliance_overlay"].model_copy(
        update={"default": "financial-services"}
    )
    facts = _add(_drop(sample_facts, "compliance_overlay"), centralized_logging="false")
    assert semantic_conflicts(catalog, facts) == []
    with pytest.raises(EmitBlocked, match="OVERLAY_REQUIRES_CENTRAL_LOGGING"):
        resolve(catalog, make_review(facts), facts, allow_defaults=True)


def test_default_account_cannot_collide_with_workload(catalog, sample_facts, make_review):
    facts = _drop(sample_facts, "security_tooling_account")
    facts = [
        f.model_copy(update={"value": f.value + ", SecurityTooling"})
        if f.decision_key == "workload_accounts"
        else f
        for f in facts
    ]
    assert semantic_conflicts(catalog, facts) == []
    with pytest.raises(EmitBlocked, match="ACCOUNT_NAME_RESERVED"):
        resolve(catalog, make_review(facts), facts, allow_defaults=True)


@pytest.mark.parametrize("runner", [scan.run_checkov, scan.run_trivy])
@pytest.mark.parametrize("stdout", ["{}", "[]", "not json"])
@pytest.mark.parametrize("exit_code", [0, 2])
def test_failed_or_malformed_scan_never_passes(monkeypatch, tmp_path, runner, stdout, exit_code):
    monkeypatch.setattr(scan.shutil, "which", lambda _: "/scanner")
    monkeypatch.setattr(
        scan,
        "_run",
        lambda command: subprocess.CompletedProcess(
            command, exit_code, stdout, "scanner failure" if exit_code else ""
        ),
    )
    result = runner(tmp_path)
    assert result.status == "error"
    assert result.blocking


@pytest.mark.parametrize(
    "runner,payload",
    [
        (
            scan.run_checkov,
            {
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "parsing_errors": 0,
                "resource_count": 0,
                "checkov_version": "3.3.10",
            },
        ),
        (
            scan.run_trivy,
            {"SchemaVersion": 2, "ArtifactType": "filesystem", "ArtifactName": "/bundle"},
        ),
    ],
)
def test_real_empty_reports_are_unassessed(monkeypatch, tmp_path, runner, payload):
    monkeypatch.setattr(scan.shutil, "which", lambda _: "/scanner")
    monkeypatch.setattr(
        scan,
        "_run",
        lambda command: subprocess.CompletedProcess(command, 0, json.dumps(payload), ""),
    )
    result = runner(tmp_path)
    assert result.status == "not-assessed"
    assert result.blocking


@pytest.mark.parametrize(
    "runner,payload,exit_code,expected",
    [
        (
            scan.run_checkov,
            {
                "summary": {"passed": 1, "failed": 0, "parsing_errors": 0},
                "results": {"failed_checks": []},
            },
            0,
            "passed",
        ),
        (
            scan.run_checkov,
            {
                "summary": {"passed": 0, "failed": 1, "parsing_errors": 0},
                "results": {"failed_checks": [{"file_path": "/x", "check_id": "SECRET"}]},
            },
            1,
            "findings",
        ),
        (
            scan.run_checkov,
            {
                "summary": {"passed": 1, "failed": 0, "parsing_errors": 1},
                "results": {"failed_checks": []},
            },
            0,
            "error",
        ),
        (
            scan.run_checkov,
            {
                "summary": {"passed": 0, "failed": 2, "parsing_errors": 0},
                "results": {"failed_checks": []},
            },
            1,
            "error",
        ),
        (
            scan.run_checkov,
            {
                "summary": {"passed": 1, "failed": 0, "parsing_errors": 0},
                "results": {"failed_checks": []},
            },
            1,
            "error",
        ),
        (
            scan.run_trivy,
            {
                "SchemaVersion": 2,
                "ArtifactType": "filesystem",
                "ArtifactName": "/bundle",
                "Results": [{"Target": "/x", "Secrets": [{"RuleID": "SECRET"}]}],
            },
            0,
            "findings",
        ),
        (
            scan.run_trivy,
            {
                "SchemaVersion": 2,
                "ArtifactType": "filesystem",
                "ArtifactName": "/bundle",
                "Results": [{"Target": "/x", "MisconfSummary": {"Successes": 1, "Failures": 0}}],
            },
            0,
            "passed",
        ),
        (
            scan.run_trivy,
            {
                "SchemaVersion": 2,
                "ArtifactType": "filesystem",
                "ArtifactName": "/bundle",
                "Results": [{"Target": "/x", "MisconfSummary": {"Successes": 0, "Failures": 1}}],
            },
            0,
            "error",
        ),
        (
            scan.run_trivy,
            {
                "SchemaVersion": 2,
                "ArtifactType": "filesystem",
                "ArtifactName": "/bundle",
                "Results": [
                    {"Target": "/x", "Misconfigurations": [{"ID": "BAD", "Status": "FAIL"}]}
                ],
            },
            0,
            "findings",
        ),
    ],
)
def test_scan_verdicts_follow_report_evidence(
    monkeypatch, tmp_path, runner, payload, exit_code, expected
):
    monkeypatch.setattr(scan.shutil, "which", lambda _: "/scanner")
    monkeypatch.setattr(
        scan,
        "_run",
        lambda command: subprocess.CompletedProcess(command, exit_code, json.dumps(payload), ""),
    )
    result = runner(tmp_path)
    assert result.status == expected
    assert result.blocking == (expected != "passed")


@pytest.mark.parametrize("runner", [scan.run_checkov, scan.run_trivy])
@pytest.mark.parametrize(
    "failure", [OSError("cannot execute"), subprocess.TimeoutExpired("tool", 300)]
)
def test_scanner_process_failures_return_error(monkeypatch, tmp_path, runner, failure):
    monkeypatch.setattr(scan.shutil, "which", lambda _: "/scanner")

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(scan.subprocess, "run", fail)
    assert runner(tmp_path).status == "error"


@pytest.mark.parametrize("status", ["not-installed", "not-assessed", "error", "findings", "passed"])
def test_scan_cli_exit_status(monkeypatch, tmp_path, status):
    monkeypatch.setattr(
        "intent_engine.cli.scan_bundle",
        lambda *args: [scan.ToolResult("checkov", status, "scope of check")],
    )
    result = CliRunner().invoke(app, ["scan", str(tmp_path), "--json"])
    assert result.exit_code == (0 if status == "passed" else 1)
    assert json.loads(result.stdout)[0]["status"] == status


@pytest.mark.skipif(shutil.which("opa") is None, reason="opa is not installed")
@pytest.mark.parametrize(
    "filename,path",
    [
        ("global-config.yaml", ["terminationProtection"]),
        ("global-config.yaml", ["logging", "cloudtrail", "organizationTrail"]),
        ("global-config.yaml", ["enabledRegions"]),
        ("global-config.yaml", ["homeRegion"]),
        ("security-config.yaml", ["centralSecurityServices", "guardduty", "enable"]),
        ("security-config.yaml", ["centralSecurityServices", "s3PublicAccessBlock", "enable"]),
        (
            "security-config.yaml",
            ["centralSecurityServices", "ebsDefaultVolumeEncryption", "enable"],
        ),
        ("security-config.yaml", ["iamPasswordPolicy", "minimumPasswordLength"]),
        ("accounts-config.yaml", ["mandatoryAccounts"]),
        ("accounts-config.yaml", ["workloadAccounts"]),
        ("iam-config.yaml", ["identityCenter", "identityCenterAssignments"]),
    ],
)
@pytest.mark.parametrize("mutation", ["missing", "wrong-type"])
def test_policy_rejects_missing_or_mistyped_fields(
    catalog, sample_facts, make_review, tmp_path, filename, path, mutation
):
    review = make_review(sample_facts)
    emit_bundle(resolve(catalog, review, sample_facts), review, tmp_path)
    target = tmp_path / filename
    data = _load(target)
    parent = data
    for part in path[:-1]:
        parent = parent[part]
    if mutation == "missing":
        del parent[path[-1]]
    else:
        parent[path[-1]] = {"unexpected": "object"}
    with target.open("w") as handle:
        _YAML.dump(data, handle)
    result = scan.run_opa(tmp_path)
    assert result.status == "findings", result


@pytest.mark.skipif(shutil.which("opa") is None, reason="opa is not installed")
def test_minimal_mapping_bundle_cannot_pass_policy(tmp_path):
    for name in scan._BUNDLE_INPUTS.values():
        (tmp_path / name).write_text("{}\n", encoding="utf-8")
    (tmp_path / "global-config.yaml").write_text(
        "homeRegion: eu-central-1\nenabledRegions: [eu-central-1]\n", encoding="utf-8"
    )
    result = scan.run_opa(tmp_path)
    assert result.status == "findings"
    assert any("terminationProtection" in item for item in result.findings)


def test_emitted_contract_and_owner_handoff(catalog, sample_facts, make_review, tmp_path):
    result = make_review(sample_facts)
    emit_bundle(resolve(catalog, result, sample_facts), result, tmp_path)
    documents = {name: _load(tmp_path / name) for name in CONFIG_FILES}
    assert validate_configs(documents) == []
    handoff = _load(tmp_path / "handoff.yaml")
    assert handoff["target"]["version"] == LZA_VERSION
    assert handoff["status"] == "requires-owner-validation"
    assert set(handoff["configurationFiles"]) == set(CONFIG_FILES)
    assert set(handoff["layers"]) == {"network", "identity", "data", "application"}
    assert handoff["layers"]["data"]["approvedRegions"] == ["eu-central-1", "eu-west-1"]
    assert handoff["owner"] == "Digital Banking Platform team"
    permission_sets = documents["iam-config.yaml"]["identityCenter"]["identityCenterPermissionSets"]
    policies = {entry["name"]: entry["policies"]["awsManaged"] for entry in permission_sets}
    assert policies["BreakGlassAdmin"] == ["AdministratorAccess"]
    assert policies["NetworkAdmin"] == ["AmazonVPCFullAccess"]
    assert (
        documents["security-config.yaml"]["centralSecurityServices"]["delegatedAdminAccount"]
        == "SecurityTooling"
    )
    assert documents["network-config.yaml"]["defaultVpc"]["delete"] is False


@pytest.mark.parametrize("filename", CONFIG_FILES)
def test_contract_rejects_unknown_fields(catalog, sample_facts, make_review, tmp_path, filename):
    result = make_review(sample_facts)
    emit_bundle(resolve(catalog, result, sample_facts), result, tmp_path)
    documents = {name: _load(tmp_path / name) for name in CONFIG_FILES}
    documents[filename]["inventedField"] = True
    errors = validate_configs(documents)
    assert any(filename in error and "inventedField" in error for error in errors)


def test_schema_failure_writes_no_bundle(catalog, sample_facts, make_review, tmp_path, monkeypatch):
    monkeypatch.setattr("intent_engine.emit._network_config", lambda values: {})
    result = make_review(sample_facts)
    out = tmp_path / "bundle"
    with pytest.raises(EmitBlocked, match="schema validation failed"):
        emit_bundle(resolve(catalog, result, sample_facts), result, out)
    assert not out.exists()


def test_scan_revalidates_edited_configs(catalog, sample_facts, make_review, tmp_path, monkeypatch):
    result = make_review(sample_facts)
    emit_bundle(resolve(catalog, result, sample_facts), result, tmp_path)
    path = tmp_path / "network-config.yaml"
    data = _load(path)
    del data["endpointPolicies"]
    with path.open("w") as handle:
        _YAML.dump(data, handle)
    monkeypatch.setattr(scan.shutil, "which", lambda _: None)
    schema = scan.scan_bundle(tmp_path)[0]
    assert schema.tool == "lza-schema"
    assert schema.status == "findings"
    assert any("endpointPolicies" in finding for finding in schema.findings)


def test_missing_policy_mapping_blocks_emit(catalog, sample_facts, make_review):
    facts = _drop(sample_facts, "identity_center_policy_mappings")
    with pytest.raises(EmitBlocked, match="identity_center_policy_mappings"):
        resolve(catalog, make_review(facts), facts)


def test_owner_network_provenance_and_content(catalog, sample_facts, make_review, tmp_path):
    import hashlib

    result = make_review(sample_facts)
    resolution = resolve(catalog, result, sample_facts)
    skeleton = tmp_path / "skeleton"
    emit_bundle(resolution, result, skeleton)
    network = _load(skeleton / "network-config.yaml")
    network["vpcs"][0]["routeTables"] = [{"name": "OwnerPrivate", "routes": []}]
    owner = tmp_path / "approved-network.yaml"
    with owner.open("w") as handle:
        _YAML.dump(network, handle)
    original = owner.read_bytes()
    out = tmp_path / "bundle"
    emit_bundle(resolution, result, out, network_config=owner)
    assert _load(out / "network-config.yaml") == network
    assert owner.read_bytes() == original
    source = _load(out / "handoff.yaml")["layers"]["network"]["source"]
    assert source == {
        "origin": "owner-file",
        "path": str(owner),
        "sha256": hashlib.sha256(original).hexdigest(),
    }


@pytest.mark.parametrize(
    "case,message",
    [
        ("missing", "cannot read owner"),
        ("malformed", "cannot read owner"),
        ("list", "must be a YAML mapping"),
        ("schema", "schema validation failed"),
        ("home", "homeRegion differs"),
        ("cidr", "matching the packet"),
        ("gateway", "needs a transit gateway"),
    ],
)
def test_bad_owner_network_blocks_before_writing(
    catalog, sample_facts, make_review, tmp_path, case, message
):
    result = make_review(sample_facts)
    resolution = resolve(catalog, result, sample_facts)
    skeleton = tmp_path / "skeleton"
    emit_bundle(resolution, result, skeleton)
    network = _load(skeleton / "network-config.yaml")
    owner = tmp_path / "owner.yaml"
    if case == "malformed":
        owner.write_text("vpcs: [\n", encoding="utf-8")
    elif case == "list":
        owner.write_text("[]\n", encoding="utf-8")
    elif case != "missing":
        if case == "schema":
            del network["endpointPolicies"]
        elif case == "home":
            network["homeRegion"] = "eu-west-1"
        elif case == "cidr":
            network["vpcs"][0]["cidrs"] = ["10.99.0.0/16"]
        elif case == "gateway":
            network["transitGateways"] = []
        with owner.open("w") as handle:
            _YAML.dump(network, handle)
    out = tmp_path / "bundle"
    with pytest.raises(EmitBlocked, match=message):
        emit_bundle(resolution, result, out, network_config=owner)
    assert not out.exists()


@pytest.mark.parametrize("symlink", [False, True])
def test_owner_source_cannot_be_overwritten(catalog, sample_facts, make_review, tmp_path, symlink):
    result = make_review(sample_facts)
    resolution = resolve(catalog, result, sample_facts)
    out = tmp_path / "bundle"
    emit_bundle(resolution, result, out)
    source = out / "network-config.yaml"
    original = source.read_bytes()
    if symlink:
        owner = tmp_path / "owner.yaml"
        owner.write_bytes(original)
        source.unlink()
        source.symlink_to(owner)
        source = owner
    with pytest.raises(EmitBlocked, match="separate from the output"):
        emit_bundle(resolution, result, out, network_config=source)
    assert source.read_bytes() == original
