"""Organisation references stay distinct from client decisions."""

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from ruamel.yaml import YAML

from intent_engine.analysis import typed_values
from intent_engine.catalog import load_catalog
from intent_engine.ingest import IngestError, extract_facts, read_document
from intent_engine.models import Organisation
from intent_engine.organisation import assess, load_organisation, organisation_catalog

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "organisation"


def test_reference_values_do_not_answer_client_questions():
    base = load_catalog()
    org = load_organisation(SAMPLE / "organisation.yaml", base)
    catalog = organisation_catalog(base, org)
    facts = extract_facts(read_document(SAMPLE / "client.md"), catalog)
    values, _ = typed_values(catalog, facts)
    assert "hybrid_connection" not in values
    assert "us-east-1" in values["enabled_regions"]
    assert len(org.systems) == 4
    assert all(reference.sha256 for reference in org.references)


@pytest.mark.skipif(shutil.which("opa") is None, reason="OPA not installed")
def test_real_organisation_policy_conflict_then_correction():
    base = load_catalog()
    org = load_organisation(SAMPLE / "organisation.yaml", base)
    catalog = organisation_catalog(base, org)
    results = []
    for name in ("client.md", "confirmed.md"):
        facts = extract_facts(read_document(SAMPLE / name), catalog)
        values, _ = typed_values(catalog, facts)
        results.append(assess(org, values)[0])
    assert [r.status for r in results] == ["conflict", "passed"]
    assert "us-east-1" in results[0].message
    assert results[0].input_sha256 != results[1].input_sha256
    assert assess(org, {})[0].status == "not-assessed"


@pytest.mark.parametrize(
    "output", [[], {}, [{"policy_id": "unknown", "status": "passed", "message": "ok"}]]
)
def test_missing_or_malformed_opa_coverage_never_passes(output):
    org = load_organisation(SAMPLE / "organisation.yaml", load_catalog())
    with (
        patch("intent_engine.organisation.shutil.which", return_value="opa"),
        patch("intent_engine.organisation.subprocess.run") as run,
    ):
        run.return_value.returncode = 0
        run.return_value.stdout = json.dumps({"result": [{"expressions": [{"value": output}]}]})
        assert assess(org, {})[0].status == "not-assessed"
    with patch("intent_engine.organisation.shutil.which", return_value=None):
        assert assess(org, {})[0].status == "not-assessed"


@pytest.mark.parametrize("broken", ["evidence", "endpoint", "scope", "duplicate", "default"])
def test_invalid_organisation_is_rejected_before_ingest(tmp_path, broken):
    for path in SAMPLE.iterdir():
        if path.is_file():
            shutil.copyfile(path, tmp_path / path.name)
    path = tmp_path / "organisation.yaml"
    yaml = YAML(typ="safe")
    config = yaml.load(path.read_text())
    if broken == "evidence":
        config["systems"][0]["evidence"]["quote"] = "invented quote"
    elif broken == "endpoint":
        config["integrations"][0]["target"] = "unknown"
    elif broken == "scope":
        config["policies"][0]["decision_keys"] = ["unknown"]
    elif broken == "duplicate":
        config["questions"].append(config["questions"][0])
    else:
        config["questions"][0]["default"] = "site-to-site-vpn"
    path.write_text(json.dumps(config))
    with pytest.raises(IngestError):
        load_organisation(path, load_catalog())


def test_snapshot_does_not_need_original_reference_files(tmp_path):
    org = load_organisation(SAMPLE / "organisation.yaml", load_catalog())
    restored = Organisation.model_validate_json(org.model_dump_json())
    assert restored == org
    assert "enabledRegions" in restored.references[1].content
