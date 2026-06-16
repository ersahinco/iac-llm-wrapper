"""Policy graph metadata tests."""

from __future__ import annotations

from intent_engine.core.policy import (
    PolicyControl,
    PolicyPack,
    PolicyRequirementMapping,
    map_findings_to_controls,
    policy_pack_to_dict,
)


def test_policy_pack_serializes_with_contract_aliases():
    pack = PolicyPack(
        name="regulated-test-v1",
        version="1.0.0",
        frameworks=["SOC2", "CUSTOM_CLIENT"],
        controls=[
            PolicyControl(
                id="CTRL-001",
                title="Account routing",
                mapping=PolicyRequirementMapping(
                    requirement_keys=["target_account_id"],
                    target_contracts=["terraform-aws-vpc-module"],
                    artifact_paths=["decision-report.yaml:delivery.targetAccountId"],
                    module_variables=["cidr"],
                    checkov_check_ids=["CKV_CUSTOM_1"],
                    owner_policy_refs=["owner://policy"],
                ),
            )
        ],
    )

    data = policy_pack_to_dict(pack)

    mapping = data["controls"][0]["mapping"]
    assert mapping["requirementKeys"] == ["target_account_id"]
    assert mapping["targetContracts"] == ["terraform-aws-vpc-module"]
    assert mapping["artifactPaths"] == ["decision-report.yaml:delivery.targetAccountId"]
    assert mapping["moduleVariables"] == ["cidr"]
    assert mapping["checkovCheckIds"] == ["CKV_CUSTOM_1"]
    assert mapping["ownerPolicyRefs"] == ["owner://policy"]


def test_findings_map_to_registered_policy_controls():
    pack = PolicyPack(
        name="regulated-test-v1",
        version="1.0.0",
        controls=[
            PolicyControl(
                id="CTRL-001",
                title="CIDR control",
                mapping=PolicyRequirementMapping(checkov_check_ids=["CKV_CUSTOM_1"]),
            )
        ],
    )

    mapped, unmapped = map_findings_to_controls(
        [
            {"checkId": "CKV_CUSTOM_1", "resource": "module.vpc", "filePath": "/main.tf"},
            {"checkId": "CKV_OTHER", "resource": "module.other"},
        ],
        [pack],
    )

    assert mapped[0]["policyPack"] == "regulated-test-v1"
    assert mapped[0]["controlId"] == "CTRL-001"
    assert unmapped == [{"checkId": "CKV_OTHER", "resource": "module.other"}]
