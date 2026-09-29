"""No-clobber exports and network checks at the handoff boundary."""

import json
from pathlib import Path

import pytest

from intent_engine.analysis import applicable_keys, semantic_conflicts, typed_values
from intent_engine.catalog import load_catalog
from intent_engine.emit import emit_bundle, resolve
from intent_engine.ingest import extract_facts, read_document
from intent_engine.models import Review
from intent_engine.output import EmitBlocked, write_bundle
from intent_engine.tfvars import emit_tfvars

VPC = Path(__file__).resolve().parents[1] / "samples" / "vpc"


@pytest.mark.parametrize("kind", ["lza", "tfvars"])
@pytest.mark.parametrize("collision", ["file", "symlink", "dangling-symlink", "directory"])
def test_export_preserves_every_existing_destination(
    catalog, sample_facts, make_review, tmp_path, kind, collision
):
    review = make_review(sample_facts)
    if kind == "tfvars":
        catalog = load_catalog(VPC / "decisions.yaml")
        doc = read_document(VPC / "confirmed.md")
        sample_facts = extract_facts(doc, catalog)
        review = Review(
            document=doc.path,
            sha256=doc.sha256,
            applicable=list(catalog),
            answered=list(catalog),
            gaps=[],
            conflicts=[],
            facts=sample_facts,
        )
    resolution = resolve(catalog, review)
    out = tmp_path / "output"
    out.mkdir()
    # Use the final destination to catch partial writes from insufficient preflight.
    target = out / ("decision-trace.yaml" if kind == "lza" else "decision-trace.json")
    owner = tmp_path / "owner.txt"
    owner.write_text("keep owner content")
    if collision == "file":
        target.write_text("keep existing output")
    elif collision == "directory":
        target.mkdir()
    else:
        target.symlink_to(owner if collision == "symlink" else tmp_path / "absent")
    unrelated = out / "notes.md"
    unrelated.write_text("keep owner notes")
    with pytest.raises(EmitBlocked, match="fresh output directory"):
        if kind == "lza":
            emit_bundle(resolution, review, out)
        else:
            emit_tfvars(resolution, review, VPC / "module-inputs.json", out)
    assert set(out.iterdir()) == {target, unrelated}
    assert owner.read_text() == "keep owner content"
    assert unrelated.read_text() == "keep owner notes"
    if collision == "file":
        assert target.read_text() == "keep existing output"
    elif "symlink" in collision:
        assert target.is_symlink()


def test_write_failure_removes_only_files_created_by_this_attempt(tmp_path, monkeypatch):
    owner = tmp_path / "notes.md"
    owner.write_text("keep")
    original = Path.open

    def open_file(path, *args, **kwargs):
        if path.name == "second.json":
            raise PermissionError("simulated write failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_file)
    with pytest.raises(EmitBlocked, match="could not write bundle"):
        write_bundle(tmp_path, {"first.json": "{}", "second.json": "{}"})
    assert list(tmp_path.iterdir()) == [owner]
    assert owner.read_text() == "keep"


@pytest.mark.parametrize(
    "subnets,code",
    [
        ("not-a-cidr, 10.42.2.0/24", "SUBNET_CIDR_MALFORMED"),
        ("10.42.1.5/24, 10.42.2.0/24", "SUBNET_CIDR_MALFORMED"),
        ("10.42.1.0/24, 10.42.1.0/25", "SUBNET_CIDR_OVERLAP"),
        ("10.42.1.0/24, 10.42.1.0/24", "SUBNET_CIDR_OVERLAP"),
        ("10.99.1.0/24, 10.42.2.0/24", "SUBNET_OUTSIDE_VPC"),
        ("fd00::/64, 10.42.2.0/24", "SUBNET_OUTSIDE_VPC"),
        ("10.42.1.0/24", "SUBNET_ZONE_COUNT"),
    ],
)
def test_invalid_subnets_block_resolution_even_with_a_stale_clean_review(subnets, code):
    catalog = load_catalog(VPC / "decisions.yaml")
    doc = read_document(VPC / "confirmed.md")
    facts = [
        f.model_copy(update={"value": subnets}) if f.decision_key == "private_subnets" else f
        for f in extract_facts(doc, catalog)
    ]
    values, invalid = typed_values(catalog, facts)
    assert not invalid
    assert code in {c.code for c in semantic_conflicts(values)}
    review = Review(
        document=doc.path,
        sha256=doc.sha256,
        applicable=applicable_keys(catalog, facts),
        answered=list(catalog),
        gaps=[],
        conflicts=[],
        facts=facts,
    )
    with pytest.raises(EmitBlocked, match=code):
        resolve(catalog, review)


def test_valid_subnets_export_with_parent_containment(tmp_path):
    catalog = load_catalog(VPC / "decisions.yaml")
    doc = read_document(VPC / "confirmed.md")
    facts = extract_facts(doc, catalog)
    values, invalid = typed_values(catalog, facts)
    assert not invalid
    assert not semantic_conflicts(values)
    review = Review(
        document=doc.path,
        sha256=doc.sha256,
        applicable=list(catalog),
        answered=list(catalog),
        gaps=[],
        conflicts=[],
        facts=facts,
    )
    paths = emit_tfvars(resolve(catalog, review), review, VPC / "module-inputs.json", tmp_path)
    assert json.loads(paths[0].read_text())["private_subnets"] == ["10.42.1.0/24", "10.42.2.0/24"]


def test_parent_host_bits_are_not_silently_normalized():
    catalog = load_catalog(VPC / "decisions.yaml")
    doc = read_document(VPC / "confirmed.md")
    facts = [
        f.model_copy(update={"value": "10.42.1.1/16"}) if f.decision_key == "network_cidr" else f
        for f in extract_facts(doc, catalog)
    ]
    values, invalid = typed_values(catalog, facts)
    assert not invalid
    assert "NETWORK_CIDR_MALFORMED" in {c.code for c in semantic_conflicts(values)}
