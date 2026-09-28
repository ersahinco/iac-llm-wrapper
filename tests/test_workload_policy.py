"""Native OPA policies: scoped allocations, instance allowlists and visible exceptions."""

import json
import shutil
from pathlib import Path

import pytest

from intent_engine.analysis import typed_values
from intent_engine.catalog import load_catalog
from intent_engine.ingest import extract_facts, read_document
from intent_engine.organisation import (
    assess,
    load_organisation,
    organisation_catalog,
    policy_conflicts,
)

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "vpc"
pytestmark = pytest.mark.skipif(shutil.which("opa") is None, reason="OPA not installed")


def case():
    base = load_catalog(SAMPLE / "decisions.yaml")
    org = load_organisation(SAMPLE / "organisation.yaml", base)
    catalog = organisation_catalog(base, org)
    facts = extract_facts(read_document(SAMPLE / "confirmed-policy.md"), catalog)
    values, _ = typed_values(catalog, facts)
    return org, facts, values


@pytest.mark.parametrize(
    "updates,policy,status,phrase",
    [
        ({}, "existing-networks", "passed", "No overlap"),
        ({"network_cidr": "10.20.1.0/24"}, "existing-networks", "conflict", "datacentre"),
        ({"routing_domain": "isolated-lab"}, "existing-networks", "conflict", "disconnected-lab"),
        ({"routing_domain": "unknown"}, "existing-networks", "not-assessed", "allocation list"),
        ({"network_cidr": "broken"}, "existing-networks", "not-assessed", "valid VPC"),
        ({"instance_type": "t3.small"}, "instance-size", "passed", "allowlist"),
        ({"instance_type": "r5.xlarge"}, "instance-size", "conflict", "t3.small"),
        ({}, "instance-size", "warning", "EXAMPLE-42"),
        (
            {"environment": "production", "instance_type": "t3.small"},
            "instance-size",
            "conflict",
            "m5.large",
        ),
        ({"environment": "unknown"}, "instance-size", "not-assessed", "allowlist"),
        ({}, "monitoring", "warning", "monitoring is disabled"),
        ({"detailed_monitoring": True}, "monitoring", "passed", "requested"),
    ],
)
def test_scoped_policy_outcomes(updates, policy, status, phrase):
    org, facts, values = case()
    results = assess(org, values | updates)
    result = next(r for r in results if r.policy_id == policy)
    assert result.status == status
    assert phrase in result.message
    assert result.input_sha256
    conflicts = policy_conflicts(org, [result], facts, "client.md")
    assert bool(conflicts) == (status in {"conflict", "not-assessed"})


@pytest.mark.parametrize(
    "change",
    [
        "missing-allocations",
        "bad-allocation",
        "missing-allowlist",
        "bad-allowlist",
        "exception-without-reason",
    ],
)
def test_incomplete_reference_or_exception_cannot_pass(change):
    org, _, values = case()
    reference = next(r for r in org.references if r.id == "estate")
    from ruamel.yaml import YAML

    data = YAML(typ="safe").load(reference.content)
    if change == "missing-allocations":
        del data["routing_domains"]["corporate"]
    elif change == "bad-allocation":
        data["routing_domains"]["corporate"][0]["cidr"] = "not-a-network"
    elif change == "missing-allowlist":
        del data["instance_types"]["development"]
    elif change == "bad-allowlist":
        data["instance_types"]["development"] = [None]
    else:
        data["instance_exceptions"][0]["reason"] = " "
    reference.content = json.dumps(data)
    results = {r.policy_id: r for r in assess(org, values)}
    policy = "existing-networks" if "allocation" in change else "instance-size"
    assert results[policy].status == (
        "conflict" if change == "exception-without-reason" else "not-assessed"
    )
