"""Portable bundle member boundary tests."""

from pathlib import Path

import pytest

from intent_engine.core.paths import BundleFileError, resolve_bundle_file
from intent_engine.core.yaml_utils import load_bundle_yaml_mapping, read_yaml_mapping


def test_bundle_resolver_accepts_nested_regular_file(tmp_path: Path):
    nested = tmp_path / "config" / "network"
    nested.mkdir(parents=True)
    expected = nested / "vpc.yaml"
    expected.write_text("region: eu-central-1\n")

    assert resolve_bundle_file(tmp_path, "config/network/vpc.yaml") == expected.resolve()
    assert load_bundle_yaml_mapping(tmp_path, "config/network/vpc.yaml") == {
        "region": "eu-central-1"
    }


def test_optional_bundle_file_is_empty_only_when_absent(tmp_path: Path):
    assert resolve_bundle_file(tmp_path, "optional.yaml", required=False) is None
    assert load_bundle_yaml_mapping(tmp_path, "optional.yaml", required=False) == {}


def test_required_bundle_file_reports_missing(tmp_path: Path):
    with pytest.raises(BundleFileError, match="Missing required bundle file") as exc_info:
        resolve_bundle_file(tmp_path, "required.yaml")

    assert exc_info.value.reason == "missing"


@pytest.mark.parametrize("content", ["broken: [yaml\n", "- not\n- a\n- mapping\n"])
def test_present_optional_yaml_must_be_a_valid_mapping(tmp_path: Path, content: str):
    path = tmp_path / "optional.yaml"
    path.write_text(content)

    with pytest.raises(ValueError):
        read_yaml_mapping(path)
    with pytest.raises(ValueError):
        load_bundle_yaml_mapping(tmp_path, "optional.yaml", required=False)


def test_broken_optional_yaml_symlink_is_not_treated_as_absent(tmp_path: Path):
    path = tmp_path / "optional.yaml"
    path.symlink_to(tmp_path / "missing.yaml")

    with pytest.raises(ValueError, match="optional.yaml: invalid YAML"):
        read_yaml_mapping(path)


def test_bundle_resolver_rejects_directory_in_file_position(tmp_path: Path):
    (tmp_path / "config.yaml").mkdir()

    with pytest.raises(BundleFileError, match="regular file") as exc_info:
        resolve_bundle_file(tmp_path, "config.yaml")

    assert exc_info.value.reason == "not-file"


@pytest.mark.parametrize("broken", [False, True])
def test_bundle_resolver_rejects_leaf_symlink(tmp_path: Path, broken: bool):
    target = tmp_path / "target.yaml"
    if not broken:
        target.write_text("safe: true\n")
    (tmp_path / "config.yaml").symlink_to(target)

    with pytest.raises(BundleFileError, match="symlink") as exc_info:
        resolve_bundle_file(tmp_path, "config.yaml")

    assert exc_info.value.reason == "symlink"


def test_bundle_resolver_rejects_symlinked_parent(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "config.yaml").write_text("secret: outside\n")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "nested").symlink_to(outside, target_is_directory=True)

    with pytest.raises(BundleFileError, match="symlink parents"):
        resolve_bundle_file(bundle, "nested/config.yaml")


@pytest.mark.parametrize(
    "name",
    ["../escape.yaml", "/tmp/escape.yaml", "nested\\config.yaml", "./config.yaml"],
)
def test_bundle_resolver_rejects_non_portable_or_escaping_name(tmp_path: Path, name: str):
    with pytest.raises(BundleFileError, match="invalid path"):
        resolve_bundle_file(tmp_path, name)
